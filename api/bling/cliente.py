# api/bling/cliente.py — OAuth 2.0 e cliente HTTP Bling API v3
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from api.bling.tokens import criptografar_token, descriptografar_token
from global_utils import Var_ConectarBanco, agora_utc, obter_base_url

_log = logging.getLogger(__name__)

BLING_AUTH_BASE = "https://www.bling.com.br/Api/v3"
BLING_API_BASE = "https://api.bling.com.br/Api/v3"
# OAuth deve terminar antes do timeout do Gunicorn (default 30s).
BLING_OAUTH_TIMEOUT = (5, 15)

# Endpoints documentados para POST /oauth/revoke (tentamos em ordem).
BLING_REVOKE_URLS = (
    f"{BLING_AUTH_BASE}/oauth/revoke",
    "https://api.bling.com.br/Api/v3/oauth/revoke",
    "https://api.bling.com.br/oauth/revoke",
)


def _env(key: str) -> str:
    return (os.getenv(key) or "").strip()


def bling_configurado() -> bool:
    return bool(_env("BLING_CLIENT_ID") and _env("BLING_CLIENT_SECRET"))


def credenciais_bling() -> tuple[str, str]:
    client_id = _env("BLING_CLIENT_ID")
    client_secret = _env("BLING_CLIENT_SECRET")
    if not client_id or not client_secret:
        raise RuntimeError(
            "Credenciais Bling incompletas. Configure BLING_CLIENT_ID e BLING_CLIENT_SECRET no .env."
        )
    return client_id, client_secret


def redirect_uri_oauth() -> str:
    return f"{obter_base_url().rstrip('/')}/api/integracoes/bling/oauth/callback"


def gerar_state_oauth() -> str:
    return secrets.token_urlsafe(24)


def url_autorizacao(state: str) -> str:
    client_id, _ = credenciais_bling()
    qs = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "state": state,
        }
    )
    return f"{BLING_AUTH_BASE}/oauth/authorize?{qs}"


def _headers_token() -> dict[str, str]:
    client_id, client_secret = credenciais_bling()
    import base64

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    return {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "enable-jwt": "1",
    }


def _post_token(body: dict[str, str]) -> dict[str, Any]:
    try:
        r = requests.post(
            f"{BLING_AUTH_BASE}/oauth/token",
            headers=_headers_token(),
            data=body,
            timeout=BLING_OAUTH_TIMEOUT,
        )
    except requests.Timeout as e:
        raise RuntimeError(
            "Bling demorou para responder na troca do código OAuth. Tente conectar novamente."
        ) from e
    except requests.RequestException as e:
        raise RuntimeError(f"Falha de rede ao contactar o Bling: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(f"Bling OAuth falhou ({r.status_code}): {r.text[:500]}")
    data = r.json()
    if not data.get("access_token"):
        raise RuntimeError("Bling OAuth não retornou access_token.")
    return data


def trocar_code_por_tokens(code: str) -> dict[str, Any]:
    return _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
        }
    )


def renovar_access_token(refresh_token: str) -> dict[str, Any]:
    return _post_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    )


def _revoke_urls() -> tuple[str, ...]:
    custom = _env("BLING_OAUTH_REVOKE_URL")
    if custom:
        return (custom.rstrip("/"),) + tuple(u for u in BLING_REVOKE_URLS if u != custom.rstrip("/"))
    return BLING_REVOKE_URLS


def _token_ja_invalido_resposta(status: int, texto: str) -> bool:
    if status not in (400, 401):
        return False
    t = (texto or "").lower()
    return any(
        x in t
        for x in (
            "invalid",
            "expir",
            "revog",
            "invalid_grant",
            "token inv",
            "não encontrado",
            "nao encontrado",
        )
    )


