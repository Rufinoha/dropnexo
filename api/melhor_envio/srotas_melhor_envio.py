# api/melhor_envio/srotas_melhor_envio.py — OAuth, webhook e config Melhor Envio
from __future__ import annotations

import json
import logging
from pathlib import Path

from flask import Blueprint, jsonify, redirect, request, session, url_for

from api.melhor_envio.cliente import (
    atualizar_conta_info,
    carregar_config_me,
    desconectar_me,
    gerar_state_oauth,
    me_configurado,
    me_conectado,
    obter_access_token_valido,
    redirect_uri_oauth,
    salvar_preferencias_me,
    salvar_tokens,
    trocar_code_por_tokens,
    url_autorizacao,
    verificar_assinatura_webhook,
    webhook_url,
    diagnostico_oauth_me,
)
from global_utils import Var_ConectarBanco, login_obrigatorio, usuario_tem_permissao
from sistema.plataforma.sessao import garantir_modulo_sessao

_log = logging.getLogger(__name__)

_MOD = Path(__file__).resolve().parent

me_bp = Blueprint(
    "melhor_envio",
    __name__,
    root_path=str(_MOD),
    static_folder="static",
    static_url_path="/static/api/melhor_envio",
)


def init_app(app):
    app.register_blueprint(me_bp)


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
                erro="Conecte o Melhor Envio no módulo Vendedor (troque o perfil no topo).",
            )
        )
    return redirect(url_for("integracoes.pagina", erro="Melhor Envio é apenas para vendedores."))


@me_bp.get("/api/integracoes/melhor-envio/oauth/diagnostico")
@login_obrigatorio()
def oauth_diagnostico():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if (r := _exigir_vendedor()) is not None:
        return r
    try:
        d = diagnostico_oauth_me()
        return jsonify(success=True, diagnostico=d)
    except Exception as e:
        return jsonify(success=False, message=str(e)[:200]), 500


@me_bp.get("/api/integracoes/melhor-envio/oauth/iniciar")
@login_obrigatorio()
def oauth_iniciar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    if (r := _exigir_vendedor()) is not None:
        return r
    if not me_configurado():
        return redirect(
            url_for(
                "integracoes.pagina",
                erro="Melhor Envio indisponível. Configure ME_CLIENT_ID_PROD e ME_CLIENT_SECRET_PROD no servidor.",
            )
        )
    state = gerar_state_oauth()
    session["me_oauth_state"] = state
    session["me_oauth_tenant"] = session.get("id_tenant")
    return redirect(url_autorizacao(state))


@me_bp.get("/api/integracoes/melhor-envio/oauth/callback")
@login_obrigatorio(exigir_tenant=False)
def oauth_callback():
    if not _pode_integracoes():
        return redirect(url_for("integracoes.pagina", erro="permissao"))

    erro = request.args.get("error")
    if erro:
        return redirect(url_for("integracoes.pagina", erro=erro))

    state = request.args.get("state") or ""
    code = request.args.get("code") or ""
    if not code or state != session.get("me_oauth_state"):
        return redirect(url_for("integracoes.pagina", erro="state_invalido"))

    id_tenant = session.get("me_oauth_tenant") or session.get("id_tenant")
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
            try:
                cfg = carregar_config_me(cur, int(id_tenant))
                salvar_preferencias_me(
                    cur,
                    int(id_tenant),
                    opcao_recebimento=True,
                    opcao_maos_proprias=bool(cfg.get("opcao_maos_proprias")),
                )
            except RuntimeError:
                pass
            conn.commit()
        finally:
            conn.close()
        session.pop("me_oauth_state", None)
        session.pop("me_oauth_tenant", None)
        return redirect(url_for("integracoes.pagina_melhor_envio", conectado="1"))
    except Exception as e:
        return redirect(url_for("integracoes.pagina", erro=str(e)[:120]))


@me_bp.post("/api/integracoes/melhor-envio/desconectar")
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
        desconectar_me(cur, int(id_tenant))
        conn.commit()
        return jsonify(success=True, message="Melhor Envio desconectado.")
    finally:
        conn.close()


@me_bp.get("/api/integracoes/melhor-envio/status")
@login_obrigatorio()
def status():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cfg = carregar_config_me(cur, int(id_tenant))
        cfg["configurado_servidor"] = me_configurado()
        return jsonify(success=True, **cfg)
    finally:
        conn.close()


