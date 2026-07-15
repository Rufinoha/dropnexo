# api/tiktok/srotas_tiktok.py — OAuth TikTok Shop (vendedor)
from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, jsonify, redirect, request, session, url_for

from api.tiktok.tiktok import (
    atualizar_shop_info,
    carregar_config_tiktok,
    desconectar_tiktok,
    gerar_state_oauth,
    listar_mapeamento_categorias_tiktok,
    publicar_produtos_tiktok,
    redirect_uri_oauth,
    salvar_config_tiktok,
    salvar_mapeamento_categorias_tiktok,
    salvar_tokens,
    tiktok_configurado,
    tiktok_conectado,
    trocar_code_por_tokens,
    url_autorizacao,
    webhook_url,
)
from global_utils import Var_ConectarBanco, login_obrigatorio, usuario_tem_permissao
from sistema.plataforma.sessao import garantir_modulo_sessao

_log = logging.getLogger(__name__)

_MOD = Path(__file__).resolve().parent

tiktok_bp = Blueprint(
    "tiktok",
    __name__,
    root_path=str(_MOD),
    static_folder="static",
    static_url_path="/static/api/tiktok",
)


def init_app(app):
    app.register_blueprint(tiktok_bp)


def _pode_integracoes() -> bool:
    return bool(
        session.get("eh_desenvolvedor")
        or usuario_tem_permissao("integracoes.ver")
        or usuario_tem_permissao("fn_integracoes.ver")
    )


def _exigir_vendedor():
    if session.get("eh_desenvolvedor"):
        return None
    if garantir_modulo_sessao() == "vendedor":
        return None
    if session.get("tenant_tipo_negocio") == "hibrido":
        return redirect(
            url_for(
                "integracoes.pagina",
                erro="Conecte o TikTok Shop no módulo Vendedor (troque o perfil no topo).",
            )
        )
    return redirect(url_for("integracoes.pagina", erro="TikTok Shop é apenas para vendedores."))


@tiktok_bp.get("/api/integracoes/tiktok/oauth/iniciar")
@login_obrigatorio()
def oauth_iniciar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if (r := _exigir_vendedor()) is not None:
        return r
    if not tiktok_configurado():
        return redirect(
            url_for(
                "integracoes.pagina",
                erro="TikTok Shop indisponível. Configure TIKTOK_APP_KEY e TIKTOK_APP_SECRET no .env.",
            )
        )
    state = gerar_state_oauth()
    session["tiktok_oauth_state"] = state
    session["tiktok_oauth_tenant"] = session.get("id_tenant")
    return redirect(url_autorizacao(state))


@tiktok_bp.get("/api/integracoes/tiktok/oauth/callback")
@login_obrigatorio(exigir_tenant=False)
def oauth_callback():
    if not _pode_integracoes():
        return redirect(url_for("integracoes.pagina", erro="permissao"))

    erro = request.args.get("error") or request.args.get("error_description")
    if erro:
        return redirect(url_for("integracoes.pagina", erro=erro))

    state = request.args.get("state") or ""
    code = request.args.get("code") or request.args.get("auth_code") or ""
    if not code or state != session.get("tiktok_oauth_state"):
        return redirect(url_for("integracoes.pagina", erro="state_invalido"))

    id_tenant = session.get("tiktok_oauth_tenant") or session.get("id_tenant")
    if not id_tenant:
        return redirect(url_for("integracoes.pagina", erro="sessao"))

    try:
        tokens = trocar_code_por_tokens(code)
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            salvar_tokens(cur, int(id_tenant), tokens)
            access = tokens.get("access_token") or ""
            if access:
                atualizar_shop_info(cur, int(id_tenant), access)
            conn.commit()
        finally:
            conn.close()
        session.pop("tiktok_oauth_state", None)
        session.pop("tiktok_oauth_tenant", None)
        return redirect(url_for("integracoes.pagina", conectado_tiktok="1"))
    except Exception as e:
        _log.exception("TikTok OAuth callback")
        return redirect(url_for("integracoes.pagina", erro=str(e)[:120]))


@tiktok_bp.post("/api/integracoes/tiktok/desconectar")
@login_obrigatorio()
def desconectar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        desconectar_tiktok(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, message="TikTok Shop desconectado.")
    finally:
        conn.close()


