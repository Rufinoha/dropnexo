# api/olist/srotas_olist.py — OAuth e importação de produtos do Olist ERP
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from api.olist.cliente import (
    MSG_USUARIO_SEM_PERMISSAO,
    consultar_conta,
    colunas_aplicativo_ok,
    credenciais_da_conta,
    desconectar,
    garantir_tabelas,
    mensagem_publica_olist,
    olist_configurado,
    olist_conectado,
    redirect_uri_oauth,
    salvar_aplicativo,
    salvar_tokens,
    trocar_code_por_tokens,
    url_autorizacao,
    validar_acessos_integracao,
    gerar_state_oauth,
)
from api.olist.painel import (
    ler_config,
    listar_categorias,
    listar_depositos,
    listar_logs,
    salvar_categoria,
    salvar_config,
    vincular_deposito,
)
from api.olist.produtos import importar_lote
from global_utils import Var_ConectarBanco, login_obrigatorio, usuario_tem_permissao
from sistema.plataforma.sessao import MODULO_ARMAZEM, MODULO_FORNECEDOR, garantir_modulo_sessao

_MOD = Path(__file__).resolve().parent

olist_bp = Blueprint(
    "olist",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/api/olist",
)


def init_app(app):
    app.register_blueprint(olist_bp)


def _pode() -> bool:
    return bool(
        session.get("eh_desenvolvedor")
        or usuario_tem_permissao("integracoes.ver")
        or usuario_tem_permissao("fn_integracoes.ver")
        or usuario_tem_permissao("az_integracoes.ver")
    )


def _modulo_catalogo() -> bool:
    if session.get("eh_desenvolvedor"):
        return True
    return garantir_modulo_sessao() in (MODULO_FORNECEDOR, MODULO_ARMAZEM)


@olist_bp.get("/integracoes/olist")
@login_obrigatorio()
def pagina():
    if not _pode():
        return redirect(url_for("dashboard.index"))
    from sistema.planos.limites import limites_plano, mensagem_upgrade_integracao

    if not limites_plano().get("integracao"):
        return redirect(url_for("integracoes.pagina", erro=mensagem_upgrade_integracao()))
    if not _modulo_catalogo():
        return redirect(url_for("integracoes.pagina", erro="Esta integração está disponível apenas para fornecedores."))

    from sistema.integracoes.srotas_integracoes import url_icone_integracao

    id_tenant = session.get("id_tenant")
    conectado = False
    conta = ""
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if id_tenant:
            garantir_tabelas(cur)
            conectado = olist_conectado(cur, int(id_tenant))
            cur.execute(
                "SELECT conta_nome FROM tbl_integracao_olist WHERE id_tenant = %s",
                (int(id_tenant),),
            )
            row = cur.fetchone()
            conta = (row[0] or "") if row else ""
        conn.commit()
    finally:
        conn.close()

    return render_template(
        "frm_olist_integracao.html",
        nav_codigo="integracoes",
        olist_conectado=conectado,
        olist_conta=conta,
        olist_configurado=olist_configurado(),
        olist_redirect=redirect_uri_oauth(),
        eh_dev=bool(session.get("eh_desenvolvedor")),
        icone_olist=url_icone_integracao("olist"),
    )


@olist_bp.get("/api/integracoes/olist/oauth/iniciar")
@login_obrigatorio()
def oauth_iniciar():
    from sistema.planos.limites import limites_plano, mensagem_upgrade_integracao

    if not _pode() or not _modulo_catalogo():
        return redirect(url_for("integracoes.pagina", erro="Sem permissão para conectar o Olist."))
    if not limites_plano().get("integracao"):
        return redirect(url_for("integracoes.pagina", erro=mensagem_upgrade_integracao()))
    id_tenant = session.get("id_tenant")
    if not id_tenant:
        return redirect(url_for("integracoes.pagina", erro="sessao"))
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        client_id, _ = credenciais_da_conta(cur, int(id_tenant))
    except RuntimeError as e:
        return redirect(url_for("olist.pagina", erro=str(e)[:240]))
    finally:
        conn.close()

    state = gerar_state_oauth()
    session["olist_oauth_state"] = state
    session["olist_oauth_tenant"] = int(id_tenant)
    return redirect(url_autorizacao(state, client_id))


