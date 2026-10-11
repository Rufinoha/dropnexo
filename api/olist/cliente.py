# api/olist/cliente.py — OAuth 2 e cliente HTTP da API v3 do Olist ERP
from __future__ import annotations

import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from core.tokens import criptografar_token, descriptografar_token
from global_utils import Var_ConectarBanco, agora_utc, obter_base_url

_log = logging.getLogger(__name__)

OLIST_AUTH = "https://accounts.tiny.com.br/realms/tiny/protocol/openid-connect"
OLIST_API = "https://api.tiny.com.br/public-api/v3"
_TIMEOUT = (8, 40)
_MARGEM = timedelta(minutes=5)


def _env(key: str) -> str:
    return (os.getenv(key) or "").strip()


def olist_configurado() -> bool:
    return bool(_env("OLIST_CLIENT_ID") and _env("OLIST_CLIENT_SECRET"))


def credenciais() -> tuple[str, str]:
    cid, sec = _env("OLIST_CLIENT_ID"), _env("OLIST_CLIENT_SECRET")
    if not cid or not sec:
        raise RuntimeError("OLIST_CLIENT_ID e OLIST_CLIENT_SECRET não estão no .env.")
    return cid, sec


def redirect_uri_oauth() -> str:
    return f"{obter_base_url().rstrip('/')}/api/integracoes/olist/oauth/callback"


def gerar_state_oauth() -> str:
    return secrets.token_urlsafe(24)


def url_autorizacao(state: str) -> str:
    client_id, _ = credenciais()
    qs = urlencode(
        {
            "client_id": client_id,
            "redirect_uri": redirect_uri_oauth(),
            "scope": "openid",
            "response_type": "code",
            "state": state,
        }
    )
    return f"{OLIST_AUTH}/auth?{qs}"


def _token_request(data: dict[str, str]) -> dict[str, Any]:
    client_id, client_secret = credenciais()
    body = {"client_id": client_id, "client_secret": client_secret, **data}
    r = requests.post(
        f"{OLIST_AUTH}/token",
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        timeout=_TIMEOUT,
    )
    if r.status_code >= 400:
        _log.warning("Olist recusou o token (%s).", r.status_code)
        raise RuntimeError(f"Olist recusou a autorização ({r.status_code}).")
    payload = r.json()
    if not isinstance(payload, dict) or not (payload.get("access_token") or "").strip():
        raise RuntimeError("Olist não devolveu access token.")
    return payload


def trocar_code_por_tokens(code: str) -> dict[str, Any]:
    return _token_request(
        {
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri_oauth(),
            "code": code,
        }
    )


def renovar_access_token(refresh: str) -> dict[str, Any]:
    return _token_request({"grant_type": "refresh_token", "refresh_token": refresh})


