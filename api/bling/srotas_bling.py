# api/bling/srotas_bling.py — rotas OAuth, config e sync Bling
from __future__ import annotations

import json
import mimetypes
import os
from pathlib import Path

from flask import Blueprint, abort, current_app, jsonify, redirect, render_template, request, send_file, session, url_for

from api.bling.cliente import (
    bling_configurado,
    carregar_tokens_armazenados,
    gerar_state_oauth,
    redirect_uri_oauth,
    renovar_access_token,
    revogar_tokens_bling,
    trocar_code_por_tokens,
    url_autorizacao,
    _salvar_tokens,
)
from api.bling.config_padrao import aplicar_defaults_conexao, garantir_config_contexto
from api.bling.homologacao import executar_homologacao
from api.bling.manual_conteudo import (
    MANUAL_BLING_BOTOES_FORNECEDOR,
    MANUAL_BLING_CONFIG_FORNECEDOR,
    MANUAL_BLING_PASSOS,
    MANUAL_IMAGENS_PERMITIDAS,
)
from api.bling.sync_categorias import listar_categorias_bling_flat
from api.bling.mapeamento_categorias import (
    listar_painel_categorias_bling,
    salvar_mapeamento_categoria_ui,
    validar_mapeamento_para_importacao,
)
from api.bling.sync_produtos import importar_produtos
from api.bling.tokens import descriptografar_token
from global_utils import Var_ConectarBanco, agora_utc, login_obrigatorio, obter_url_site_publico, usuario_tem_permissao
from srotas_plataforma import garantir_modulo_sessao, rotulo_modulo

_MOD_BLING = Path(__file__).resolve().parent

bling_bp = Blueprint(
    "bling",
    __name__,
    root_path=str(_MOD_BLING),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/api/bling",
)


def init_app(app):
    app.register_blueprint(bling_bp)


def _raiz_projeto() -> Path:
    return Path(__file__).resolve().parents[2]


def _urls_manual_publico(base: str) -> dict[str, str]:
    return {
        "url_login": f"{base}/login",
        "url_cadastro_fornecedor": f"{base}/cadastro?tipo=fornecedor",
        "url_cadastro_vendedor": f"{base}/cadastro?tipo=vendedor",
        "url_home": f"{base}/",
    }


def _passos_manual_com_urls(base: str) -> list[dict]:
    urls = _urls_manual_publico(base)
    passos = []
    for p in MANUAL_BLING_PASSOS:
        item = {**p, "img_url": url_for("bling.ajuda_bling_imagem", nome=p["img"])}
        if "{" in item.get("texto", ""):
            item["texto"] = item["texto"].format(**urls)
        passos.append(item)
    return passos


@bling_bp.get("/ajuda/bling")
def ajuda_bling():
    """Manual público — conexão OAuth com o Bling."""
    base = obter_url_site_publico()
    urls = _urls_manual_publico(base)
    return render_template(
        "ajuda_bling.html",
        passos=_passos_manual_com_urls(base),
        config_fornecedor=MANUAL_BLING_CONFIG_FORNECEDOR,
        botoes_fornecedor=MANUAL_BLING_BOTOES_FORNECEDOR,
        url_home=url_for("public.home"),
        url_login=url_for("auth.pagina_login"),
        url_login_publico=urls["url_login"],
        url_cadastro_fornecedor=urls["url_cadastro_fornecedor"],
        url_cadastro_vendedor=urls["url_cadastro_vendedor"],
        css_url=url_for("bling.static", filename="style/ajuda_bling.css"),
    )


@bling_bp.get("/ajuda/bling/imagens/<path:nome>")
def ajuda_bling_imagem(nome: str):
    if nome not in MANUAL_IMAGENS_PERMITIDAS:
        abort(404)
    arquivo = _MOD_BLING / "manual" / nome
    if not arquivo.is_file():
        abort(404)
    mime, _ = mimetypes.guess_type(str(arquivo))
    return send_file(arquivo, mimetype=mime or "image/jpeg", max_age=86400)


def _pode_integracoes() -> bool:
    return bool(
        session.get("eh_desenvolvedor")
        or usuario_tem_permissao("integracoes.ver")
        or usuario_tem_permissao("fn_integracoes.ver")
    )


def _pode_bling_sync() -> bool:
    """Integrações ou edição de catálogo (importar do Bling na lista de produtos)."""
    return _pode_integracoes() or usuario_tem_permissao("catalogos.editar")