@olist_bp.get("/api/integracoes/olist/oauth/callback")
@login_obrigatorio(exigir_tenant=False)
def oauth_callback():
    if not _pode():
        return redirect(url_for("integracoes.pagina", erro="permissao"))

    erro = (request.args.get("error") or "").strip()
    if erro:
        return redirect(url_for("olist.pagina", erro="O Olist não autorizou a conexão."))

    state = request.args.get("state") or ""
    code = (request.args.get("code") or "").strip()
    if not code or state != session.get("olist_oauth_state"):
        return redirect(url_for("olist.pagina", erro="A autorização expirou. Conecte de novo."))

    id_tenant = session.get("olist_oauth_tenant") or session.get("id_tenant")
    if not id_tenant:
        return redirect(url_for("integracoes.pagina", erro="sessao"))

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabelas(cur)
        try:
            client_id, client_secret = credenciais_da_conta(cur, int(id_tenant))
            tokens = trocar_code_por_tokens(code, client_id, client_secret)
        except Exception as e:
            return redirect(url_for("olist.pagina", erro=str(e)[:240]))
        salvar_tokens(cur, int(id_tenant), tokens)
        conn.commit()
    finally:
        conn.close()

    try:
        validar_acessos_integracao(int(id_tenant))
    except RuntimeError as e:
        if str(e) == MSG_USUARIO_SEM_PERMISSAO:
            conn = Var_ConectarBanco()
            try:
                cur = conn.cursor()
                desconectar(cur, int(id_tenant))
                conn.commit()
            finally:
                conn.close()
            session.pop("olist_oauth_state", None)
            session.pop("olist_oauth_tenant", None)
            return redirect(url_for("olist.pagina", erro=MSG_USUARIO_SEM_PERMISSAO))

    conta = ""
    try:
        conta = consultar_conta(int(id_tenant))
    except Exception:
        conta = ""
    if conta:
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            cur.execute(
                "UPDATE tbl_integracao_olist SET conta_nome = %s WHERE id_tenant = %s",
                (conta[:180], int(id_tenant)),
            )
            conn.commit()
        finally:
            conn.close()

    session.pop("olist_oauth_state", None)
    session.pop("olist_oauth_tenant", None)
    return redirect(url_for("olist.pagina", ok="conectado"))