@me_bp.post("/api/integracoes/melhor-envio/config/salvar")
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
        salvar_preferencias_me(
            cur,
            int(id_tenant),
            opcao_recebimento=bool(body.get("opcao_recebimento")),
            opcao_maos_proprias=bool(body.get("opcao_maos_proprias")),
        )
        conn.commit()
        return jsonify(success=True, message="Preferências salvas.")
    except RuntimeError as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()


def _processar_evento_etiqueta(cur, payload: dict) -> None:
    """Atualiza pedido conforme status da etiqueta (order.posted, order.delivered, …)."""
    evento = (payload.get("event") or "").strip()
    dados = payload.get("data") or {}
    if not isinstance(dados, dict):
        return

    me_id = str(dados.get("id") or "").strip()
    status = (dados.get("status") or "").strip().lower()
    tracking = (dados.get("tracking") or dados.get("self_tracking") or "").strip()
    protocolo = (dados.get("protocol") or "").strip()

    if not me_id and not protocolo:
        return

    from core.pedidos.servico import marcar_em_expedicao, marcar_entregue

    cur.execute(
        """
        SELECT id, status, id_tenant_fornecedor
        FROM tbl_pedido
        WHERE (me_order_id = %s AND me_order_id <> '')
           OR (me_protocol = %s AND me_protocol <> '')
        ORDER BY id DESC
        LIMIT 1
        """,
        (me_id, protocolo),
    )
    row = cur.fetchone()
    if not row:
        _log.info("ME webhook %s — pedido não encontrado (%s / %s)", evento, me_id, protocolo)
        return

    id_pedido, status_pedido, id_fornecedor = int(row[0]), row[1], int(row[2])

    transportadora = "Melhor Envio"
    if tracking:
        cur.execute(
            """
            UPDATE tbl_pedido SET
                codigo_rastreio = COALESCE(NULLIF(%s, ''), codigo_rastreio),
                transportadora = COALESCE(NULLIF(transportadora, ''), %s),
                me_order_id = COALESCE(NULLIF(me_order_id, ''), %s),
                me_protocol = COALESCE(NULLIF(me_protocol, ''), %s),
                atualizado_em = NOW()
            WHERE id = %s
            """,
            (tracking, transportadora, me_id, protocolo, id_pedido),
        )

    if evento in ("order.posted", "order.generated", "order.released") or status in ("posted", "generated", "released"):
        if status_pedido == "pago":
            marcar_em_expedicao(
                cur,
                id_pedido,
                id_fornecedor=id_fornecedor,
                codigo_rastreio=tracking or None,
                transportadora=transportadora,
            )
    elif evento == "order.delivered" or status == "delivered":
        if status_pedido in ("pago", "em_expedicao"):
            marcar_entregue(cur, id_pedido, id_fornecedor=id_fornecedor)


@me_bp.route("/api/integracoes/melhor-envio/webhook", methods=["GET", "POST"])
def webhook():
    """Recebe notificações de status de etiquetas do Melhor Envio."""
    if request.method == "GET":
        return jsonify(ok=True, service="dropnexo-melhor-envio"), 200

    corpo = request.get_data()
    assinatura = request.headers.get("X-ME-Signature") or ""

    assinatura_valida = True
    if corpo and assinatura and me_configurado():
        assinatura_valida = verificar_assinatura_webhook(corpo, assinatura)
        if not assinatura_valida:
            # ME exige HTTP 200 no cadastro do webhook; não processar evento sem assinatura válida.
            _log.warning(
                "ME webhook: assinatura inválida (confira ME_CLIENT_SECRET no servidor)"
            )

    payload: dict = {}
    if corpo:
        try:
            payload = json.loads(corpo.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            _log.warning("ME webhook: corpo JSON inválido")
            return jsonify(success=True), 200

    if assinatura_valida and payload.get("event"):
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            _processar_evento_etiqueta(cur, payload)
            conn.commit()
        except Exception as e:
            conn.rollback()
            _log.exception("ME webhook erro: %s", e)
        finally:
            conn.close()

    return jsonify(success=True), 200


@me_bp.post("/api/integracoes/melhor-envio/conta/atualizar")
@login_obrigatorio()
def conta_atualizar():
    if not _pode_integracoes():
        return jsonify(success=False, message="Sem permissão."), 403
    id_tenant = session.get("id_tenant")
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not me_conectado(cur, int(id_tenant)):
            return jsonify(success=False, message="Não conectado."), 400
        access = obter_access_token_valido(cur, int(id_tenant))
        info = atualizar_conta_info(cur, int(id_tenant), access)
        conn.commit()
        return jsonify(success=True, conta=info)
    except Exception as e:
        return jsonify(success=False, message=str(e)), 400
    finally:
        conn.close()
