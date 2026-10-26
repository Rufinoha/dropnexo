# api/efi/srotas_efi.py — webhook / notificações Efi Pay
from __future__ import annotations

import os

from flask import Blueprint, jsonify, request

from global_utils import Var_ConectarBanco

efi_bp = Blueprint("efi", __name__)


def init_app(app):
    app.register_blueprint(efi_bp)


def _mapa_status_efi(status: str) -> str:
    s = (status or "").lower()
    return {
        "paid": "pago",
        "settled": "pago",
        "approved": "pago",
        "waiting": "pendente",
        "unpaid": "pendente",
        "pending": "pendente",
        "new": "pendente",
        "waiting_payment": "pendente",
        "identified": "pendente",
        "expired": "vencido",
        "canceled": "cancelado",
        "cancelled": "cancelado",
        "refunded": "cancelado",
        "concluida": "pago",
        "ativa": "pendente",
        "removida_pelo_usuario_recebedor": "cancelado",
    }.get(s, "pendente")


def _autorizado_webhook() -> bool:
    secret = (os.getenv("EFI_WEBHOOK_SECRET") or "").strip()
    if not secret:
        return True
    token = (
        request.headers.get("X-Webhook-Token")
        or request.args.get("token")
        or ""
    ).strip()
    return token == secret


def _extrair_notification_token() -> str:
    """Efi Cobranças envia form: notification=<token>."""
    tok = (request.form.get("notification") or request.values.get("notification") or "").strip()
    if tok:
        return tok
    payload = request.get_json(silent=True) or {}
    if isinstance(payload, dict):
        return str(
            payload.get("notification")
            or payload.get("token")
            or ""
        ).strip()
    return ""


def _status_notificacao(valor) -> str:
    """A Efí manda status como texto ou como {current, previous}."""
    if isinstance(valor, dict):
        return str(valor.get("current") or valor.get("current_status") or "").strip()
    return str(valor or "").strip()


def _charge_id_notificacao(item: dict) -> str:
    """charge_id oficial fica em identifiers. O campo id é só a ordem do aviso."""
    ident = item.get("identifiers") if isinstance(item.get("identifiers"), dict) else {}
    bruto = (
        ident.get("charge_id")
        or item.get("charge_id")
        or ident.get("txid")
        or item.get("txid")
        or ""
    )
    return str(bruto).strip()


def _payload_da_notificacao(notif_data: dict) -> dict:
    """Normaliza GET /notification/:token → charge_id + status atual."""
    charges = []
    if isinstance(notif_data.get("charges"), list):
        charges = notif_data["charges"]
    elif isinstance(notif_data.get("data"), list):
        charges = notif_data["data"]
    elif isinstance(notif_data.get("data"), dict) and isinstance(notif_data["data"].get("charges"), list):
        charges = notif_data["data"]["charges"]

    if charges:
        last = charges[-1] if isinstance(charges[-1], dict) else {}
    else:
        last = notif_data if isinstance(notif_data, dict) else {}

    ident = last.get("identifiers") if isinstance(last.get("identifiers"), dict) else {}
    custom = last.get("custom_id") or ident.get("custom_id") or ""
    return {
        "charge_id": _charge_id_notificacao(last),
        "status": _status_notificacao(last.get("status") or last.get("current_status")),
        "tipo": str(last.get("type") or "").strip().lower(),
        "custom_id": str(custom).strip(),
        "subscription_id": str(ident.get("subscription_id") or last.get("subscription_id") or "").strip(),
        "raw_notification": notif_data,
    }


@efi_bp.route("/api/efi/webhook", methods=["GET", "POST"])
def webhook_efi():
    """
    Endpoint de notificação Efi (API Cobranças).

    Cadastro: não fica no painel fixo — a URL vai em metadata.notification_url
    de cada cobrança (o DropNexo já envia automaticamente):

      https://dropnexo.com.br/api/efi/webhook
      (opcional) ?token=SEU_EFI_WEBHOOK_SECRET
    """
    if not _autorizado_webhook():
        return jsonify(success=False, message="Não autorizado."), 401

    # Health-check / abertura no navegador
    if request.method == "GET" and not _extrair_notification_token():
        from api.efi.efi import notification_url_efi

        return jsonify(
            success=True,
            message="Webhook Efi DropNexo ativo.",
            notification_url=notification_url_efi(),
        )

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from sistema.financeiro.cobranca import processar_webhook_efi, registrar_efi_log

        notif_token = _extrair_notification_token()
        payload: dict = {}

        if notif_token:
            from api.efi.efi import consultar_notificacao

            try:
                notif = consultar_notificacao(notif_token)
                payload = _payload_da_notificacao(notif if isinstance(notif, dict) else {})
                registrar_efi_log(
                    cur,
                    id_tenant=None,
                    id_fatura=None,
                    direcao="in",
                    operacao="notification_token",
                    ok=bool(payload.get("charge_id")),
                    efi_charge_id=str(payload.get("charge_id") or "") or None,
                    request_resumo={"notification": notif_token},
                    response_resumo=payload.get("raw_notification") or notif,
                )
            except Exception as e:
                registrar_efi_log(
                    cur,
                    id_tenant=None,
                    id_fatura=None,
                    direcao="in",
                    operacao="notification_token",
                    ok=False,
                    request_resumo={"notification": notif_token},
                    response_resumo=str(e),
                )
                conn.commit()
                return jsonify(success=False, message=f"Falha ao consultar notificação: {e}"), 502
        else:
            payload = request.get_json(silent=True) or {}
            if not isinstance(payload, dict):
                payload = {}
            # form alternativo
            if request.form:
                payload = {**payload, **{k: request.form.get(k) for k in request.form}}

        result = processar_webhook_efi(cur, payload)
        conn.commit()
        return jsonify(success=bool(result.get("ok")), **result)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()


@efi_bp.post("/api/financeiro/job-diario")
def job_diario_financeiro():
    """Cron: marcar vencidas, avisar e, 30 dias após o vencimento, cancelar a recorrência."""
    secret = (os.getenv("CRON_SECRET") or os.getenv("EFI_WEBHOOK_SECRET") or "").strip()
    token = (request.headers.get("X-Cron-Token") or request.args.get("token") or "").strip()
    if not secret or token != secret:
        return jsonify(success=False, message="Não autorizado."), 401
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        from sistema.financeiro.cobranca import job_financeiro_diario

        res = job_financeiro_diario(cur)
        conn.commit()
        return jsonify(success=True, **res)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()
