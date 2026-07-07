# servico_pedido_mp.py — checkout Mercado Pago nos pedidos B2B (Fase 2)
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from api.mercadopago.cliente import (
    criar_pagamento_pix,
    criar_preference_checkout,
    meios_pagamento_fornecedor,
    mp_conectado,
    obter_access_token_valido,
    obter_pagamento_mp,
)
from global_utils import agora_utc, obter_base_url
from servico_pedido import (
    STATUS_AGUARDANDO,
    STATUS_IMPORTADO,
    STATUS_PAGO,
    _status_vendedor_pagavel,
    marcar_pedido_pago,
    obter_pedido,
    status_vendedor_pedido,
)

_log = logging.getLogger(__name__)

MP_STATUS_APROVADO = {"approved"}
MP_STATUS_PENDENTE = {"pending", "in_process", "authorized"}
MP_STATUS_REJEITADO = {"rejected", "cancelled", "refunded", "charged_back"}


def external_reference_pedido(id_pedido: int) -> str:
    return f"dn_pedido_{id_pedido}"


def parse_external_reference(ref: str | None) -> int | None:
    if not ref:
        return None
    m = re.match(r"^dn_pedido_(\d+)$", str(ref).strip())
    return int(m.group(1)) if m else None


def _webhook_url() -> str:
    return f"{obter_base_url().rstrip('/')}/api/integracoes/mercadopago/webhook"


def _modo_producao() -> bool:
    return (os.getenv("MODO_PRODUCAO") or "").strip().lower() in ("1", "true", "yes", "sim")


def _carregar_pagador_vendedor(cur, id_vendedor: int, email_sessao: str | None) -> dict[str, str]:
    cur.execute(
        """
        SELECT COALESCE(NULLIF(TRIM(nome_fantasia), ''), nome),
               COALESCE(NULLIF(TRIM(email_comercial), ''), '')
        FROM tbl_tenant WHERE id = %s
        """,
        (id_vendedor,),
    )
    row = cur.fetchone()
    nome = (row[0] if row else "") or "Vendedor DropNexo"
    email = (row[1] if row else "") or (email_sessao or "").strip()
    if not email:
        raise ValueError("Configure o e-mail comercial do vendedor antes de pagar.")
    partes = nome.split(None, 1)
    return {
        "email": email,
        "first_name": partes[0][:80],
        "last_name": (partes[1] if len(partes) > 1 else partes[0])[:80],
    }


def _validar_pedido_pagamento(cur, id_vendedor: int, id_pedido: int) -> dict:
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if not _status_vendedor_pagavel(status_vendedor_pedido(ped)):
        raise ValueError("Somente pedidos importados ou aguardando pagamento podem ser pagos.")
    if ped["valor_total"] <= 0:
        raise ValueError("Valor do pedido inválido.")
    return ped


def meios_pagamento_pedido(cur, id_vendedor: int, id_pedido: int) -> dict:
    ped = _validar_pedido_pagamento(cur, id_vendedor, id_pedido)
    meios = meios_pagamento_fornecedor(cur, int(ped["id_tenant_fornecedor"]))
    return {
        "valor_total": ped["valor_total"],
        "fornecedor_nome": ped.get("fornecedor_nome"),
        **meios,
    }


def _salvar_checkout_pix(
    cur,
    id_pedido: int,
    payment: dict[str, Any],
) -> dict[str, Any]:
    payment_id = payment.get("id")
    status = payment.get("status") or "pending"
    poi = (payment.get("point_of_interaction") or {}).get("transaction_data") or {}
    qr = poi.get("qr_code") or ""
    expira = payment.get("date_of_expiration")

    expira_dt = None
    if expira:
        try:
            expira_dt = datetime.fromisoformat(str(expira).replace("Z", "+00:00"))
        except ValueError:
            expira_dt = None

    cur.execute(
        """
        UPDATE tbl_pedido SET
            meio_pagamento = 'pix',
            mp_payment_id = %s,
            mp_payment_status = %s,
            mp_checkout_url = %s,
            mp_pix_qr = %s,
            mp_pix_expira_em = %s,
            mp_preference_id = NULL,
            atualizado_em = %s
        WHERE id = %s
        """,
        (
            int(payment_id) if payment_id else None,
            status,
            poi.get("ticket_url"),
            qr,
            expira_dt,
            agora_utc(),
            id_pedido,
        ),
    )
    return {
        "meio": "pix",
        "payment_id": payment_id,
        "status": status,
        "qr_code": qr,
        "qr_code_base64": poi.get("qr_code_base64"),
        "ticket_url": poi.get("ticket_url"),
        "expira_em": expira_dt.isoformat() if expira_dt else None,
    }


