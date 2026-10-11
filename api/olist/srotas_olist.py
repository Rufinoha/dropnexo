# api/olist/srotas_olist.py — OAuth e importação de produtos do Olist ERP
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from api.olist.cliente import (
    consultar_conta,
    desconectar,
    garantir_tabelas,
    olist_configurado,
    olist_conectado,
    salvar_tokens,
    trocar_code_por_tokens,
    url_autorizacao,
    gerar_state_oauth,
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
    logs = []
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
            cur.execute(
                """
                SELECT status, resumo, detalhe, criado_em
                FROM tbl_integracao_log
                WHERE id_tenant = %s AND provedor = 'olist'
                ORDER BY id DESC
                LIMIT 12
                """,
                (int(id_tenant),),
            )
            for item in cur.fetchall():
                logs.append(
                    {
                        "status": item[0],
                        "resumo": item[1] or "",
                        "detalhe": item[2] or "",
                        "quando": item[3].strftime("%d/%m/%Y %H:%M") if item[3] else "",
                    }
                )
        conn.commit()
    finally:
        conn.close()

    return render_template(
        "frm_olist_integracao.html",
        nav_codigo="integracoes",
        olist_conectado=conectado,
        olist_conta=conta,
        olist_logs=logs,
        olist_configurado=olist_configurado(),
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
    if not olist_configurado():
        return redirect(url_for("olist.pagina", erro="Integração Olist indisponível neste servidor."))

    state = gerar_state_oauth()
    session["olist_oauth_state"] = state
    session["olist_oauth_tenant"] = session.get("id_tenant")
    return redirect(url_autorizacao(state))


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

    try:
        tokens = trocar_code_por_tokens(code)
    except Exception as e:
        return redirect(url_for("olist.pagina", erro=str(e)[:240]))

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabelas(cur)
        salvar_tokens(cur, int(id_tenant), tokens)
        conn.commit()
    finally:
        conn.close()

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
            return jsonify(success=False, message=str(e)[:400]), 502
        conn.commit()
        return jsonify(success=True, **resultado)
    finally:
        conn.close()
