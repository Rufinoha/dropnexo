# api/efi/efi.py — cliente Efi Pay (boleto, PIX, cartão)
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

from efipay import EfiPay


def _env(key: str, fallback: str = "") -> str:
    return (os.getenv(key) or fallback).strip()


def _efi_credenciais() -> dict:
    sandbox = _env("EFI_SANDBOX", "true").lower() in ("1", "true", "yes", "on")
    # Se sandbox não definido, assume DEV quando MODO_PRODUCAO=false
    if not _env("EFI_SANDBOX"):
        sandbox = _env("MODO_PRODUCAO", "false").lower() not in ("1", "true", "yes", "on")
    sufixo = "_DEV" if sandbox else "_PROD"
    client_id = (
        _env(f"EFI_CHAVE_ID{sufixo}")
        or _env(f"EFI_CLIENT_ID{sufixo}")
        or _env("EFI_CLIENT_ID")
        or _env(f"CHAVE_CLIENTE_ID{sufixo}")
        or _env("CHAVE_CLIENTE_ID")
    )
    client_secret = (
        _env(f"EFI_CHAVE_SECRET{sufixo}")
        or _env(f"EFI_CLIENT_SECRET{sufixo}")
        or _env("EFI_CLIENT_SECRET")
        or _env(f"CHAVE_CLIENTE_SECRET{sufixo}")
        or _env("CHAVE_CLIENTE_SECRET")
    )
    cert = (
        _env(f"EFI_CERT_PATH{sufixo}")
        or _env(f"EFI_CERTIFICATE_PATH{sufixo}")
        or _env("EFI_CERTIFICATE")
        or _env("EFI_CERT_PATH")
        or _env("EFI_CERTIFICATE_PATH")
    )
    cert_pwd = (
        _env(f"EFI_CERT_PASSWORD{sufixo}")
        or _env("EFI_CERT_PASSWORD")
        or _env(f"EFI_CERTIFICATE_PASSWORD{sufixo}")
    )
    if not client_id or not client_secret or not cert:
        raise RuntimeError(
            "Credenciais Efi incompletas. Configure CHAVE_CLIENTE_ID/SECRET e EFI_CERTIFICATE_PATH no .env."
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


def efi_sandbox() -> bool:
    try:
        return bool(_efi_credenciais().get("sandbox", True))
    except RuntimeError:
        return True


def efi_payee_code() -> str:
    """Identificador de Conta (API > Introdução no painel Efi)."""
    sandbox = efi_sandbox()
    sufixo = "_DEV" if sandbox else "_PROD"
    return (
        _env(f"EFI_PAYEE_CODE{sufixo}")
        or _env(f"EFI_IDENTIFICADOR_CONTA{sufixo}")
        or _env(f"EFI_ACCOUNT_ID{sufixo}")
        or _env("EFI_PAYEE_CODE")
        or _env("EFI_IDENTIFICADOR_CONTA")
        or _env("EFI_ACCOUNT_ID")
    )


def efi_front_config() -> dict:
    return {
        "disponivel": efi_disponivel(),
        "payee_code": efi_payee_code(),
        "environment": "sandbox" if efi_sandbox() else "production",
        "pix_disponivel": False,  # PIX adiado
    }


def efi_pix_chave() -> str:
    return _env("EFI_PIX_KEY") or _env("EFI_CHAVE_PIX") or _env("CHAVE_PIX")


def _cliente() -> EfiPay:
    return EfiPay(_efi_credenciais())


def _doc_tipo(documento: str) -> tuple[str, str]:
    doc = "".join(c for c in (documento or "") if c.isdigit())
    if len(doc) == 11:
        return "cpf", doc
    if len(doc) == 14:
        return "cnpj", doc
    raise ValueError("Documento do cliente inválido (CPF/CNPJ).")


def _raise_resp(resp: Any) -> dict:
    if isinstance(resp, str):
        raise RuntimeError(resp)
    if not isinstance(resp, dict):
        raise RuntimeError("Resposta inválida da Efi.")
    if resp.get("code", 200) >= 400:
        raise RuntimeError(str(resp.get("message") or resp))
    return resp


def notification_url_efi() -> str:
    """
    URL pública que a Efi chama ao mudar status da cobrança (boleto/cartão).
    Em produção use HTTPS público. Em localhost a Efi não consegue notificar.
    """
    from global_utils import obter_url_site_publico

    base = (_env("EFI_NOTIFICATION_BASE") or obter_url_site_publico()).rstrip("/")
    url = f"{base}/api/efi/webhook"
    secret = _env("EFI_WEBHOOK_SECRET")
    if secret:
        from urllib.parse import quote

        url = f"{url}?token={quote(secret)}"
    return url


def consultar_notificacao(token: str) -> dict:
    """Consulta detalhe da notificação (fluxo oficial API Cobranças)."""
    resp = _raise_resp(_cliente().get_notification(params={"token": token}))
    data = resp.get("data") if isinstance(resp, dict) else None
    return data if isinstance(data, dict) else (resp if isinstance(resp, dict) else {})


def criar_cobranca_boleto(
    *,
    nome_cliente: str,
    documento: str,
    email: str,
    valor_centavos: int,
    descricao: str,
    vencimento: date | None = None,
) -> dict:
    """Cria cobrança one-step (boleto)."""
    if valor_centavos <= 0:
        raise ValueError("Valor da cobrança deve ser maior que zero.")
    venc = vencimento or (date.today() + timedelta(days=7))
    tipo_doc, doc = _doc_tipo(documento)
    body = {
        "items": [{"name": descricao[:255], "value": int(valor_centavos), "amount": 1}],
        "metadata": {"notification_url": notification_url_efi()},
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
    resp = _raise_resp(_cliente().create_one_step_charge(params={}, body=body))
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


def criar_cobranca_pix(
    *,
    nome_cliente: str,
    documento: str,
    valor_centavos: int,
    descricao: str,
    expiracao_segundos: int = 86400,
) -> dict:
    """Cria cobrança PIX imediata (API Pix)."""
    chave = efi_pix_chave()
    if not chave:
        raise RuntimeError(
            "PIX não configurado. Defina EFI_PIX_KEY (chave Pix da conta Efi) no .env."
        )
    if valor_centavos <= 0:
        raise ValueError("Valor da cobrança deve ser maior que zero.")
    tipo_doc, doc = _doc_tipo(documento)
    valor = f"{valor_centavos / 100:.2f}"
    body = {
        "calendario": {"expiracao": max(600, int(expiracao_segundos))},
        "devedor": {tipo_doc: doc, "nome": (nome_cliente or "Cliente")[:200]},
        "valor": {"original": valor},
        "chave": chave,
        "solicitacaoPagador": (descricao or "DropNexo")[:140],
    }
    resp = _raise_resp(_cliente().pix_create_immediate_charge(body=body))
    data = resp if "txid" in resp else (resp.get("data") or resp)
    txid = str(data.get("txid") or "")
    loc = data.get("loc") or {}
    loc_id = loc.get("id") or data.get("loc", {}).get("id")
    qrcode = None
    copia = data.get("pixCopiaECola") or data.get("pix_copia_cola")
    if loc_id and not copia:
        try:
            qr = _cliente().pix_generate_qrcode(params={"id": int(loc_id)})
            if isinstance(qr, dict):
                copia = qr.get("qrcode") or qr.get("pixCopiaECola")
                img_b64 = qr.get("imagemQrcode") or qr.get("image")
                if img_b64:
                    if str(img_b64).startswith("data:"):
                        qrcode = str(img_b64)
                    else:
                        qrcode = f"data:image/png;base64,{img_b64}"
        except Exception:
            pass
    return {
        "charge_id": txid,
        "txid": txid,
        "pix_copia_cola": copia,
        "pix_qrcode": qrcode,
        "link_pagamento": None,
        "raw": resp,
    }


def criar_cobranca_cartao(
    *,
    nome_cliente: str,
    documento: str,
    email: str,
    valor_centavos: int,
    descricao: str,
    payment_token: str,
    installments: int = 1,
    telefone: str | None = None,
    endereco: dict | None = None,
) -> dict:
    """Cria cobrança one-step com cartão (payment_token do JS Efi)."""
    if valor_centavos <= 0:
        raise ValueError("Valor da cobrança deve ser maior que zero.")
    token = (payment_token or "").strip()
    if not token:
        raise ValueError("payment_token obrigatório para cartão.")
    tipo_doc, doc = _doc_tipo(documento)
    phone = "".join(c for c in (telefone or "") if c.isdigit())
    if len(phone) < 10:
        phone = "11999999999"
    customer: dict[str, Any] = {
        "name": (nome_cliente or "Cliente")[:255],
        "email": (email or "contato@dropnexo.com.br")[:255],
        "phone_number": phone[-11:] if len(phone) > 11 else phone,
        tipo_doc: doc,
    }
    credit: dict[str, Any] = {
        "customer": customer,
        "installments": max(1, min(12, int(installments or 1))),
        "payment_token": token,
    }
    end = endereco or {}
    street = (end.get("street") or end.get("logradouro") or "").strip()
    number = (end.get("number") or end.get("numero") or "S/N").strip() or "S/N"
    neighborhood = (end.get("neighborhood") or end.get("bairro") or "").strip()
    zipcode = "".join(c for c in (end.get("zipcode") or end.get("cep") or "") if c.isdigit())
    city = (end.get("city") or end.get("cidade") or "").strip()
    state = (end.get("state") or end.get("uf") or "").strip().upper()[:2]
    if street and neighborhood and len(zipcode) == 8 and city and state:
        billing = {
            "street": street[:200],
            "number": number[:40],
            "neighborhood": neighborhood[:100],
            "zipcode": zipcode,
            "city": city[:100],
            "state": state,
            "complement": (end.get("complement") or end.get("complemento") or "")[:100] or None,
        }
        credit["billing_address"] = {k: v for k, v in billing.items() if v is not None}

    body = {
        "items": [{"name": descricao[:255], "value": int(valor_centavos), "amount": 1}],
        "metadata": {"notification_url": notification_url_efi()},
        "payment": {"credit_card": credit},
    }
    resp = _raise_resp(_cliente().create_one_step_charge(params={}, body=body))
    data = resp.get("data") or {}
    charge_id = str(data.get("charge_id") or "")
    status = (data.get("status") or "").lower()
    pago = status in ("approved", "paid", "settled")
    reason = data.get("reason") or ""
    if status in ("unpaid", "canceled", "cancelled") and reason:
        raise RuntimeError(f"Cartão recusado: {reason}")
    return {
        "charge_id": charge_id,
        "pago": pago,
        "status": status,
        "link_pagamento": None,
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