def _salvar_checkout_cartao(cur, id_pedido: int, preference: dict[str, Any]) -> dict[str, Any]:
    pref_id = preference.get("id")
    init_point = preference.get("init_point") if _modo_producao() else (
        preference.get("sandbox_init_point") or preference.get("init_point")
    )
    cur.execute(
        """
        UPDATE tbl_pedido SET
            meio_pagamento = 'cartao',
            mp_preference_id = %s,
            mp_checkout_url = %s,
            mp_payment_id = NULL,
            mp_payment_status = 'pending',
            mp_pix_qr = NULL,
            mp_pix_expira_em = NULL,
            atualizado_em = %s
        WHERE id = %s
        """,
        (pref_id, init_point, agora_utc(), id_pedido),
    )
    return {
        "meio": "cartao",
        "preference_id": pref_id,
        "checkout_url": init_point,
        "status": "pending",
    }


def iniciar_pagamento(
    cur,
    id_vendedor: int,
    id_pedido: int,
    meio: str,
    *,
    email_sessao: str | None = None,
) -> dict[str, Any]:
    meio = (meio or "").strip().lower()
    if meio not in ("pix", "cartao"):
        raise ValueError("Meio de pagamento inválido. Use pix ou cartao.")

    ped = _validar_pedido_pagamento(cur, id_vendedor, id_pedido)
    id_forn = int(ped["id_tenant_fornecedor"])
    if not mp_conectado(cur, id_forn):
        raise ValueError("Fornecedor não conectou o Mercado Pago.")

    meios = meios_pagamento_fornecedor(cur, id_forn)
    if meio == "pix" and not meios.get("pix"):
        raise ValueError("Fornecedor não aceita PIX.")
    if meio == "cartao" and not meios.get("cartao"):
        raise ValueError("Fornecedor não aceita cartão.")

    access = obter_access_token_valido(cur, id_forn)
    pagador = _carregar_pagador_vendedor(cur, id_vendedor, email_sessao)
    ref = external_reference_pedido(id_pedido)
    valor = round(float(ped["valor_total"]), 2)
    base = obter_base_url().rstrip("/")
    notification_url = _webhook_url()

    if meio == "pix":
        payload = {
            "transaction_amount": valor,
            "description": f"Pedido {ped['numero']} — DropNexo",
            "payment_method_id": "pix",
            "payer": {"email": pagador["email"]},
            "external_reference": ref,
            "notification_url": notification_url,
        }
        payment = criar_pagamento_pix(access, payload)
        return _salvar_checkout_pix(cur, id_pedido, payment)

    payload = {
        "items": [
            {
                "title": f"Pedido {ped['numero']}",
                "quantity": 1,
                "unit_price": valor,
                "currency_id": "BRL",
            }
        ],
        "payer": pagador,
        "external_reference": ref,
        "notification_url": notification_url,
        "back_urls": {
            "success": f"{base}/vendedor/pedidos/pagamento/retorno?status=success&id_pedido={id_pedido}",
            "failure": f"{base}/vendedor/pedidos/pagamento/retorno?status=failure&id_pedido={id_pedido}",
            "pending": f"{base}/vendedor/pedidos/pagamento/retorno?status=pending&id_pedido={id_pedido}",
        },
        "auto_return": "approved",
        "payment_methods": {
            "excluded_payment_types": [
                {"id": "bank_transfer"},
                {"id": "ticket"},
                {"id": "debit_card"},
            ],
        },
    }
    preference = criar_preference_checkout(access, payload)
    return _salvar_checkout_cartao(cur, id_pedido, preference)


