# api/amazon/srotas_amazon.py — OAuth Amazon SP-API (vendedor)
from __future__ import annotations

import logging
from pathlib import Path

from flask import Blueprint, jsonify, redirect, request, session, url_for

from api.amazon.amazon import (
    amazon_configurado,
    amazon_conectado,
    atualizar_seller_info,
    buscar_product_types_amazon,
    carregar_config_amazon,
    desconectar_amazon,
    gerar_state_oauth,
    listar_mapeamento_categorias_amazon,
    publicar_produtos_amazon,
    redirect_uri_oauth,
    salvar_config_amazon,
    salvar_mapeamento_categorias_amazon,
    salvar_tokens,
    trocar_code_por_tokens,
    url_autorizacao,
)
from global_utils import Var_ConectarBanco, login_obrigatorio, usuario_tem_permissao
from sistema.plataforma.sessao import garantir_modulo_sessao

_log = logging.getLogger(__name__)

_MOD = Path(__file__).resolve().parent

amazon_bp = Blueprint(
    "amazon",
    __name__,
    root_path=str(_MOD),
    static_folder="static",
    static_url_path="/static/api/amazon",
)


def init_app(app):
    app.register_blueprint(amazon_bp)


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
                erro="Conecte a Amazon no módulo Vendedor (troque o perfil no topo).",
            )
        )
    return redirect(url_for("integracoes.pagina", erro="Amazon é apenas para vendedores."))


@amazon_bp.get("/api/integracoes/amazon/oauth/iniciar")
@login_obrigatorio()
def oauth_iniciar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if (r := _exigir_vendedor()) is not None:
        return r
    if not amazon_configurado():
        return redirect(
            url_for(
                "integracoes.pagina",
                erro="Amazon indisponível. Configure AMAZON_LWA_CLIENT_ID, "
                "AMAZON_LWA_CLIENT_SECRET e AMAZON_APP_ID no .env.",
            )
        )
    state = gerar_state_oauth()
    session["amazon_oauth_state"] = state
    session["amazon_oauth_tenant"] = session.get("id_tenant")
    return redirect(url_autorizacao(state))


@amazon_bp.get("/api/integracoes/amazon/oauth/callback")
@login_obrigatorio(exigir_tenant=False)
def oauth_callback():
    if not _pode_integracoes():
        return redirect(url_for("integracoes.pagina", erro="permissao"))

    erro = request.args.get("error") or request.args.get("error_description")
    if erro:
        return redirect(url_for("integracoes.pagina", erro=erro))

    state = request.args.get("state") or ""
    code = request.args.get("spapi_oauth_code") or request.args.get("code") or ""
    selling_partner_id = (
        request.args.get("selling_partner_id")
        or request.args.get("seller_id")
        or ""
    ).strip()
    if not code or state != session.get("amazon_oauth_state"):
        return redirect(url_for("integracoes.pagina", erro="state_invalido"))

    id_tenant = session.get("amazon_oauth_tenant") or session.get("id_tenant")
    if not id_tenant:
        return redirect(url_for("integracoes.pagina", erro="sessao"))

    try:
        tokens = trocar_code_por_tokens(code)
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            salvar_tokens(cur, int(id_tenant), tokens, seller_id=selling_partner_id or None)
            atualizar_seller_info(cur, int(id_tenant), seller_id=selling_partner_id or None)
            conn.commit()
        finally:
            conn.close()
        session.pop("amazon_oauth_state", None)
        session.pop("amazon_oauth_tenant", None)
        return redirect(url_for("integracoes.pagina", conectado_amazon="1"))
    except Exception as e:
        _log.exception("Amazon OAuth callback")
        return redirect(url_for("integracoes.pagina", erro=str(e)[:120]))


@amazon_bp.post("/api/integracoes/amazon/desconectar")
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
        desconectar_amazon(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, message="Amazon desconectada.")
    finally:
        conn.close()


@amazon_bp.get("/api/integracoes/amazon/status")
@login_obrigatorio()
def status():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cfg = carregar_config_amazon(cur, int(id_tenant))
        cfg["configurado_servidor"] = amazon_configurado()
        cfg["conectado"] = amazon_conectado(cur, int(id_tenant))
        return jsonify(success=True, config=cfg)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 500
    finally:
        conn.close()


@amazon_bp.post("/api/integracoes/amazon/config/salvar")
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
        if not amazon_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Conecte a Amazon primeiro."), 400
        salvar_config_amazon(
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


@amazon_bp.post("/api/integracoes/amazon/sync/pedidos")
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
        if not amazon_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Amazon não conectada."), 400
        from api.amazon.amazon import importar_pedidos_amazon

        resultado = importar_pedidos_amazon(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, **resultado)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@amazon_bp.post("/api/integracoes/amazon/sync/estoque")
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
        from api.amazon.amazon import sincronizar_estoque_amazon

        resultado = sincronizar_estoque_amazon(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, **resultado)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@amazon_bp.get("/api/integracoes/amazon/categorias-mapeamento")
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
        if not amazon_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Amazon não conectada."), 400
        itens = listar_mapeamento_categorias_amazon(cur, int(id_tenant))
        return jsonify(success=True, itens=itens)
    finally:
        conn.close()


@amazon_bp.post("/api/integracoes/amazon/categorias-mapeamento/salvar")
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
        if not amazon_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Amazon não conectada."), 400
        n = salvar_mapeamento_categorias_amazon(cur, int(id_tenant), itens)
        conn.commit()
        return jsonify(success=True, message=f"{n} categoria(s) mapeada(s).", salvos=n)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@amazon_bp.get("/api/integracoes/amazon/product-types/buscar")
@login_obrigatorio()
def product_types_buscar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != "vendedor" and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas vendedores."), 403
    keywords = (request.args.get("keywords") or request.args.get("q") or "").strip()
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not amazon_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Amazon não conectada."), 400
        tipos = buscar_product_types_amazon(cur, int(id_tenant), keywords)
        return jsonify(success=True, itens=tipos)
    except Exception as e:
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@amazon_bp.post("/api/integracoes/amazon/produtos/publicar")
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
        resultado = publicar_produtos_amazon(cur, int(id_tenant), ids)
        conn.commit()
        return jsonify(success=True, **resultado)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)[:300]), 400
    finally:
        conn.close()


@amazon_bp.get("/api/integracoes/amazon/diagnostico")
@login_obrigatorio()
def diagnostico():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    return jsonify(
        success=True,
        configurado=amazon_configurado(),
        redirect_uri=redirect_uri_oauth(),
    )
