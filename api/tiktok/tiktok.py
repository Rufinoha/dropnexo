# api/tiktok/tiktok.py — OAuth, API e sync TikTok Shop
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import urlencode

import requests

from core.tokens import criptografar_token, descriptografar_token
from global_utils import agora_utc, is_modo_producao, obter_base_url, obter_url_site_publico, url_imagem_produto

_log = logging.getLogger(__name__)

TIKTOK_AUTH_BASE_DEFAULT = "https://auth.tiktok-shops.com"
TIKTOK_API_BASE_DEFAULT = "https://open-api.tiktokglobalshop.com"
TIKTOK_OAUTH_AUTHORIZE = "/oauth/authorize"
TIKTOK_TOKEN_GET = "/api/v2/token/get"
TIKTOK_TOKEN_REFRESH = "/api/v2/token/refresh"
TIKTOK_API_VERSION = "202309"
TIKTOK_OAUTH_TIMEOUT = (5, 25)
TIKTOK_API_TIMEOUT = (10, 60)

_TABELA_OK: bool | None = None
_TIKTOK_MAX_CRIAR_POR_SYNC = 20


def _env(key: str) -> str:
    return (os.getenv(key) or "").strip()


def _tiktok_env(sufixo: str) -> str:
    if is_modo_producao():
        return _env(f"TIKTOK_{sufixo}_PROD") or _env(f"TIKTOK_{sufixo}_DEV")
    return _env(f"TIKTOK_{sufixo}_DEV") or _env(f"TIKTOK_{sufixo}_PROD")


def tiktok_app_key() -> str:
    return _tiktok_env("APP_KEY") or _env("TIKTOK_APP_KEY")


def tiktok_app_secret() -> str:
    return _tiktok_env("APP_SECRET") or _env("TIKTOK_APP_SECRET")


def tiktok_auth_base() -> str:
    return (_env("TIKTOK_AUTH_BASE") or TIKTOK_AUTH_BASE_DEFAULT).rstrip("/")


def tiktok_api_base() -> str:
    return (_env("TIKTOK_API_BASE") or TIKTOK_API_BASE_DEFAULT).rstrip("/")


def tiktok_configurado() -> bool:
    return bool(tiktok_app_key() and tiktok_app_secret())


def credenciais_tiktok() -> tuple[str, str]:
    app_key = tiktok_app_key()
    app_secret = tiktok_app_secret()
    if not app_key or not app_secret:
        raise RuntimeError(
            "Credenciais TikTok Shop incompletas. Configure TIKTOK_APP_KEY e "
            "TIKTOK_APP_SECRET no .env do servidor."
        )
    return app_key, app_secret


def redirect_uri_oauth() -> str:
    return f"{obter_base_url().rstrip('/')}/api/integracoes/tiktok/oauth/callback"


def webhook_url() -> str:
    return f"{obter_url_site_publico().rstrip('/')}/api/integracoes/tiktok/webhook"


def gerar_state_oauth() -> str:
    return secrets.token_urlsafe(24)


def url_autorizacao(state: str) -> str:
    app_key, _ = credenciais_tiktok()
    qs = urlencode(
        {
            "app_key": app_key,
            "state": state,
            "redirect_uri": redirect_uri_oauth(),
        }
    )
    return f"{tiktok_auth_base()}{TIKTOK_OAUTH_AUTHORIZE}?{qs}"


def _calcular_sign(
    app_secret: str,
    path: str,
    params: dict[str, Any],
    *,
    body: str = "",
    method: str = "GET",
) -> str:
    filtrados = {
        str(k): str(v)
        for k, v in (params or {}).items()
        if k not in ("sign", "access_token") and v is not None and str(v) != ""
    }
    partes = "".join(f"{k}{filtrados[k]}" for k in sorted(filtrados.keys()))
    texto = f"{app_secret}{path}{partes}"
    if method.upper() != "GET" and body:
        texto += body
    texto += app_secret
    return hmac.new(app_secret.encode("utf-8"), texto.encode("utf-8"), hashlib.sha256).hexdigest()


def _formatar_erro_tiktok(status: int, text: str) -> str:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            msg = (data.get("message") or data.get("msg") or "").strip()
            code = data.get("code")
            if msg:
                return f"TikTok Shop ({status}, código {code}): {msg[:280]}"
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return f"TikTok Shop API ({status}): {(text or '')[:280]}"


def _extrair_data(resposta: Any) -> Any:
    if isinstance(resposta, dict):
        if "data" in resposta:
            return resposta.get("data")
        return resposta
    return resposta