def _post_revoke(body: dict[str, str]) -> tuple[bool, str]:
    """
    POST /oauth/revoke no Bling.

    Requisitos (documentação developer.bling.com.br):
    - Authorization: Basic base64(client_id:client_secret)
    - Content-Type: application/x-www-form-urlencoded
    - Header enable-jwt: 1 (tokens JWT)
    - Body: token=<access ou refresh>
    - Para desinstalar do ponto de vista do usuário (Minhas instalações):
      token=<refresh_token>, revoke_action=logout, revoke_target=user
    """
    if not bling_configurado():
        return False, "bling_nao_configurado"

    ultimo = "sem_resposta"
    for url in _revoke_urls():
        try:
            r = requests.post(
                url,
                headers=_headers_token(),
                data=body,
                timeout=BLING_OAUTH_TIMEOUT,
            )
        except requests.Timeout:
            ultimo = f"timeout:{url}"
            continue
        except requests.RequestException as exc:
            ultimo = f"rede:{url}:{exc}"
            continue

        texto = (r.text or "")[:200]
        if r.status_code in (200, 204):
            _log.info("Bling revoke OK em %s body_keys=%s", url, list(body.keys()))
            return True, f"ok:{url}"

        if _token_ja_invalido_resposta(r.status_code, texto):
            _log.info("Bling revoke token já inválido em %s (%s)", url, r.status_code)
            return True, f"ja_invalido:{url}:{r.status_code}"

        ultimo = f"http_{r.status_code}:{url}:{texto}"
        _log.warning("Bling revoke falhou: %s", ultimo)

    return False, ultimo


def revogar_tokens_bling(
    *,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> dict[str, Any]:
    """
    Revoga tokens no Bling para remover a instalação em Minhas instalações.

    Estratégia:
    1. refresh_token + revoke_action=logout + revoke_target=user (revoga o usuário no app)
    2. Revogação simples do refresh_token e access_token (fallback)
    """
    resultado: dict[str, Any] = {"revogado_bling": False, "detalhes": []}
    if not bling_configurado():
        resultado["detalhes"].append("bling_nao_configurado")
        return resultado

    refresh = (refresh_token or "").strip()
    access = (access_token or "").strip()
    if not refresh and not access:
        resultado["detalhes"].append("sem_tokens_locais")
        return resultado

    def _marcar(ok: bool, det: str) -> None:
        resultado["detalhes"].append(det)
        if ok:
            resultado["revogado_bling"] = True

    # Passo crítico: remove "Autenticado" em Minhas instalações no Bling
    if refresh:
        ok, det = _post_revoke(
            {
                "token": refresh,
                "revoke_action": "logout",
                "revoke_target": "user",
            }
        )
        _marcar(ok, f"logout_user_refresh:{det}")

    if access and not resultado["revogado_bling"]:
        ok, det = _post_revoke(
            {
                "token": access,
                "revoke_action": "logout",
                "revoke_target": "user",
            }
        )
        _marcar(ok, f"logout_user_access:{det}")

    for label, tok in (("refresh_token", refresh), ("access_token", access)):
        if not tok:
            continue
        ok, det = _post_revoke({"token": tok})
        _marcar(ok, f"{label}:{det}")

    return resultado


def carregar_tokens_armazenados(cur, id_tenant: int) -> dict[str, str]:
    """Lê tokens criptografados do tenant (independente de status conectado)."""
    cur.execute(
        """
        SELECT access_token_enc, refresh_token_enc
        FROM tbl_integracao_bling WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {"access_token": "", "refresh_token": ""}
    return {
        "access_token": descriptografar_token(row[0]),
        "refresh_token": descriptografar_token(row[1]),
    }


def _salvar_tokens(cur, id_tenant: int, payload: dict[str, Any]) -> None:
    expires_in = int(payload.get("expires_in") or 3600)
    expires_em = datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 60))
    cur.execute(
        """
        INSERT INTO tbl_integracao_bling (
            id_tenant, status, access_token_enc, refresh_token_enc,
            token_expires_em, conectado_em, ultimo_erro, atualizado_em
        ) VALUES (%s, 'conectado', %s, %s, %s, %s, NULL, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            status = 'conectado',
            access_token_enc = EXCLUDED.access_token_enc,
            refresh_token_enc = EXCLUDED.refresh_token_enc,
            token_expires_em = EXCLUDED.token_expires_em,
            conectado_em = COALESCE(tbl_integracao_bling.conectado_em, EXCLUDED.conectado_em),
            ultimo_erro = NULL,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            criptografar_token(payload.get("access_token") or ""),
            criptografar_token(payload.get("refresh_token") or ""),
            expires_em,
            agora_utc(),
            agora_utc(),
        ),
    )


def _carregar_tokens(cur, id_tenant: int) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT access_token_enc, refresh_token_enc, token_expires_em, status
        FROM tbl_integracao_bling WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row or row[3] != "conectado":
        return None
    return {
        "access_token": descriptografar_token(row[0]),
        "refresh_token": descriptografar_token(row[1]),
        "expires_em": row[2],
    }


def obter_access_token_valido(id_tenant: int) -> str:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        dados = _carregar_tokens(cur, id_tenant)
        if not dados or not dados["access_token"]:
            raise RuntimeError("Conta Bling não conectada para este tenant.")

        expires = dados["expires_em"]
        agora = datetime.now(timezone.utc)
        if expires and expires > agora:
            return dados["access_token"]

        refresh = dados["refresh_token"]
        if not refresh:
            raise RuntimeError("Refresh token Bling ausente. Reconecte a integração.")

        novo = renovar_access_token(refresh)
        _salvar_tokens(cur, id_tenant, novo)
        conn.commit()
        return novo["access_token"]
    finally:
        conn.close()


def api_request(
    id_tenant: int,
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
) -> dict[str, Any]:
    token = obter_access_token_valido(id_tenant)
    url = f"{BLING_API_BASE}{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
    }
    r = requests.request(
        method.upper(),
        url,
        headers=headers,
        params=params,
        json=json_body,
        timeout=45,
    )
    if r.status_code == 204:
        return {}
    try:
        body = r.json()
    except Exception:
        body = {"raw": r.text[:1000]}
    if r.status_code >= 400:
        msg = body.get("error", {}).get("message") if isinstance(body.get("error"), dict) else None
        raise RuntimeError(msg or f"Bling API {r.status_code}: {r.text[:500]}")
    return body


