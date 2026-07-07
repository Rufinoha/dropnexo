# api/mercadopago/srotas_mercadopago.py — OAuth e config Mercado Pago
from __future__ import annotations

import logging
from pathlib import Path
from flask import Blueprint, jsonify, redirect, request, session, url_for

from api.mercadopago.cliente import (
    atualizar_conta_info,
    carregar_config_mp,
    desconectar_mp,
    gerar_state_oauth,
    mp_configurado,
    mp_conectado,
    obter_access_token_valido,
    redirect_uri_oauth,
    salvar_config_mp,
    salvar_tokens,
    trocar_code_por_tokens,
    url_autorizacao,
)
from global_utils import Var_ConectarBanco, login_obrigatorio, obter_base_url, usuario_tem_permissao
from srotas_plataforma import MODULO_FORNECEDOR, garantir_modulo_sessao

_log = logging.getLogger(__name__)

_MOD = Path(__file__).resolve().parent

mp_bp = Blueprint(
    "mercadopago",
    __name__,
    root_path=str(_MOD),
    template_folder="templates",
    static_folder="static",
    static_url_path="/static/api/mercadopago",
)


def init_app(app):
    app.register_blueprint(mp_bp)


def _pode_integracoes() -> bool:
    return bool(
        session.get("eh_desenvolvedor")
        or usuario_tem_permissao("integracoes.ver")
        or usuario_tem_permissao("fn_integracoes.ver")
    )


def _exigir_fornecedor():
    if session.get("eh_desenvolvedor"):
        return None
    if garantir_modulo_sessao() == MODULO_FORNECEDOR:
        return None
    return redirect(url_for("integracoes.pagina", erro="Opções financeiras são apenas para fornecedores."))


@mp_bp.get("/api/integracoes/mercadopago/oauth/iniciar")
@login_obrigatorio()
def oauth_iniciar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if (r := _exigir_fornecedor()) is not None:
        return r
    if not mp_configurado():
        return redirect(
            url_for(
                "integracoes.pagina",
                erro="Mercado Pago indisponível. Configure APPLICATION_ID_DEV e ACCESS_TOKEN_DEV no servidor.",
            )
        )
    state = gerar_state_oauth()
    session["mp_oauth_state"] = state
    session["mp_oauth_tenant"] = session.get("id_tenant")
    return redirect(url_autorizacao(state))


@mp_bp.get("/api/integracoes/mercadopago/oauth/callback")
@login_obrigatorio(exigir_tenant=False)
def oauth_callback():
    if not _pode_integracoes():
        return redirect(url_for("integracoes.pagina", erro="permissao"))

    erro = request.args.get("error")
    if erro:
        return redirect(url_for("integracoes.pagina", erro=erro))

    state = request.args.get("state") or ""
    code = request.args.get("code") or ""
    if not code or state != session.get("mp_oauth_state"):
        return redirect(url_for("integracoes.pagina", erro="state_invalido"))

    id_tenant = session.get("mp_oauth_tenant") or session.get("id_tenant")
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
        session.pop("mp_oauth_state", None)
        session.pop("mp_oauth_tenant", None)
        return redirect(url_for("integracoes.pagina", conectado="mercadopago"))
    except Exception as e:
        return redirect(url_for("integracoes.pagina", erro=str(e)[:120]))


@mp_bp.post("/api/integracoes/mercadopago/desconectar")
@login_obrigatorio()
def desconectar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != MODULO_FORNECEDOR and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas fornecedores."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        desconectar_mp(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, message="Mercado Pago desconectado.")
    finally:
        conn.close()


@mp_bp.get("/api/integracoes/mercadopago/status")
@login_obrigatorio()
def status():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cfg = carregar_config_mp(cur, int(id_tenant))
        cfg["webhook_url"] = f"{obter_base_url().rstrip('/')}/api/integracoes/mercadopago/webhook"
        cfg["redirect_uri"] = redirect_uri_oauth()
        cfg["configurado_servidor"] = mp_configurado()
        return jsonify(success=True, **cfg)
    finally:
        conn.close()


@mp_bp.post("/api/integracoes/mercadopago/config/salvar")
@login_obrigatorio()
def config_salvar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if garantir_modulo_sessao() != MODULO_FORNECEDOR and not session.get("eh_desenvolvedor"):
        return jsonify(success=False, message="Apenas fornecedores."), 403
    body = request.get_json(silent=True) or {}
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        salvar_config_mp(
            cur,
            int(id_tenant),
            bool(body.get("aceita_pix", True)),
            bool(body.get("aceita_cartao", True)),
        )
        conn.commit()
        return jsonify(success=True, message="Configuração salva.")
    except ValueError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


@mp_bp.route("/api/integracoes/mercadopago/webhook", methods=["GET", "POST"])
def webhook():
    """Recebe notificações MP e confirma pagamentos de pedidos."""
    payment_id = None
    body = request.get_json(silent=True) or {}
    if isinstance(body.get("data"), dict):
        payment_id = body["data"].get("id")
    if not payment_id:
        payment_id = request.args.get("data.id") or request.args.get("id")
    topic = (
        request.args.get("type")
        or request.args.get("topic")
        or body.get("type")
        or body.get("action")
        or ""
    ).lower()
    if payment_id and ("payment" in topic or topic == ""):
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            from servico_pedido_mp import processar_webhook_pagamento

            result = processar_webhook_pagamento(cur, payment_id)
            conn.commit()
            if result:
                _log.info("MP webhook payment %s → pedido %s status %s", payment_id, result.get("id_pedido"), result.get("status"))
        except Exception as e:
            conn.rollback()
            _log.exception("MP webhook erro payment %s: %s", payment_id, e)
        finally:
            conn.close()
    return jsonify(success=True), 200


@mp_bp.post("/api/integracoes/mercadopago/conta/atualizar")
@login_obrigatorio()
def conta_atualizar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not mp_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Não conectado."), 400
        access = obter_access_token_valido(cur, int(id_tenant))
        info = atualizar_conta_info(cur, int(id_tenant), access)
        conn.commit()
        return jsonify(success=True, conta=info)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()
