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


def _headers_token(*, com_jwt: bool = True) -> dict[str, str]:
    client_id, client_secret = credenciais_bling()
    import base64

    basic = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()
    headers = {
        "Authorization": f"Basic {basic}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    }
    if com_jwt:
        headers["enable-jwt"] = "1"
    return headers


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
            "invalid_grant",
            "token expir",
            "token inv",
            "token revog",
            "already revoked",
            "já revog",
            "ja revog",
        )
    )


def _post_revoke(body: dict[str, str]) -> tuple[bool, str, bool]:
    """
    POST /oauth/revoke no Bling.

    Documentação oficial (developer.bling.com.br/aplicativos):
    - Basic auth (client_id:client_secret)
    - Body: token, token_type_hint (opcional)
    - Revogação avançada:
        revoke_action = logout | uninstall
        revoke_target = user | company
    - Para sumir de Minhas instalações: revoke_action=uninstall

    Retorna (sucesso_confirmado, detalhe, instalacao_removida).
    instalacao_removida=True quando a estratégia inclui uninstall e HTTP 2xx.
    """
    if not bling_configurado():
        return False, "bling_nao_configurado", False

    eh_uninstall = body.get("revoke_action") == "uninstall"
    ultimo = "sem_resposta"
    header_variants = (True, False)

    for com_jwt in header_variants:
        for url in _revoke_urls():
            try:
                r = requests.post(
                    url,
                    headers=_headers_token(com_jwt=com_jwt),
                    data=body,
                    timeout=BLING_OAUTH_TIMEOUT,
                )
            except requests.Timeout:
                ultimo = f"timeout:{url}:jwt={int(com_jwt)}"
                continue
            except requests.RequestException as exc:
                ultimo = f"rede:{url}:jwt={int(com_jwt)}:{exc}"
                continue

            texto = (r.text or "")[:240]
            tag = f"jwt={int(com_jwt)}"
            if r.status_code in (200, 204):
                _log.info("Bling revoke OK (%s) %s keys=%s", tag, url, list(body.keys()))
                return True, f"ok:{url}:{tag}", eh_uninstall

            if _token_ja_invalido_resposta(r.status_code, texto):
                _log.info("Bling revoke token já inválido (%s) %s", tag, url)
                return True, f"ja_invalido:{url}:{r.status_code}:{tag}", False

            ultimo = f"http_{r.status_code}:{url}:{tag}:{texto}"
            _log.warning("Bling revoke falhou: %s", ultimo)

    return False, ultimo, False


def revogar_tokens_bling(
    *,
    access_token: str | None = None,
    refresh_token: str | None = None,
) -> dict[str, Any]:
    """
    Revoga tokens e desinstala o app no Bling (Minhas instalações).

    Ordem: uninstall (company/user) → logout (company/user) → revoke simples.
    """
    resultado: dict[str, Any] = {
        "revogado_bling": False,
        "instalacao_removida": False,
        "detalhes": [],
    }
    if not bling_configurado():
        resultado["detalhes"].append("bling_nao_configurado")
        return resultado

    refresh = (refresh_token or "").strip()
    access = (access_token or "").strip()
    if not refresh and not access:
        resultado["detalhes"].append("sem_tokens_locais")
        return resultado

    def _marcar(ok: bool, det: str, instalacao: bool) -> None:
        resultado["detalhes"].append(det)
        if ok:
            resultado["revogado_bling"] = True
        if ok and instalacao:
            resultado["instalacao_removida"] = True

    estrategias: list[tuple[str, dict[str, str]]] = []
    for alvo in ("company", "user"):
        if refresh:
            estrategias.append(
                (
                    f"uninstall_{alvo}_refresh",
                    {
                        "token": refresh,
                        "token_type_hint": "refresh_token",
                        "revoke_action": "uninstall",
                        "revoke_target": alvo,
                    },
                )
            )
        if access:
            estrategias.append(
                (
                    f"uninstall_{alvo}_access",
                    {
                        "token": access,
                        "token_type_hint": "access_token",
                        "revoke_action": "uninstall",
                        "revoke_target": alvo,
                    },
                )
            )

    for alvo in ("company", "user"):
        if refresh:
            estrategias.append(
                (
                    f"logout_{alvo}_refresh",
                    {
                        "token": refresh,
                        "token_type_hint": "refresh_token",
                        "revoke_action": "logout",
                        "revoke_target": alvo,
                    },
                )
            )

    for label, tok in (("refresh_token", refresh), ("access_token", access)):
        if not tok:
            continue
        hint = "refresh_token" if label == "refresh_token" else "access_token"
        estrategias.append((label, {"token": tok, "token_type_hint": hint}))

    for nome, body in estrategias:
        if resultado["instalacao_removida"]:
            break
        ok, det, instalacao = _post_revoke(body)
        _marcar(ok, f"{nome}:{det}", instalacao)

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