@tiktok_bp.get("/api/integracoes/tiktok/status")
@login_obrigatorio()
def status():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cfg = carregar_config_tiktok(cur, int(id_tenant))
        cfg["configurado_servidor"] = tiktok_configurado()
        cfg["conectado"] = tiktok_conectado(cur, int(id_tenant))
        return jsonify(success=True, config=cfg)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 500
    finally:
        conn.close()


@tiktok_bp.post("/api/integracoes/tiktok/config/salvar")
@login_obrigatorio()
def config_salvar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    body = request.get_json(silent=True) or {}
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not tiktok_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Conecte o TikTok Shop primeiro."), 400
        salvar_config_tiktok(
            cur,
            int(id_tenant),
            pedidos_importar_auto=body.get("pedidos_importar_auto") if "pedidos_importar_auto" in body else None,
            produtos_exportar_auto=body.get("produtos_exportar_auto") if "produtos_exportar_auto" in body else None,
            produtos_modo=body.get("produtos_modo") if "produtos_modo" in body else None,
            estoque_sync_ativo=body.get("estoque_sync_ativo") if "estoque_sync_ativo" in body else None,
        )
        conn.commit()
        return jsonify(success=True, message="Preferências salvas.")
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@tiktok_bp.post("/api/integracoes/tiktok/sync/pedidos")
@login_obrigatorio()
def sync_pedidos():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not tiktok_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="TikTok Shop não conectado."), 400
        from api.tiktok.tiktok import importar_pedidos_tiktok

        resultado = importar_pedidos_tiktok(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, **resultado)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@tiktok_bp.post("/api/integracoes/tiktok/sync/estoque")
@login_obrigatorio()
def sync_estoque():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from api.tiktok.tiktok import sincronizar_estoque_tiktok

        resultado = sincronizar_estoque_tiktok(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, **resultado)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@tiktok_bp.get("/api/integracoes/tiktok/categorias-mapeamento")
@login_obrigatorio()
def categorias_mapeamento_listar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not tiktok_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="TikTok Shop não conectado."), 400
        itens = listar_mapeamento_categorias_tiktok(cur, int(id_tenant))
        return jsonify(success=True, itens=itens)
    finally:
        conn.close()


@tiktok_bp.post("/api/integracoes/tiktok/categorias-mapeamento/salvar")
@login_obrigatorio()
def categorias_mapeamento_salvar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    body = request.get_json(silent=True) or {}
    itens = body.get("itens") or []
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not tiktok_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="TikTok Shop não conectado."), 400
        n = salvar_mapeamento_categorias_tiktok(cur, int(id_tenant), itens)
        conn.commit()
        return jsonify(success=True, message=f"{n} categoria(s) mapeada(s).", salvos=n)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@tiktok_bp.post("/api/integracoes/tiktok/produtos/publicar")
@login_obrigatorio()
def produtos_publicar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    body = request.get_json(silent=True) or {}
    ids = body.get("ids") or []
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        resultado = publicar_produtos_tiktok(cur, int(id_tenant), ids)
        conn.commit()
        return jsonify(success=True, **resultado)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@tiktok_bp.get("/api/integracoes/tiktok/diagnostico")
@login_obrigatorio()
def diagnostico():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    return jsonify(
        success=True,
        configurado=tiktok_configurado(),
        redirect_uri=redirect_uri_oauth(),
        webhook_url=webhook_url(),
    )


@tiktok_bp.post("/api/integracoes/tiktok/webhook")
def webhook():
    """Recebe notificações TikTok Shop (sem auth — retorna 200)."""
    raw = request.get_data(as_text=True) or ""
    _log.info("Webhook TikTok Shop: %s", raw[:500])
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        try:
            import json as _json

            payload = _json.loads(raw) if raw else {}
        except Exception:
            payload = {}
    if not isinstance(payload, dict):
        payload = {}

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from api.tiktok.pedidos_tiktok import processar_webhook_tiktok

        resultado = processar_webhook_tiktok(cur, payload)
        conn.commit()
        if resultado.get("importado"):
            _log.info("Webhook TikTok importou pedido: %s", resultado)
        elif resultado.get("cancelado"):
            _log.info("Webhook TikTok cancelou pedido: %s", resultado)
        elif not resultado.get("ok"):
            _log.warning("Webhook TikTok sem processamento: %s", resultado)
    except Exception:
        conn.rollback()
        _log.exception("Erro no webhook TikTok Shop")
    finally:
        conn.close()
    return "", 200
