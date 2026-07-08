# api/mercado_livre/srotas_mercado_livre.py — OAuth Mercado Livre (vendedor)
from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, jsonify, redirect, request, session, url_for

from api.mercado_livre.mercado_livre import (
    atualizar_conta_info,
    buscar_categorias_ml,
    carregar_config_ml,
    desconectar_ml,
    gerar_state_oauth,
    listar_mapeamento_categorias_ml,
    ml_configurado,
    ml_conectado,
    publicar_produtos_ml,
    redirect_uri_oauth,
    salvar_config_ml,
    salvar_mapeamento_categorias_ml,
    salvar_tokens,
    trocar_code_por_tokens,
    url_autorizacao,
    webhook_url,
)
from global_utils import Var_ConectarBanco, login_obrigatorio, usuario_tem_permissao
from sistema.plataforma.sessao import garantir_modulo_sessao

_log = logging.getLogger(__name__)

_MOD = Path(__file__).resolve().parent

ml_bp = Blueprint(
    "mercado_livre",
    __name__,
    root_path=str(_MOD),
)


def init_app(app):
    app.register_blueprint(ml_bp)


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
                erro="Conecte o Mercado Livre no módulo Vendedor (troque o perfil no topo).",
            )
        )
    return redirect(url_for("integracoes.pagina", erro="Mercado Livre é apenas para vendedores."))


@ml_bp.get("/api/integracoes/mercado-livre/oauth/iniciar")
@login_obrigatorio()
def oauth_iniciar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if (r := _exigir_vendedor()) is not None:
        return r
    if not ml_configurado():
        return redirect(
            url_for(
                "integracoes.pagina",
                erro="Mercado Livre indisponível. Configure ML_CLIENT_ID_DEV/PROD e ML_CLIENT_SECRET_DEV/PROD no .env.",
            )
        )
    state = gerar_state_oauth()
    session["ml_oauth_state"] = state
    session["ml_oauth_tenant"] = session.get("id_tenant")
    return redirect(url_autorizacao(state))


@ml_bp.get("/api/integracoes/mercado-livre/oauth/callback")
@login_obrigatorio(exigir_tenant=False)
def oauth_callback():
    if not _pode_integracoes():
        return redirect(url_for("integracoes.pagina", erro="permissao"))

    erro = request.args.get("error")
    if erro:
        return redirect(url_for("integracoes.pagina", erro=erro))

    state = request.args.get("state") or ""
    code = request.args.get("code") or ""
    if not code or state != session.get("ml_oauth_state"):
        return redirect(url_for("integracoes.pagina", erro="state_invalido"))

    id_tenant = session.get("ml_oauth_tenant") or session.get("id_tenant")
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
                atualizar_conta_info(cur, int(id_tenant), access)
            conn.commit()
        finally:
            conn.close()
        session.pop("ml_oauth_state", None)
        session.pop("ml_oauth_tenant", None)
        return redirect(url_for("integracoes.pagina_mercado_livre", conectado="1"))
    except Exception as e:
        _log.exception("ML OAuth callback")
        return redirect(url_for("integracoes.pagina", erro=str(e)[:120]))


@ml_bp.post("/api/integracoes/mercado-livre/desconectar")
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
        desconectar_ml(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, message="Mercado Livre desconectado.")
    finally:
        conn.close()


@ml_bp.get("/api/integracoes/mercado-livre/status")
@login_obrigatorio()
def status():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cfg = carregar_config_ml(cur, int(id_tenant))
        cfg["configurado_servidor"] = ml_configurado()
        cfg["conectado"] = ml_conectado(cur, int(id_tenant))
        return jsonify(success=True, config=cfg)
    finally:
        conn.close()


@ml_bp.post("/api/integracoes/mercado-livre/config/salvar")
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
        if not ml_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Conecte o Mercado Livre primeiro."), 400
        salvar_config_ml(
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


@ml_bp.post("/api/integracoes/mercado-livre/sync/pedidos")
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
        if not ml_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Mercado Livre não conectado."), 400
        from api.mercado_livre.mercado_livre import importar_pedidos_mercado_livre

        resultado = importar_pedidos_mercado_livre(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, **resultado)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@ml_bp.post("/api/integracoes/mercado-livre/sync/produtos")
@login_obrigatorio()
def sync_produtos():
    """Legado: sincronização em massa. Prefira publicar em Meus produtos."""
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from api.mercado_livre.mercado_livre import exportar_produtos_ml

        resultado = exportar_produtos_ml(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, **resultado)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@ml_bp.get("/api/integracoes/mercado-livre/categorias-mapeamento")
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
        if not ml_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Mercado Livre não conectado."), 400
        itens = listar_mapeamento_categorias_ml(cur, int(id_tenant))
        return jsonify(success=True, itens=itens)
    finally:
        conn.close()


@ml_bp.post("/api/integracoes/mercado-livre/categorias-mapeamento/salvar")
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
        if not ml_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Mercado Livre não conectado."), 400
        n = salvar_mapeamento_categorias_ml(cur, int(id_tenant), itens)
        conn.commit()
        return jsonify(success=True, message=f"{n} categoria(s) mapeada(s).", salvos=n)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@ml_bp.get("/api/integracoes/mercado-livre/categorias/buscar")
@login_obrigatorio()
def categorias_buscar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    q = (request.args.get("q") or "").strip()
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not ml_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Mercado Livre não conectado."), 400
        itens = buscar_categorias_ml(cur, int(id_tenant), q)
        return jsonify(success=True, itens=itens)
    finally:
        conn.close()


@ml_bp.post("/api/integracoes/mercado-livre/produtos/publicar")
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
        resultado = publicar_produtos_ml(cur, int(id_tenant), ids)
        conn.commit()
        return jsonify(success=True, **resultado)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@ml_bp.post("/api/integracoes/mercado-livre/sync/estoque")
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
        from api.mercado_livre.mercado_livre import sincronizar_estoque_ml

        resultado = sincronizar_estoque_ml(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, **resultado)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@ml_bp.get("/api/integracoes/mercado-livre/diagnostico")
@login_obrigatorio()
def diagnostico():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    return jsonify(
        success=True,
        configurado=ml_configurado(),
        redirect_uri=redirect_uri_oauth(),
        webhook_url=webhook_url(),
    )


@ml_bp.post("/api/integracoes/mercado-livre/webhook")
def webhook():
    """Recebe notificações ML (orders_v2). Processamento completo na fase 2."""
    _log.info("Webhook Mercado Livre: %s", (request.get_data(as_text=True) or "")[:500])
    return "", 200