def _config_dict(row) -> dict:
    out = {
        "contexto": row[0],
        "fonte_principal": row[1],
        "modo_imagem": row[2],
        "produtos_modo": row[3],
        "estoque_modo": row[4],
        "pedidos_modo": row[5],
        "ultima_sync_produtos": row[6].isoformat() if row[6] else None,
        "ultima_sync_estoque": row[7].isoformat() if row[7] else None,
        "ultima_sync_pedidos": row[8].isoformat() if row[8] else None,
    }
    if len(row) > 9:
        out["ultima_sync_estoque_recebido"] = row[9].isoformat() if row[9] else None
    if len(row) > 10:
        out["ultima_sync_estoque_enviado"] = row[10].isoformat() if row[10] else None
    if len(row) > 11 and row[11]:
        raw = row[11]
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                raw = {}
        out["opcoes"] = raw if isinstance(raw, dict) else {}
    return out


@bling_bp.get("/api/integracoes/bling/status")
@login_obrigatorio()
def api_status():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT status, conectado_em, ultimo_erro, token_expires_em
            FROM tbl_integracao_bling WHERE id_tenant = %s
            """,
            (id_tenant,),
        )
        row = cur.fetchone()
        conectado = bool(row and row[0] == "conectado")
        contexto = garantir_modulo_sessao()
        bling_conta = None
        depositos_resumo = {"vinculados": 0, "pendentes": 0}
        if conectado:
            garantir_config_contexto(cur, id_tenant, contexto)
            from api.bling.conta_empresa import garantir_conta_bling
            from api.bling.depositos import resumo_depositos_bling

            try:
                bling_conta = garantir_conta_bling(cur, int(id_tenant))
                depositos_resumo = resumo_depositos_bling(cur, int(id_tenant))
            except Exception:
                pass
            conn.commit()
        try:
            cur.execute(
                """
                SELECT contexto, fonte_principal, modo_imagem, produtos_modo, estoque_modo, pedidos_modo,
                       ultima_sync_produtos, ultima_sync_estoque, ultima_sync_pedidos,
                       ultima_sync_estoque_recebido, ultima_sync_estoque_enviado, opcoes
                FROM tbl_integracao_bling_config WHERE id_tenant = %s ORDER BY contexto
                """,
                (id_tenant,),
            )
        except Exception:
            try:
                cur.execute(
                    """
                    SELECT contexto, fonte_principal, modo_imagem, produtos_modo, estoque_modo, pedidos_modo,
                           ultima_sync_produtos, ultima_sync_estoque, ultima_sync_pedidos,
                           ultima_sync_estoque_recebido, ultima_sync_estoque_enviado
                    FROM tbl_integracao_bling_config WHERE id_tenant = %s ORDER BY contexto
                    """,
                    (id_tenant,),
                )
            except Exception:
                cur.execute(
                    """
                    SELECT contexto, fonte_principal, modo_imagem, produtos_modo, estoque_modo, pedidos_modo,
                           ultima_sync_produtos, ultima_sync_estoque, ultima_sync_pedidos
                    FROM tbl_integracao_bling_config WHERE id_tenant = %s ORDER BY contexto
                    """,
                    (id_tenant,),
                )
        configs = [_config_dict(r) for r in cur.fetchall()]

        cur.execute(
            """
            SELECT status, resumo, detalhe, criado_em FROM tbl_integracao_log
            WHERE id_tenant = %s AND provedor = 'bling'
            ORDER BY criado_em DESC LIMIT 8
            """,
            (id_tenant,),
        )
        logs = [
            {
                "status": r[0],
                "resumo": r[1],
                "detalhe": r[2] or "",
                "criado_em": r[3].isoformat() if r[3] else None,
            }
            for r in cur.fetchall()
        ]

        return jsonify(
            success=True,
            app_configurado=bling_configurado(),
            redirect_uri=redirect_uri_oauth(),
            webhook_url=f"{obter_url_site_publico().rstrip('/')}/api/integracoes/bling/webhook",
            conectado=conectado,
            bling_conta=bling_conta,
            depositos=depositos_resumo,
            contexto_modulo=garantir_modulo_sessao(),
            contexto_modulo_rotulo=rotulo_modulo(garantir_modulo_sessao()),
            conectado_em=row[1].isoformat() if row and row[1] else None,
            ultimo_erro=row[2] if row else None,
            token_expires_em=row[3].isoformat() if row and row[3] else None,
            configs=configs,
            logs=logs,
        )
    finally:
        conn.close()


@bling_bp.get("/api/integracoes/bling/oauth/iniciar")
@login_obrigatorio()
def oauth_iniciar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if not bling_configurado():
        return redirect(url_for("integracoes.pagina", erro="Integração Bling indisponível. Tente novamente mais tarde."))

    state = gerar_state_oauth()
    session["bling_oauth_state"] = state
    session["bling_oauth_tenant"] = session.get("id_tenant")
    session["bling_oauth_contexto"] = garantir_modulo_sessao()
    return redirect(url_autorizacao(state))


@bling_bp.get("/api/integracoes/bling/oauth/callback")
@login_obrigatorio(exigir_tenant=False)
def oauth_callback():
    if not _pode_integracoes():
        return redirect(url_for("integracoes.pagina", erro="permissao"))

    erro = request.args.get("error")
    if erro:
        return redirect(url_for("integracoes.pagina", erro=erro))

    state = request.args.get("state") or ""
    code = request.args.get("code") or ""
    if not code or state != session.get("bling_oauth_state"):
        return redirect(url_for("integracoes.pagina", erro="state_invalido"))

    id_tenant = session.get("bling_oauth_tenant") or session.get("id_tenant")
    if not id_tenant:
        return redirect(url_for("integracoes.pagina", erro="sessao"))

    try:
        tokens = trocar_code_por_tokens(code)
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            from api.bling.cliente import _salvar_tokens

            _salvar_tokens(cur, int(id_tenant), tokens)
            contexto = session.get("bling_oauth_contexto") or garantir_modulo_sessao()
            aplicar_defaults_conexao(cur, int(id_tenant), contexto)
            from api.bling.conta_empresa import garantir_conta_bling

            try:
                garantir_conta_bling(cur, int(id_tenant), forcar=True)
            except Exception:
                pass
            conn.commit()
        finally:
            conn.close()
        session.pop("bling_oauth_state", None)
        session.pop("bling_oauth_contexto", None)
        return redirect(url_for("integracoes.pagina", conectado="bling"))
    except Exception as e:
        return redirect(url_for("integracoes.pagina", erro=str(e)[:120]))


@bling_bp.post("/api/integracoes/bling/desconectar")
@login_obrigatorio()
def desconectar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        tokens = carregar_tokens_armazenados(cur, int(id_tenant))
        revogacao = revogar_tokens_bling(
            access_token=tokens.get("access_token") or None,
            refresh_token=tokens.get("refresh_token") or None,
        )

        detalhes_revoke = "; ".join(revogacao.get("detalhes") or [])
        client_id = (os.getenv("BLING_CLIENT_ID") or "")[:8]
        token_inativo = bool(revogacao.get("token_inativo"))

        if revogacao.get("instalacao_removida"):
            msg = (
                "Bling desconectado. Tokens revogados e verificação confirmou que a API "
                "não responde mais com este acesso."
            )
        elif token_inativo:
            msg = (
                "Bling desconectado no DropNexo. A API do Bling não aceita mais este token, "
                "mas o card em Minhas instalações pode demorar a sumir. Se continuar "
                "como Autenticado, use Desinstalar aplicativo no menu ⋮ do card no Bling."
            )
        elif revogacao.get("revogado_bling"):
            msg = (
                "Bling desconectado no DropNexo, porém a revogação na API do Bling "
                "não foi confirmada. Verifique se o Client ID do servidor corresponde "
                "ao app DropNexo no portal do desenvolvedor."
            )
        elif not (tokens.get("refresh_token") or tokens.get("access_token")):
            msg = (
                "Bling desconectado no DropNexo. "
                "Não havia tokens salvos — reconecte e desconecte novamente, "
                "ou desinstale manualmente em Minhas instalações no Bling."
            )
        else:
            msg = (
                "Bling desconectado no DropNexo, mas não foi possível revogar no Bling. "
                "Desinstale manualmente: Central de Extensões → Minhas instalações → "
                "DropNexo → ⋮ → Desinstalar aplicativo."
            )

        ultimo_erro = None
        if not token_inativo and (tokens.get("refresh_token") or tokens.get("access_token")):
            ultimo_erro = f"revoke:{detalhes_revoke[:900]}"

        cur.execute(
            """
            UPDATE tbl_integracao_bling SET
                status = 'desconectado',
                access_token_enc = NULL,
                refresh_token_enc = NULL,
                token_expires_em = NULL,
                ultimo_erro = %s,
                atualizado_em = %s
            WHERE id_tenant = %s
            """,
            (ultimo_erro, agora_utc(), id_tenant),
        )
        conn.commit()

        return jsonify(
            success=True,
            message=msg,
            revogacao_bling=bool(revogacao.get("revogado_bling")),
            instalacao_removida=bool(revogacao.get("instalacao_removida")),
            token_inativo=token_inativo,
            revogacao_detalhes=detalhes_revoke,
            bling_client_id_prefix=client_id or None,
        )
    finally:
        conn.close()


@bling_bp.post("/api/integracoes/bling/config/salvar")
@login_obrigatorio()
def salvar_config():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403

    body = request.get_json(silent=True) or {}
    contexto = (body.get("contexto") or garantir_modulo_sessao() or "").strip()
    if contexto not in ("fornecedor", "vendedor"):
        return jsonify(success=False, message="Contexto inválido."), 400

    def modo(campo: str, padrao: str) -> str:
        v = (body.get(campo) or padrao).strip()
        return v if v in ("importar", "exportar", "atualizar") else padrao

    id_tenant = session.get("id_tenant")
    opcoes_body = body.get("opcoes") if isinstance(body.get("opcoes"), dict) else None
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        agora = agora_utc()
        if contexto == "vendedor":
            produtos_modo = "exportar"
            estoque_modo = "importar"
            pedidos_modo = modo("pedidos_modo", "atualizar")
            fonte = "bling"
            modo_img = "link"
        else:
            pedidos_modo = modo("pedidos_modo", "exportar")
            produtos_modo = modo("produtos_modo", "importar")
            estoque_modo = modo("estoque_modo", "importar")
            fonte = (body.get("fonte_principal") or "bling").strip()
            if fonte not in ("bling", "dropnexo"):
                fonte = "bling"
            modo_img = (body.get("modo_imagem") or "link").strip()
            if modo_img not in ("link", "download"):
                modo_img = "link"

        cur.execute(
            """
            INSERT INTO tbl_integracao_bling_config (
                id_tenant, contexto, fonte_principal, modo_imagem,
                produtos_modo, estoque_modo, pedidos_modo, atualizado_em
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (id_tenant, contexto) DO UPDATE SET
                fonte_principal = EXCLUDED.fonte_principal,
                modo_imagem = EXCLUDED.modo_imagem,
                produtos_modo = EXCLUDED.produtos_modo,
                estoque_modo = EXCLUDED.estoque_modo,
                pedidos_modo = EXCLUDED.pedidos_modo,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (
                id_tenant,
                contexto,
                fonte,
                modo_img,
                produtos_modo,
                estoque_modo,
                pedidos_modo,
                agora,
            ),
        )
        if opcoes_body is not None:
            cur.execute(
                """
                UPDATE tbl_integracao_bling_config
                SET opcoes = COALESCE(opcoes, '{}'::jsonb) || %s::jsonb,
                    atualizado_em = %s
                WHERE id_tenant = %s AND contexto = %s
                """,
                (json.dumps(opcoes_body, ensure_ascii=False), agora, id_tenant, contexto),
            )
        if contexto == "fornecedor":
            cur.execute(
                """
                UPDATE tbl_integracao_bling_config
                SET modo_imagem = %s, atualizado_em = %s
                WHERE id_tenant = %s
                """,
                (modo_img, agora, id_tenant),
            )
        conn.commit()
        return jsonify(success=True, message="Configuração salva.")
    finally:
        conn.close()