def _buscar_pedido_por_mp(cur, payment_id: int) -> tuple[int, int] | None:
    cur.execute(
        """
        SELECT id, id_tenant_fornecedor FROM tbl_pedido
        WHERE mp_payment_id = %s
        """,
        (payment_id,),
    )
    row = cur.fetchone()
    if row:
        return int(row[0]), int(row[1])

    cur.execute(
        """
        SELECT DISTINCT id_tenant_fornecedor FROM tbl_pedido
        WHERE status = %s AND mp_preference_id IS NOT NULL
        ORDER BY id_tenant_fornecedor
        """,
        (STATUS_AGUARDANDO,),
    )
    fornecedores = [int(r[0]) for r in cur.fetchall()]
    for id_forn in fornecedores:
        if not mp_conectado(cur, id_forn):
            continue
        try:
            access = obter_access_token_valido(cur, id_forn)
            pay = obter_pagamento_mp(access, payment_id)
        except Exception as e:
            _log.warning("MP fetch payment %s fornecedor %s: %s", payment_id, id_forn, e)
            continue
        id_ped = parse_external_reference(pay.get("external_reference"))
        if id_ped:
            cur.execute(
                """
                UPDATE tbl_pedido SET mp_payment_id = %s, atualizado_em = %s
                WHERE id = %s AND id_tenant_fornecedor = %s
                """,
                (payment_id, agora_utc(), id_ped, id_forn),
            )
            return id_ped, id_forn
    return None


def aplicar_status_mp(cur, id_pedido: int, payment: dict[str, Any]) -> dict[str, Any]:
    status = (payment.get("status") or "").lower()
    payment_id = payment.get("id")
    cur.execute(
        """
        UPDATE tbl_pedido SET
            mp_payment_id = COALESCE(%s, mp_payment_id),
            mp_payment_status = %s,
            atualizado_em = %s
        WHERE id = %s
        """,
        (payment_id, status, agora_utc(), id_pedido),
    )

    if status in MP_STATUS_APROVADO:
        marcar_pedido_pago(
            cur,
            id_pedido,
            mp_payment_id=int(payment_id) if payment_id else None,
            mp_status=status,
        )
        return {"id_pedido": id_pedido, "status": STATUS_PAGO, "mp_status": status}

    return {"id_pedido": id_pedido, "status": STATUS_AGUARDANDO, "mp_status": status}


def sincronizar_pagamento_pedido(cur, id_vendedor: int, id_pedido: int) -> dict[str, Any]:
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if status_vendedor_pedido(ped) == STATUS_PAGO:
        return {"status": STATUS_PAGO, "status_vendedor": STATUS_PAGO, "mp_status": "approved"}

    cur.execute(
        """
        SELECT mp_payment_id, meio_pagamento, mp_payment_status, mp_checkout_url,
               mp_pix_qr, mp_pix_expira_em
        FROM tbl_pedido WHERE id = %s
        """,
        (id_pedido,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return {
            "status": status_vendedor_pedido(ped),
            "status_vendedor": status_vendedor_pedido(ped),
            "mp_status": row[2] if row else None,
            "meio_pagamento": row[1] if row else None,
            "checkout_url": row[3] if row else None,
            "qr_code": row[4] if row else None,
            "expira_em": row[5].isoformat() if row and row[5] else None,
        }

    id_forn = int(ped["id_tenant_fornecedor"])
    access = obter_access_token_valido(cur, id_forn)
    payment = obter_pagamento_mp(access, int(row[0]))
    result = aplicar_status_mp(cur, id_pedido, payment)
    result["meio_pagamento"] = row[1]
    result["checkout_url"] = row[3]
    result["qr_code"] = row[4]
    result["expira_em"] = row[5].isoformat() if row[5] else None
    return result


def processar_webhook_pagamento(cur, payment_id: int | str) -> dict[str, Any] | None:
    try:
        pid = int(payment_id)
    except (TypeError, ValueError):
        return None

    localizado = _buscar_pedido_por_mp(cur, pid)
    if not localizado:
        _log.info("MP webhook: payment %s sem pedido associado.", pid)
        return None

    id_pedido, id_forn = localizado
    access = obter_access_token_valido(cur, id_forn)
    payment = obter_pagamento_mp(access, pid)
    return aplicar_status_mp(cur, id_pedido, payment)
