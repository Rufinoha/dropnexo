# api/mercadopago/cliente.py — OAuth e cliente HTTP Mercado Pago
from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from api.bling.tokens import criptografar_token, descriptografar_token
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
    conta = row[2] if isinstance(row[2], dict) else {}
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
