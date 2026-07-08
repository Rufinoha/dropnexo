# api/efi/efi.py — cliente Efi Pay (cobranças / boleto)
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

from efipay import EfiPay


def _env(key: str, fallback: str = "") -> str:
    return (os.getenv(key) or fallback).strip()


def _efi_credenciais() -> dict:
    sandbox = _env("EFI_SANDBOX", "true").lower() in ("1", "true", "yes", "on")
    sufixo = "_DEV" if sandbox else "_PROD"
    client_id = (
        _env(f"EFI_CLIENT_ID{sufixo}")
        or _env("EFI_CLIENT_ID")
        or _env("CHAVE_CLIENTE_ID_DEV")
        or _env("CHAVE_CLIENTE_ID")
    )
    client_secret = (
        _env(f"EFI_CLIENT_SECRET{sufixo}")
        or _env("EFI_CLIENT_SECRET")
        or _env("CHAVE_CLIENTE_SECRET_DEV")
        or _env("CHAVE_CLIENTE_SECRET")
    )
    cert = (
        _env(f"EFI_CERT_PATH{sufixo}")
        or _env("EFI_CERTIFICATE")
        or _env("EFI_CERT_PATH")
    )
    cert_pwd = _env(f"EFI_CERT_PASSWORD{sufixo}") or _env("EFI_CERT_PASSWORD")
    if not client_id or not client_secret or not cert:
        raise RuntimeError(
            "Credenciais Efi incompletas. Configure EFI_CLIENT_ID, EFI_CLIENT_SECRET e EFI_CERT_PATH no .env."
        )
    opts: dict[str, Any] = {
        "client_id": client_id,
        "client_secret": client_secret,
        "sandbox": sandbox,
        "certificate": cert,
    }
    if cert_pwd:
        opts["certificate_password"] = cert_pwd
    return opts


def efi_disponivel() -> bool:
    try:
        _efi_credenciais()
        return True
    except RuntimeError:
        return False


def _cliente() -> EfiPay:
    return EfiPay(_efi_credenciais())


def criar_cobranca_boleto(
    *,
    nome_cliente: str,
    documento: str,
    email: str,
    valor_centavos: int,
    descricao: str,
    vencimento: date | None = None,
) -> dict:
    """Cria cobrança one-step (boleto). Retorna dict normalizado."""
    if valor_centavos <= 0:
        raise ValueError("Valor da cobrança deve ser maior que zero.")
    venc = vencimento or (date.today() + timedelta(days=7))
    doc = "".join(c for c in (documento or "") if c.isdigit())
    tipo_doc = "cpf" if len(doc) == 11 else "cnpj"
    body = {
        "items": [{"name": descricao[:255], "value": int(valor_centavos), "amount": 1}],
        "payment": {
            "banking_billet": {
                "expire_at": venc.isoformat(),
                "customer": {
                    "name": (nome_cliente or "Cliente")[:255],
                    "email": (email or "contato@dropnexo.com.br")[:255],
                    tipo_doc: doc,
                },
            }
        },
    }
    efi = _cliente()
    resp = efi.create_one_step_charge(params={}, body=body)
    if isinstance(resp, str):
        raise RuntimeError(resp)
    if not isinstance(resp, dict):
        raise RuntimeError("Resposta inválida da Efi.")
    if resp.get("code", 200) >= 400:
        raise RuntimeError(str(resp.get("message") or resp))
    data = resp.get("data") or {}
    charge_id = str(data.get("charge_id") or "")
    billet = data.get("banking_billet") or {}
    if not billet and isinstance(data.get("payment"), dict):
        billet = data["payment"].get("banking_billet") or {}
    return {
        "charge_id": charge_id,
        "link_boleto": billet.get("link") or data.get("link"),
        "codigo_barras": billet.get("barcode"),
        "vencimento": venc.isoformat(),
        "raw": resp,
    }


def consultar_cobranca(charge_id: str) -> dict:
    efi = _cliente()
    resp = efi.detail_charge(params={"id": int(charge_id)})
    if isinstance(resp, str):
        raise RuntimeError(resp)
    data = (resp.get("data") if isinstance(resp, dict) else None) or {}
    status = (data.get("status") or "").lower()
    mapa = {
        "paid": "pago",
        "settled": "pago",
        "approved": "pago",
        "waiting": "pendente",
        "unpaid": "pendente",
        "pending": "pendente",
        "expired": "vencido",
        "canceled": "cancelado",
        "cancelled": "cancelado",
    }
    return {
        "status": mapa.get(status, "pendente"),
        "status_efi": status,
        "raw": data,
    }


def cancelar_cobranca(charge_id: str) -> dict:
    efi = _cliente()
    return efi.cancel_charge(params={"id": int(charge_id)})