def _get_token(params: dict[str, str]) -> dict[str, Any]:
    app_key, app_secret = credenciais_tiktok()
    path = TIKTOK_TOKEN_GET
    qs = {
        "app_key": app_key,
        "app_secret": app_secret,
        **params,
    }
    sign = _calcular_sign(app_secret, path, qs, method="GET")
    qs["sign"] = sign
    url = f"{tiktok_auth_base()}{path}"
    try:
        r = requests.get(url, params=qs, timeout=TIKTOK_OAUTH_TIMEOUT)
    except requests.Timeout as e:
        raise RuntimeError("TikTok Shop demorou para responder. Tente novamente.") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Falha de rede ao contactar TikTok Shop: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(_formatar_erro_tiktok(r.status_code, r.text))
    data = r.json() if r.content else {}
    token_data = _extrair_data(data)
    if not isinstance(token_data, dict):
        token_data = data if isinstance(data, dict) else {}
    access = token_data.get("access_token") or data.get("access_token")
    if not access:
        raise RuntimeError("TikTok Shop não retornou access_token.")
    out = dict(token_data)
    out["access_token"] = access
    if token_data.get("refresh_token"):
        out["refresh_token"] = token_data.get("refresh_token")
    exp = token_data.get("access_token_expire_in") or token_data.get("expires_in")
    if exp:
        out["expires_in"] = int(exp) - int(time.time()) if int(exp) > 10_000_000_000 else int(exp)
    return out


def trocar_code_por_tokens(code: str) -> dict[str, Any]:
    return _get_token({"auth_code": code, "grant_type": "authorized_code"})


def renovar_access_token(refresh_token: str) -> dict[str, Any]:
    app_key, app_secret = credenciais_tiktok()
    path = TIKTOK_TOKEN_REFRESH
    qs = {
        "app_key": app_key,
        "app_secret": app_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    sign = _calcular_sign(app_secret, path, qs, method="GET")
    qs["sign"] = sign
    url = f"{tiktok_auth_base()}{path}"
    try:
        r = requests.get(url, params=qs, timeout=TIKTOK_OAUTH_TIMEOUT)
    except requests.RequestException as e:
        raise RuntimeError(f"Falha ao renovar token TikTok Shop: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(_formatar_erro_tiktok(r.status_code, r.text))
    data = r.json() if r.content else {}
    token_data = _extrair_data(data)
    if not isinstance(token_data, dict):
        token_data = data if isinstance(data, dict) else {}
    access = token_data.get("access_token") or data.get("access_token")
    if not access:
        raise RuntimeError("TikTok Shop não retornou access_token na renovação.")
    out = dict(token_data)
    out["access_token"] = access
    if token_data.get("refresh_token"):
        out["refresh_token"] = token_data.get("refresh_token")
    exp = token_data.get("access_token_expire_in") or token_data.get("expires_in")
    if exp:
        out["expires_in"] = int(exp) - int(time.time()) if int(exp) > 10_000_000_000 else int(exp)
    return out


def _expires_em(expires_in: int | None) -> datetime | None:
    if not expires_in:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))


def _tem_tabela_tiktok(cur) -> bool:
    global _TABELA_OK
    if _TABELA_OK is True:
        return True
    cur.execute("SELECT to_regclass(%s)", ("tbl_integracao_tiktok",))
    row = cur.fetchone()
    ok = bool(row and row[0])
    if ok:
        _TABELA_OK = True
    return ok


def salvar_tokens(cur, id_tenant: int, tokens: dict[str, Any]) -> None:
    if not _tem_tabela_tiktok(cur):
        raise RuntimeError("Tabela tbl_integracao_tiktok não existe. Aplique o SQL 078.")
    access = tokens.get("access_token") or ""
    refresh = tokens.get("refresh_token") or ""
    expires = _expires_em(tokens.get("expires_in"))
    cur.execute(
        """
        INSERT INTO tbl_integracao_tiktok (
            id_tenant, status, access_token_enc, refresh_token_enc,
            token_expires_em, conectado_em, ultimo_erro, atualizado_em
        ) VALUES (%s, 'conectado', %s, %s, %s, %s, NULL, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            status = 'conectado',
            access_token_enc = EXCLUDED.access_token_enc,
            refresh_token_enc = EXCLUDED.refresh_token_enc,
            token_expires_em = EXCLUDED.token_expires_em,
            conectado_em = COALESCE(tbl_integracao_tiktok.conectado_em, EXCLUDED.conectado_em),
            ultimo_erro = NULL,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            criptografar_token(access),
            criptografar_token(refresh),
            expires,
            agora_utc(),
            agora_utc(),
        ),
    )


def carregar_tokens_armazenados(cur, id_tenant: int) -> dict[str, Any]:
    if not _tem_tabela_tiktok(cur):
        return {"status": "desconectado"}
    cur.execute(
        """
        SELECT status, access_token_enc, refresh_token_enc, token_expires_em,
               shop_id, shop_cipher
        FROM tbl_integracao_tiktok WHERE id_tenant = %s
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
        "shop_id": row[4],
        "shop_cipher": row[5],
    }


