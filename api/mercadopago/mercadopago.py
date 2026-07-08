# api/mercadopago/mercadopago.py — cliente OAuth Mercado Pago e checkout de pedidos
from __future__ import annotations

# ── cliente ───────────────────────────────────────────

import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from core.tokens import criptografar_token, descriptografar_token
from global_utils import Var_ConectarBanco, agora_utc, is_modo_producao, obter_base_url

_log = logging.getLogger(__name__)

MP_AUTH_URL = "https://auth.mercadopago.com.br/authorization"
MP_TOKEN_URL = "https://api.mercadopago.com/oauth/token"
MP_API_BASE = "https://api.mercadopago.com"
MP_OAUTH_TIMEOUT = (5, 20)


def _env(key: str) -> str:
    return (os.getenv(key) or "").strip()


def _mp_env(sufixo: str) -> str:
    """Lê VAR_DEV ou VAR_PROD conforme MODO_PRODUCAO (padrão do .env DropNexo)."""
    if is_modo_producao():
        return _env(f"{sufixo}_PROD") or _env(f"{sufixo}_DEV")
    return _env(f"{sufixo}_DEV") or _env(f"{sufixo}_PROD")


def mp_client_id() -> str:
    """
    Client ID OAuth.
    Prioriza CLIENT_ID (credenciais de produção — usado no OAuth mesmo em homolog).
    """
    return (
        _env("CLIENT_ID")
        or _mp_env("CLIENT_ID")
        or _mp_env("APPLICATION_ID")
        or _env("MP_CLIENT_ID")
    )


def mp_client_secret() -> str:
    """
    Client Secret OAuth.
    Prioriza CLIENT_SECRET (credenciais de produção).
    """
    return (
        _env("CLIENT_SECRET")
        or _mp_env("CLIENT_SECRET")
        or _env("MP_CLIENT_SECRET")
        or _mp_env("ACCESS_TOKEN")
    )


def mp_public_key() -> str:
    return _mp_env("PUBLIC_KEY")


def mp_configurado() -> bool:
    return bool(mp_client_id() and mp_client_secret())


def credenciais_mp() -> tuple[str, str]:
    client_id = mp_client_id()
    client_secret = mp_client_secret()
    if not client_id or not client_secret:
        raise RuntimeError(
            "Credenciais Mercado Pago incompletas. Configure APPLICATION_ID_DEV e "
            "ACCESS_TOKEN_DEV (ou CLIENT_SECRET_DEV) no .env."
        )
    return client_id, client_secret


def redirect_uri_oauth() -> str:
    return f"{obter_base_url().rstrip('/')}/api/integracoes/mercadopago/oauth/callback"


def gerar_state_oauth() -> str:
    return secrets.token_urlsafe(24)


def url_autorizacao(state: str) -> str:
    client_id, _ = credenciais_mp()
    qs = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "platform_id": "mp",
            "state": state,
            "redirect_uri": redirect_uri_oauth(),
        }
    )
    return f"{MP_AUTH_URL}?{qs}"


def _post_token(body: dict[str, str]) -> dict[str, Any]:
    client_id, client_secret = credenciais_mp()
    payload = {"client_id": client_id, "client_secret": client_secret, **body}
    try:
        r = requests.post(MP_TOKEN_URL, data=payload, timeout=MP_OAUTH_TIMEOUT)
    except requests.Timeout as e:
        raise RuntimeError("Mercado Pago demorou para responder. Tente novamente.") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Falha de rede ao contactar Mercado Pago: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(f"Mercado Pago OAuth falhou ({r.status_code}): {r.text[:500]}")
    data = r.json()
    if not data.get("access_token"):
        raise RuntimeError("Mercado Pago não retornou access_token.")
    return data


def trocar_code_por_tokens(code: str) -> dict[str, Any]:
    return _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri_oauth(),
        }
    )