@bling_bp.post("/api/integracoes/bling/homologacao/executar")
@login_obrigatorio()
def homologacao_executar():
    """Executa o fluxo de homologação exigido pelo Bling (5 passos API)."""
    if not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Somente desenvolvedor."), 403
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if not bling_configurado():
        return jsonify(success=False, message="Credenciais Bling não configuradas."), 400

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT status, access_token_enc, refresh_token_enc
            FROM tbl_integracao_bling WHERE id_tenant = %s
            """,
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de executar a homologação."), 400

        from api.bling.cliente import renovar_access_token

        access = descriptografar_token(row[1])
        refresh = descriptografar_token(row[2]) if row[2] else None
        refresh_holder = {"token": refresh}

        def refresh_fn() -> str:
            rt = refresh_holder["token"]
            if not rt:
                raise RuntimeError("Refresh token ausente. Reconecte o Bling.")
            payload = renovar_access_token(rt)
            refresh_holder["token"] = payload.get("refresh_token") or rt
            _salvar_tokens(cur, int(id_tenant), payload)
            conn.commit()
            return payload["access_token"]

        resultado = executar_homologacao(
            access,
            refresh_token_fn=refresh_fn if refresh else None,
        )
        return jsonify(success=resultado.sucesso, message=resultado.mensagem, dados=resultado.to_dict())
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@bling_bp.post("/api/integracoes/bling/sync/produtos")
@login_obrigatorio()
def sync_produtos():
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403

    body = request.get_json(silent=True) or {}
    contexto = (body.get("contexto") or garantir_modulo_sessao() or "fornecedor").strip()
    if contexto not in ("fornecedor", "vendedor"):
        return jsonify(success=False, message="Contexto inválido."), 400

    id_categoria_bling = (body.get("id_categoria_bling") or "").strip() or None
    raw_ids = body.get("ids_categorias_bling")
    ids_categorias_bling: list[str] | None = None
    if isinstance(raw_ids, list):
        ids_categorias_bling = [str(c).strip() for c in raw_ids if str(c or "").strip()]
    elif raw_ids:
        ids_categorias_bling = [str(raw_ids).strip()]
    incluir_subcategorias = body.get("incluir_subcategorias", True)
    if isinstance(incluir_subcategorias, str):
        incluir_subcategorias = incluir_subcategorias.lower() in ("1", "true", "sim", "yes")

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de sincronizar."), 400

        from api.bling.mapeamento_categorias import validar_mapeamento_para_importacao

        val = validar_mapeamento_para_importacao(
            cur,
            int(id_tenant),
            contexto,
            ids_categorias_bling=ids_categorias_bling,
            incluir_subcategorias=bool(incluir_subcategorias),
        )
        if not val.get("importacao_liberada"):
            return jsonify(
                success=False,
                message=val.get("mensagem"),
                validacao=val,
            ), 400

        from fornecedor.importacao.servico_importacao import (
            MODULO_CATALOGO,
            ORIGEM_INTEGRACAO,
            criar_lote,
        )

        id_usuario = session.get("id_usuario")
        id_lote, numero = criar_lote(
            cur,
            id_tenant=int(id_tenant),
            modulo=MODULO_CATALOGO,
            origem=ORIGEM_INTEGRACAO,
            id_usuario=int(id_usuario) if id_usuario else None,
            provedor="bling",
            nome_lote=f"Bling — {contexto}",
            meta={"contexto": contexto},
        )
        conn.commit()

        resultado = importar_produtos(
            cur,
            int(id_tenant),
            contexto,
            id_categoria_bling=id_categoria_bling,
            ids_categorias_bling=ids_categorias_bling,
            incluir_subcategorias=bool(incluir_subcategorias),
            id_importacao_lote=id_lote,
            id_usuario=int(id_usuario) if id_usuario else None,
            modo_categorias="mapeamento",
        )
        conn.commit()
        status = resultado.get("status") or "ok"
        total_falhas = int(resultado.get("total_falhas") or 0)
        if status == "erro":
            msg = f"Importação {numero}: nenhum produto importado. {total_falhas} com falha."
        elif status == "aviso":
            msg = f"Importação {numero}: {total_falhas} produto(s) não importado(s)."
        else:
            msg = f"Importação {numero} concluída."
        resultado["numero"] = numero
        return jsonify(success=True, message=msg, dados=resultado)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        msg = str(e)
        if "transaction is aborted" in msg.lower():
            msg = (
                "Falha no banco durante a importação. "
                "Verifique se a migration 023_integracao_bling_categoria_map.sql foi aplicada em produção."
            )
        return jsonify(success=False, message=msg), 500
    finally:
        conn.close()


@bling_bp.post("/api/integracoes/bling/sync/pedidos")
@login_obrigatorio()
def sync_pedidos():
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403

    body = request.get_json(silent=True) or {}
    contexto = (body.get("contexto") or garantir_modulo_sessao() or "vendedor").strip()
    if contexto != "vendedor":
        return jsonify(success=False, message="Importação de pedidos Bling disponível apenas para vendedor."), 400

    try:
        dias = int(body.get("dias") or 30)
    except (TypeError, ValueError):
        dias = 30
    data_inicial = (body.get("data_inicial") or body.get("data_pedido") or "").strip() or None

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de importar pedidos."), 400

        from api.bling.sync_pedidos import importar_pedidos_bling

        uid = session.get("id_usuario")
        resultado = importar_pedidos_bling(
            cur,
            int(id_tenant),
            contexto=contexto,
            dias=dias,
            data_inicial=data_inicial,
            id_usuario=int(uid) if uid else None,
        )
        conn.commit()
        return jsonify(success=True, **resultado)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@bling_bp.get("/api/integracoes/bling/categorias")
@login_obrigatorio()
def api_categorias_bling():
    """Lista categorias de produtos do Bling (árvore) para importação seletiva."""
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de listar categorias."), 400
    finally:
        conn.close()

    try:
        categorias = listar_categorias_bling_flat(int(id_tenant))
        return jsonify(success=True, categorias=categorias)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500


@bling_bp.get("/api/integracoes/bling/categorias/mapeamento")
@login_obrigatorio()
def api_categorias_bling_mapeamento():
    """Painel de mapeamento Bling ↔ DropNexo (aba Categorias)."""
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403

    contexto = (request.args.get("contexto") or "fornecedor").strip()
    if contexto not in ("fornecedor", "vendedor"):
        return jsonify(success=False, message="Contexto inválido."), 400

    forcar_sync = (request.args.get("modo") or "").strip().lower() == "sync" or request.args.get("sync") in (
        "1",
        "true",
        "sim",
    )

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de mapear categorias."), 400

        from api.bling.categorias_sync_progresso import iniciar_carregar_painel_categorias
        from api.bling.sync_categorias import (
            PAINEL_ENRIQUECER_ASYNC_MIN,
            cache_categorias_precisa_enriquecer,
            carregar_mapa_categorias_bling_listagem,
        )

        id_tenant_int = int(id_tenant)
        cache = carregar_mapa_categorias_bling_listagem(id_tenant_int)
        if (
            not forcar_sync
            and cache_categorias_precisa_enriquecer(cache)
            and len(cache) >= PAINEL_ENRIQUECER_ASYNC_MIN
        ):
            job_id = iniciar_carregar_painel_categorias(
                current_app._get_current_object(),
                id_tenant=id_tenant_int,
                contexto=contexto,
            )
            return jsonify(success=True, carregamento_async=True, sync_job_id=job_id, total=len(cache))

        dados = listar_painel_categorias_bling(cur, id_tenant_int, contexto)
        return jsonify(success=True, dados=dados)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@bling_bp.get("/api/integracoes/bling/categorias/mapeamento-job/<job_id>")
@login_obrigatorio()
def api_categorias_bling_mapeamento_job(job_id: str):
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403
    from api.bling.categorias_sync_progresso import obter_job_painel_categorias

    id_tenant = session.get("id_tenant")
    job = obter_job_painel_categorias(job_id, int(id_tenant))
    if not job:
        return jsonify(success=False, message="Job não encontrado."), 404
    return jsonify(success=True, job=job)


@bling_bp.post("/api/integracoes/bling/categorias/salvar")
@login_obrigatorio()
def api_categorias_bling_salvar():
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403

    body = request.get_json(silent=True) or {}
    contexto = (body.get("contexto") or "fornecedor").strip()
    if contexto not in ("fornecedor", "vendedor"):
        return jsonify(success=False, message="Contexto inválido."), 400

    id_bling = (body.get("id_bling") or "").strip()
    acao = (body.get("acao") or "").strip().lower()
    id_segmento = body.get("id_segmento")
    id_dropnexo = body.get("id_dropnexo")
    id_parent = body.get("id_parent_dropnexo")

    try:
        id_seg = int(id_segmento) if id_segmento not in (None, "") else None
    except (TypeError, ValueError):
        id_seg = None
    try:
        id_drop = int(id_dropnexo) if id_dropnexo not in (None, "") else None
    except (TypeError, ValueError):
        id_drop = None
    try:
        id_parent_drop = int(id_parent) if id_parent not in (None, "") else None
    except (TypeError, ValueError):
        id_parent_drop = None

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de mapear categorias."), 400

        resultado = salvar_mapeamento_categoria_ui(
            cur,
            int(id_tenant),
            contexto,
            id_bling=id_bling,
            acao=acao,
            id_segmento=id_seg,
            id_dropnexo=id_drop,
            id_parent_dropnexo=id_parent_drop,
        )
        conn.commit()
        return jsonify(success=True, message="Mapeamento salvo.", dados=resultado)
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@bling_bp.post("/api/integracoes/bling/categorias/salvar-lote")
@login_obrigatorio()
def api_categorias_bling_salvar_lote():
    """Salva mapeamento de várias categorias em background (throttle + retry 429)."""
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403

    body = request.get_json(silent=True) or {}
    contexto = (body.get("contexto") or "fornecedor").strip()
    if contexto not in ("fornecedor", "vendedor"):
        return jsonify(success=False, message="Contexto inválido."), 400

    acoes = body.get("acoes")
    if not isinstance(acoes, list) or not acoes:
        return jsonify(success=False, message="Informe ao menos uma ação."), 400

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de mapear categorias."), 400
    finally:
        conn.close()

    from api.bling.categorias_sync_progresso import iniciar_salvar_categorias_lote

    job_id = iniciar_salvar_categorias_lote(
        current_app._get_current_object(),
        id_tenant=int(id_tenant),
        contexto=contexto,
        acoes=acoes,
    )
    return jsonify(success=True, sync_job_id=job_id)


@bling_bp.get("/api/integracoes/bling/categorias/progresso/<job_id>")
@login_obrigatorio()
def api_categorias_sync_progresso(job_id: str):
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403
    from api.bling.categorias_sync_progresso import obter_progresso_categorias

    id_tenant = session.get("id_tenant")
    job = obter_progresso_categorias(job_id, int(id_tenant))
    if not job:
        return jsonify(success=False, message="Job não encontrado."), 404
    return jsonify(success=True, progresso=job)


@bling_bp.post("/api/integracoes/bling/categorias/reparar-hierarquia")
@login_obrigatorio()
def api_categorias_bling_reparar_hierarquia():
    """Reorganiza parent_id das categorias já mapeadas conforme árvore Bling."""
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403

    body = request.get_json(silent=True) or {}
    contexto = (body.get("contexto") or "fornecedor").strip()
    if contexto not in ("fornecedor", "vendedor"):
        return jsonify(success=False, message="Contexto inválido."), 400

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de reorganizar categorias."), 400
    finally:
        conn.close()

    from api.bling.categorias_sync_progresso import iniciar_reparar_hierarquia_categorias

    job_id = iniciar_reparar_hierarquia_categorias(
        current_app._get_current_object(),
        id_tenant=int(id_tenant),
        contexto=contexto,
    )
    return jsonify(success=True, sync_job_id=job_id)


@bling_bp.post("/api/integracoes/bling/categorias/validar-importacao")
@login_obrigatorio()
def api_categorias_bling_validar_importacao():
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403

    body = request.get_json(silent=True) or {}
    contexto = (body.get("contexto") or "fornecedor").strip()
    if contexto not in ("fornecedor", "vendedor"):
        return jsonify(success=False, message="Contexto inválido."), 400

    raw_ids = body.get("ids_categorias_bling")
    ids_categorias_bling: list[str] | None = None
    if isinstance(raw_ids, list):
        ids_categorias_bling = [str(c).strip() for c in raw_ids if str(c or "").strip()]
    incluir_sub = body.get("incluir_subcategorias", True)
    if isinstance(incluir_sub, str):
        incluir_sub = incluir_sub.lower() in ("1", "true", "sim", "yes")

    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes de importar."), 400
        val = validar_mapeamento_para_importacao(
            cur,
            int(id_tenant),
            contexto,
            ids_categorias_bling=ids_categorias_bling,
            incluir_subcategorias=bool(incluir_sub),
        )
        return jsonify(success=True, dados=val)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@bling_bp.get("/api/integracoes/bling/depositos")
@login_obrigatorio()
def api_depositos_bling():
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT status FROM tbl_integracao_bling WHERE id_tenant = %s",
            (id_tenant,),
        )
        row = cur.fetchone()
        if not row or row[0] != "conectado":
            return jsonify(success=False, message="Conecte o Bling antes."), 400

        from api.bling.depositos import carregar_depositos_bling_ui

        mapa_enriquecido, bling_deps, aviso_bling = carregar_depositos_bling_ui(cur, int(id_tenant))
        conn.commit()
        cur.execute(
            """
            SELECT id, nome FROM tbl_deposito_expedicao
            WHERE id_tenant = %s AND ativo = TRUE ORDER BY principal DESC, nome
            """,
            (id_tenant,),
        )
        drop_deps = [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]
        return jsonify(
            success=True,
            mapa=mapa_enriquecido,
            depositos_bling=bling_deps,
            depositos_dropnexo=drop_deps,
            aviso_bling=aviso_bling,
        )
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@bling_bp.post("/api/integracoes/bling/depositos/vincular")
@login_obrigatorio()
def api_vincular_deposito_bling():
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403
    body = request.get_json(silent=True) or {}
    id_bling = (body.get("id_bling_deposito") or "").strip()
    nome_bling = (body.get("nome_bling") or "").strip() or None
    criar_igual = bool(body.get("criar_igual"))
    padrao_bling = bool(body.get("padrao_bling"))
    id_drop_raw = body.get("id_deposito_dropnexo")
    if str(id_drop_raw or "").strip() in ("", "__criar_igual__"):
        id_drop = None
        if str(id_drop_raw or "").strip() == "__criar_igual__":
            criar_igual = True
    else:
        id_drop = int(id_drop_raw)
    if not id_bling:
        return jsonify(success=False, message="Depósito Bling inválido."), 400
    if not criar_igual and id_drop is None and id_drop_raw not in (None, "", "__criar_igual__"):
        return jsonify(success=False, message="Depósito DropNexo inválido."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from api.bling.depositos import vincular_ou_criar_deposito_bling

        rid, id_drop, criou, alterado = vincular_ou_criar_deposito_bling(
            cur,
            int(id_tenant),
            id_bling_deposito=id_bling,
            nome_bling=nome_bling,
            id_deposito_dropnexo=id_drop,
            criar_igual=criar_igual,
            padrao_bling=padrao_bling,
        )
        conn.commit()
        msg = "Depósito criado e vinculado." if criou else ("Vínculo salvo." if alterado else "Nenhuma alteração no vínculo.")
        estoque_sync_pendente = False
        if id_drop:
            cur.execute(
                """
                SELECT estoque_sync_pendente FROM tbl_integracao_deposito_map
                WHERE id_tenant = %s AND id_bling_deposito = %s
                """,
                (id_tenant, id_bling),
            )
            row_p = cur.fetchone()
            estoque_sync_pendente = bool(row_p[0]) if row_p else alterado
        return jsonify(
            success=True,
            message=msg,
            id=rid,
            id_deposito_dropnexo=id_drop,
            criou_deposito=criou,
            alterado=alterado,
            estoque_sync_pendente=estoque_sync_pendente,
        )
    except ValueError as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 400
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@bling_bp.post("/api/integracoes/bling/depositos/sincronizar-estoque")
@login_obrigatorio()
def api_sincronizar_estoque_deposito_bling():
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403
    body = request.get_json(silent=True) or {}
    id_bling = (body.get("id_bling_deposito") or "").strip()
    if not id_bling:
        return jsonify(success=False, message="Depósito Bling inválido."), 400
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id_deposito_dropnexo, estoque_sync_pendente
            FROM tbl_integracao_deposito_map
            WHERE id_tenant = %s AND id_bling_deposito = %s
            """,
            (id_tenant, id_bling),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            return jsonify(success=False, message="Vincule o depósito antes de sincronizar."), 400
        if not row[1]:
            return jsonify(success=False, message="Estoque deste depósito já foi sincronizado. Altere o vínculo para sincronizar novamente."), 409

        from api.bling.estoque_sync_progresso import deposito_tem_sync_ativa, iniciar_sync_inicial_deposito

        if deposito_tem_sync_ativa(cur, int(id_tenant), id_bling):
            return jsonify(success=False, message="Sincronização já em andamento para este depósito."), 409

        sync_job_id = iniciar_sync_inicial_deposito(
            current_app._get_current_object(),
            id_tenant=int(id_tenant),
            id_bling_deposito=id_bling,
        )
        return jsonify(success=True, sync_job_id=sync_job_id)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@bling_bp.post("/api/integracoes/bling/webhook")