def desconectar_tiktok(cur, id_tenant: int) -> None:
    if not _tem_tabela_tiktok(cur):
        return
    cur.execute(
        """
        UPDATE tbl_integracao_tiktok SET
            status = 'desconectado',
            access_token_enc = NULL,
            refresh_token_enc = NULL,
            token_expires_em = NULL,
            shop_id = NULL,
            shop_cipher = NULL,
            shop_info = '{}',
            ultimo_erro = NULL,
            atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (agora_utc(), id_tenant),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO tbl_integracao_tiktok (id_tenant, status, atualizado_em)
            VALUES (%s, 'desconectado', %s)
            ON CONFLICT (id_tenant) DO NOTHING
            """,
            (id_tenant, agora_utc()),
        )


def tiktok_conectado(cur, id_tenant: int) -> bool:
    if not _tem_tabela_tiktok(cur):
        return False
    cur.execute(
        "SELECT status FROM tbl_integracao_tiktok WHERE id_tenant = %s",
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
        raise RuntimeError("TikTok Shop não conectado.")
    access = dados.get("access_token") or ""
    if access and not _token_expirado(dados.get("token_expires_em")):
        return access
    refresh = dados.get("refresh_token") or ""
    if not refresh:
        raise RuntimeError("Token TikTok Shop expirado. Reconecte a conta.")
    novos = renovar_access_token(refresh)
    salvar_tokens(cur, id_tenant, novos)
    return novos.get("access_token") or ""


def _shop_cipher(cur, id_tenant: int) -> str:
    cur.execute(
        "SELECT shop_cipher FROM tbl_integracao_tiktok WHERE id_tenant = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    return (row[0] or "").strip() if row else ""


def api_request(
    cur,
    id_tenant: int,
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
) -> Any:
    app_key, app_secret = credenciais_tiktok()
    token = obter_access_token_valido(cur, id_tenant)
    api_path = path if path.startswith("/") else f"/{path}"
    url = api_path if api_path.startswith("http") else f"{tiktok_api_base()}{api_path}"

    query: dict[str, Any] = dict(params or {})
    query.setdefault("app_key", app_key)
    query.setdefault("timestamp", str(int(time.time())))
    query.setdefault("version", TIKTOK_API_VERSION)
    shop_cipher = _shop_cipher(cur, id_tenant)
    if shop_cipher and "shop_cipher" not in query:
        query["shop_cipher"] = shop_cipher

    body_str = ""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if json_body is not None:
        body_str = json.dumps(json_body, ensure_ascii=False, separators=(",", ":"))

    query["access_token"] = token
    sign_path = api_path.split("?")[0]
    query["sign"] = _calcular_sign(
        app_secret,
        sign_path,
        query,
        body=body_str,
        method=method,
    )

    try:
        r = requests.request(
            method.upper(),
            url,
            headers=headers,
            params=query,
            data=body_str if body_str else None,
            timeout=TIKTOK_API_TIMEOUT,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Falha na API TikTok Shop: {e}") from e

    if r.status_code >= 400:
        raise RuntimeError(_formatar_erro_tiktok(r.status_code, r.text))

    if not r.content:
        return {}

    data = r.json()
    if isinstance(data, dict):
        code = data.get("code")
        if code not in (0, "0", None):
            raise RuntimeError(
                _formatar_erro_tiktok(r.status_code, json.dumps(data, ensure_ascii=False))
            )
    return _extrair_data(data)


def api_request_bytes(
    cur,
    id_tenant: int,
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
) -> bytes:
    app_key, app_secret = credenciais_tiktok()
    token = obter_access_token_valido(cur, id_tenant)
    api_path = path if path.startswith("/") else f"/{path}"
    url = api_path if api_path.startswith("http") else f"{tiktok_api_base()}{api_path}"

    query: dict[str, Any] = dict(params or {})
    query.setdefault("app_key", app_key)
    query.setdefault("timestamp", str(int(time.time())))
    query.setdefault("version", TIKTOK_API_VERSION)
    shop_cipher = _shop_cipher(cur, id_tenant)
    if shop_cipher and "shop_cipher" not in query:
        query["shop_cipher"] = shop_cipher

    body_str = ""
    headers = {"Content-Type": "application/json", "Accept": "*/*"}
    if json_body is not None:
        body_str = json.dumps(json_body, ensure_ascii=False, separators=(",", ":"))

    query["access_token"] = token
    sign_path = api_path.split("?")[0]
    query["sign"] = _calcular_sign(app_secret, sign_path, query, body=body_str, method=method)

    try:
        r = requests.request(
            method.upper(),
            url,
            headers=headers,
            params=query,
            data=body_str if body_str else None,
            timeout=TIKTOK_API_TIMEOUT,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Falha na API TikTok Shop: {e}") from e

    if r.status_code >= 400:
        raise RuntimeError(_formatar_erro_tiktok(r.status_code, r.text))

    if isinstance(r.content, bytes):
        try:
            data = r.json()
            if isinstance(data, dict) and data.get("code") not in (0, "0", None):
                raise RuntimeError(
                    _formatar_erro_tiktok(r.status_code, json.dumps(data, ensure_ascii=False))
                )
        except ValueError:
            pass
    return r.content or b""


def atualizar_shop_info(cur, id_tenant: int, access_token: str | None = None) -> dict[str, Any]:
    if not _tem_tabela_tiktok(cur):
        return {}

    if access_token:
        app_key, app_secret = credenciais_tiktok()
        path = "/authorization/202309/shops"
        qs = {
            "app_key": app_key,
            "timestamp": str(int(time.time())),
            "access_token": access_token,
            "version": TIKTOK_API_VERSION,
        }
        qs["sign"] = _calcular_sign(app_secret, path, qs, method="GET")
        url = f"{tiktok_api_base()}{path}"
        try:
            r = requests.get(url, params=qs, timeout=TIKTOK_API_TIMEOUT)
        except requests.RequestException as e:
            raise RuntimeError(f"Não foi possível ler lojas TikTok Shop: {e}") from e
        if r.status_code >= 400:
            raise RuntimeError(_formatar_erro_tiktok(r.status_code, r.text))
        payload = r.json() if r.content else {}
        if isinstance(payload, dict) and payload.get("code") not in (0, "0", None):
            raise RuntimeError(_formatar_erro_tiktok(r.status_code, r.text))
        data = _extrair_data(payload)
    else:
        data = api_request(cur, id_tenant, "GET", "/authorization/202309/shops")

    shops = []
    if isinstance(data, dict):
        shops = data.get("shops") or data.get("shop_list") or []
    elif isinstance(data, list):
        shops = data

    shop = shops[0] if shops else {}
    if not isinstance(shop, dict):
        shop = {}

    shop_id = shop.get("id") or shop.get("shop_id") or ""
    shop_cipher = shop.get("cipher") or shop.get("shop_cipher") or ""
    info = {
        "shop_id": shop_id,
        "shop_cipher": shop_cipher,
        "name": shop.get("name") or shop.get("shop_name") or "",
        "region": shop.get("region") or "",
        "seller_type": shop.get("seller_type") or "",
    }

    cur.execute(
        """
        UPDATE tbl_integracao_tiktok SET
            shop_id = %s,
            shop_cipher = %s,
            shop_info = %s::jsonb,
            atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (
            str(shop_id) if shop_id else None,
            str(shop_cipher) if shop_cipher else None,
            json.dumps({**info, "raw": shop}, ensure_ascii=False),
            agora_utc(),
            id_tenant,
        ),
    )
    return info


def carregar_config_tiktok(cur, id_tenant: int) -> dict[str, Any]:
    base = {
        "status": "desconectado",
        "conectado": False,
        "shop_id": None,
        "shop_cipher": None,
        "loja": {},
        "pedidos_importar_auto": False,
        "produtos_exportar_auto": False,
        "produtos_modo": "vincular_sku",
        "estoque_sync_ativo": False,
        "ultima_sync_pedidos": None,
        "conectado_em": None,
        "ultimo_erro": None,
        "redirect_uri": redirect_uri_oauth(),
        "webhook_url": webhook_url(),
    }
    if not _tem_tabela_tiktok(cur):
        return base
    cur.execute(
        """
        SELECT status, shop_id, shop_cipher, shop_info,
               pedidos_importar_auto, produtos_exportar_auto, produtos_modo,
               estoque_sync_ativo, ultima_sync_pedidos, conectado_em, ultimo_erro
        FROM tbl_integracao_tiktok WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return base
    loja_raw = row[3]
    if isinstance(loja_raw, str):
        try:
            loja = json.loads(loja_raw)
        except (TypeError, ValueError):
            loja = {}
    elif isinstance(loja_raw, dict):
        loja = loja_raw
    else:
        loja = {}
    st = row[0] or "desconectado"
    modo = (row[6] or "vincular_sku").strip()
    if modo not in ("vincular_sku", "criar_anuncio"):
        modo = "vincular_sku"
    return {
        **base,
        "status": st,
        "conectado": st == "conectado",
        "shop_id": row[1],
        "shop_cipher": row[2],
        "loja": loja,
        "pedidos_importar_auto": bool(row[4]),
        "produtos_exportar_auto": bool(row[5]),
        "produtos_modo": modo,
        "estoque_sync_ativo": bool(row[7]),
        "ultima_sync_pedidos": row[8].isoformat() if row[8] else None,
        "conectado_em": row[9].isoformat() if row[9] else None,
        "ultimo_erro": row[10],
    }


def salvar_config_tiktok(
    cur,
    id_tenant: int,
    *,
    pedidos_importar_auto: bool | None = None,
    produtos_exportar_auto: bool | None = None,
    produtos_modo: str | None = None,
    estoque_sync_ativo: bool | None = None,
) -> None:
    if not _tem_tabela_tiktok(cur):
        raise RuntimeError("Tabela tbl_integracao_tiktok não existe. Aplique o SQL 078.")
    updates: dict[str, Any] = {}
    if pedidos_importar_auto is not None:
        updates["pedidos_importar_auto"] = bool(pedidos_importar_auto)
    if produtos_exportar_auto is not None:
        updates["produtos_exportar_auto"] = bool(produtos_exportar_auto)
    if produtos_modo is not None:
        modo = (produtos_modo or "vincular_sku").strip()
        if modo not in ("vincular_sku", "criar_anuncio"):
            modo = "vincular_sku"
        updates["produtos_modo"] = modo
    if estoque_sync_ativo is not None:
        updates["estoque_sync_ativo"] = bool(estoque_sync_ativo)
    if not updates:
        return
    set_parts = [f"{c} = %s" for c in updates]
    set_parts.append("atualizado_em = %s")
    vals = [*updates.values(), agora_utc(), id_tenant]
    cur.execute(
        f"UPDATE tbl_integracao_tiktok SET {', '.join(set_parts)} WHERE id_tenant = %s",
        vals,
    )
    if cur.rowcount == 0:
        cols = ["id_tenant", *updates.keys(), "atualizado_em"]
        placeholders = ", ".join(["%s"] * len(cols))
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in updates) + ", atualizado_em = EXCLUDED.atualizado_em"
        cur.execute(
            f"""
            INSERT INTO tbl_integracao_tiktok ({", ".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT (id_tenant) DO UPDATE SET {set_clause}
            """,
            [id_tenant, *updates.values(), agora_utc()],
        )


def _garantir_tabela_tiktok_categoria_map(cur) -> bool:
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tbl_integracao_tiktok_categoria_map (
                id SERIAL PRIMARY KEY,
                id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
                id_categoria INTEGER NOT NULL REFERENCES tbl_categoria(id) ON DELETE CASCADE,
                tiktok_category_id VARCHAR(64) NOT NULL,
                meta JSONB NOT NULL DEFAULT '{}',
                criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (id_tenant, id_categoria)
            )
            """
        )
        return True
    except Exception:
        return False


def _mapa_categoria_tiktok(cur, id_tenant: int, id_categoria: int | None) -> str:
    if not id_categoria:
        return ""
    _garantir_tabela_tiktok_categoria_map(cur)
    try:
        cur.execute(
            """
            SELECT tiktok_category_id
            FROM tbl_integracao_tiktok_categoria_map
            WHERE id_tenant = %s AND id_categoria = %s
            """,
            (id_tenant, int(id_categoria)),
        )
        row = cur.fetchone()
        return str(row[0]).strip() if row and row[0] else ""
    except Exception:
        return ""


def listar_mapeamento_categorias_tiktok(cur, id_tenant: int) -> list[dict]:
    _garantir_tabela_tiktok_categoria_map(cur)
    cur.execute(
        """
        SELECT c.id, c.nome, COALESCE(m.tiktok_category_id, '')
        FROM tbl_categoria c
        LEFT JOIN tbl_integracao_tiktok_categoria_map m
            ON m.id_categoria = c.id AND m.id_tenant = c.id_tenant
        WHERE c.id_tenant = %s AND c.ativo = TRUE
        ORDER BY c.nome
        """,
        (id_tenant,),
    )
    return [
        {
            "id_categoria": int(r[0]),
            "nome": r[1],
            "tiktok_category_id": r[2] or "",
        }
        for r in cur.fetchall()
    ]


def salvar_mapeamento_categorias_tiktok(cur, id_tenant: int, itens: list[dict]) -> int:
    if not _garantir_tabela_tiktok_categoria_map(cur):
        raise RuntimeError("Tabela de mapeamento TikTok indisponível. Aplique o SQL 079.")
    salvos = 0
    agora = agora_utc()
    for item in itens:
        try:
            id_cat = int(item.get("id_categoria") or 0)
        except (TypeError, ValueError):
            continue
        tt_cat = (item.get("tiktok_category_id") or "").strip()
        if not id_cat or not tt_cat:
            continue
        cur.execute(
            "SELECT 1 FROM tbl_categoria WHERE id = %s AND id_tenant = %s AND ativo = TRUE",
            (id_cat, id_tenant),
        )
        if not cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO tbl_integracao_tiktok_categoria_map (
                id_tenant, id_categoria, tiktok_category_id, atualizado_em
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_tenant, id_categoria) DO UPDATE SET
                tiktok_category_id = EXCLUDED.tiktok_category_id,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_tenant, id_cat, tt_cat, agora),
        )
        salvos += 1
    return salvos


def _sql_produtos_vitrine_tiktok(ids_produtos: list[int] | None = None) -> tuple[str, list]:
    extra = ""
    params_tail: list = []
    if ids_produtos:
        extra = " AND p.id = ANY(%s)"
        params_tail.append(ids_produtos)
    sql = f"""
        SELECT pv.id, pv.id_variante, pv.id_produto,
               TRIM(COALESCE(NULLIF(v.sku, ''), p.sku, '')) AS sku,
               COALESCE(NULLIF(TRIM(pv.nome_vitrine), ''), NULLIF(TRIM(v.nome_exibicao), ''), p.nome) AS titulo,
               COALESCE(pv.preco_venda, v.preco, p.preco, 0) AS preco,
               LEFT(COALESCE(
                   NULLIF(TRIM(pv.descricao_vitrine), ''),
                   NULLIF(TRIM(v.descricao), ''),
                   NULLIF(TRIM(p.descricao), ''),
                   ''
               ), 50000) AS descricao,
               COALESCE(NULLIF(TRIM(pv.imagem_url_vitrine), ''), v.imagem_url, p.imagem_url) AS imagem,
               COALESCE(ve.quantidade, 0) AS estoque,
               p.condicao,
               COALESCE(NULLIF(TRIM(p.marca), ''), '') AS marca,
               COALESCE(NULLIF(TRIM(v.gtin), ''), NULLIF(TRIM(p.gtin), ''), '') AS gtin,
               pv.id_categoria_vendedor
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = v.id
        WHERE pv.id_tenant_vendedor = %s AND pv.ativo = TRUE{extra}
        ORDER BY p.id, pv.id
    """
    return sql, params_tail


def _imagem_publica_tiktok(imagem_path: str | None) -> str:
    rel = url_imagem_produto(imagem_path)
    if not rel:
        return ""
    if rel.lower().startswith(("http://", "https://")):
        return rel
    base = obter_base_url()
    if not base:
        return ""
    path = rel if rel.startswith("/") else f"/{rel}"
    return f"{base.rstrip('/')}{path}"


def _item_ja_vinculado_tiktok(cur, id_tenant: int, id_variante: int) -> str | None:
    cur.execute(
        """
        SELECT id_bling FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'tiktok' AND contexto = 'vendedor'
          AND entidade = 'produto' AND id_dropnexo = %s
        LIMIT 1
        """,
        (id_tenant, id_variante),
    )
    row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _parse_map_tiktok(id_bling: str) -> tuple[str, str]:
    raw = (id_bling or "").strip()
    if ":" in raw:
        pid, sid = raw.split(":", 1)
        return pid.strip(), sid.strip()
    return raw, ""


def _salvar_map_produto_tiktok(
    cur,
    id_tenant: int,
    id_variante: int,
    id_produto: int,
    sku: str,
    product_id: str,
    sku_id: str = "",
) -> None:
    id_bling = f"{product_id}:{sku_id}" if sku_id else str(product_id)
    cur.execute(
        """
        DELETE FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'tiktok' AND contexto = 'vendedor'
          AND entidade = 'produto' AND id_dropnexo = %s
        """,
        (id_tenant, id_variante),
    )
    meta = json.dumps(
        {
            "id_produto": id_produto,
            "product_id": product_id,
            "sku_id": sku_id or None,
        },
        ensure_ascii=False,
    )
    cur.execute(
        """
        INSERT INTO tbl_integracao_map (
            id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta, atualizado_em
        ) VALUES (%s, 'tiktok', 'vendedor', 'produto', %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling) DO UPDATE SET
            id_dropnexo = EXCLUDED.id_dropnexo,
            sku = EXCLUDED.sku,
            meta = EXCLUDED.meta,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, id_bling, id_variante, sku, meta, agora_utc()),
    )


def _buscar_produto_tiktok_por_sku(cur, id_tenant: int, sku: str) -> tuple[str, str] | None:
    sku = (sku or "").strip()
    if not sku:
        return None
    try:
        data = api_request(
            cur,
            id_tenant,
            "POST",
            "/product/202309/products/search",
            json_body={"page_size": 20, "seller_sku_list": [sku]},
        )
    except RuntimeError:
        return None
    produtos = []
    if isinstance(data, dict):
        produtos = data.get("products") or data.get("product_list") or []
    for prod in produtos:
        if not isinstance(prod, dict):
            continue
        product_id = str(prod.get("id") or prod.get("product_id") or "").strip()
        skus = prod.get("skus") or prod.get("sku_list") or []
        for s in skus:
            if not isinstance(s, dict):
                continue
            seller_sku = (s.get("seller_sku") or s.get("sku") or "").strip()
            if seller_sku == sku:
                sku_id = str(s.get("id") or s.get("sku_id") or "").strip()
                if product_id:
                    return product_id, sku_id
        if product_id and (prod.get("seller_sku") or "").strip() == sku:
            return product_id, str(prod.get("sku_id") or "")
    return None


def _criar_produto_tiktok(
    cur,
    id_tenant: int,
    *,
    id_variante: int,
    id_produto: int,
    sku: str,
    titulo: str,
    preco: float,
    descricao: str,
    imagem: str,
    estoque: int,
    id_categoria_vendedor: int | None,
) -> tuple[str, str]:
    categoria = _mapa_categoria_tiktok(cur, id_tenant, id_categoria_vendedor)
    if not categoria:
        raise RuntimeError(
            f"«{titulo}»: mapeie a categoria em Integrações → TikTok Shop → Mapear categorias."
        )
    if preco <= 0:
        raise RuntimeError(f"Preço inválido para «{titulo}».")
    img_url = _imagem_publica_tiktok(imagem)
    if not img_url:
        raise RuntimeError(f"«{titulo}»: foto pública obrigatória para publicar no TikTok Shop.")

    payload: dict[str, Any] = {
        "title": (titulo or sku or "Produto")[:255],
        "description": (descricao or titulo or "")[:5000],
        "category_id": categoria,
        "main_images": [{"uri": img_url}],
        "skus": [
            {
                "seller_sku": sku[:100],
                "original_price": str(round(float(preco), 2)),
                "available_stock": max(0, int(estoque or 0)),
            }
        ],
    }
    data = api_request(cur, id_tenant, "POST", "/product/202309/products", json_body=payload)
    product_id = ""
    sku_id = ""
    if isinstance(data, dict):
        product_id = str(data.get("product_id") or data.get("id") or "").strip()
        skus = data.get("skus") or []
        if skus and isinstance(skus[0], dict):
            sku_id = str(skus[0].get("id") or skus[0].get("sku_id") or "").strip()
    if not product_id:
        raise RuntimeError(f"«{titulo}»: TikTok Shop não retornou product_id.")
    _salvar_map_produto_tiktok(
        cur, id_tenant, id_variante, id_produto, sku, product_id, sku_id
    )
    return product_id, sku_id


def _atualizar_estoque_map_tiktok(
    cur,
    id_tenant: int,
    id_bling: str,
    *,
    quantidade: int,
    preco: float | None = None,
) -> None:
    from api.tiktok.eco_estoque import registrar_eco_tiktok_pendente

    product_id, sku_id = _parse_map_tiktok(id_bling)
    if not product_id:
        raise RuntimeError("Produto TikTok Shop não mapeado.")
    sku_key = f"{product_id}:{sku_id}" if sku_id else product_id
    registrar_eco_tiktok_pendente(
        cur,
        id_tenant,
        tiktok_sku_key=sku_key,
        quantidade_esperada=max(0, int(quantidade)),
        origem="dropnexo_export",
    )
    body: dict[str, Any] = {
        "product_id": product_id,
        "skus": [
            {
                "id": sku_id or product_id,
                "available_stock": max(0, int(quantidade)),
            }
        ],
    }
    if preco is not None and float(preco) > 0:
        body["skus"][0]["original_price"] = str(round(float(preco), 2))
    api_request(cur, id_tenant, "POST", "/product/202309/inventory/update", json_body=body)


def publicar_produtos_tiktok(cur, id_tenant: int, ids_produtos: list[int]) -> dict:
    ids = []
    for x in ids_produtos:
        try:
            pid = int(x)
            if pid > 0:
                ids.append(pid)
        except (TypeError, ValueError):
            continue
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise RuntimeError("Selecione ao menos um produto.")

    cfg = carregar_config_tiktok(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("Conecte o TikTok Shop em Integrações.")
    if not cfg.get("produtos_exportar_auto"):
        raise RuntimeError(
            "Ative a exportação de produtos em Integrações → TikTok Shop → Produtos."
        )

    modo = cfg.get("produtos_modo") or "vincular_sku"
    sql, extra = _sql_produtos_vitrine_tiktok(ids)
    cur.execute(sql, [id_tenant, *extra])
    linhas = cur.fetchall()
    if not linhas:
        raise RuntimeError("Nenhuma variação ativa encontrada nos produtos selecionados.")

    exportados = 0
    atualizados = 0
    vinculados = 0
    nao_encontrados = 0
    sem_sku = 0
    erros: list[str] = []
    resultados: list[dict] = []
    processados = 0

    for row in linhas:
        if processados >= _TIKTOK_MAX_CRIAR_POR_SYNC:
            break
        (
            _pv_id,
            id_variante,
            id_produto,
            sku,
            titulo,
            preco,
            descricao,
            imagem,
            estoque,
            _condicao,
            _marca,
            _gtin,
            id_cat_vd,
        ) = row
        processados += 1
        sku_limpo = (sku or "").strip()
        nome = (titulo or sku_limpo or "Produto")[:80]
        map_id = _item_ja_vinculado_tiktok(cur, id_tenant, int(id_variante))

        if modo == "criar_anuncio" and not map_id:
            if not sku_limpo:
                sem_sku += 1
                resultados.append(
                    {
                        "id_produto": int(id_produto),
                        "titulo": nome,
                        "sku": sku_limpo,
                        "status": "erro",
                        "mensagem": "Produto sem SKU para publicar no TikTok Shop.",
                    }
                )
                continue
            try:
                product_id, sku_id = _criar_produto_tiktok(
                    cur,
                    id_tenant,
                    id_variante=int(id_variante),
                    id_produto=int(id_produto),
                    sku=sku_limpo,
                    titulo=titulo or "",
                    preco=float(preco or 0),
                    descricao=descricao or "",
                    imagem=imagem or "",
                    estoque=int(estoque or 0),
                    id_categoria_vendedor=int(id_cat_vd) if id_cat_vd else None,
                )
                exportados += 1
                resultados.append(
                    {
                        "id_produto": int(id_produto),
                        "titulo": nome,
                        "sku": sku_limpo,
                        "status": "ok",
                        "acao": "criado",
                        "mensagem": "Produto publicado no TikTok Shop.",
                        "product_id": product_id,
                        "sku_id": sku_id,
                    }
                )
            except RuntimeError as e:
                msg = str(e)[:300]
                if msg not in erros:
                    erros.append(msg)
                resultados.append(
                    {
                        "id_produto": int(id_produto),
                        "titulo": nome,
                        "sku": sku_limpo,
                        "status": "erro",
                        "mensagem": msg,
                    }
                )
            continue

        if not map_id:
            if not sku_limpo:
                sem_sku += 1
                resultados.append(
                    {
                        "id_produto": int(id_produto),
                        "titulo": nome,
                        "sku": sku_limpo,
                        "status": "erro",
                        "mensagem": "Produto sem SKU para vincular ao TikTok Shop.",
                    }
                )
                continue
            found = _buscar_produto_tiktok_por_sku(cur, id_tenant, sku_limpo)
            if not found:
                nao_encontrados += 1
                resultados.append(
                    {
                        "id_produto": int(id_produto),
                        "titulo": nome,
                        "sku": sku_limpo,
                        "status": "erro",
                        "mensagem": "Nenhum produto encontrado no TikTok Shop com este SKU.",
                    }
                )
                continue
            product_id, sku_id = found
            _salvar_map_produto_tiktok(
                cur,
                id_tenant,
                int(id_variante),
                int(id_produto),
                sku_limpo,
                product_id,
                sku_id,
            )
            map_id = f"{product_id}:{sku_id}" if sku_id else product_id
            vinculados += 1

        try:
            _atualizar_estoque_map_tiktok(
                cur,
                id_tenant,
                map_id,
                quantidade=int(estoque or 0),
                preco=float(preco or 0) if preco else None,
            )
            atualizados += 1
            resultados.append(
                {
                    "id_produto": int(id_produto),
                    "titulo": nome,
                    "sku": sku_limpo,
                    "status": "ok",
                    "acao": "atualizado",
                    "mensagem": "Estoque/preço atualizado no TikTok Shop.",
                    "map_id": map_id,
                }
            )
        except RuntimeError as e:
            msg = str(e)[:300]
            if msg not in erros:
                erros.append(msg)
            resultados.append(
                {
                    "id_produto": int(id_produto),
                    "titulo": nome,
                    "sku": sku_limpo,
                    "status": "erro",
                    "mensagem": msg,
                }
            )

    total = len(linhas)
    partes: list[str] = []
    if exportados:
        partes.append(f"{exportados} produto(s) criado(s)")
    if vinculados:
        partes.append(f"{vinculados} vinculado(s)")
    if atualizados:
        partes.append(f"{atualizados} atualizado(s)")
    if erros:
        partes.append(f"{len(erros)} com erro")
    msg = " · ".join(partes) + " no TikTok Shop." if partes else "Nenhum produto processado."
    if total > _TIKTOK_MAX_CRIAR_POR_SYNC and processados >= _TIKTOK_MAX_CRIAR_POR_SYNC:
        msg += (
            f" Limite de {_TIKTOK_MAX_CRIAR_POR_SYNC} por sincronização — "
            "execute novamente para continuar."
        )
    if nao_encontrados:
        msg += f" {nao_encontrados} sem SKU correspondente no TikTok Shop."
    if sem_sku:
        msg += f" {sem_sku} sem SKU."

    out = {
        "message": msg,
        "total_produtos": total,
        "modo": modo,
        "exportados": exportados,
        "atualizados": atualizados,
        "vinculados": vinculados,
        "nao_encontrados": nao_encontrados,
        "erros": len([r for r in resultados if r.get("status") == "erro"]),
        "resultados": resultados,
    }
    if erros:
        out["detalhes_erros"] = erros[:8]
    return out


def sincronizar_estoque_tiktok(cur, id_tenant: int) -> dict:
    from api.tiktok.sync_runtime import sincronizar_todos_estoques_tiktok

    return sincronizar_todos_estoques_tiktok(cur, id_tenant)


def importar_pedidos_tiktok(cur, id_tenant: int, *, dias: int = 7) -> dict:
    from api.tiktok.pedidos_tiktok import importar_pedidos_tiktok as _importar

    return _importar(cur, id_tenant, dias=dias)