@olist_bp.post("/api/integracoes/olist/desconectar")
@login_obrigatorio()
def api_desconectar():
    if not _pode():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    if not id_tenant:
        return jsonify(success=False, message="Sessão sem empresa."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        desconectar(cur, int(id_tenant))
        conn.commit()
    finally:
        conn.close()
    return jsonify(success=True)


@olist_bp.post("/api/integracoes/olist/produtos/importar")
@login_obrigatorio()
def api_importar():
    if not _pode() or not _modulo_catalogo():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    if not id_tenant:
        return jsonify(success=False, message="Sessão sem empresa."), 400
    corpo = request.get_json(silent=True) or {}
    try:
        offset = max(0, int(corpo.get("offset") or 0))
    except (TypeError, ValueError):
        offset = 0

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not olist_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Conecte o Olist antes de importar."), 400
        try:
            resultado = importar_lote(cur, int(id_tenant), offset=offset)
        except ValueError as e:
            conn.commit()
            return jsonify(success=False, message=str(e), fim=True), 400
        except Exception as e:
            conn.rollback()
            return jsonify(success=False, message=mensagem_publica_olist(e)[:400]), 502
        conn.commit()
        return jsonify(success=True, **resultado)
    finally:
        conn.close()


def _tenant_ok():
    if not _pode() or not _modulo_catalogo():
        return None, (jsonify(success=False, message="Sem permissão."), 403)
    id_tenant = session.get("id_tenant")
    if not id_tenant:
        return None, (jsonify(success=False, message="Sessão sem empresa."), 400)
    return int(id_tenant), None


@olist_bp.get("/api/integracoes/olist/status")
@login_obrigatorio()
def api_status():
    id_tenant, erro = _tenant_ok()
    if erro:
        return erro
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabelas(cur)
        conectado = olist_conectado(cur, id_tenant)
        if colunas_aplicativo_ok(cur):
            cur.execute(
                "SELECT conta_nome, client_id FROM tbl_integracao_olist WHERE id_tenant = %s",
                (id_tenant,),
            )
            row = cur.fetchone()
            client_id = (row[1] if row else "") or ""
        else:
            cur.execute(
                "SELECT conta_nome FROM tbl_integracao_olist WHERE id_tenant = %s",
                (id_tenant,),
            )
            row = cur.fetchone()
            client_id = ""
        from fornecedor.catalogo.catalogo import obter_bytes_imagens_tenant

        try:
            bytes_img = int(obter_bytes_imagens_tenant(cur, id_tenant) or 0)
        except Exception:
            bytes_img = 0
        cfg = ler_config(cur, id_tenant)
        logs = listar_logs(cur, id_tenant)
        conn.commit()
        return jsonify(
            success=True,
            conectado=conectado,
            conta_nome=(row[0] if row else "") or "",
            client_id=client_id,
            config=cfg,
            logs=logs,
            armazenamento={"bytes_imagens": bytes_img},
        )
    finally:
        conn.close()


@olist_bp.post("/api/integracoes/olist/aplicativo")
@login_obrigatorio()
def api_salvar_aplicativo():
    id_tenant, erro = _tenant_ok()
    if erro:
        return erro
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        encerrou = salvar_aplicativo(
            cur,
            id_tenant,
            str(body.get("client_id") or ""),
            str(body.get("client_secret") or ""),
        )
        conn.commit()
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()
    mensagem = "Aplicativo salvo."
    if encerrou:
        mensagem = "Aplicativo salvo. A conexão anterior foi encerrada. Conecte de novo com o usuário dono."
    return jsonify(success=True, message=mensagem, desconectou=encerrou)


@olist_bp.post("/api/integracoes/olist/config/salvar")
@login_obrigatorio()
def api_salvar_config():
    id_tenant, erro = _tenant_ok()
    if erro:
        return erro
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        salvar_config(cur, id_tenant, body)
        conn.commit()
    finally:
        conn.close()
    return jsonify(success=True, message="Configuração salva.")


@olist_bp.get("/api/integracoes/olist/status-padrao")
@login_obrigatorio()
def api_status_padrao():
    id_tenant, erro = _tenant_ok()
    if erro:
        return erro
    from core.integracoes.status_padrao import listar_status_padrao

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        linhas = listar_status_padrao(cur, aplicacao="olist", contexto="fornecedor")
        conn.commit()
    finally:
        conn.close()
    return jsonify(success=True, linhas=linhas, precisa_migrar=False)


@olist_bp.get("/api/integracoes/olist/depositos")
@login_obrigatorio()
def api_depositos():
    id_tenant, erro = _tenant_ok()
    if erro:
        return erro
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not olist_conectado(cur, id_tenant):
            return jsonify(success=False, message="Conecte o Olist antes."), 400
        dados = listar_depositos(cur, id_tenant)
        conn.commit()
        return jsonify(success=True, **dados)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:240]), 502
    finally:
        conn.close()


@olist_bp.post("/api/integracoes/olist/depositos/vincular")
@login_obrigatorio()
def api_vincular_deposito():
    id_tenant, erro = _tenant_ok()
    if erro:
        return erro
    body = request.get_json(silent=True) or {}
    id_olist = str(body.get("id_olist") or "").strip()
    if not id_olist:
        return jsonify(success=False, message="Depósito do Olist inválido."), 400
    bruto = body.get("id_deposito")
    id_deposito = None
    if bruto not in (None, ""):
        try:
            id_deposito = int(bruto)
        except (TypeError, ValueError):
            return jsonify(success=False, message="Depósito DropNexo inválido."), 400
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        vincular_deposito(cur, id_tenant, id_olist, str(body.get("nome") or ""), id_deposito)
        conn.commit()
    finally:
        conn.close()
    return jsonify(success=True, message="Vínculo salvo.")


@olist_bp.get("/api/integracoes/olist/categorias")
@login_obrigatorio()
def api_categorias():
    id_tenant, erro = _tenant_ok()
    if erro:
        return erro
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not olist_conectado(cur, id_tenant):
            return jsonify(success=False, message="Conecte o Olist antes."), 400
        dados = listar_categorias(cur, id_tenant)
        conn.commit()
        return jsonify(success=True, **dados)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:240]), 502
    finally:
        conn.close()


@olist_bp.post("/api/integracoes/olist/categorias/salvar")
@login_obrigatorio()
def api_salvar_categoria():
    id_tenant, erro = _tenant_ok()
    if erro:
        return erro
    body = request.get_json(silent=True) or {}
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        salvar_categoria(cur, id_tenant, body)
        conn.commit()
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()
    return jsonify(success=True, message="Categoria salva.")