def listar_produtos(
    id_tenant: int,
    *,
    pagina: int = 1,
    limite: int = 100,
    id_categoria: str | None = None,
) -> list[dict]:
    params: dict[str, Any] = {"pagina": pagina, "limite": limite, "criterio": 1}
    if id_categoria:
        params["idCategoria"] = id_categoria
    resp = api_request(
        id_tenant,
        "GET",
        "/produtos",
        params=params,
    )
    data = resp.get("data") or []
    return data if isinstance(data, list) else []


def listar_categorias_produtos(id_tenant: int, *, pagina: int = 1, limite: int = 100) -> list[dict]:
    resp = api_request(
        id_tenant,
        "GET",
        "/categorias/produtos",
        params={"pagina": pagina, "limite": limite},
    )
    data = resp.get("data") or []
    return data if isinstance(data, list) else []


def obter_categoria_produto(id_tenant: int, id_bling: int | str) -> dict:
    resp = api_request(id_tenant, "GET", f"/categorias/produtos/{id_bling}")
    data = resp.get("data") or {}
    return data if isinstance(data, dict) else {}


def obter_produto(id_tenant: int, id_bling: int | str) -> dict:
    resp = api_request(id_tenant, "GET", f"/produtos/{id_bling}")
    data = resp.get("data") or {}
    return data if isinstance(data, dict) else {}


def obter_variacoes_produto(id_tenant: int, id_pai: int | str) -> dict:
    """Retorna produto pai com lista de variações (Bling API v3)."""
    resp = api_request(id_tenant, "GET", f"/produtos/variacoes/{id_pai}")
    data = resp.get("data") or {}
    return data if isinstance(data, dict) else {}


def listar_depositos_bling(id_tenant: int, *, pagina: int = 1, limite: int = 100) -> list[dict]:
    resp = api_request(
        id_tenant,
        "GET",
        "/depositos",
        params={"pagina": pagina, "limite": limite},
    )
    data = resp.get("data") or []
    return data if isinstance(data, list) else []


def obter_saldos_estoque(id_tenant: int, id_bling_produto: str | int) -> dict:
    resp = api_request(
        id_tenant,
        "GET",
        "/estoques/saldos",
        params={"idsProdutos[]": str(id_bling_produto)},
    )
    data = resp.get("data") or []
    if isinstance(data, list) and data:
        item = data[0] if isinstance(data[0], dict) else {}
        return item
    if isinstance(data, dict):
        return data
    return {}
