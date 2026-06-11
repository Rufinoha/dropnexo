# api/efi/srotas_efi.py — webhook Efi Pay
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
        "expired": "vencido",
        "canceled": "cancelado",
        "cancelled": "cancelado",
    }.get(s, "pendente")


@efi_bp.post("/api/efi/webhook")
def webhook_efi():
    secret = (os.getenv("EFI_WEBHOOK_SECRET") or "").strip()
    if secret:
        token = (request.headers.get("X-Webhook-Token") or request.args.get("token") or "").strip()
        if token != secret:
            return jsonify(success=False, message="Não autorizado."), 401

    payload = request.get_json(silent=True) or {}
    charge_id = str(
        payload.get("charge_id")
        or payload.get("id")
        or (payload.get("data") or {}).get("charge_id")
        or ""
    ).strip()
    status_raw = (
        payload.get("status")
        or (payload.get("data") or {}).get("status")
        or ""
    )
    if not charge_id:
        return jsonify(success=False, message="charge_id ausente."), 400

    novo_status = _mapa_status_efi(str(status_raw))
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE tbl_fatura
            SET status = %s, pago_em = CASE WHEN %s = 'pago' THEN NOW() ELSE pago_em END
            WHERE efi_charge_id = %s
            """,
            (novo_status, novo_status, charge_id),
        )
        conn.commit()
        return jsonify(success=True, atualizadas=cur.rowcount, status=novo_status)
    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e)), 500
    finally:
        conn.close()
