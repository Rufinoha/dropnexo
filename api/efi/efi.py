# api/efi/efi.py — cliente Efi Pay (boleto, PIX, cartão)
from __future__ import annotations

import os
from datetime import date, timedelta
from typing import Any

from efipay import EfiPay


def _env(key: str, fallback: str = "") -> str:
    return (os.getenv(key) or fallback).strip()


def _garantir_cert_pem(cert_path: "Path", cert_pwd: str | None) -> "Path":
    """
    O efipay + OpenSSL recente falha com alguns .p12 (SSL PEM lib).
    Se o path for .p12, gera .pem irmão (nodes) e usa o PEM.
    """
    from pathlib import Path
    import subprocess

    p = Path(cert_path)
    if p.suffix.lower() != ".p12":
        return p
    pem = p.with_suffix(".pem")
    precisa = (not pem.is_file()) or (pem.stat().st_mtime < p.stat().st_mtime)
    if precisa:
        pwd = cert_pwd if cert_pwd is not None else ""
        tentativas = [
            ["openssl", "pkcs12", "-in", str(p), "-out", str(pem), "-nodes", "-passin", f"pass:{pwd}"],
            ["openssl", "pkcs12", "-in", str(p), "-out", str(pem), "-nodes", "-passin", f"pass:{pwd}", "-legacy"],
        ]
        last_err = ""
        for cmd in tentativas:
            proc = subprocess.run(cmd, capture_output=True, text=True)
            if proc.returncode == 0 and pem.is_file():
                try:
                    pem.chmod(0o640)
                except OSError:
                    pass
                break
            last_err = (proc.stderr or proc.stdout or "").strip()
        else:
            raise RuntimeError(
                f"Não converti o certificado Efí .p12 → .pem ({p}). OpenSSL: {last_err[:240]}"
            )
    return pem


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
    # Resolve relativo ao cwd do app (produção: /srv/dropnexo).
    # Em alguns OpenSSL o SDK falha com .p12 cru (SSL PEM lib); preferimos .pem.
    from pathlib import Path

    cert_path = Path(cert)
    if not cert_path.is_absolute():
        cert_path = (Path.cwd() / cert_path).resolve()
    if not cert_path.is_file():
        raise RuntimeError(
            f"Certificado Efí não encontrado: {cert_path}. "
            "Coloque o .p12/.pem em api/efi/secrets/ (Pix/MED/saldo exigem mTLS)."
        )
    cert_path = _garantir_cert_pem(cert_path, cert_pwd)
    opts: dict[str, Any] = {
        "client_id": client_id,
        "client_secret": client_secret,
        "sandbox": sandbox,
        "certificate": str(cert_path),
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


def _customer_efi(
    *,
    nome_cliente: str,
    documento: str,
    email: str | None = None,
    telefone: str | None = None,
) -> dict[str, Any]:
    """
    Monta customer da API Cobranças.
    CPF: name + cpf. CNPJ: juridical_person (cnpj não vai na raiz do customer).
    """
    tipo_doc, doc = _doc_tipo(documento)
    nome = (nome_cliente or "Cliente")[:255]
    customer: dict[str, Any] = {}
    if email and "@" in email:
        customer["email"] = email.strip()[:255]
    phone = "".join(c for c in (telefone or "") if c.isdigit())
    if len(phone) >= 10:
        customer["phone_number"] = phone[-11:] if len(phone) > 11 else phone
    if tipo_doc == "cpf":
        customer["name"] = nome
        customer["cpf"] = doc
    else:
        customer["juridical_person"] = {
            "corporate_name": nome,
            "cnpj": doc,
        }
    return customer


def _raise_resp(resp: Any) -> dict:
    if isinstance(resp, BaseException):
        raise RuntimeError(f"Efi: {resp}") from resp
    if isinstance(resp, str):
        raise RuntimeError(resp)
    if not isinstance(resp, dict):
        raise RuntimeError(f"Resposta inválida da Efi ({type(resp).__name__}).")
    code = resp.get("code", 200)
    try:
        code_n = int(code)
    except (TypeError, ValueError):
        code_n = 200
    if code_n >= 400:
        desc = resp.get("error_description") or resp.get("message") or resp
        if isinstance(desc, dict):
            prop = desc.get("property") or ""
            msg = desc.get("message") or str(desc)
            raise RuntimeError(f"Efi: {msg}" + (f" ({prop})" if prop else ""))
        raise RuntimeError(str(desc))
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
    telefone: str | None = None,
    endereco: dict | None = None,
) -> dict:
    """Cria cobrança one-step (boleto)."""
    if valor_centavos <= 0:
        raise ValueError("Valor da cobrança deve ser maior que zero.")
    venc = vencimento or (date.today() + timedelta(days=7))
    customer = _customer_efi(
        nome_cliente=nome_cliente,
        documento=documento,
        email=email or "contato@dropnexo.com.br",
        telefone=telefone,
    )
    end = endereco or {}
    street = (end.get("street") or end.get("logradouro") or "").strip()
    number = (end.get("number") or end.get("numero") or "S/N").strip() or "S/N"
    neighborhood = (end.get("neighborhood") or end.get("bairro") or "").strip()
    zipcode = "".join(c for c in (end.get("zipcode") or end.get("cep") or "") if c.isdigit())
    city = (end.get("city") or end.get("cidade") or "").strip()
    state = (end.get("state") or end.get("uf") or "").strip().upper()[:2]
    if street and neighborhood and len(zipcode) == 8 and city and state:
        customer["address"] = {
            "street": street[:200],
            "number": number[:40],
            "neighborhood": neighborhood[:100],
            "zipcode": zipcode,
            "city": city[:100],
            "state": state,
            "complement": (end.get("complement") or end.get("complemento") or "")[:100] or "",
        }
    body = {
        "items": [{"name": descricao[:255], "value": int(valor_centavos), "amount": 1}],
        "metadata": {"notification_url": notification_url_efi()},
        "payment": {
            "banking_billet": {
                "expire_at": venc.isoformat(),
                "customer": customer,
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


def _motivo_recusa_cartao(data: dict) -> str:
    reason = str((data or {}).get("reason") or "").strip()
    if reason:
        return reason
    hist = (data or {}).get("history") or []
    if isinstance(hist, list):
        for item in reversed(hist):
            if not isinstance(item, dict):
                continue
            msg = str(item.get("message") or "").strip()
            baixo = msg.casefold()
            if msg and ("recus" in baixo or "função crédito" in baixo or "funcao credito" in baixo):
                return msg
    return ""


def _mensagem_recusa_cartao(reason: str) -> str:
    baixo = (reason or "").casefold()
    if "função crédito" in baixo or "funcao credito" in baixo:
        return (
            "Este cartão não tem função crédito. "
            "Aceitamos somente cartão de crédito. "
            "Se o seu cartão for só de débito, pague no boleto."
        )
    if reason:
        return f"Cartão recusado: {reason}"
    return (
        "O pagamento não foi autorizado. "
        "Aceitamos somente cartão de crédito. "
        "Cartão de débito não é cobrado."
    )


def _motivo_da_cobranca(data: dict, charge_id: str) -> str:
    reason = _motivo_recusa_cartao(data)
    if reason or not charge_id.isdigit():
        return reason
    try:
        det = _raise_resp(_cliente().detail_charge(params={"id": int(charge_id)}))
    except Exception:
        return reason
    det_data = det.get("data") if isinstance(det, dict) else None
    return _motivo_recusa_cartao(det_data if isinstance(det_data, dict) else {}) or reason


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
    custom_id: str | None = None,
) -> dict:
    """Cria cobrança one-step com cartão (payment_token do JS Efi)."""
    if valor_centavos <= 0:
        raise ValueError("Valor da cobrança deve ser maior que zero.")
    token = (payment_token or "").strip()
    if not token:
        raise ValueError("payment_token obrigatório para cartão.")
    phone = "".join(c for c in (telefone or "") if c.isdigit())
    if len(phone) < 10:
        phone = "11999999999"
    customer = _customer_efi(
        nome_cliente=nome_cliente,
        documento=documento,
        email=email or "contato@dropnexo.com.br",
        telefone=phone,
    )
    # Cartão exige name na raiz mesmo para PJ
    if "name" not in customer:
        customer["name"] = (nome_cliente or "Cliente")[:255]
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

    meta = {"notification_url": notification_url_efi()}
    if (custom_id or "").strip():
        meta["custom_id"] = str(custom_id).strip()[:255]
    body = {
        "items": [{"name": descricao[:255], "value": int(valor_centavos), "amount": 1}],
        "metadata": meta,
        "payment": {"credit_card": credit},
    }
    resp = _raise_resp(_cliente().create_one_step_charge(params={}, body=body))
    data = resp.get("data") or {}
    charge_id = str(data.get("charge_id") or "")
    status = (data.get("status") or "").lower()
    pago = status in ("approved", "paid", "settled")
    if status in ("unpaid", "canceled", "cancelled"):
        raise ValueError(_mensagem_recusa_cartao(_motivo_da_cobranca(data, charge_id)))
    return {
        "charge_id": charge_id,
        "pago": pago,
        "status": status,
        "link_pagamento": None,
        "raw": resp,
    }


def criar_plano_assinatura(*, nome: str, intervalo_meses: int) -> str:
    """Plano Efí com repetição indefinida até o cancelamento."""
    intervalo = max(1, min(24, int(intervalo_meses or 1)))
    body = {"name": (nome or "DropNexo")[:255], "interval": intervalo, "repeats": None}
    resp = _raise_resp(_cliente().create_plan(body=body))
    data = resp.get("data") or {}
    plan_id = str(data.get("plan_id") or "").strip()
    if not plan_id:
        raise RuntimeError("A Efí não devolveu o plano da assinatura.")
    return plan_id


def criar_assinatura_one_step(
    *,
    plan_id: str,
    nome_cliente: str,
    documento: str,
    email: str,
    valor_centavos: int,
    descricao: str,
    custom_id: str,
    forma: str,
    vencimento: date | None = None,
    payment_token: str | None = None,
    telefone: str | None = None,
    endereco: dict | None = None,
) -> dict:
    """Cria a assinatura recorrente e a primeira cobrança."""
    if valor_centavos <= 0:
        raise ValueError("Valor da cobrança deve ser maior que zero.")
    phone = "".join(c for c in (telefone or "") if c.isdigit())
    if len(phone) < 10:
        phone = "11999999999"
    customer = _customer_efi(
        nome_cliente=nome_cliente,
        documento=documento,
        email=email or "contato@dropnexo.com.br",
        telefone=phone,
    )
    end = endereco or {}
    street = (end.get("street") or end.get("logradouro") or "").strip()
    number = (end.get("number") or end.get("numero") or "S/N").strip() or "S/N"
    neighborhood = (end.get("neighborhood") or end.get("bairro") or "").strip()
    zipcode = "".join(c for c in (end.get("zipcode") or end.get("cep") or "") if c.isdigit())
    city = (end.get("city") or end.get("cidade") or "").strip()
    state = (end.get("state") or end.get("uf") or "").strip().upper()[:2]
    if street and neighborhood and len(zipcode) == 8 and city and state:
        address = {
            "street": street[:200],
            "number": number[:40],
            "neighborhood": neighborhood[:100],
            "zipcode": zipcode,
            "city": city[:100],
            "state": state,
            "complement": (end.get("complement") or end.get("complemento") or "")[:100] or "",
        }
        customer["address"] = address
    else:
        address = None

    meta = {"custom_id": (custom_id or "")[:255], "notification_url": notification_url_efi()}
    item = {"name": descricao[:255], "value": int(valor_centavos), "amount": 1}
    if forma == "cartao":
        token = (payment_token or "").strip()
        if not token:
            raise ValueError("payment_token obrigatório para cartão.")
        credit: dict[str, Any] = {
            "customer": customer,
            "payment_token": token,
        }
        if address:
            credit["billing_address"] = {k: v for k, v in address.items() if v}
        payment = {"credit_card": credit}
    else:
        venc = vencimento or (date.today() + timedelta(days=10))
        payment = {
            "banking_billet": {
                "customer": customer,
                "expire_at": venc.isoformat(),
                "message": "Mensalidade DropNexo",
            }
        }
    body = {"items": [item], "metadata": meta, "payment": payment}
    resp = _raise_resp(
        _cliente().create_one_step_subscription(params={"id": int(plan_id)}, body=body)
    )
    data = resp.get("data") or {}
    charge = data.get("charge") or {}
    status = str(charge.get("status") or data.get("status") or "").lower()
    pago = status in ("approved", "paid", "settled")
    reason = str(data.get("reason") or charge.get("reason") or "").strip()
    if status in ("unpaid", "canceled", "cancelled"):
        sub_id = str(data.get("subscription_id") or "").strip()
        if sub_id.isdigit():
            try:
                cancelar_assinatura(sub_id)
            except Exception:
                pass
        raise ValueError(_mensagem_recusa_cartao(reason) if forma == "cartao" else (reason or "Cobrança não autorizada."))
    pdf = data.get("pdf") if isinstance(data.get("pdf"), dict) else {}
    link = data.get("billet_link") or data.get("link") or pdf.get("charge")
    return {
        "subscription_id": str(data.get("subscription_id") or ""),
        "plan_id": str(plan_id),
        "charge_id": str(charge.get("id") or ""),
        "pago": pago,
        "status": status,
        "link_boleto": link,
        "codigo_barras": data.get("barcode"),
        "vencimento": data.get("expire_at"),
        "txid": None,
        "pix_copia_cola": None,
        "pix_qrcode": None,
        "link_pagamento": None,
        "raw": resp,
    }


def definir_forma_assinatura(
    *,
    subscription_id: str,
    forma: str,
    nome_cliente: str,
    documento: str,
    email: str,
    telefone: str | None = None,
    endereco: dict | None = None,
    payment_token: str | None = None,
    vencimento: date | None = None,
) -> dict:
    """Troca boleto/cartão da assinatura. Cobranças já emitidas não mudam."""
    sub = str(subscription_id or "").strip()
    if not sub.isdigit():
        raise RuntimeError("Assinatura Efí ausente.")
    phone = "".join(c for c in (telefone or "") if c.isdigit())
    if len(phone) < 10:
        phone = "11999999999"
    customer = _customer_efi(
        nome_cliente=nome_cliente,
        documento=documento,
        email=email or "contato@dropnexo.com.br",
        telefone=phone,
    )
    end = endereco or {}
    street = (end.get("street") or end.get("logradouro") or "").strip()
    number = (end.get("number") or end.get("numero") or "S/N").strip() or "S/N"
    neighborhood = (end.get("neighborhood") or end.get("bairro") or "").strip()
    zipcode = "".join(c for c in (end.get("zipcode") or end.get("cep") or "") if c.isdigit())
    city = (end.get("city") or end.get("cidade") or "").strip()
    state = (end.get("state") or end.get("uf") or "").strip().upper()[:2]
    address = None
    if street and neighborhood and len(zipcode) == 8 and city and state:
        address = {
            "street": street[:200],
            "number": number[:40],
            "neighborhood": neighborhood[:100],
            "zipcode": zipcode,
            "city": city[:100],
            "state": state,
            "complement": (end.get("complement") or end.get("complemento") or "")[:100] or "",
        }
        customer["address"] = address
    if forma == "cartao":
        token = (payment_token or "").strip()
        if not token:
            raise ValueError("payment_token obrigatório para cartão.")
        if "name" not in customer:
            customer["name"] = (nome_cliente or "Cliente")[:255]
        credit: dict[str, Any] = {"customer": customer, "payment_token": token}
        if address:
            credit["billing_address"] = {k: v for k, v in address.items() if v}
        payment = {"credit_card": credit}
    else:
        venc = vencimento or (date.today() + timedelta(days=10))
        payment = {
            "banking_billet": {
                "customer": customer,
                "expire_at": venc.isoformat(),
                "message": "Mensalidade DropNexo",
            }
        }
    resp = _raise_resp(
        _cliente().define_subscription_pay_method(params={"id": int(sub)}, body={"payment": payment})
    )
    return {"ok": True, "raw": resp}


def cancelar_assinatura(subscription_id: str) -> dict:
    sub = str(subscription_id or "").strip()
    if not sub.isdigit():
        raise RuntimeError("Assinatura Efí ausente.")
    return _raise_resp(_cliente().cancel_subscription(params={"id": int(sub)}))


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
    return _raise_resp(efi.cancel_charge(params={"id": int(charge_id)}))


def cancelar_cobranca_pix(txid: str) -> dict:
    """Encerra cobrança PIX imediata ainda ativa. PIX pago não é removido."""
    efi = _cliente()
    tx = (txid or "").strip()
    if not tx:
        raise RuntimeError("txid PIX ausente.")
    det = _raise_resp(efi.pix_detail_charge(params={"txid": tx}))
    corpo = det.get("data") if isinstance(det.get("data"), dict) else det
    status = str((corpo or {}).get("status") or "").upper()
    if status == "CONCLUIDA":
        raise RuntimeError("PIX pago")
    if status.startswith("REMOVIDA"):
        return det
    return _raise_resp(
        efi.pix_update_charge(
            params={"txid": tx},
            body={"status": "REMOVIDA_PELO_USUARIO_RECEBEDOR"},
        )
    )


def listar_infracoes_med(*, inicio: str, fim: str) -> dict:
    """GET /v2/gn/infracoes — MED/contestação Pix (escopo gn.infractions.read)."""
    resp = _raise_resp(
        _cliente().med_list(params={"inicio": str(inicio), "fim": str(fim)})
    )
    if isinstance(resp.get("infracoes"), list):
        return resp
    data = resp.get("data") if isinstance(resp.get("data"), dict) else {}
    if isinstance(data.get("infracoes"), list):
        return data
    return {"infracoes": [], "raw": resp}


def consultar_saldo_efi(*, com_bloqueios: bool = True) -> dict:
    """GET /v2/gn/saldo — escopo gn.balance.read. Com bloqueios=true traz MED/judicial."""
    params = {"bloqueios": "true"} if com_bloqueios else {}
    resp = _raise_resp(_cliente().get_account_balance(params=params))
    corpo = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    if not isinstance(corpo, dict):
        return {"saldo": "0.00", "bloqueios": {}}
    return corpo


def consultar_pix_recebido(e2e_id: str) -> dict:
    """GET /v2/pix/:e2eId — detalhe do Pix recebido (traz txid)."""
    e2e = (e2e_id or "").strip()
    if not e2e:
        raise RuntimeError("endToEndId ausente.")
    resp = _raise_resp(_cliente().pix_detail_received(params={"e2eId": e2e}))
    corpo = resp.get("data") if isinstance(resp.get("data"), dict) else resp
    return corpo if isinstance(corpo, dict) else {"raw": resp}