def api_bling_webhook():
    """Webhook público Bling (estoque, produtos, etc.) — autenticado por HMAC."""
    from api.bling.webhook_estoque import receber_webhook_http

    body, code = receber_webhook_http(current_app._get_current_object(), request)
    return jsonify(body), code


@bling_bp.get("/api/integracoes/bling/estoque/sync-progresso/<job_id>")
@login_obrigatorio()
def api_estoque_sync_progresso(job_id: str):
    if not _pode_bling_sync():
        return jsonify(success=False, message="Sem permissão."), 403
    from api.bling.estoque_sync_progresso import obter_progresso_sync

    id_tenant = session.get("id_tenant")
    job = obter_progresso_sync(job_id, int(id_tenant))
    if not job:
        return jsonify(success=False, message="Job não encontrado."), 404
    return jsonify(success=True, progresso=job)


@bling_bp.get("/api/produto-imagem/arquivo")
@login_obrigatorio()
def api_produto_imagem_arquivo():
    caminho = (request.args.get("caminho") or "").strip().replace("\\", "/")
    if not caminho or ".." in caminho.split("/"):
        return jsonify(success=False, message="Caminho inválido."), 400
    if not caminho.lower().startswith("upload/tenant"):
        return jsonify(success=False, message="Caminho não permitido."), 403

    id_tenant = session.get("id_tenant")
    prefixo = f"upload/tenant{id_tenant}/produtos/"
    if not caminho.lower().startswith(prefixo.lower()):
        return jsonify(success=False, message="Arquivo de outro tenant."), 403

    arquivo = _raiz_projeto() / caminho.replace("/", os.sep)
    if not arquivo.is_file():
        return jsonify(success=False, message="Arquivo não encontrado."), 404

    mime, _ = mimetypes.guess_type(str(arquivo))
    return send_file(arquivo, mimetype=mime or "application/octet-stream", max_age=3600)