def garantir_tabelas(cur) -> None:
    cur.execute("SELECT to_regclass('public.tbl_integracao_olist')")
    if not cur.fetchone()[0]:
        cur.execute(
            """
            CREATE TABLE tbl_integracao_olist (
                id_tenant INTEGER PRIMARY KEY,
                status VARCHAR(20) NOT NULL DEFAULT 'desconectado',
                access_token_enc TEXT,
                refresh_token_enc TEXT,
                token_expires_em TIMESTAMPTZ,
                conta_nome VARCHAR(180),
                conectado_em TIMESTAMPTZ,
                ultimo_erro TEXT,
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
    cur.execute("SELECT to_regclass('public.tbl_integracao_olist_mapa')")
    if not cur.fetchone()[0]:
        cur.execute(
            """
            CREATE TABLE tbl_integracao_olist_mapa (
                id SERIAL PRIMARY KEY,
                id_tenant INTEGER NOT NULL,
                id_olist VARCHAR(40) NOT NULL,
                id_produto INTEGER,
                sku VARCHAR(80),
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (id_tenant, id_olist)
            )
            """
        )


def salvar_tokens(cur, id_tenant: int, payload: dict[str, Any], conta_nome: str = "") -> None:
    expires_in = int(payload.get("expires_in") or 14400)
    expires_em = datetime.now(timezone.utc) + timedelta(seconds=max(120, expires_in - 300))
    refresh = (payload.get("refresh_token") or "").strip()
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_integracao_olist (
            id_tenant, status, access_token_enc, refresh_token_enc,
            token_expires_em, conta_nome, conectado_em, ultimo_erro, atualizado_em
        ) VALUES (%s, 'conectado', %s, %s, %s, NULLIF(%s, ''), %s, NULL, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            status = 'conectado',
            access_token_enc = EXCLUDED.access_token_enc,
            refresh_token_enc = COALESCE(NULLIF(EXCLUDED.refresh_token_enc, ''), tbl_integracao_olist.refresh_token_enc),
            token_expires_em = EXCLUDED.token_expires_em,
            conta_nome = COALESCE(NULLIF(EXCLUDED.conta_nome, ''), tbl_integracao_olist.conta_nome),
            conectado_em = COALESCE(tbl_integracao_olist.conectado_em, EXCLUDED.conectado_em),
            ultimo_erro = NULL,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            int(id_tenant),
            criptografar_token(payload.get("access_token") or ""),
            criptografar_token(refresh) if refresh else "",
            expires_em,
            (conta_nome or "")[:180],
            agora,
            agora,
        ),
    )


def olist_conectado(cur, id_tenant: int) -> bool:
    garantir_tabelas(cur)
    cur.execute(
        "SELECT status FROM tbl_integracao_olist WHERE id_tenant = %s",
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return bool(row and row[0] == "conectado")


def _carregar(cur, id_tenant: int) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT access_token_enc, refresh_token_enc, token_expires_em, status, conta_nome
        FROM tbl_integracao_olist WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    if not row or row[3] != "conectado":
        return None
    expires = row[2]
    if isinstance(expires, datetime) and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return {
        "access_token": descriptografar_token(row[0]),
        "refresh_token": descriptografar_token(row[1]),
        "expires_em": expires,
        "conta_nome": row[4] or "",
    }


def obter_access_token_valido(id_tenant: int) -> str:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabelas(cur)
        dados = _carregar(cur, id_tenant)
        if not dados or not (dados.get("access_token") or "").strip():
            raise RuntimeError("Conta Olist não conectada para este tenant.")
        expires = dados.get("expires_em")
        if isinstance(expires, datetime) and expires > datetime.now(timezone.utc) + _MARGEM:
            return dados["access_token"]
        refresh = (dados.get("refresh_token") or "").strip()
        if not refresh:
            raise RuntimeError("Não há refresh token do Olist. Conecte de novo.")
        novo = renovar_access_token(refresh)
        salvar_tokens(cur, id_tenant, novo, dados.get("conta_nome") or "")
        conn.commit()
        return (novo.get("access_token") or "").strip()
    finally:
        conn.close()


def api_request(id_tenant: int, method: str, path: str, *, params: dict | None = None) -> Any:
    token = obter_access_token_valido(id_tenant)
    url = f"{OLIST_API}{path}"
    time.sleep(0.4)
    r = requests.request(
        method,
        url,
        params=params or None,
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=_TIMEOUT,
    )
    if r.status_code == 204:
        return None
    if r.status_code >= 400:
        _log.warning("Olist %s %s respondeu %s.", method, path, r.status_code)
        raise RuntimeError(f"Olist {method} {path} respondeu {r.status_code}.")
    if not r.content:
        return None
    return r.json()


def consultar_conta(id_tenant: int) -> str:
    try:
        dados = api_request(id_tenant, "GET", "/info")
    except Exception as e:
        _log.info("Olist /info indisponível: %s", e)
        return ""
    if not isinstance(dados, dict):
        return ""
    return str(dados.get("fantasia") or dados.get("razaoSocial") or "").strip()[:180]


def desconectar(cur, id_tenant: int) -> None:
    garantir_tabelas(cur)
    cur.execute(
        """
        UPDATE tbl_integracao_olist
        SET status = 'desconectado',
            access_token_enc = NULL,
            refresh_token_enc = NULL,
            token_expires_em = NULL,
            ultimo_erro = NULL,
            atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (agora_utc(), int(id_tenant)),
    )