def renovar_access_token(refresh_token: str) -> dict[str, Any]:
    return _post_token({"grant_type": "refresh_token", "refresh_token": refresh_token})


def _expires_em(expires_in: int | None) -> datetime | None:
    if not expires_in:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))


def salvar_tokens(cur, id_tenant: int, tokens: dict[str, Any]) -> None:
    access = tokens.get("access_token") or ""
    refresh = tokens.get("refresh_token") or ""
    mp_user = tokens.get("user_id")
    expires = _expires_em(tokens.get("expires_in"))
    cur.execute(
        """
        INSERT INTO tbl_integracao_mercadopago (
            id_tenant, status, access_token_enc, refresh_token_enc,
            token_expires_em, mp_user_id, conectado_em, ultimo_erro, atualizado_em
        ) VALUES (%s, 'conectado', %s, %s, %s, %s, %s, NULL, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            status = 'conectado',
            access_token_enc = EXCLUDED.access_token_enc,
            refresh_token_enc = EXCLUDED.refresh_token_enc,
            token_expires_em = EXCLUDED.token_expires_em,
            mp_user_id = EXCLUDED.mp_user_id,
            conectado_em = COALESCE(tbl_integracao_mercadopago.conectado_em, EXCLUDED.conectado_em),
            ultimo_erro = NULL,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            criptografar_token(access),
            criptografar_token(refresh),
            expires,
            int(mp_user) if mp_user else None,
            agora_utc(),
            agora_utc(),
        ),
    )


def carregar_tokens_armazenados(cur, id_tenant: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT status, access_token_enc, refresh_token_enc, token_expires_em, mp_user_id
        FROM tbl_integracao_mercadopago WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {"status": "desconectado"}
    return {
        "status": row[0],
        "access_token": descriptografar_token(row[1]),
        "refresh_token": descriptografar_token(row[2]),
        "token_expires_em": row[3],
        "mp_user_id": row[4],
    }


def desconectar_mp(cur, id_tenant: int) -> None:
    cur.execute(
        """
        UPDATE tbl_integracao_mercadopago SET
            status = 'desconectado',
            access_token_enc = NULL,
            refresh_token_enc = NULL,
            token_expires_em = NULL,
            mp_user_id = NULL,
            mp_conta_info = '{}',
            ultimo_erro = NULL,
            atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (agora_utc(), id_tenant),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO tbl_integracao_mercadopago (id_tenant, status, atualizado_em)
            VALUES (%s, 'desconectado', %s)
            ON CONFLICT (id_tenant) DO NOTHING
            """,
            (id_tenant, agora_utc()),
        )


def mp_conectado(cur, id_tenant: int) -> bool:
    cur.execute(
        "SELECT status FROM tbl_integracao_mercadopago WHERE id_tenant = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    return bool(row and row[0] == "conectado")


def _token_expirado(expires_em) -> bool:
    if not expires_em:
        return False
    if expires_em.tzinfo is None:
        expires_em = expires_em.replace(tzinfo=timezone.utc)
    return expires_em <= datetime.now(timezone.utc) + timedelta(minutes=2)


def obter_access_token_valido(cur, id_tenant: int) -> str:
    dados = carregar_tokens_armazenados(cur, id_tenant)
    if dados.get("status") != "conectado":
        raise RuntimeError("Mercado Pago não conectado.")
    access = dados.get("access_token") or ""
    if access and not _token_expirado(dados.get("token_expires_em")):
        return access
    refresh = dados.get("refresh_token") or ""
    if not refresh:
        raise RuntimeError("Token Mercado Pago expirado. Reconecte a conta.")
    novos = renovar_access_token(refresh)
    salvar_tokens(cur, id_tenant, novos)
    return novos.get("access_token") or ""


def buscar_conta_mp(access_token: str) -> dict[str, Any]:
    try:
        r = requests.get(
            f"{MP_API_BASE}/users/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=MP_OAUTH_TIMEOUT,
        )
        if r.status_code >= 400:
            return {}
        return r.json() or {}
    except Exception as e:
        _log.warning("MP users/me falhou: %s", e)
        return {}


def atualizar_conta_info(cur, id_tenant: int, access_token: str) -> dict:
    info = buscar_conta_mp(access_token)
    if info:
        cur.execute(
            """
            UPDATE tbl_integracao_mercadopago
            SET mp_conta_info = %s::jsonb, atualizado_em = %s
            WHERE id_tenant = %s
            """,
            (json.dumps(info, ensure_ascii=False), agora_utc(), id_tenant),
        )
    return info


def carregar_config_mp(cur, id_tenant: int) -> dict:
    cur.execute(
        """
        SELECT status, mp_user_id, mp_conta_info, aceita_pix, aceita_cartao,
               conectado_em, ultimo_erro
        FROM tbl_integracao_mercadopago WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {
            "status": "desconectado",
            "aceita_pix": True,
            "aceita_cartao": True,
            "mp_user_id": None,
            "conta": {},
        }
    raw_conta = row[2]
    if isinstance(raw_conta, dict):
        conta = raw_conta
    elif isinstance(raw_conta, str) and raw_conta.strip():
        try:
            conta = json.loads(raw_conta)
        except json.JSONDecodeError:
            conta = {}
    else:
        conta = {}
    return {
        "status": row[0],
        "mp_user_id": row[1],
        "conta": conta,
        "aceita_pix": bool(row[3]),
        "aceita_cartao": bool(row[4]),
        "conectado_em": row[5].isoformat() if row[5] else None,
        "ultimo_erro": row[6],
    }


def salvar_config_mp(cur, id_tenant: int, aceita_pix: bool, aceita_cartao: bool) -> None:
    if not aceita_pix and not aceita_cartao:
        raise ValueError("Habilite ao menos PIX ou cartão.")
    cur.execute(
        """
        INSERT INTO tbl_integracao_mercadopago (id_tenant, aceita_pix, aceita_cartao, atualizado_em)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            aceita_pix = EXCLUDED.aceita_pix,
            aceita_cartao = EXCLUDED.aceita_cartao,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, aceita_pix, aceita_cartao, agora_utc()),
    )


def meios_pagamento_fornecedor(cur, id_fornecedor: int) -> dict:
    """Meios habilitados para checkout (Fase 2)."""
    cfg = carregar_config_mp(cur, id_fornecedor)
    conectado = cfg.get("status") == "conectado"
    return {
        "conectado": conectado,
        "pix": conectado and cfg.get("aceita_pix", True),
        "cartao": conectado and cfg.get("aceita_cartao", True),
    }


def _mp_request(
    method: str,
    path: str,
    access_token: str,
    *,
    json_body: dict | None = None,
    params: dict | None = None,
) -> dict[str, Any]:
    url = f"{MP_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        r = requests.request(
            method,
            url,
            headers=headers,
            json=json_body,
            params=params,
            timeout=MP_OAUTH_TIMEOUT,
        )
    except requests.Timeout as e:
        raise RuntimeError("Mercado Pago demorou para responder. Tente novamente.") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Falha de rede ao contactar Mercado Pago: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(f"Mercado Pago ({r.status_code}): {r.text[:500]}")
    return r.json() if r.text else {}


def criar_pagamento_pix(access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _mp_request("POST", "/v1/payments", access_token, json_body=payload)


def criar_preference_checkout(access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    return _mp_request("POST", "/checkout/preferences", access_token, json_body=payload)


def obter_pagamento_mp(access_token: str, payment_id: int | str) -> dict[str, Any]:
    return _mp_request("GET", f"/v1/payments/{payment_id}", access_token)


# ── pedido ────────────────────────────────────────────

import logging
import os
import re
from datetime import datetime, timezone
from typing import Any

from global_utils import agora_utc, obter_base_url
from core.pedidos.servico import (
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
