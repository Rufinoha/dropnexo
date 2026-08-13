# api/mercado_livre/mercado_livre.py — OAuth, API e sync de pedidos ML
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import unicodedata
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlencode

import requests

from core.tokens import criptografar_token, descriptografar_token
from global_utils import agora_utc, is_modo_producao, obter_base_url, obter_url_site_publico

_log = logging.getLogger(__name__)

ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_API_BASE = "https://api.mercadolibre.com"
ML_OAUTH_TIMEOUT = (5, 25)
ML_API_TIMEOUT = (10, 60)
ML_API_TIMEOUT_RAPIDO = (4, 12)

_TABELA_OK: bool | None = None


def _env(key: str) -> str:
    return (os.getenv(key) or "").strip()


def _ml_env(sufixo: str) -> str:
    if is_modo_producao():
        return _env(f"ML_{sufixo}_PROD") or _env(f"ML_{sufixo}_DEV")
    return _env(f"ML_{sufixo}_DEV") or _env(f"ML_{sufixo}_PROD")


def ml_client_id() -> str:
    return (
        _ml_env("CLIENT_ID")
        or _env("ML_CLIENT_ID")
        or _env("ID_MERCADO_LIVRE")
        or _env("ID_MERCADO_LIRE")
    )


def ml_client_secret() -> str:
    return (
        _ml_env("CLIENT_SECRET")
        or _env("ML_CLIENT_SECRET")
        or _env("SECRET_MERCADO_LIVRE")
    )


def ml_configurado() -> bool:
    return bool(ml_client_id() and ml_client_secret())


def credenciais_ml() -> tuple[str, str]:
    client_id = ml_client_id()
    client_secret = ml_client_secret()
    if not client_id or not client_secret:
        raise RuntimeError(
            "Credenciais Mercado Livre incompletas. Configure ML_CLIENT_ID_PROD e "
            "ML_CLIENT_SECRET_PROD no .env do servidor."
        )
    return client_id, client_secret


def redirect_uri_oauth() -> str:
    return f"{obter_base_url().rstrip('/')}/api/integracoes/mercado-livre/oauth/callback"


def webhook_url() -> str:
    # Notificações do ML precisam de HTTPS público (não localhost).
    return f"{obter_url_site_publico().rstrip('/')}/api/integracoes/mercado-livre/webhook"


def gerar_state_oauth() -> str:
    return secrets.token_urlsafe(24)


def url_autorizacao(state: str) -> str:
    client_id, _ = credenciais_ml()
    qs = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri_oauth(),
            "state": state,
        }
    )
    return f"{ML_AUTH_URL}?{qs}"


def _post_token(body: dict[str, str]) -> dict[str, Any]:
    client_id, client_secret = credenciais_ml()
    payload = {"client_id": client_id, "client_secret": client_secret, **body}
    headers = {"Accept": "application/json", "Content-Type": "application/x-www-form-urlencoded"}
    try:
        r = requests.post(ML_TOKEN_URL, data=payload, headers=headers, timeout=ML_OAUTH_TIMEOUT)
    except requests.Timeout as e:
        raise RuntimeError("Mercado Livre demorou para responder. Tente novamente.") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Falha de rede ao contactar Mercado Livre: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(f"Mercado Livre OAuth falhou ({r.status_code}): {r.text[:500]}")
    data = r.json()
    if not data.get("access_token"):
        raise RuntimeError("Mercado Livre não retornou access_token.")
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


def _tem_tabela_ml(cur) -> bool:
    """Detecta migração 071. Só cacheia True — False pode mudar após aplicar o SQL sem reiniciar o app."""
    global _TABELA_OK
    if _TABELA_OK is True:
        return True
    cur.execute("SELECT to_regclass(%s)", ("tbl_integracao_mercado_livre",))
    row = cur.fetchone()
    ok = bool(row and row[0])
    if ok:
        _TABELA_OK = True
    return ok


def salvar_tokens(cur, id_tenant: int, tokens: dict[str, Any]) -> None:
    if not _tem_tabela_ml(cur):
        raise RuntimeError("Tabela tbl_integracao_mercado_livre não existe. Aplique o SQL 071.")
    access = tokens.get("access_token") or ""
    refresh = tokens.get("refresh_token") or ""
    ml_user = tokens.get("user_id")
    expires = _expires_em(tokens.get("expires_in"))
    cur.execute(
        """
        INSERT INTO tbl_integracao_mercado_livre (
            id_tenant, status, access_token_enc, refresh_token_enc,
            token_expires_em, ml_user_id, conectado_em, ultimo_erro, atualizado_em
        ) VALUES (%s, 'conectado', %s, %s, %s, %s, %s, NULL, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            status = 'conectado',
            access_token_enc = EXCLUDED.access_token_enc,
            refresh_token_enc = EXCLUDED.refresh_token_enc,
            token_expires_em = EXCLUDED.token_expires_em,
            ml_user_id = EXCLUDED.ml_user_id,
            conectado_em = COALESCE(tbl_integracao_mercado_livre.conectado_em, EXCLUDED.conectado_em),
            ultimo_erro = NULL,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            criptografar_token(access),
            criptografar_token(refresh),
            expires,
            int(ml_user) if ml_user else None,
            agora_utc(),
            agora_utc(),
        ),
    )


def carregar_tokens_armazenados(cur, id_tenant: int) -> dict[str, Any]:
    if not _tem_tabela_ml(cur):
        return {"status": "desconectado"}
    cur.execute(
        """
        SELECT status, access_token_enc, refresh_token_enc, token_expires_em, ml_user_id
        FROM tbl_integracao_mercado_livre WHERE id_tenant = %s
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
        "ml_user_id": row[4],
    }


def desconectar_ml(cur, id_tenant: int) -> None:
    if not _tem_tabela_ml(cur):
        return
    cur.execute(
        """
        UPDATE tbl_integracao_mercado_livre SET
            status = 'desconectado',
            access_token_enc = NULL,
            refresh_token_enc = NULL,
            token_expires_em = NULL,
            ml_user_id = NULL,
            ml_site_id = NULL,
            ml_conta_info = '{}',
            ultimo_erro = NULL,
            atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (agora_utc(), id_tenant),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO tbl_integracao_mercado_livre (id_tenant, status, atualizado_em)
            VALUES (%s, 'desconectado', %s)
            ON CONFLICT (id_tenant) DO NOTHING
            """,
            (id_tenant, agora_utc()),
        )


def ml_conectado(cur, id_tenant: int) -> bool:
    if not _tem_tabela_ml(cur):
        return False
    cur.execute(
        "SELECT status FROM tbl_integracao_mercado_livre WHERE id_tenant = %s",
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
        raise RuntimeError("Mercado Livre não conectado.")
    access = dados.get("access_token") or ""
    if access and not _token_expirado(dados.get("token_expires_em")):
        return access
    refresh = dados.get("refresh_token") or ""
    if not refresh:
        raise RuntimeError("Token Mercado Livre expirado. Reconecte a conta.")
    novos = renovar_access_token(refresh)
    salvar_tokens(cur, id_tenant, novos)
    return novos.get("access_token") or ""


def api_request(
    cur,
    id_tenant: int,
    method: str,
    path: str,
    *,
    params: dict | None = None,
    json_body: dict | None = None,
    timeout: tuple[float, float] | None = None,
    extra_headers: dict | None = None,
) -> Any:
    token = obter_access_token_valido(cur, id_tenant)
    url = path if path.startswith("http") else f"{ML_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    if extra_headers:
        headers.update({str(k): str(v) for k, v in extra_headers.items() if v is not None})
    try:
        r = requests.request(
            method.upper(),
            url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=timeout or ML_API_TIMEOUT,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Falha na API Mercado Livre: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(_formatar_erro_ml(r.status_code, r.text))
    if not r.content:
        return {}
    return r.json()


def api_request_bytes(
    cur,
    id_tenant: int,
    method: str,
    path: str,
    *,
    params: dict | None = None,
) -> bytes:
    """GET/POST que retorna corpo binário (ex.: PDF de etiqueta)."""
    token = obter_access_token_valido(cur, id_tenant)
    url = path if path.startswith("http") else f"{ML_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "*/*"}
    try:
        r = requests.request(
            method.upper(),
            url,
            headers=headers,
            params=params,
            timeout=ML_API_TIMEOUT,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Falha na API Mercado Livre: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(_formatar_erro_ml(r.status_code, r.text))
    return r.content or b""


def atualizar_conta_info(cur, id_tenant: int, access_token: str | None = None) -> dict[str, Any]:
    if not _tem_tabela_ml(cur):
        return {}
    if access_token:
        r = requests.get(
            f"{ML_API_BASE}/users/me",
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=ML_API_TIMEOUT,
        )
        if r.status_code >= 400:
            raise RuntimeError(f"Não foi possível ler perfil ML ({r.status_code}).")
        info = r.json()
    else:
        info = api_request(cur, id_tenant, "GET", "/users/me")

    ml_user_id = info.get("id")
    site_id = info.get("site_id") or ""
    conta = {
        "id": ml_user_id,
        "nickname": info.get("nickname") or "",
        "email": info.get("email") or "",
        "first_name": info.get("first_name") or "",
        "last_name": info.get("last_name") or "",
        "site_id": site_id,
        "permalink": info.get("permalink") or "",
    }
    cur.execute(
        """
        UPDATE tbl_integracao_mercado_livre SET
            ml_user_id = %s,
            ml_site_id = %s,
            ml_conta_info = %s::jsonb,
            atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (
            int(ml_user_id) if ml_user_id else None,
            site_id or None,
            json.dumps(conta, ensure_ascii=False),
            agora_utc(),
            id_tenant,
        ),
    )
    return conta


_ML_COLS_EXT_OK: bool | None = None
_ML_COLS_ANUNCIO_OK: bool | None = None


def _rollback_cur(cur) -> None:
    try:
        conn = getattr(cur, "connection", None)
        if conn:
            conn.rollback()
    except Exception:
        pass


def _tem_colunas_config_ext(cur) -> bool:
    """Colunas do SQL 072 (produtos/estoque). Só cacheia True."""
    global _ML_COLS_EXT_OK
    if _ML_COLS_EXT_OK is True:
        return True
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'tbl_integracao_mercado_livre'
          AND column_name = 'produtos_exportar_auto'
        LIMIT 1
        """
    )
    ok = cur.fetchone() is not None
    if ok:
        _ML_COLS_EXT_OK = True
    return ok


def _garantir_colunas_config_ext(cur) -> bool:
    """Cria colunas do SQL 072 se ainda não existirem (deploy sem migração manual)."""
    global _ML_COLS_EXT_OK
    if _tem_colunas_config_ext(cur):
        _garantir_colunas_anuncio_config(cur)
        return True
    try:
        cur.execute(
            """
            ALTER TABLE tbl_integracao_mercado_livre
                ADD COLUMN IF NOT EXISTS produtos_exportar_auto BOOLEAN NOT NULL DEFAULT FALSE
            """
        )
        cur.execute(
            """
            ALTER TABLE tbl_integracao_mercado_livre
                ADD COLUMN IF NOT EXISTS produtos_modo VARCHAR(24) NOT NULL DEFAULT 'vincular_sku'
            """
        )
        cur.execute(
            """
            ALTER TABLE tbl_integracao_mercado_livre
                ADD COLUMN IF NOT EXISTS estoque_sync_ativo BOOLEAN NOT NULL DEFAULT FALSE
            """
        )
        _garantir_colunas_anuncio_config(cur)
        _ML_COLS_EXT_OK = True
        return True
    except Exception:
        _rollback_cur(cur)
        _ML_COLS_EXT_OK = None
        _ML_COLS_ANUNCIO_OK = None
        return False


_ML_LISTING_TYPES = frozenset({"auto", "gold_special", "gold_pro", "gold_premium", "free"})


def _tem_colunas_anuncio_config(cur) -> bool:
    global _ML_COLS_ANUNCIO_OK
    if _ML_COLS_ANUNCIO_OK is True:
        return True
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema()
          AND table_name = 'tbl_integracao_mercado_livre'
          AND column_name = 'listing_type_padrao'
        LIMIT 1
        """
    )
    ok = cur.fetchone() is not None
    if ok:
        _ML_COLS_ANUNCIO_OK = True
    return ok


def _garantir_colunas_anuncio_config(cur) -> bool:
    global _ML_COLS_ANUNCIO_OK
    if _tem_colunas_anuncio_config(cur):
        _garantir_colunas_garantia_ml(cur)
        return True
    try:
        cur.execute(
            """
            ALTER TABLE tbl_integracao_mercado_livre
                ADD COLUMN IF NOT EXISTS listing_type_padrao VARCHAR(24) NOT NULL DEFAULT 'auto'
            """
        )
        cur.execute(
            """
            ALTER TABLE tbl_integracao_mercado_livre
                ADD COLUMN IF NOT EXISTS frete_gratis BOOLEAN NOT NULL DEFAULT FALSE
            """
        )
        _garantir_colunas_garantia_ml(cur)
        _ML_COLS_ANUNCIO_OK = True
        return True
    except Exception:
        _rollback_cur(cur)
        _ML_COLS_ANUNCIO_OK = None
        return False


_ML_COLS_GARANTIA_OK: bool | None = None
_ML_COLS_PRODUTO_EXTRA_OK: bool | None = None


def _garantir_colunas_garantia_ml(cur) -> bool:
    """Defaults de garantia na conta ML (SQL 091)."""
    global _ML_COLS_GARANTIA_OK
    if _ML_COLS_GARANTIA_OK is True:
        return True
    try:
        cur.execute(
            """
            ALTER TABLE tbl_integracao_mercado_livre
                ADD COLUMN IF NOT EXISTS garantia_tipo_padrao VARCHAR(80)
            """
        )
        cur.execute(
            """
            ALTER TABLE tbl_integracao_mercado_livre
                ADD COLUMN IF NOT EXISTS garantia_tempo_padrao VARCHAR(40)
            """
        )
        _ML_COLS_GARANTIA_OK = True
        return True
    except Exception:
        _rollback_cur(cur)
        _ML_COLS_GARANTIA_OK = False
        return False


def _garantir_colunas_produto_ml_extra(cur) -> bool:
    """garantia/vídeo em tbl_produto (SQL 091)."""
    global _ML_COLS_PRODUTO_EXTRA_OK
    if _ML_COLS_PRODUTO_EXTRA_OK is True:
        return True
    try:
        cur.execute(
            """
            ALTER TABLE tbl_produto
                ADD COLUMN IF NOT EXISTS garantia_tipo VARCHAR(80)
            """
        )
        cur.execute(
            """
            ALTER TABLE tbl_produto
                ADD COLUMN IF NOT EXISTS garantia_tempo VARCHAR(40)
            """
        )
        cur.execute(
            """
            ALTER TABLE tbl_produto
                ADD COLUMN IF NOT EXISTS video_youtube VARCHAR(120)
            """
        )
        _ML_COLS_PRODUTO_EXTRA_OK = True
        return True
    except Exception:
        _rollback_cur(cur)
        _ML_COLS_PRODUTO_EXTRA_OK = False
        return False


def _erro_colunas_anuncio_ml() -> RuntimeError:
    return RuntimeError(
        "Não foi possível salvar tipo de anúncio ou frete grátis. "
        "Aplique o SQL 074 (__doc/sql/074_integracao_mercado_livre_anuncio_config.sql) no banco."
    )


def carregar_config_ml(cur, id_tenant: int) -> dict[str, Any]:
    base = {
        "status": "desconectado",
        "conectado": False,
        "ml_user_id": None,
        "ml_site_id": None,
        "conta": {},
        "pedidos_importar_auto": False,
        "produtos_exportar_auto": False,
        "produtos_modo": "vincular_sku",
        "estoque_sync_ativo": False,
        "listing_type_padrao": "auto",
        "frete_gratis": False,
        "garantia_tipo_padrao": "",
        "garantia_tempo_padrao": "",
        "config_ext_disponivel": False,
        "ultima_sync_pedidos": None,
        "conectado_em": None,
        "ultimo_erro": None,
        "redirect_uri": redirect_uri_oauth(),
        "webhook_url": webhook_url(),
    }
    if not _tem_tabela_ml(cur):
        return base
    ext = _garantir_colunas_config_ext(cur)
    anuncio_cfg = _garantir_colunas_anuncio_config(cur)
    gar_cfg = _garantir_colunas_garantia_ml(cur)
    cols_ext = ""
    if anuncio_cfg:
        cols_ext = ", listing_type_padrao, frete_gratis"
        if gar_cfg:
            cols_ext += ", garantia_tipo_padrao, garantia_tempo_padrao"
    if ext:
        cur.execute(
            f"""
            SELECT status, ml_user_id, ml_site_id, ml_conta_info,
                   pedidos_importar_auto, ultima_sync_pedidos, conectado_em, ultimo_erro,
                   produtos_exportar_auto, produtos_modo, estoque_sync_ativo{cols_ext}
            FROM tbl_integracao_mercado_livre WHERE id_tenant = %s
            """,
            (id_tenant,),
        )
    else:
        cur.execute(
            """
            SELECT status, ml_user_id, ml_site_id, ml_conta_info,
                   pedidos_importar_auto, ultima_sync_pedidos, conectado_em, ultimo_erro
            FROM tbl_integracao_mercado_livre WHERE id_tenant = %s
            """,
            (id_tenant,),
        )
    row = cur.fetchone()
    if not row:
        return {**base, "config_ext_disponivel": ext}
    conta_raw = row[3]
    if isinstance(conta_raw, str):
        try:
            conta = json.loads(conta_raw)
        except (TypeError, ValueError):
            conta = {}
    elif isinstance(conta_raw, dict):
        conta = conta_raw
    else:
        conta = {}
    st = row[0] or "desconectado"
    out = {
        **base,
        "status": st,
        "conectado": st == "conectado",
        "ml_user_id": row[1],
        "ml_site_id": row[2],
        "conta": conta,
        "pedidos_importar_auto": bool(row[4]),
        "ultima_sync_pedidos": row[5].isoformat() if row[5] else None,
        "conectado_em": row[6].isoformat() if row[6] else None,
        "ultimo_erro": row[7],
        "config_ext_disponivel": ext,
    }
    if ext and len(row) > 8:
        modo = (row[9] or "vincular_sku").strip()
        if modo not in ("vincular_sku", "criar_anuncio"):
            modo = "vincular_sku"
        out["produtos_exportar_auto"] = bool(row[8])
        out["produtos_modo"] = modo
        out["estoque_sync_ativo"] = bool(row[10])
        if anuncio_cfg and len(row) > 12:
            lt = (row[11] or "auto").strip()
            out["listing_type_padrao"] = lt if lt in _ML_LISTING_TYPES else "auto"
            out["frete_gratis"] = bool(row[12])
            if gar_cfg and len(row) > 14:
                out["garantia_tipo_padrao"] = (row[13] or "").strip()
                out["garantia_tempo_padrao"] = (row[14] or "").strip()
    return out


def salvar_config_ml(
    cur,
    id_tenant: int,
    *,
    pedidos_importar_auto: bool | None = None,
    produtos_exportar_auto: bool | None = None,
    produtos_modo: str | None = None,
    estoque_sync_ativo: bool | None = None,
    listing_type_padrao: str | None = None,
    frete_gratis: bool | None = None,
    garantia_tipo_padrao: str | None = None,
    garantia_tempo_padrao: str | None = None,
) -> None:
    if not _tem_tabela_ml(cur):
        raise RuntimeError("Tabela tbl_integracao_mercado_livre não existe.")
    updates: dict[str, Any] = {}
    if pedidos_importar_auto is not None:
        updates["pedidos_importar_auto"] = bool(pedidos_importar_auto)
    precisa_ext = any(
        v is not None
        for v in (
            produtos_exportar_auto,
            produtos_modo,
            estoque_sync_ativo,
            listing_type_padrao,
            frete_gratis,
            garantia_tipo_padrao,
            garantia_tempo_padrao,
        )
    )
    if precisa_ext and not _garantir_colunas_config_ext(cur):
        raise RuntimeError(
            "Preferências de produtos/estoque indisponíveis. Aplique o SQL 072 no banco."
        )
    ext = _tem_colunas_config_ext(cur)
    if ext:
        if produtos_exportar_auto is not None:
            updates["produtos_exportar_auto"] = bool(produtos_exportar_auto)
        if produtos_modo is not None:
            modo = (produtos_modo or "vincular_sku").strip()
            if modo not in ("vincular_sku", "criar_anuncio"):
                modo = "vincular_sku"
            updates["produtos_modo"] = modo
        if estoque_sync_ativo is not None:
            updates["estoque_sync_ativo"] = bool(estoque_sync_ativo)
        if listing_type_padrao is not None:
            if not _garantir_colunas_anuncio_config(cur):
                raise _erro_colunas_anuncio_ml()
            lt = (listing_type_padrao or "auto").strip()
            updates["listing_type_padrao"] = lt if lt in _ML_LISTING_TYPES else "auto"
        if frete_gratis is not None:
            if not _garantir_colunas_anuncio_config(cur):
                raise _erro_colunas_anuncio_ml()
            updates["frete_gratis"] = bool(frete_gratis)
        if garantia_tipo_padrao is not None or garantia_tempo_padrao is not None:
            if not _garantir_colunas_garantia_ml(cur):
                raise RuntimeError(
                    "Colunas de garantia ML indisponíveis. Aplique o SQL 091 no banco."
                )
            if garantia_tipo_padrao is not None:
                updates["garantia_tipo_padrao"] = (garantia_tipo_padrao or "").strip()[:80] or None
            if garantia_tempo_padrao is not None:
                updates["garantia_tempo_padrao"] = (garantia_tempo_padrao or "").strip()[:40] or None
    if not updates:
        return
    set_parts = [f"{c} = %s" for c in updates]
    set_parts.append("atualizado_em = %s")
    vals = [*updates.values(), agora_utc(), id_tenant]
    cur.execute(
        f"UPDATE tbl_integracao_mercado_livre SET {', '.join(set_parts)} WHERE id_tenant = %s",
        vals,
    )
    if cur.rowcount == 0:
        cols = ["id_tenant", *updates.keys(), "atualizado_em"]
        placeholders = ", ".join(["%s"] * len(cols))
        set_clause = (
            ", ".join(f"{c} = EXCLUDED.{c}" for c in updates)
            + ", atualizado_em = EXCLUDED.atualizado_em"
        )
        cur.execute(
            f"""
            INSERT INTO tbl_integracao_mercado_livre ({", ".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT (id_tenant) DO UPDATE SET {set_clause}
            """,
            [id_tenant, *updates.values(), agora_utc()],
        )


# ── sync_pedidos ──────────────────────────────────

from datetime import datetime, timedelta, timezone



def importar_pedidos_mercado_livre(cur, id_tenant: int, *, dias: int = 7) -> dict:
    from api.mercado_livre.pedidos_ml import importar_pedidos_mercado_livre as _importar

    return _importar(cur, id_tenant, dias=dias)


_ML_CURRENCY_SITE = {
    "MLB": "BRL",
    "MLA": "ARS",
    "MLM": "MXN",
    "MLC": "CLP",
    "MLU": "UYU",
    "MCO": "COP",
    "MPE": "PEN",
}
_ML_MAX_CRIAR_POR_SYNC = 20
_ML_FAMILY_NAME_MAX = 60
_ML_ATTR_CACHE: dict[str, list] = {}
_SELLER_UP_CACHE: dict[int, bool] = {}


def _formatar_erro_ml(status: int, text: str) -> str:
    try:
        data = json.loads(text)
        if not isinstance(data, dict):
            return f"Mercado Livre API ({status}): {(text or '')[:280]}"
        err = (data.get("error") or "").strip()
        causes = data.get("cause") or []
        if not isinstance(causes, list):
            causes = [causes] if causes else []
        partes: list[str] = []
        if err:
            partes.append(err)
        for c in causes:
            if isinstance(c, str):
                msg = c.strip()
                if msg:
                    partes.append(msg)
                continue
            if not isinstance(c, dict):
                continue
            code = (c.get("code") or "").strip()
            msg = (c.get("message") or "").strip()
            refs = c.get("references") or c.get("department") or ""
            if isinstance(refs, list):
                refs = ", ".join(str(x) for x in refs if x)
            elif refs is not None and not isinstance(refs, str):
                refs = str(refs)
            if code == "item.attributes.missing_required" and msg:
                partes.append(msg)
            elif code == "body.required_fields" and msg:
                partes.append(msg)
            elif code == "body.invalid_fields" and msg:
                partes.append(msg)
            elif msg:
                extra = f" ({refs})" if refs else ""
                partes.append(f"{code}: {msg}{extra}" if code else f"{msg}{extra}")
        if partes:
            # dedupe mantendo ordem
            vistos: set[str] = set()
            unicos = []
            for p in partes:
                if p not in vistos:
                    vistos.add(p)
                    unicos.append(p)
            return f"Mercado Livre ({status}): " + "; ".join(unicos[:3])
        msg = (data.get("message") or "").strip()
        if msg:
            return f"Mercado Livre ({status}): {msg}"
    except (TypeError, ValueError, json.JSONDecodeError, AttributeError):
        pass
    return f"Mercado Livre API ({status}): {(text or '')[:280]}"


def _erro_ml_para_usuario(texto: str) -> str:
    """Traduz erros técnicos da API ML para mensagens claras."""
    t = (texto or "").strip()
    if t.lower().startswith("mercado livre"):
        partes = t.split(":", 1)
        if len(partes) > 1:
            t = partes[1].strip()
    low = t.lower()
    if "gtin" in low and ("required" in low or "missing" in low or "conditional" in low):
        return (
            "Código GTIN/EAN obrigatório nesta categoria. "
            "Cadastre o código de barras no produto ou informe que ele não possui GTIN."
        )
    if "family_name" in low or "family name" in low:
        if "length" in low or "caracter" in low:
            return (
                f"Nome da família muito longo (máx. {_ML_FAMILY_NAME_MAX} caracteres). "
                "Encurte o nome do produto e tente de novo."
            )
        return (
            "O Mercado Livre rejeitou o nome do anúncio (família/título). "
            "Confira o nome do produto e se a categoria está mapeada."
        )
    if "properties [title]" in low or (
        "title" in low and ("contain" in low or "required" in low or "missing" in low)
    ):
        return (
            "O Mercado Livre exigiu o título do anúncio. "
            "Tente exportar de novo; se persistir, reconecte a conta ML."
        )
    if "description.type.invalid" in low or (
        "description" in low and "plain text" in low
    ):
        return (
            "A descrição do produto ainda tem formatação/HTML que o Mercado Livre não aceita. "
            "Reexporte após a correção automática, ou edite a descrição em texto simples."
        )
    if "imagem" in low or "pictures" in low or "picture" in low:
        return "Foto pública obrigatória. Adicione uma imagem ao produto antes de publicar."
    if "preço" in low or "price" in low:
        return "Preço de venda inválido ou abaixo do mínimo permitido pelo Mercado Livre."
    if "categoria" in low or "category" in low:
        return "Categoria não configurada. Associe ao produto e mapeie em Integrações → Mercado Livre."
    if (
        "mapeie" in low
        or "mapear categorias" in low
        or "associe uma categoria" in low
        or "ainda não está mapeada" in low
    ):
        return t
    if "validation_error" in low:
        # remove ruído técnico
        t = t.replace("validation_error;", "").replace("validation_error", "").strip(" ;")
    if len(t) > 220:
        t = t[:217] + "…"
    return t or "Não foi possível publicar este produto no Mercado Livre."


def _titulo_exibicao_ml(titulo: str, sku: str) -> str:
    nome = (titulo or sku or "Produto").strip()
    return nome[:80]


_ML_TITULO_PROMO_RE = re.compile(
    r"\b("
    r"frete\s*gr[aá]tis|envio\s*gr[aá]tis|promo[cç][aã]o|oferta|desconto|"
    r"imperd[ií]vel|liquidação|liquidacao|super\s*oferta|"
    r"parcelamento|sem\s*juros|100%\s*original|"
    r"produto\s*novo|seminovo"
    r")\b",
    re.IGNORECASE,
)


def _truncar_titulo_ml(texto: str, max_len: int) -> str:
    t = (texto or "").strip()
    if len(t) <= max_len:
        return t
    corte = t[: max_len + 1]
    if " " in corte:
        corte = corte.rsplit(" ", 1)[0]
    return (corte or t[:max_len]).strip()[:max_len]


def _normalizar_titulo_ml(titulo: str, *, max_len: int = 60) -> str:
    """
    Padroniza título/family_name para o Mercado Livre:
    texto limpo, sem HTML/símbolos, até max_len (padrão 60).
    """
    t = _texto_plano_ml(titulo)
    if not t:
        return "Produto"

    t = _ML_TITULO_PROMO_RE.sub(" ", t)
    # ML recomenda separar só com espaços — sem pontuação/símbolos.
    t = t.replace("_", " ")
    t = re.sub(r"[^\w\s%]", " ", t, flags=re.UNICODE)
    t = t.replace("_", " ")
    t = re.sub(r"\s+", " ", t).strip()

    letras = [c for c in t if c.isalpha()]
    if letras and (sum(1 for c in letras if c.isupper()) / len(letras)) >= 0.8:
        # Evita título gritado em CAPS.
        t = t.title()
        for particula in (" Da ", " De ", " Do ", " Das ", " Dos ", " E ", " Em ", " Com "):
            t = t.replace(particula, particula.lower())

    t = _truncar_titulo_ml(t, max_len)
    return t or "Produto"


def _seller_usa_user_products_ml(
    cur, id_tenant: int, ml_user_id: int, site_id: str = "MLB"
) -> bool:
    """Só ativa User Products quando a conta ML realmente tem a tag.

    Antes forçávamos UP em todo MLB; contas clássicas recebiam family_name
    sem title e o ML respondia «title missing / family name invalid».
    """
    _ = site_id  # reservado para regras futuras por site
    if id_tenant in _SELLER_UP_CACHE:
        return _SELLER_UP_CACHE[id_tenant]
    usa_up = False
    try:
        info = api_request(cur, id_tenant, "GET", f"/users/{int(ml_user_id)}")
        tags = info.get("tags") or []
        usa_up = "user_product_seller" in tags
    except RuntimeError:
        pass
    _SELLER_UP_CACHE[id_tenant] = usa_up
    return usa_up


def _moeda_site(site_id: str) -> str:
    return _ML_CURRENCY_SITE.get((site_id or "MLB").upper(), "BRL")


def _condicao_ml(condicao: str | None) -> str:
    c = (condicao or "").strip().lower()
    if c in ("usado", "used", "seminovo", "recondicionado"):
        return "used"
    return "new"


def _imagem_publica_ml(imagem_path: str | None) -> str:
    """URL pública estável (pipeline JPG compartilhado)."""
    from api.bling.imagens_export import preparar_imagem_export

    prep = preparar_imagem_export(imagem_path)
    return str(prep.get("url") or "") if prep.get("ok") else ""


_ML_MAX_PICTURES = 12


def _texto_plano_ml(texto: str | None) -> str:
    """Converte HTML da vitrine em plain_text aceito pela API de descrição do ML."""
    from html.parser import HTMLParser

    class _StripHtml(HTMLParser):
        def __init__(self) -> None:
            super().__init__(convert_charrefs=True)
            self.parts: list[str] = []

        def handle_data(self, data: str) -> None:
            if data:
                self.parts.append(data)

        def handle_starttag(self, tag: str, attrs) -> None:
            if tag.lower() in ("br", "p", "div", "li", "tr", "h1", "h2", "h3", "h4", "hr"):
                self.parts.append("\n")

        def handle_endtag(self, tag: str) -> None:
            if tag.lower() in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4"):
                self.parts.append("\n")

        def handle_startendtag(self, tag: str, attrs) -> None:
            if tag.lower() in ("br", "hr"):
                self.parts.append("\n")

    t = (texto or "").strip()
    if not t:
        return ""

    # Entidades HTML podem estar “duplas” no banco (&amp;lt; …).
    for _ in range(3):
        novo = unescape(t)
        if novo == t:
            break
        t = novo

    try:
        parser = _StripHtml()
        parser.feed(t)
        parser.close()
        t = "".join(parser.parts)
    except Exception:
        t = re.sub(r"(?is)<script[^>]*>.*?</script>", "", t)
        t = re.sub(r"(?is)<style[^>]*>.*?</style>", "", t)
        t = re.sub(r"(?i)<br\s*/?>", "\n", t)
        t = re.sub(r"(?i)</(?:p|div|li|h[1-6])\s*>", "\n", t)
        t = re.sub(r"<[^>]*>", "", t)

    # ML trata qualquer < > como marcação — remove restos.
    t = t.replace("<", " ").replace(">", " ")
    t = (
        t.replace("\u00a0", " ")
        .replace("\u200b", "")
        .replace("\u200c", "")
        .replace("\u200d", "")
        .replace("\ufeff", "")
    )
    limpo: list[str] = []
    for ch in t:
        o = ord(ch)
        if ch == "\n":
            limpo.append("\n")
        elif ch == "\r":
            limpo.append("\n")
        elif ch == "\t":
            limpo.append(" ")
        elif o < 32 or o == 127:
            limpo.append(" ")
        else:
            limpo.append(ch)
    t = "".join(limpo)
    t = re.sub(r"[ \t]+\n", "\n", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def _caminhos_galeria_ml(
    cur,
    *,
    id_produto: int,
    id_variante: int,
    imagem_fallback: str = "",
) -> list[str]:
    from api.bling.imagens_export import coletar_caminhos_galeria_export

    return coletar_caminhos_galeria_export(
        cur,
        id_produto=int(id_produto),
        id_variante=int(id_variante),
        imagem_fallback=imagem_fallback or "",
    )


def _upload_picture_ml(cur, id_tenant: int, arquivo: Path) -> str | None:
    """Sobe arquivo local para o CDN do ML; retorna picture id."""
    token = obter_access_token_valido(cur, id_tenant)
    try:
        with arquivo.open("rb") as fh:
            r = requests.post(
                f"{ML_API_BASE}/pictures/items/upload",
                headers={"Authorization": f"Bearer {token}"},
                files={"file": (arquivo.name, fh)},
                timeout=ML_API_TIMEOUT,
            )
    except requests.RequestException as e:
        _log.warning("Falha upload foto ML (%s): %s", arquivo.name, e)
        return None
    if r.status_code >= 400:
        _log.warning(
            "Upload foto ML rejeitado (%s): %s %s",
            arquivo.name,
            r.status_code,
            (r.text or "")[:300],
        )
        return None
    try:
        data = r.json() if r.content else {}
    except ValueError:
        return None
    pid = str((data or {}).get("id") or "").strip()
    return pid or None


def _coletar_pictures_ml(
    cur,
    id_tenant: int,
    *,
    id_produto: int,
    id_variante: int,
    imagem_fallback: str = "",
) -> list[dict[str, str]]:
    """
    Monta pictures do anúncio.
    1) Normaliza JPG (pipeline compartilhado)
    2) Prefere upload multipart do cache JPG
    3) Fallback: source com URL pública assinada
    """
    from api.bling.imagens_export import caminho_arquivo_cache, preparar_imagem_export

    pictures: list[dict[str, str]] = []
    vistos: set[str] = set()
    for caminho in _caminhos_galeria_ml(
        cur,
        id_produto=int(id_produto),
        id_variante=int(id_variante),
        imagem_fallback=imagem_fallback or "",
    ):
        chave = (caminho or "").strip().lower()
        if not chave or chave in vistos:
            continue
        vistos.add(chave)

        prep = preparar_imagem_export(caminho)
        if not prep.get("ok"):
            continue

        local = caminho_arquivo_cache(prep.get("cache"))
        if local is not None:
            pic_id = _upload_picture_ml(cur, id_tenant, local)
            if pic_id:
                pictures.append({"id": pic_id})
                if len(pictures) >= _ML_MAX_PICTURES:
                    break
                continue

        url = str(prep.get("url") or "").strip()
        if not url or url in vistos:
            continue
        vistos.add(url)
        pictures.append({"source": url})
        if len(pictures) >= _ML_MAX_PICTURES:
            break
    return pictures


def _enviar_descricao_ml(cur, id_tenant: int, item_id: str, descricao: str) -> None:
    texto = _texto_plano_ml(descricao)
    if not texto:
        return
    body = {"plain_text": texto[:50000]}
    params = {"api_version": "2"}
    try:
        api_request(
            cur,
            id_tenant,
            "PUT",
            f"/items/{item_id}/description",
            params=params,
            json_body=body,
        )
    except RuntimeError:
        api_request(
            cur,
            id_tenant,
            "POST",
            f"/items/{item_id}/description",
            params=params,
            json_body=body,
        )


def _atualizar_anuncio_completo_ml(
    cur,
    id_tenant: int,
    ml_item_id: str,
    *,
    id_variante: int,
    id_produto: int,
    sku: str,
    preco: float,
    descricao: str,
    imagem: str,
    estoque: int,
    marca: str = "",
    gtin: str = "",
    condicao: str | None = None,
    altura_cm: float | None = None,
    largura_cm: float | None = None,
    profundidade_cm: float | None = None,
    peso_kg: float | None = None,
    titulo: str = "",
    attrs_variacao_dn: dict[str, str] | None = None,
    garantia_tipo: str = "",
    garantia_tempo: str = "",
    video_youtube: str = "",
    cfg: dict | None = None,
    ncm: str = "",
    cest: str = "",
    origem_fiscal: str = "",
    producao: str = "",
    unidade: str = "UN",
    preco_custo: float | None = None,
    peso_liquido_kg: float | None = None,
    peso_bruto_kg: float | None = None,
) -> None:
    """Atualiza anúncio já vinculado: preço, estoque, fotos, descrição, attrs, garantia e vídeo."""
    from api.mercado_livre.eco_estoque import registrar_eco_ml_pendente

    ml_item_id = (ml_item_id or "").strip()
    if not ml_item_id:
        raise RuntimeError("Anúncio ML não informado.")

    pictures = _coletar_pictures_ml(
        cur,
        id_tenant,
        id_produto=int(id_produto),
        id_variante=int(id_variante),
        imagem_fallback=imagem or "",
    )
    payload: dict[str, Any] = {}
    if preco and float(preco) > 0:
        payload["price"] = round(float(preco), 2)
    payload["available_quantity"] = max(0, int(estoque or 0))
    if pictures:
        payload["pictures"] = pictures

    estado = _estado_anuncio_ml(cur, id_tenant, ml_item_id)
    category_id = str(estado.get("category_id") or "").strip()
    cat_attrs = _attrs_categoria_ml(cur, id_tenant, category_id) if category_id else []

    attrs = _montar_atributos_obrigatorios_ml(
        cat_attrs,
        marca=marca or "",
        gtin=gtin or "",
        titulo=titulo or "",
        sku=sku or "",
        condicao=condicao or "",
        altura_cm=altura_cm,
        largura_cm=largura_cm,
        profundidade_cm=profundidade_cm,
        peso_kg=peso_kg,
        so_pacote=True,
        attrs_variacao_dn=attrs_variacao_dn or {},
    )
    if attrs:
        payload["attributes"] = attrs

    cfg = cfg or {}
    gar_tipo = (garantia_tipo or cfg.get("garantia_tipo_padrao") or "").strip()
    gar_tempo = (garantia_tempo or cfg.get("garantia_tempo_padrao") or "").strip()
    if category_id and (gar_tipo or gar_tempo):
        sale_terms = _montar_sale_terms_ml(
            cur,
            id_tenant,
            category_id,
            garantia_tipo=gar_tipo,
            garantia_tempo=gar_tempo,
        )
        if sale_terms:
            payload["sale_terms"] = sale_terms

    registrar_eco_ml_pendente(
        cur,
        id_tenant,
        ml_item_id=ml_item_id,
        quantidade_esperada=max(0, int(estoque or 0)),
        origem="dropnexo_export",
    )
    if payload:
        try:
            api_request(cur, id_tenant, "PUT", f"/items/{ml_item_id}", json_body=payload)
        except RuntimeError as e:
            msg = str(e).lower()
            if payload.get("sale_terms") and (
                "sale_term" in msg or "warranty" in msg or "garantia" in msg
            ):
                payload.pop("sale_terms", None)
                api_request(cur, id_tenant, "PUT", f"/items/{ml_item_id}", json_body=payload)
            else:
                raise

    video_id = _extrair_youtube_id_ml(video_youtube)
    if video_id:
        try:
            api_request(
                cur,
                id_tenant,
                "PUT",
                f"/items/{ml_item_id}",
                json_body={"video_id": video_id},
            )
        except RuntimeError as e:
            _log.info("Vídeo ML não atualizado em %s: %s", ml_item_id, e)

    titulo_limpo = _normalizar_titulo_ml(titulo or "", max_len=60)
    if titulo_limpo and titulo_limpo != "Produto":
        try:
            api_request(
                cur,
                id_tenant,
                "PUT",
                f"/items/{ml_item_id}",
                json_body={"title": titulo_limpo},
            )
        except RuntimeError as e:
            # User Products / moderação pode bloquear alteração de título.
            _log.info("Título ML não atualizado em %s: %s", ml_item_id, e)

    texto = _texto_plano_ml(descricao)
    if texto:
        _enviar_descricao_ml(cur, id_tenant, ml_item_id, texto)
    else:
        _log.info("ML item %s: descrição vazia no DropNexo — não enviada.", ml_item_id)

    _salvar_map_produto_ml(
        cur, id_tenant, int(id_variante), int(id_produto), sku or "", ml_item_id
    )

    if _ncm_ml(ncm) and (sku or "").strip():
        try:
            _enviar_dados_fiscais_ml(
                cur,
                id_tenant,
                sku=sku or "",
                titulo=titulo or sku or "",
                ml_item_id=ml_item_id,
                ncm=ncm,
                cest=cest,
                origem_fiscal=origem_fiscal,
                producao=producao,
                gtin=gtin or "",
                unidade=unidade or "UN",
                custo=preco_custo,
                peso_liquido_kg=peso_liquido_kg or peso_kg,
                peso_bruto_kg=peso_bruto_kg or peso_kg,
            )
        except RuntimeError as e:
            _log.warning("Dados fiscais ML não enviados para %s: %s", ml_item_id, e)
            raise RuntimeError(
                f"Anúncio atualizado, mas dados fiscais (NCM/CEST/origem) falharam: "
                f"{_erro_ml_para_usuario(str(e)[:300])}. "
                "Confira a aba Tributação e sincronize novamente."
            ) from e


def _item_ja_vinculado_ml(cur, id_tenant: int, id_variante: int) -> str | None:
    cur.execute(
        """
        SELECT id_bling FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'mercado_livre' AND contexto = 'vendedor'
          AND entidade = 'produto' AND id_dropnexo = %s
        LIMIT 1
        """,
        (id_tenant, id_variante),
    )
    row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _prever_categoria_ml(cur, id_tenant: int, site_id: str, titulo: str) -> str | None:
    titulo = (titulo or "").strip()
    if not titulo:
        return None
    try:
        data = api_request(
            cur,
            id_tenant,
            "GET",
            f"/sites/{site_id}/domain_discovery/search",
            params={"q": titulo[:200], "limit": 1},
        )
        if isinstance(data, list) and data:
            cat = (data[0] or {}).get("category_id")
            return str(cat).strip() if cat else None
    except RuntimeError:
        pass
    return None


def _garantir_tabela_ml_categoria_map(cur) -> bool:
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tbl_integracao_ml_categoria_map (
                id SERIAL PRIMARY KEY,
                id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
                id_categoria INTEGER NOT NULL REFERENCES tbl_categoria(id) ON DELETE CASCADE,
                ml_category_id VARCHAR(32) NOT NULL,
                family_name VARCHAR(120),
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


def _family_name_ml(titulo: str, marca: str, override: str = "") -> str:
    """Monta family_name a partir do nome do produto (campo nome / vitrine).

    Override do mapeamento só entra se for um texto útil (≥ 3 chars).
    """
    ov = (override or "").strip()
    if len(ov) >= 3:
        return _normalizar_titulo_ml(ov, max_len=_ML_FAMILY_NAME_MAX)
    marca = (marca or "").strip()
    titulo = _normalizar_titulo_ml(titulo or "", max_len=_ML_FAMILY_NAME_MAX)
    if marca and titulo and not titulo.lower().startswith(marca.lower()):
        fam = f"{marca} {titulo}"
    else:
        fam = titulo or marca or "Produto"
    out = _normalizar_titulo_ml(fam, max_len=_ML_FAMILY_NAME_MAX)
    return out if len(out) >= 3 else "Produto"


def _mapa_categoria_ml(cur, id_tenant: int, id_categoria: int | None) -> tuple[str, str]:
    if not id_categoria:
        return "", ""
    _garantir_tabela_ml_categoria_map(cur)
    try:
        cur.execute(
            """
            SELECT ml_category_id, COALESCE(family_name, '')
            FROM tbl_integracao_ml_categoria_map
            WHERE id_tenant = %s AND id_categoria = %s
            """,
            (id_tenant, int(id_categoria)),
        )
        row = cur.fetchone()
        if row and row[0]:
            return str(row[0]).strip(), (row[1] or "").strip()
    except Exception:
        pass
    return "", ""


def listar_mapeamento_categorias_ml(cur, id_tenant: int) -> list[dict]:
    _garantir_tabela_ml_categoria_map(cur)
    cfg = carregar_config_ml(cur, id_tenant)
    site_id = (cfg.get("ml_site_id") or "MLB").upper()
    try:
        from sistema.tarefas_secundarias.servico import garantir_tabelas_tarefas

        garantir_tabelas_tarefas(cur)
        cur.execute(
            """
            SELECT c.id, c.nome,
                   COALESCE(m.ml_category_id, ''),
                   COALESCE(m.family_name, ''),
                   COALESCE(ch.nome, '')
            FROM tbl_categoria c
            LEFT JOIN tbl_integracao_ml_categoria_map m
                ON m.id_categoria = c.id AND m.id_tenant = c.id_tenant
            LEFT JOIN tbl_ml_categoria_cache ch
                ON ch.site_id = %s
               AND ch.category_id = UPPER(TRIM(COALESCE(m.ml_category_id, '')))
            WHERE c.id_tenant = %s AND c.ativo = TRUE
            ORDER BY c.nome
            """,
            (site_id, id_tenant),
        )
        return [
            {
                "id_categoria": int(r[0]),
                "nome": r[1],
                "ml_category_id": r[2] or "",
                "family_name": r[3] or "",
                "ml_category_nome": (r[4] or "").strip(),
                "ml_site_id": site_id,
            }
            for r in cur.fetchall()
        ]
    except Exception:
        _log.debug("Cache ML indisponível no mapeamento; fallback sem nome", exc_info=True)
        cur.execute(
            """
            SELECT c.id, c.nome,
                   COALESCE(m.ml_category_id, ''),
                   COALESCE(m.family_name, '')
            FROM tbl_categoria c
            LEFT JOIN tbl_integracao_ml_categoria_map m
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
                "ml_category_id": r[2] or "",
                "family_name": r[3] or "",
                "ml_category_nome": "",
                "ml_site_id": site_id,
            }
            for r in cur.fetchall()
        ]


def salvar_mapeamento_categorias_ml(cur, id_tenant: int, itens: list[dict]) -> int:
    if not _garantir_tabela_ml_categoria_map(cur):
        raise RuntimeError("Tabela de mapeamento ML indisponível. Aplique o SQL 073.")
    salvos = 0
    agora = agora_utc()
    for item in itens:
        try:
            id_cat = int(item.get("id_categoria") or 0)
        except (TypeError, ValueError):
            continue
        ml_cat = (item.get("ml_category_id") or "").strip().upper()
        if not id_cat or not ml_cat:
            continue
        cur.execute(
            "SELECT 1 FROM tbl_categoria WHERE id = %s AND id_tenant = %s AND ativo = TRUE",
            (id_cat, id_tenant),
        )
        if not cur.fetchone():
            continue
        # Família não é mais editada nesta tela; preserva valor já salvo se omitida.
        if "family_name" in item:
            familia = (item.get("family_name") or "").strip()[:_ML_FAMILY_NAME_MAX] or None
        else:
            familia = None
        cur.execute(
            """
            INSERT INTO tbl_integracao_ml_categoria_map (
                id_tenant, id_categoria, ml_category_id, family_name, atualizado_em
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id_tenant, id_categoria) DO UPDATE SET
                ml_category_id = EXCLUDED.ml_category_id,
                family_name = COALESCE(EXCLUDED.family_name, tbl_integracao_ml_categoria_map.family_name),
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_tenant, id_cat, ml_cat, familia, agora),
        )
        salvos += 1
    return salvos


def _norm_txt_ml(texto: str) -> str:
    s = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", s).strip()


def _score_nome_categoria_ml(cat_nome: str, termo: str) -> int:
    a, b = _norm_txt_ml(cat_nome), _norm_txt_ml(termo)
    if not a or not b:
        return 0
    if a == b:
        return 100
    if b in a or a in b:
        return 85
    ta, tb = set(a.split()), set(b.split())
    if not tb:
        return 0
    return int((len(ta & tb) / len(tb)) * 70)


def _titulos_amostra_categoria_vendedor(
    cur, id_tenant: int, id_categoria: int | None, limite: int = 4
) -> list[str]:
    if not id_categoria:
        return []
    try:
        cur.execute(
            """
            SELECT DISTINCT COALESCE(NULLIF(TRIM(pv.nome_vitrine), ''), NULLIF(TRIM(p.nome), ''))
            FROM tbl_produto_vendedor pv
            INNER JOIN tbl_produto p ON p.id = pv.id_produto
            WHERE pv.id_tenant_vendedor = %s
              AND pv.id_categoria_vendedor = %s
              AND COALESCE(NULLIF(TRIM(pv.nome_vitrine), ''), NULLIF(TRIM(p.nome), '')) IS NOT NULL
            ORDER BY 1
            LIMIT %s
            """,
            (int(id_tenant), int(id_categoria), max(1, min(int(limite), 8))),
        )
        return [str(r[0]).strip() for r in cur.fetchall() if r and r[0]]
    except Exception:
        _log.debug("Amostra de títulos por categoria ML indisponível", exc_info=True)
        return []


def _domain_discovery_categorias(
    cur, id_tenant: int, site_id: str, termo: str, limit: int
) -> list[dict]:
    data = api_request(
        cur,
        id_tenant,
        "GET",
        f"/sites/{site_id}/domain_discovery/search",
        params={"q": termo[:120], "limit": max(1, min(int(limit), 8))},
        timeout=ML_API_TIMEOUT_RAPIDO,
    )
    out: list[dict] = []
    for item in data or []:
        if not isinstance(item, dict):
            continue
        cat_id = str(item.get("category_id") or "").strip().upper()
        if not cat_id:
            continue
        nome = (
            item.get("category_name")
            or item.get("domain_name")
            or item.get("category_id")
            or ""
        )
        out.append(
            {
                "category_id": cat_id,
                "nome": str(nome).strip() or cat_id,
                "fonte": "predictor",
                "score": 90,
            }
        )
    return out


def buscar_categorias_ml(
    cur,
    id_tenant: int,
    termo: str,
    limit: int = 8,
    id_categoria: int | None = None,
) -> list[dict]:
    """Sugere categorias ML via predictor (rápido).

    No máximo 2 chamadas ao ML: termo + 1 título de produto se o termo vier vazio.
    Levanta RuntimeError se a API ML falhar (token/rede/erro HTTP).
    """
    termo = (termo or "").strip()
    if len(termo) < 3:
        return []
    cfg = carregar_config_ml(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("Mercado Livre não conectado.")
    site_id = (cfg.get("ml_site_id") or "MLB").upper()
    lim = max(1, min(int(limit or 8), 8))

    candidatos: list[dict] = []
    vistos: set[str] = set()

    def _add(itens: list[dict]) -> None:
        for item in itens:
            cat_id = str(item.get("category_id") or "").strip().upper()
            nome = str(item.get("nome") or "").strip()
            if not cat_id or cat_id in vistos or not nome:
                continue
            vistos.add(cat_id)
            candidatos.append(item)

    # 1) Cache local (nome legível) — preferido para o usuário.
    try:
        from sistema.tarefas_secundarias.servico import (
            buscar_categorias_cache,
            nome_categoria_cache,
        )

        for h in buscar_categorias_cache(cur, site_id, termo, limit=lim):
            _add(
                [
                    {
                        "category_id": h["category_id"],
                        "nome": h["nome"],
                        "fonte": "cache",
                        "score": 100 + _score_nome_categoria_ml(h["nome"], termo),
                    }
                ]
            )
    except Exception:
        nome_categoria_cache = None  # type: ignore
        _log.debug("Cache ML indisponível na sugestão", exc_info=True)

    termos_busca: list[str] = [termo]
    if len(termo.split()) <= 1:
        for tit in _titulos_amostra_categoria_vendedor(cur, id_tenant, id_categoria, limite=1):
            if tit and _norm_txt_ml(tit) != _norm_txt_ml(termo):
                termos_busca.append(tit)
                break

    ultimo_erro: Exception | None = None
    predictor_ok = False
    if len(candidatos) < lim:
        for t in termos_busca[:2]:
            try:
                pred = _domain_discovery_categorias(cur, id_tenant, site_id, t, lim)
                for p in pred:
                    cat_id = str(p.get("category_id") or "").strip().upper()
                    nome = str(p.get("nome") or "").strip()
                    if nome_categoria_cache and cat_id:
                        nome_cache = nome_categoria_cache(cur, site_id, cat_id)
                        if nome_cache:
                            nome = nome_cache
                    if not nome:
                        continue
                    _add(
                        [
                            {
                                "category_id": cat_id,
                                "nome": nome,
                                "fonte": "predictor",
                                "score": int(p.get("score") or 90),
                            }
                        ]
                    )
                predictor_ok = True
            except RuntimeError as e:
                ultimo_erro = e
                _log.warning("domain_discovery ML falhou para %r: %s", t, e)
            if len(candidatos) >= lim:
                break

    if not candidatos and not predictor_ok and ultimo_erro:
        raise RuntimeError(str(ultimo_erro))

    for item in candidatos:
        item["score"] = int(item.get("score") or 0) + _score_nome_categoria_ml(
            str(item.get("nome") or ""), termo
        )

    candidatos.sort(key=lambda x: (-int(x.get("score") or 0), x.get("nome") or ""))
    return [
        {
            "category_id": c["category_id"],
            "nome": c["nome"],
            "fonte": c.get("fonte") or "predictor",
            "score": int(c.get("score") or 0),
        }
        for c in candidatos[:lim]
        if str(c.get("nome") or "").strip()
    ]


def prefetch_sugestoes_categorias_ml(
    cur, id_tenant: int, categorias: list[dict], *, limit: int = 6
) -> list[dict]:
    """Pré-carrega sugestões para várias categorias do vendedor (1 call ML cada)."""
    out: list[dict] = []
    for item in categorias or []:
        try:
            id_cat = int(item.get("id_categoria") or 0)
        except (TypeError, ValueError):
            continue
        nome = (item.get("nome") or "").strip()
        if not id_cat or len(nome) < 3:
            continue
        try:
            itens = buscar_categorias_ml(
                cur, id_tenant, nome, limit=limit, id_categoria=id_cat
            )
            out.append(
                {
                    "id_categoria": id_cat,
                    "nome": nome,
                    "itens": itens,
                    "ok": True,
                    "message": "" if itens else f"Nenhuma sugestão para «{nome}».",
                }
            )
        except RuntimeError as e:
            out.append(
                {
                    "id_categoria": id_cat,
                    "nome": nome,
                    "itens": [],
                    "ok": False,
                    "message": str(e)[:240],
                }
            )
    return out


def _resolver_categoria_ml(
    cur,
    id_tenant: int,
    site_id: str,
    id_categoria_vendedor: int | None,
    titulo: str,
) -> tuple[str, str]:
    ml_cat, familia = _mapa_categoria_ml(cur, id_tenant, id_categoria_vendedor)
    if ml_cat:
        return ml_cat, familia
    prevista = _prever_categoria_ml(cur, id_tenant, site_id, titulo)
    return (prevista or ""), ""


def _extrair_listing_type_id(item) -> str:
    """Normaliza id de tipo de anúncio (string ou objeto da API ML)."""
    if item is None:
        return ""
    if isinstance(item, str):
        return item.strip()
    if isinstance(item, dict):
        lid = item.get("id") or item.get("listing_type_id")
        return str(lid).strip() if lid else ""
    return ""


def _tipos_listing_disponiveis_ml(
    cur,
    id_tenant: int,
    ml_user_id: int,
    category_id: str,
) -> list[str]:
    ids: list[str] = []
    try:
        cat = api_request(cur, id_tenant, "GET", f"/categories/{category_id}")
        tipos = cat.get("listing_types") or []
        for t in tipos:
            lid = _extrair_listing_type_id(t)
            if lid:
                ids.append(lid)
        if ids:
            return list(dict.fromkeys(ids))
    except RuntimeError:
        pass
    try:
        data = api_request(
            cur,
            id_tenant,
            "GET",
            f"/users/{int(ml_user_id)}/available_listing_types",
            params={"category_id": category_id},
        )
        disponiveis = data.get("available") or []
        disp_ids = [_extrair_listing_type_id(x) for x in disponiveis]
        disp_ids = [x for x in disp_ids if x]
        if disp_ids:
            return list(dict.fromkeys(disp_ids))
    except RuntimeError:
        pass
    return []


def _resolver_listing_type_ml(
    cur,
    id_tenant: int,
    ml_user_id: int,
    category_id: str,
    preferido: str = "auto",
) -> str:
    pref = (preferido or "auto").strip()
    disponiveis = _tipos_listing_disponiveis_ml(cur, id_tenant, ml_user_id, category_id)

    if pref == "auto" or not pref:
        if not disponiveis:
            return "gold_special"
        for prefer in ("gold_special", "gold_pro", "gold_premium", "free"):
            if prefer in disponiveis:
                return prefer
        return disponiveis[0]

    if pref not in _ML_LISTING_TYPES:
        return _resolver_listing_type_ml(cur, id_tenant, ml_user_id, category_id, "auto")

    if not disponiveis:
        return pref

    if pref not in disponiveis:
        nomes = ", ".join(_nome_listing_type_ml(x) for x in disponiveis)
        if pref == "free":
            raise RuntimeError(
                "Esta categoria não aceita anúncio Grátis no Mercado Livre. "
                f"Tipos permitidos: {nomes}. "
                "Altere o tipo em Integrações → Mercado Livre ou use Automático/Clássico."
            )
        raise RuntimeError(
            f"Tipo «{_nome_listing_type_ml(pref)}» indisponível nesta categoria. "
            f"Permitidos: {nomes}."
        )
    return pref


def _listing_type_ml(
    cur,
    id_tenant: int,
    ml_user_id: int,
    category_id: str,
    preferido: str = "auto",
) -> str:
    return _resolver_listing_type_ml(cur, id_tenant, ml_user_id, category_id, preferido)


def _montar_shipping_ml(frete_gratis: bool) -> dict[str, Any]:
    return {
        "mode": "me2",
        "local_pick_up": False,
        "free_shipping": bool(frete_gratis),
    }


def _nome_listing_type_ml(listing_type_id: str) -> str:
    nomes = {
        "gold_special": "Clássico",
        "gold_pro": "Premium",
        "gold_premium": "Premium",
        "free": "Grátis",
    }
    return nomes.get((listing_type_id or "").strip(), listing_type_id or "—")


def _estado_anuncio_ml(cur, id_tenant: int, item_id: str) -> dict[str, Any]:
    try:
        data = api_request(cur, id_tenant, "GET", f"/items/{item_id}")
        if not isinstance(data, dict):
            return {}
        return {
            "status": data.get("status") or "",
            "sub_status": data.get("sub_status") or [],
            "category_id": data.get("category_id") or "",
            "listing_type_id": data.get("listing_type_id") or "",
        }
    except RuntimeError:
        return {}


def _mensagem_pos_publicacao_ml(estado: dict[str, Any], category_id: str) -> str:
    st = (estado.get("status") or "").lower()
    subs = [str(s).lower() for s in (estado.get("sub_status") or [])]
    cat = estado.get("category_id") or category_id or ""
    tipo = _nome_listing_type_ml(estado.get("listing_type_id") or "")
    base = f"Categoria ML: {cat}." if cat else ""
    tipo_txt = f" Tipo: {tipo}." if tipo and tipo != "—" else ""

    if st == "active":
        return f"Anúncio ativo no Mercado Livre.{tipo_txt} {base}".strip()
    if st == "under_review" or any("picture" in s or "moderation" in s for s in subs):
        return (
            "Anúncio criado. O Mercado Livre está revisando as fotos — "
            "costuma levar algumas horas para ficar ativo."
            f"{tipo_txt} {base}"
        ).strip()
    if st == "paused":
        return (
            "Anúncio criado, mas aparece como pausado/inativo no Mercado Livre. "
            "Se a revisão de fotos terminar, ative pelo painel do ML ou aguarde."
            f"{tipo_txt} {base}"
        ).strip()
    return f"Anúncio criado no Mercado Livre.{tipo_txt} {base}".strip()


def _tentar_ativar_anuncio_ml(cur, id_tenant: int, item_id: str) -> None:
    try:
        api_request(cur, id_tenant, "PUT", f"/items/{item_id}", json_body={"status": "active"})
    except RuntimeError:
        pass


def _attrs_categoria_ml(cur, id_tenant: int, category_id: str) -> list[dict]:
    if category_id in _ML_ATTR_CACHE:
        return _ML_ATTR_CACHE[category_id]
    try:
        data = api_request(cur, id_tenant, "GET", f"/categories/{category_id}/attributes")
        attrs = data if isinstance(data, list) else []
    except RuntimeError:
        attrs = []
    _ML_ATTR_CACHE[category_id] = attrs
    return attrs


def _attr_tags_ml(attr: dict) -> dict:
    """Normaliza tags da categoria ML (dict ou lista)."""
    tags = (attr or {}).get("tags")
    if isinstance(tags, dict):
        return tags
    if isinstance(tags, list):
        return {str(t): True for t in tags if t}
    return {}


def _attr_valor_lista(attr: dict, nome: str) -> dict | None:
    nome_l = (nome or "").strip().lower()
    valores = attr.get("values") or []
    if not isinstance(valores, list):
        return None
    for v in valores:
        if not isinstance(v, dict):
            continue
        if (v.get("name") or "").strip().lower() == nome_l:
            if v.get("id"):
                return {"id": attr["id"], "value_id": v["id"]}
            return {"id": attr["id"], "value_name": v.get("name")}
    for v in valores:
        if not isinstance(v, dict):
            continue
        if v.get("id"):
            return {"id": attr["id"], "value_id": v["id"]}
        if v.get("name"):
            return {"id": attr["id"], "value_name": v["name"]}
    return None


def _attr_valor_texto(attr_id: str, valor: str) -> dict:
    return {"id": attr_id, "value_name": (valor or "")[:255]}


def _atributos_pacote_ml(
    *,
    altura_cm: float | None = None,
    largura_cm: float | None = None,
    profundidade_cm: float | None = None,
    peso_kg: float | None = None,
) -> list[dict]:
    """Dimensões/peso do pacote com unidade (formato aceito pelo ML)."""
    out: list[dict] = []
    if altura_cm is not None and float(altura_cm) > 0:
        out.append(
            _attr_valor_texto("SELLER_PACKAGE_HEIGHT", f"{round(float(altura_cm), 2)} cm")
        )
    if largura_cm is not None and float(largura_cm) > 0:
        out.append(
            _attr_valor_texto("SELLER_PACKAGE_WIDTH", f"{round(float(largura_cm), 2)} cm")
        )
    if profundidade_cm is not None and float(profundidade_cm) > 0:
        out.append(
            _attr_valor_texto(
                "SELLER_PACKAGE_LENGTH", f"{round(float(profundidade_cm), 2)} cm"
            )
        )
    if peso_kg is not None and float(peso_kg) > 0:
        gramas = max(1, int(round(float(peso_kg) * 1000)))
        out.append(_attr_valor_texto("SELLER_PACKAGE_WEIGHT", f"{gramas} g"))
    return out


_ML_ATTR_ALIAS = {
    "cor": "COLOR",
    "color": "COLOR",
    "colour": "COLOR",
    "estampa": "COLOR",
    "tamanho": "SIZE",
    "size": "SIZE",
    "tam": "SIZE",
    "voltagem": "VOLTAGE",
    "voltage": "VOLTAGE",
    "sabor": "FLAVOR",
    "flavor": "FLAVOR",
    "modelo": "MODEL",
    "model": "MODEL",
    "genero": "GENDER",
    "gender": "GENDER",
}


def _parse_atributos_variante_ml(raw) -> dict[str, str]:
    if isinstance(raw, dict):
        src = raw
    elif isinstance(raw, str) and raw.strip():
        try:
            src = json.loads(raw)
        except (TypeError, ValueError):
            return {}
    else:
        return {}
    out: dict[str, str] = {}
    if not isinstance(src, dict):
        return out
    for k, v in src.items():
        nome = str(k or "").strip()
        val = str(v or "").strip()
        if nome and val:
            out[nome] = val
    return out


def _attr_eh_variacao_ml(attr: dict) -> bool:
    tags = _attr_tags_ml(attr)
    if tags.get("allow_variations") or tags.get("variation_attribute"):
        return True
    # Domínios novos: CHILD_PK / PARENT_PK
    hierarchy = str(attr.get("hierarchy") or tags.get("hierarchy") or "").upper()
    return "CHILD" in hierarchy


def _resolver_attr_id_ml(nome_dn: str, cat_attrs: list[dict]) -> str | None:
    """Mapeia rótulo DropNexo (Cor/Tamanho) → id ML (COLOR/SIZE)."""
    chave = re.sub(r"\s+", " ", (nome_dn or "").strip().lower())
    if not chave:
        return None
    alias = _ML_ATTR_ALIAS.get(chave)
    if alias:
        for attr in cat_attrs:
            if (attr.get("id") or "").strip().upper() == alias:
                return alias
    for attr in cat_attrs:
        if not isinstance(attr, dict):
            continue
        aid = (attr.get("id") or "").strip()
        nome_ml = (attr.get("name") or "").strip().lower()
        if not aid:
            continue
        if nome_ml == chave or aid.lower() == chave:
            return aid
        if chave in nome_ml or nome_ml in chave:
            return aid
    return alias


def _atributos_variacao_ml(cat_attrs: list[dict], attrs_dn: dict[str, str]) -> list[dict]:
    """Atributos de variação (CHILD_PK) a partir de v.atributos."""
    out: list[dict] = []
    vistos: set[str] = set()
    var_ids = {
        (a.get("id") or "").strip()
        for a in cat_attrs
        if isinstance(a, dict) and _attr_eh_variacao_ml(a) and a.get("id")
    }
    for nome_dn, valor in (attrs_dn or {}).items():
        aid = _resolver_attr_id_ml(nome_dn, cat_attrs)
        if not aid or aid in vistos:
            continue
        # Se a categoria declara attrs de variação, prioriza esses IDs.
        if var_ids and aid not in var_ids:
            # Ainda envia se o alias for clássico (COLOR/SIZE) — ML costuma aceitar.
            if aid not in ("COLOR", "SIZE", "VOLTAGE", "FLAVOR", "GENDER", "MODEL"):
                continue
        entry = _attr_valor_texto(aid, valor)
        # Tenta value_id quando a categoria traz lista
        for attr in cat_attrs:
            if (attr.get("id") or "").strip() != aid:
                continue
            listed = _attr_valor_lista(attr, valor)
            if listed:
                entry = listed
            break
        out.append(entry)
        vistos.add(aid)
    return out


def _extrair_youtube_id_ml(raw: str | None) -> str:
    s = (raw or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_-]{6,20}", s):
        return s
    m = re.search(
        r"(?:youtu\.be/|youtube\.com/(?:watch\?v=|embed/|shorts/)|v=)([A-Za-z0-9_-]{6,20})",
        s,
    )
    return m.group(1) if m else ""


def _montar_sale_terms_ml(
    cur,
    id_tenant: int,
    category_id: str,
    *,
    garantia_tipo: str = "",
    garantia_tempo: str = "",
) -> list[dict]:
    tipo = (garantia_tipo or "").strip()
    tempo = (garantia_tempo or "").strip()
    if not tipo and not tempo:
        return []
    if not tipo:
        tipo = "Garantia do vendedor"
    if not tempo:
        tempo = "90 dias"

    termos_cat: list[dict] = []
    if category_id:
        try:
            data = api_request(cur, id_tenant, "GET", f"/categories/{category_id}/sale_terms")
            if isinstance(data, list):
                termos_cat = data
        except RuntimeError:
            termos_cat = []

    out: list[dict] = []
    tipo_entry: dict | None = None
    tempo_entry: dict | None = None
    for term in termos_cat:
        if not isinstance(term, dict):
            continue
        tid = (term.get("id") or "").strip()
        if tid == "WARRANTY_TYPE":
            tipo_entry = _attr_valor_lista(term, tipo) or _attr_valor_texto(tid, tipo)
        elif tid == "WARRANTY_TIME":
            tempo_entry = _attr_valor_lista(term, tempo) or _attr_valor_texto(tid, tempo)
    if not tipo_entry:
        tipo_entry = _attr_valor_texto("WARRANTY_TYPE", tipo)
    if not tempo_entry:
        tempo_entry = _attr_valor_texto("WARRANTY_TIME", tempo)
    out.append(tipo_entry)
    out.append(tempo_entry)
    return out


def _so_digitos_fiscal(val: Any) -> str:
    return re.sub(r"\D", "", str(val or ""))


def _ncm_ml(val: Any) -> str:
    d = _so_digitos_fiscal(val)
    return d[:8] if len(d) >= 8 else d


def _cest_ml(val: Any) -> str:
    return _so_digitos_fiscal(val)[:7]


def _origem_detail_ml(val: Any) -> str:
    d = _so_digitos_fiscal(val)
    if d and d[0] in "012345678":
        return d[0]
    return "0"


def _origin_type_ml(origem_fiscal: Any, producao: Any) -> str:
    """manufacturer | reseller | imported — API fiscal MLB."""
    od = _origem_detail_ml(origem_fiscal)
    if od in ("1", "2", "6"):
        return "imported"
    prod = unicodedata.normalize("NFKD", str(producao or ""))
    prod = "".join(c for c in prod if not unicodedata.combining(c)).lower()
    if "propria" in prod or "fabric" in prod:
        return "manufacturer"
    return "reseller"


def _enviar_dados_fiscais_ml(
    cur,
    id_tenant: int,
    *,
    sku: str,
    titulo: str,
    ml_item_id: str,
    ncm: str = "",
    cest: str = "",
    origem_fiscal: str = "",
    producao: str = "",
    gtin: str = "",
    unidade: str = "UN",
    custo: float | None = None,
    peso_liquido_kg: float | None = None,
    peso_bruto_kg: float | None = None,
    variation_id: str | None = None,
) -> dict[str, Any]:
    """Envia NCM/CEST/origem ao Faturador ML e vincula ao anúncio.

    Docs: https://developers.mercadolivre.com.br/pt_br/envio-dos-dados-fiscais
    """
    sku = (sku or "").strip()
    ml_item_id = (ml_item_id or "").strip()
    ncm = _ncm_ml(ncm)
    if not sku:
        raise RuntimeError("SKU obrigatório para enviar dados fiscais ao Mercado Livre.")
    if not ncm:
        raise RuntimeError(
            "NCM obrigatório para o Faturador do Mercado Livre emitir NF-e. "
            "Preencha a aba Tributação do produto."
        )
    if not ml_item_id:
        raise RuntimeError("Anúncio ML não informado para vincular dados fiscais.")

    cest = _cest_ml(cest)
    origin_detail = _origem_detail_ml(origem_fiscal)
    origin_type = _origin_type_ml(origem_fiscal, producao)
    ean = _so_digitos_fiscal(gtin)
    un = (unidade or "UN").strip().upper()[:10] or "UN"
    tax: dict[str, Any] = {
        "ncm": ncm,
        "origin_type": origin_type,
        "origin_detail": origin_detail,
    }
    if cest:
        tax["cest"] = cest
    if ean:
        tax["ean"] = ean
    if peso_liquido_kg and float(peso_liquido_kg) > 0:
        tax["net_weight"] = round(float(peso_liquido_kg), 3)
    if peso_bruto_kg and float(peso_bruto_kg) > 0:
        tax["gross_weight"] = round(float(peso_bruto_kg), 3)

    body: dict[str, Any] = {
        "sku": sku,
        "title": (titulo or sku)[:120],
        "type": "single",
        "measurement_unit": un,
        "tax_information": tax,
    }
    if custo is not None and float(custo) > 0:
        body["cost"] = round(float(custo), 2)

    sku_path = quote(sku, safe="")
    try:
        api_request(cur, id_tenant, "POST", "/items/fiscal_information", json_body=body)
    except RuntimeError as e:
        msg = str(e).lower()
        # Já existe → atualiza
        if "already" in msg or "exist" in msg or "10083" in msg or "duplic" in msg:
            api_request(
                cur,
                id_tenant,
                "PUT",
                f"/items/fiscal_information/{sku_path}",
                json_body=body,
            )
        elif "csosn" in msg:
            # Simples Nacional exige CSOSN — tenta com 102 (tributada sem crédito)
            tax["csosn"] = "102"
            body["tax_information"] = tax
            try:
                api_request(cur, id_tenant, "POST", "/items/fiscal_information", json_body=body)
            except RuntimeError:
                api_request(
                    cur,
                    id_tenant,
                    "PUT",
                    f"/items/fiscal_information/{sku_path}",
                    json_body=body,
                )
        else:
            # Outro erro no POST: tenta PUT (sku já cadastrado)
            try:
                api_request(
                    cur,
                    id_tenant,
                    "PUT",
                    f"/items/fiscal_information/{sku_path}",
                    json_body=body,
                )
            except RuntimeError:
                raise e from None

    link = {
        "sku": sku,
        "item_id": ml_item_id,
        "variation_id": (variation_id or "") if variation_id is not None else "",
    }
    api_request(
        cur, id_tenant, "POST", "/items/fiscal_information/items", json_body=link
    )
    return {
        "ok": True,
        "sku": sku,
        "ml_item_id": ml_item_id,
        "ncm": ncm,
        "cest": cest,
        "origin_type": origin_type,
        "origin_detail": origin_detail,
    }


def _montar_atributos_obrigatorios_ml(
    cat_attrs: list[dict],
    *,
    marca: str,
    gtin: str,
    titulo: str,
    sku: str,
    condicao: str,
    altura_cm: float | None = None,
    largura_cm: float | None = None,
    profundidade_cm: float | None = None,
    peso_kg: float | None = None,
    so_pacote: bool = False,
    attrs_variacao_dn: dict[str, str] | None = None,
) -> list[dict]:
    out: list[dict] = []
    vistos: set[str] = set()
    marca = (marca or "").strip()
    gtin = (gtin or "").strip()
    titulo = (titulo or "").strip()
    sku = (sku or "").strip()
    eh_novo = _condicao_ml(condicao) == "new"

    if so_pacote:
        for entry in _atributos_pacote_ml(
            altura_cm=altura_cm,
            largura_cm=largura_cm,
            profundidade_cm=profundidade_cm,
            peso_kg=peso_kg,
        ):
            out.append(entry)
        for entry in _atributos_variacao_ml(cat_attrs or [], attrs_variacao_dn or {}):
            aid = entry.get("id")
            if aid and aid not in vistos:
                out.append(entry)
                vistos.add(str(aid))
        return out

    for attr in cat_attrs:
        if not isinstance(attr, dict):
            continue
        aid = (attr.get("id") or "").strip()
        if not aid or aid in vistos:
            continue
        tags = _attr_tags_ml(attr)
        obrigatorio = bool(tags.get("required"))
        if tags.get("new_required") and eh_novo:
            obrigatorio = True
        if tags.get("conditional_required"):
            obrigatorio = True
        if not obrigatorio:
            continue
        if aid in (
            "SELLER_SKU",
            "SELLER_PACKAGE_HEIGHT",
            "SELLER_PACKAGE_WIDTH",
            "SELLER_PACKAGE_LENGTH",
            "SELLER_PACKAGE_WEIGHT",
        ):
            continue

        entry: dict | None = None
        if aid == "BRAND":
            entry = _attr_valor_lista(attr, marca) if marca else _attr_valor_lista(attr, "Genérica")
            if not entry and marca:
                entry = _attr_valor_texto(aid, marca)
        elif aid == "MODEL":
            entry = _attr_valor_texto(aid, (sku or titulo or "Único")[:60])
        elif aid == "GTIN":
            if gtin:
                entry = _attr_valor_texto(aid, gtin)
        elif aid == "EMPTY_GTIN_REASON":
            if not gtin:
                for motivo in (
                    "O produto não tem código cadastrado",
                    "O produto é uma peça artesanal",
                    "Outro motivo",
                ):
                    entry = _attr_valor_lista(attr, motivo)
                    if entry:
                        break
        elif aid == "PART_NUMBER":
            entry = _attr_valor_texto(aid, sku or titulo[:60])
        else:
            vt = (attr.get("value_type") or "").lower()
            if vt == "list":
                entry = _attr_valor_lista(attr, titulo.split()[0] if titulo else "")
            elif vt in ("string", "number"):
                entry = _attr_valor_texto(aid, sku or titulo[:60] or "Não especificado")

        if not entry:
            entry = _attr_valor_lista(attr, "")
        if entry:
            out.append(entry)
            vistos.add(aid)

    if sku:
        out.append(_attr_valor_texto("SELLER_SKU", sku[:60]))
        vistos.add("SELLER_SKU")

    for entry in _atributos_pacote_ml(
        altura_cm=altura_cm,
        largura_cm=largura_cm,
        profundidade_cm=profundidade_cm,
        peso_kg=peso_kg,
    ):
        aid = entry["id"]
        if aid not in vistos:
            out.append(entry)
            vistos.add(aid)

    for entry in _atributos_variacao_ml(cat_attrs, attrs_variacao_dn or {}):
        aid = str(entry.get("id") or "")
        if aid and aid not in vistos:
            out.append(entry)
            vistos.add(aid)

    # GTIN condicional: sem código, informar motivo
    if not gtin and "GTIN" not in vistos and "EMPTY_GTIN_REASON" not in vistos:
        precisa_gtin = any(
            (a.get("id") or "").strip() == "GTIN"
            and (
                _attr_tags_ml(a).get("required")
                or _attr_tags_ml(a).get("conditional_required")
                or (_attr_tags_ml(a).get("new_required") and eh_novo)
            )
            for a in cat_attrs
            if isinstance(a, dict)
        )
        if precisa_gtin:
            for attr in cat_attrs:
                if (attr.get("id") or "").strip() != "EMPTY_GTIN_REASON":
                    continue
                for motivo in (
                    "O produto não tem código cadastrado",
                    "O produto é uma peça artesanal",
                    "Outro motivo",
                ):
                    entry = _attr_valor_lista(attr, motivo)
                    if entry:
                        out.append(entry)
                        vistos.add("EMPTY_GTIN_REASON")
                        break
                break

    return out


def _criar_anuncio_ml(
    cur,
    id_tenant: int,
    ml_user_id: int,
    site_id: str,
    *,
    id_variante: int,
    id_produto: int,
    sku: str,
    titulo: str,
    preco: float,
    descricao: str,
    imagem: str,
    estoque: int,
    condicao: str | None,
    marca: str = "",
    gtin: str = "",
    id_categoria_vendedor: int | None = None,
    cfg: dict | None = None,
    altura_cm: float | None = None,
    largura_cm: float | None = None,
    profundidade_cm: float | None = None,
    peso_kg: float | None = None,
    nome_pai: str = "",
    attrs_variacao_dn: dict[str, str] | None = None,
    garantia_tipo: str = "",
    garantia_tempo: str = "",
    video_youtube: str = "",
    variations: list[dict] | None = None,
    ncm: str = "",
    cest: str = "",
    origem_fiscal: str = "",
    producao: str = "",
    unidade: str = "UN",
    preco_custo: float | None = None,
    peso_liquido_kg: float | None = None,
    peso_bruto_kg: float | None = None,
) -> str:
    titulo = _normalizar_titulo_ml(titulo or "Produto", max_len=60)
    if preco <= 0:
        raise RuntimeError(f"Preço inválido para «{titulo}».")

    # Bloqueia antes de chamar a API / montar fotos.
    if not id_categoria_vendedor:
        raise RuntimeError(
            f"«{titulo}»: associe uma categoria DropNexo ao produto antes de exportar "
            "ao Mercado Livre."
        )
    category_id, familia_map = _mapa_categoria_ml(cur, id_tenant, id_categoria_vendedor)
    if not category_id:
        raise RuntimeError(
            f"«{titulo}»: a categoria DropNexo ainda não está mapeada para o Mercado Livre. "
            "Vá em Integrações → Mercado Livre → Mapear categorias e salve o mapeamento."
        )

    pictures = _coletar_pictures_ml(
        cur,
        id_tenant,
        id_produto=int(id_produto),
        id_variante=int(id_variante),
        imagem_fallback=imagem or "",
    )
    if not pictures and not variations:
        raise RuntimeError(
            f"«{titulo}»: nenhuma foto disponível para o anúncio no ML "
            "(verifique a galeria do produto)."
        )

    cfg = cfg or {}
    listing_pref = (cfg.get("listing_type_padrao") or "auto").strip()
    frete_gratis = bool(cfg.get("frete_gratis"))
    gar_tipo = (garantia_tipo or cfg.get("garantia_tipo_padrao") or "").strip()
    gar_tempo = (garantia_tempo or cfg.get("garantia_tempo_padrao") or "").strip()

    listing_type = _resolver_listing_type_ml(
        cur, id_tenant, ml_user_id, category_id, listing_pref
    )
    cat_attrs = _attrs_categoria_ml(cur, id_tenant, category_id)
    attrs = _montar_atributos_obrigatorios_ml(
        cat_attrs,
        marca=marca,
        gtin=gtin,
        titulo=titulo,
        sku=sku,
        condicao=condicao or "",
        altura_cm=altura_cm,
        largura_cm=largura_cm,
        profundidade_cm=profundidade_cm,
        peso_kg=peso_kg,
        attrs_variacao_dn=attrs_variacao_dn or {},
    )

    # Nome do anúncio = nome do produto (pai agrupa variações no modo UP).
    familia_base = (nome_pai or titulo or "").strip()
    titulo_anuncio = _normalizar_titulo_ml(familia_base or titulo, max_len=60)
    family_name = _family_name_ml(familia_base, marca, familia_map)
    usa_up = _seller_usa_user_products_ml(cur, id_tenant, ml_user_id, site_id)

    payload: dict[str, Any] = {
        "category_id": category_id,
        "currency_id": _moeda_site(site_id),
        "buying_mode": "buy_it_now",
        "listing_type_id": listing_type,
        "condition": _condicao_ml(condicao),
    }
    mapas_variacoes: list[tuple[int, int, str]] = []
    if variations:
        vars_api: list[dict] = []
        for var in variations:
            if not isinstance(var, dict):
                continue
            try:
                vid_map = int(var.get("_id_variante_dn") or 0)
                pid_map = int(var.get("_id_produto_dn") or id_produto)
            except (TypeError, ValueError):
                vid_map, pid_map = 0, int(id_produto)
            sku_map = str(var.get("seller_custom_field") or sku or "")
            if vid_map > 0:
                mapas_variacoes.append((vid_map, pid_map, sku_map))
            limpa = {k: v for k, v in var.items() if not str(k).startswith("_")}
            vars_api.append(limpa)
        payload["variations"] = vars_api
        if pictures:
            payload["pictures"] = pictures
    else:
        payload["price"] = round(float(preco), 2)
        payload["available_quantity"] = max(1, int(estoque or 0))
        payload["pictures"] = pictures

    sale_terms = _montar_sale_terms_ml(
        cur, id_tenant, category_id, garantia_tipo=gar_tipo, garantia_tempo=gar_tempo
    )
    if sale_terms:
        payload["sale_terms"] = sale_terms

    video_id = _extrair_youtube_id_ml(video_youtube)
    if video_id:
        payload["video_id"] = video_id

    def _aplicar_modo_up() -> None:
        payload.pop("title", None)
        payload.pop("channels", None)
        payload.pop("seller_custom_field", None)
        payload["family_name"] = family_name
        payload["shipping"] = _montar_shipping_ml(frete_gratis)

    def _aplicar_modo_classic() -> None:
        payload.pop("family_name", None)
        payload["title"] = titulo_anuncio
        payload["channels"] = ["marketplace"]
        payload["shipping"] = _montar_shipping_ml(frete_gratis)
        if sku and not variations:
            payload["seller_custom_field"] = sku[:100]

    if usa_up and not variations:
        # User Products: family_name = nome do produto; title é gerado pelo ML.
        _aplicar_modo_up()
    else:
        _aplicar_modo_classic()
    if attrs:
        payload["attributes"] = attrs

    try:
        resp = api_request(cur, id_tenant, "POST", "/items", json_body=payload)
    except RuntimeError as e:
        msg = str(e).lower()
        retried = False
        if payload.get("video_id") and ("video" in msg or "youtube" in msg):
            payload.pop("video_id", None)
            retried = True
            _log.info("ML rejeitou video_id ao criar «%s» — republicando sem vídeo.", titulo)
        if payload.get("sale_terms") and (
            "sale_term" in msg or "warranty" in msg or "garantia" in msg
        ):
            payload.pop("sale_terms", None)
            retried = True
            _log.info("ML rejeitou sale_terms ao criar «%s» — republicando sem garantia.", titulo)
        # Conta clássica vs UP: troca o modo uma vez se title/family_name falhar.
        if not variations and (
            "family name" in msg
            or "family_name" in msg
            or ("title" in msg and ("contain" in msg or "properties" in msg or "required" in msg))
        ):
            if payload.get("family_name"):
                _log.info(
                    "ML rejeitou family_name/title UP em «%s» — tentando modo clássico.",
                    titulo,
                )
                _aplicar_modo_classic()
            else:
                _log.info(
                    "ML rejeitou title clássico em «%s» — tentando User Products.",
                    titulo,
                )
                _aplicar_modo_up()
            retried = True
            # Conta pode ter mudado de modo; limpa cache para a próxima.
            _SELLER_UP_CACHE.pop(id_tenant, None)
        if not retried:
            raise
        resp = api_request(cur, id_tenant, "POST", "/items", json_body=payload)
    item_id = str(resp.get("id") or "").strip()
    if not item_id:
        raise RuntimeError(f"«{titulo}»: ML não retornou id do anúncio.")

    _tentar_ativar_anuncio_ml(cur, id_tenant, item_id)
    if mapas_variacoes:
        for vid_map, pid_map, sku_map in mapas_variacoes:
            _salvar_map_produto_ml(cur, id_tenant, vid_map, pid_map, sku_map, item_id)
    else:
        _salvar_map_produto_ml(cur, id_tenant, id_variante, id_produto, sku, item_id)

    texto_desc = _texto_plano_ml(descricao)
    if texto_desc:
        try:
            _enviar_descricao_ml(cur, id_tenant, item_id, texto_desc)
        except RuntimeError as e:
            _log.warning("Descrição ML não enviada para %s: %s", item_id, e)
            raise RuntimeError(
                f"«{titulo}»: anúncio criado ({item_id}), mas a descrição falhou: "
                f"{_erro_ml_para_usuario(str(e)[:300])}. "
                "Use o mesmo botão novamente para reenviar a descrição."
            ) from e

    if _ncm_ml(ncm) and (sku or "").strip():
        try:
            _enviar_dados_fiscais_ml(
                cur,
                id_tenant,
                sku=sku or "",
                titulo=titulo or sku or "",
                ml_item_id=item_id,
                ncm=ncm,
                cest=cest,
                origem_fiscal=origem_fiscal,
                producao=producao,
                gtin=gtin or "",
                unidade=unidade or "UN",
                custo=preco_custo,
                peso_liquido_kg=peso_liquido_kg or peso_kg,
                peso_bruto_kg=peso_bruto_kg or peso_kg,
            )
        except RuntimeError as e:
            _log.warning("Dados fiscais ML não enviados para %s: %s", item_id, e)
            raise RuntimeError(
                f"«{titulo}»: anúncio criado ({item_id}), mas dados fiscais falharam: "
                f"{_erro_ml_para_usuario(str(e)[:300])}. "
                "Preencha NCM/CEST/origem na aba Tributação e sincronize de novo."
            ) from e
    elif not _ncm_ml(ncm):
        _log.warning(
            "ML item %s criado sem NCM — Faturador não emitirá NF-e até preencher Tributação.",
            item_id,
        )

    return item_id


def _sql_produtos_vitrine_ml(ids_produtos: list[int] | None = None) -> tuple[str, list]:
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
               pv.id_categoria_vendedor,
               COALESCE(v.altura_cm, p.altura_cm) AS altura_cm,
               COALESCE(v.largura_cm, p.largura_cm) AS largura_cm,
               COALESCE(v.profundidade_cm, p.profundidade_cm) AS profundidade_cm,
               COALESCE(v.peso_bruto_kg, p.peso_bruto_kg, v.peso_liquido_kg, p.peso_liquido_kg) AS peso_kg,
               COALESCE(NULLIF(TRIM(p.nome), ''), '') AS nome_pai,
               v.atributos AS atributos_variante,
               COALESCE(NULLIF(TRIM(p.garantia_tipo), ''), '') AS garantia_tipo,
               COALESCE(NULLIF(TRIM(p.garantia_tempo), ''), '') AS garantia_tempo,
               COALESCE(NULLIF(TRIM(p.video_youtube), ''), '') AS video_youtube,
               COALESCE(NULLIF(TRIM(v.ncm), ''), NULLIF(TRIM(p.ncm), ''), '') AS ncm,
               COALESCE(NULLIF(TRIM(p.cest), ''), '') AS cest,
               COALESCE(NULLIF(TRIM(p.origem_fiscal), ''), '') AS origem_fiscal,
               COALESCE(NULLIF(TRIM(p.producao), ''), '') AS producao,
               COALESCE(NULLIF(TRIM(p.unidade), ''), 'UN') AS unidade,
               COALESCE(v.preco_custo, p.preco_custo) AS preco_custo,
               COALESCE(v.peso_liquido_kg, p.peso_liquido_kg) AS peso_liquido_kg,
               COALESCE(v.peso_bruto_kg, p.peso_bruto_kg) AS peso_bruto_kg
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = v.id
        WHERE pv.id_tenant_vendedor = %s AND pv.ativo = TRUE{extra}
        ORDER BY p.id, pv.id
    """
    return sql, params_tail


def _float_ou_none(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _desempacotar_linha_vitrine_ml(row) -> dict[str, Any]:
    """Normaliza a linha do SQL da vitrine ML (com ou sem colunas extras)."""
    n = len(row) if row is not None else 0

    def _at(i, default=None):
        return row[i] if n > i else default

    return {
        "pv_id": _at(0),
        "id_variante": int(_at(1) or 0),
        "id_produto": int(_at(2) or 0),
        "sku": (_at(3) or "").strip() if isinstance(_at(3), str) or _at(3) is None else str(_at(3) or "").strip(),
        "titulo": _at(4) or "",
        "preco": float(_at(5) or 0),
        "descricao": _at(6) or "",
        "imagem": _at(7) or "",
        "estoque": int(_at(8) or 0),
        "condicao": _at(9),
        "marca": (_at(10) or "") if _at(10) is not None else "",
        "gtin": (_at(11) or "") if _at(11) is not None else "",
        "id_cat_vd": _at(12),
        "altura_cm": _float_ou_none(_at(13)),
        "largura_cm": _float_ou_none(_at(14)),
        "profundidade_cm": _float_ou_none(_at(15)),
        "peso_kg": _float_ou_none(_at(16)),
        "nome_pai": (_at(17) or "") if n > 17 else "",
        "attrs_variacao_dn": _parse_atributos_variante_ml(_at(18) if n > 18 else None),
        "garantia_tipo": (_at(19) or "") if n > 19 else "",
        "garantia_tempo": (_at(20) or "") if n > 20 else "",
        "video_youtube": (_at(21) or "") if n > 21 else "",
        "ncm": (_at(22) or "") if n > 22 else "",
        "cest": (_at(23) or "") if n > 23 else "",
        "origem_fiscal": (_at(24) or "") if n > 24 else "",
        "producao": (_at(25) or "") if n > 25 else "",
        "unidade": (_at(26) or "UN") if n > 26 else "UN",
        "preco_custo": _float_ou_none(_at(27)) if n > 27 else None,
        "peso_liquido_kg": _float_ou_none(_at(28)) if n > 28 else None,
        "peso_bruto_kg": _float_ou_none(_at(29)) if n > 29 else None,
    }


def _kwargs_fiscais_ml(d: dict) -> dict[str, Any]:
    return {
        "ncm": d.get("ncm") or "",
        "cest": d.get("cest") or "",
        "origem_fiscal": d.get("origem_fiscal") or "",
        "producao": d.get("producao") or "",
        "unidade": d.get("unidade") or "UN",
        "preco_custo": d.get("preco_custo"),
        "peso_liquido_kg": d.get("peso_liquido_kg"),
        "peso_bruto_kg": d.get("peso_bruto_kg"),
    }


def _montar_variations_classic_ml(
    cur,
    id_tenant: int,
    *,
    category_id: str,
    itens: list[dict],
) -> list[dict]:
    """Monta variations[] para sellers clássicos (não User Products)."""
    cat_attrs = _attrs_categoria_ml(cur, id_tenant, category_id) if category_id else []
    out: list[dict] = []
    for d in itens:
        attrs_dn = d.get("attrs_variacao_dn") or {}
        combos = _atributos_variacao_ml(cat_attrs, attrs_dn)
        if not combos:
            # Sem combinação (Cor/Tamanho), variations[] não faz sentido.
            return []
        sku = (d.get("sku") or "").strip()
        var: dict[str, Any] = {
            "attribute_combinations": combos,
            "price": round(float(d.get("preco") or 0), 2),
            "available_quantity": max(0, int(d.get("estoque") or 0)),
            "_id_variante_dn": int(d["id_variante"]),
            "_id_produto_dn": int(d["id_produto"]),
        }
        if sku:
            var["seller_custom_field"] = sku[:100]
            var["attributes"] = [_attr_valor_texto("SELLER_SKU", sku[:100])]
        out.append(var)
    return out


def _criar_anuncios_ml_lote(cur, id_tenant: int, cfg: dict, linhas: list) -> dict:
    ml_user_id = int(cfg.get("ml_user_id") or 0)
    site_id = (cfg.get("ml_site_id") or "MLB").upper()
    if not ml_user_id:
        raise RuntimeError("Perfil Mercado Livre sem user_id. Reconecte a conta.")

    _garantir_colunas_produto_ml_extra(cur)

    exportados = 0
    atualizados = 0
    erros: list[str] = []
    resultados: list[dict] = []
    processados = 0
    usa_up = _seller_usa_user_products_ml(cur, id_tenant, ml_user_id, site_id)

    dados = [_desempacotar_linha_vitrine_ml(r) for r in linhas]
    # Classic multi-variação: agrupa por produto quando ainda não vinculado.
    grupos: dict[int, list[dict]] = {}
    for d in dados:
        grupos.setdefault(int(d["id_produto"]), []).append(d)

    def _atualizar_um(d: dict) -> None:
        nonlocal atualizados, processados
        if processados >= _ML_MAX_CRIAR_POR_SYNC:
            return
        processados += 1
        nome = _titulo_exibicao_ml(d["titulo"] or "", d["sku"] or "")
        ml_item_id = _item_ja_vinculado_ml(cur, id_tenant, int(d["id_variante"]))
        if not ml_item_id and d["sku"]:
            ml_item_id = _buscar_item_ml_por_sku(cur, id_tenant, ml_user_id, d["sku"])
        if not ml_item_id:
            return
        try:
            _atualizar_anuncio_completo_ml(
                cur,
                id_tenant,
                ml_item_id,
                id_variante=int(d["id_variante"]),
                id_produto=int(d["id_produto"]),
                sku=d["sku"],
                preco=float(d["preco"] or 0),
                descricao=d["descricao"] or "",
                imagem=d["imagem"] or "",
                estoque=int(d["estoque"] or 0),
                marca=d["marca"] or "",
                gtin=d["gtin"] or "",
                condicao=d["condicao"],
                altura_cm=d["altura_cm"],
                largura_cm=d["largura_cm"],
                profundidade_cm=d["profundidade_cm"],
                peso_kg=d["peso_kg"],
                titulo=d["titulo"] or "",
                attrs_variacao_dn=d.get("attrs_variacao_dn") or {},
                garantia_tipo=d.get("garantia_tipo") or "",
                garantia_tempo=d.get("garantia_tempo") or "",
                video_youtube=d.get("video_youtube") or "",
                cfg=cfg,
                **_kwargs_fiscais_ml(d),
            )
            atualizados += 1
            resultados.append(
                {
                    "id_produto": int(d["id_produto"]),
                    "titulo": nome,
                    "sku": d["sku"],
                    "status": "ok",
                    "acao": "atualizado",
                    "mensagem": (
                        "Anúncio atualizado no Mercado Livre "
                        "(fotos, preço, estoque, variação, garantia, descrição e tributação)."
                    ),
                    "ml_item_id": ml_item_id,
                }
            )
        except RuntimeError as e:
            msg_user = _erro_ml_para_usuario(str(e)[:400])
            if msg_user not in erros:
                erros.append(msg_user)
            resultados.append(
                {
                    "id_produto": int(d["id_produto"]),
                    "titulo": nome,
                    "sku": d["sku"],
                    "status": "erro",
                    "mensagem": msg_user,
                }
            )

    def _criar_um(d: dict, variations: list[dict] | None = None) -> None:
        nonlocal exportados, processados
        if processados >= _ML_MAX_CRIAR_POR_SYNC:
            return
        processados += 1
        nome = _titulo_exibicao_ml(d["titulo"] or "", d["sku"] or "")
        try:
            id_cat = int(d["id_cat_vd"]) if d.get("id_cat_vd") else None
        except (TypeError, ValueError):
            id_cat = None
        # Validação antecipada (mesma regra de _criar_anuncio_ml) para mensagem clara no lote.
        try:
            if not id_cat:
                raise RuntimeError(
                    f"«{nome}»: associe uma categoria DropNexo ao produto antes de exportar "
                    "ao Mercado Livre."
                )
            cat_ml, _fam = _mapa_categoria_ml(cur, id_tenant, id_cat)
            if not cat_ml:
                raise RuntimeError(
                    f"«{nome}»: a categoria DropNexo ainda não está mapeada para o Mercado Livre. "
                    "Vá em Integrações → Mercado Livre → Mapear categorias e salve o mapeamento."
                )
        except RuntimeError as e:
            msg_user = _erro_ml_para_usuario(str(e)[:400])
            if msg_user not in erros:
                erros.append(msg_user)
            resultados.append(
                {
                    "id_produto": int(d["id_produto"]),
                    "titulo": nome,
                    "sku": d["sku"],
                    "status": "erro",
                    "mensagem": msg_user,
                }
            )
            return
        try:
            ml_item_id = _criar_anuncio_ml(
                cur,
                id_tenant,
                ml_user_id,
                site_id,
                id_variante=int(d["id_variante"]),
                id_produto=int(d["id_produto"]),
                sku=d["sku"],
                titulo=d["titulo"] or "",
                preco=float(d["preco"] or 0),
                descricao=d["descricao"] or "",
                imagem=d["imagem"] or "",
                estoque=int(d["estoque"] or 0),
                condicao=d["condicao"],
                marca=d["marca"] or "",
                gtin=d["gtin"] or "",
                id_categoria_vendedor=id_cat,
                cfg=cfg,
                altura_cm=d["altura_cm"],
                largura_cm=d["largura_cm"],
                profundidade_cm=d["profundidade_cm"],
                peso_kg=d["peso_kg"],
                nome_pai=d.get("nome_pai") or "",
                attrs_variacao_dn=d.get("attrs_variacao_dn") or {},
                garantia_tipo=d.get("garantia_tipo") or "",
                garantia_tempo=d.get("garantia_tempo") or "",
                video_youtube=d.get("video_youtube") or "",
                variations=variations,
                **_kwargs_fiscais_ml(d),
            )
            exportados += 1
            estado = _estado_anuncio_ml(cur, id_tenant, ml_item_id)
            cat_usada = estado.get("category_id") or ""
            resultados.append(
                {
                    "id_produto": int(d["id_produto"]),
                    "titulo": nome,
                    "sku": d["sku"],
                    "status": "ok",
                    "acao": "criado",
                    "mensagem": _mensagem_pos_publicacao_ml(estado, cat_usada),
                    "ml_item_id": ml_item_id,
                    "ml_category_id": cat_usada,
                    "ml_listing_type": estado.get("listing_type_id") or "",
                    "ml_status": estado.get("status") or "",
                }
            )
            if variations:
                for v in variations:
                    vid = int(v.get("_id_variante_dn") or 0)
                    if vid and vid != int(d["id_variante"]):
                        resultados.append(
                            {
                                "id_produto": int(d["id_produto"]),
                                "titulo": nome,
                                "sku": str(v.get("seller_custom_field") or ""),
                                "status": "ok",
                                "acao": "criado",
                                "mensagem": f"Variação vinculada ao anúncio {ml_item_id}.",
                                "ml_item_id": ml_item_id,
                            }
                        )
        except RuntimeError as e:
            msg_tec = str(e)[:400]
            msg_user = _erro_ml_para_usuario(msg_tec)
            if msg_user not in erros:
                erros.append(msg_user)
            resultados.append(
                {
                    "id_produto": int(d["id_produto"]),
                    "titulo": nome,
                    "sku": d["sku"],
                    "status": "erro",
                    "mensagem": msg_user,
                }
            )

    for _id_prod, grupo in grupos.items():
        if processados >= _ML_MAX_CRIAR_POR_SYNC:
            break

        pendentes: list[dict] = []
        for d in grupo:
            ml_item_id = _item_ja_vinculado_ml(cur, id_tenant, int(d["id_variante"]))
            if not ml_item_id and d["sku"]:
                ml_item_id = _buscar_item_ml_por_sku(cur, id_tenant, ml_user_id, d["sku"])
            if ml_item_id:
                _atualizar_um(d)
            else:
                pendentes.append(d)

        if not pendentes:
            continue

        # User Products (MLB): 1 anúncio por variante, mesmo family_name + attrs CHILD_PK.
        if usa_up or len(pendentes) == 1:
            for d in pendentes:
                if processados >= _ML_MAX_CRIAR_POR_SYNC:
                    break
                _criar_um(d)
            continue

        # Classic: tenta 1 anúncio com variations[]; se falhar, cria um a um.
        base = pendentes[0]
        try:
            id_cat = int(base["id_cat_vd"]) if base.get("id_cat_vd") else None
        except (TypeError, ValueError):
            id_cat = None
        category_id, _fam = _mapa_categoria_ml(cur, id_tenant, id_cat)
        if not category_id:
            category_id = (
                _prever_categoria_ml(cur, id_tenant, site_id, base.get("titulo") or "") or ""
            )
        variations = _montar_variations_classic_ml(
            cur, id_tenant, category_id=category_id or "", itens=pendentes
        )
        if variations and len(variations) == len(pendentes):
            before_err = len(resultados)
            _criar_um(base, variations=variations)
            # Se criou ok, não reprocessa o grupo; se errou, fallback 1 a 1.
            criou = any(
                r.get("acao") == "criado" and r.get("status") == "ok"
                for r in resultados[before_err:]
            )
            if criou:
                continue
            # remove o erro do grupo e tenta individual
            if resultados and resultados[-1].get("status") == "erro":
                last = resultados.pop()
                msg_rem = last.get("mensagem")
                if (
                    msg_rem
                    and msg_rem in erros
                    and not any(r.get("mensagem") == msg_rem for r in resultados)
                ):
                    erros.remove(msg_rem)
            processados = max(0, processados - 1)

        for d in pendentes:
            if processados >= _ML_MAX_CRIAR_POR_SYNC:
                break
            if _item_ja_vinculado_ml(cur, id_tenant, int(d["id_variante"])):
                continue
            _criar_um(d)

    total = len(linhas)
    partes: list[str] = []
    if exportados:
        partes.append(f"{exportados} anúncio(s) criado(s)")
    if atualizados:
        partes.append(f"{atualizados} atualizado(s)")
    if erros:
        partes.append(f"{len(erros)} com erro")
    if partes:
        msg = " · ".join(partes) + " no Mercado Livre."
    else:
        msg = "Nenhum produto processado."
    if total > _ML_MAX_CRIAR_POR_SYNC and processados >= _ML_MAX_CRIAR_POR_SYNC:
        msg += (
            f" Limite de {_ML_MAX_CRIAR_POR_SYNC} por sincronização — "
            "execute novamente para continuar."
        )

    out = {
        "message": msg,
        "total_produtos": total,
        "modo": "criar_anuncio",
        "exportados": exportados,
        "atualizados": atualizados,
        "vinculados": atualizados,
        "ignorados": 0,
        "erros": len([r for r in resultados if r.get("status") == "erro"]),
        "resultados": resultados,
    }
    if erros:
        out["detalhes_erros"] = erros[:8]
    return out


def _buscar_item_ml_por_sku(cur, id_tenant: int, ml_user_id: int, sku: str) -> str | None:
    """Retorna id do anúncio ML (ex. MLB123) que corresponde ao SKU do vendedor."""
    sku = (sku or "").strip()
    if not sku or not ml_user_id:
        return None
    for param in ("seller_sku", "sku"):
        try:
            data = api_request(
                cur,
                id_tenant,
                "GET",
                f"/users/{int(ml_user_id)}/items/search",
                params={param: sku, "status": "active"},
            )
            results = data.get("results") or []
            if results:
                return str(results[0])
        except RuntimeError:
            continue
    return None


def _salvar_map_produto_ml(
    cur,
    id_tenant: int,
    id_variante: int,
    id_produto: int,
    sku: str,
    ml_item_id: str,
) -> None:
    cur.execute(
        """
        DELETE FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'mercado_livre' AND contexto = 'vendedor'
          AND entidade = 'produto' AND id_dropnexo = %s
        """,
        (id_tenant, id_variante),
    )
    meta = json.dumps({"id_produto": id_produto, "ml_item_id": ml_item_id}, ensure_ascii=False)
    cur.execute(
        """
        INSERT INTO tbl_integracao_map (
            id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta, atualizado_em
        ) VALUES (%s, 'mercado_livre', 'vendedor', 'produto', %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling) DO UPDATE SET
            id_dropnexo = EXCLUDED.id_dropnexo,
            sku = EXCLUDED.sku,
            meta = EXCLUDED.meta,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, ml_item_id, id_variante, sku, meta, agora_utc()),
    )


def exportar_produtos_ml(cur, id_tenant: int) -> dict:
    """Vincula por SKU ou cria novos anúncios no Mercado Livre."""
    cfg = carregar_config_ml(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("Mercado Livre não conectado.")
    if not cfg.get("produtos_exportar_auto"):
        raise RuntimeError("Ative a exportação de produtos antes de sincronizar.")

    modo = cfg.get("produtos_modo") or "vincular_sku"
    _garantir_colunas_produto_ml_extra(cur)
    sql, extra = _sql_produtos_vitrine_ml()
    cur.execute(sql, [id_tenant, *extra])
    linhas = cur.fetchall()

    if modo == "criar_anuncio":
        return _criar_anuncios_ml_lote(cur, id_tenant, cfg, linhas)

    ml_user_id = cfg.get("ml_user_id")
    if not ml_user_id:
        raise RuntimeError("Perfil Mercado Livre sem user_id. Reconecte a conta.")

    vinculados = 0
    atualizados = 0
    nao_encontrados = 0
    sem_sku = 0
    erros: list[str] = []
    for row in linhas:
        d = _desempacotar_linha_vitrine_ml(row)
        sku = d["sku"]
        ml_item = _item_ja_vinculado_ml(cur, id_tenant, int(d["id_variante"]))
        if not ml_item:
            if not sku:
                sem_sku += 1
                continue
            ml_item = _buscar_item_ml_por_sku(cur, id_tenant, int(ml_user_id), sku)
        if not ml_item:
            nao_encontrados += 1
            continue
        try:
            _atualizar_anuncio_completo_ml(
                cur,
                id_tenant,
                ml_item,
                id_variante=int(d["id_variante"]),
                id_produto=int(d["id_produto"]),
                sku=sku,
                preco=float(d["preco"] or 0),
                descricao=d["descricao"] or "",
                imagem=d["imagem"] or "",
                estoque=int(d["estoque"] or 0),
                marca=d["marca"] or "",
                gtin=d["gtin"] or "",
                condicao=d["condicao"],
                altura_cm=d["altura_cm"],
                largura_cm=d["largura_cm"],
                profundidade_cm=d["profundidade_cm"],
                peso_kg=d["peso_kg"],
                titulo=d["titulo"] or "",
                attrs_variacao_dn=d.get("attrs_variacao_dn") or {},
                garantia_tipo=d.get("garantia_tipo") or "",
                garantia_tempo=d.get("garantia_tempo") or "",
                video_youtube=d.get("video_youtube") or "",
                cfg=cfg,
                **_kwargs_fiscais_ml(d),
            )
            atualizados += 1
            vinculados += 1
        except RuntimeError as e:
            msg_user = _erro_ml_para_usuario(str(e)[:400])
            if msg_user not in erros:
                erros.append(msg_user)

    total = len(linhas)
    if atualizados <= 0 and not erros:
        msg = (
            f"Nenhum dos {total} produto(s) foi vinculado. "
            "Confira se o SKU no DropNexo é igual ao do anúncio no Mercado Livre."
        )
        if sem_sku:
            msg += f" {sem_sku} sem SKU."
    else:
        msg = (
            f"{atualizados} de {total} produto(s) atualizado(s) no Mercado Livre "
            "(fotos, preço, estoque e descrição)."
        )
        if nao_encontrados > 0:
            msg += f" {nao_encontrados} sem anúncio correspondente no ML."
        if sem_sku:
            msg += f" {sem_sku} sem SKU."
        if erros:
            msg += f" {len(erros)} com erro."

    out = {
        "message": msg,
        "total_produtos": total,
        "modo": modo,
        "exportados": 0,
        "atualizados": atualizados,
        "vinculados": vinculados,
        "nao_encontrados": nao_encontrados,
        "erros": len(erros),
    }
    if erros:
        out["detalhes_erros"] = erros[:8]
    return out


def publicar_produtos_ml(cur, id_tenant: int, ids_produtos: list[int]) -> dict:
    """Publica ou vincula produtos selecionados (Meus produtos)."""
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

    cfg = carregar_config_ml(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("Conecte o Mercado Livre em Integrações.")

    if not cfg.get("produtos_exportar_auto"):
        raise RuntimeError(
            "Ative a exportação de produtos em Integrações → Mercado Livre → Produtos."
        )

    modo = cfg.get("produtos_modo") or "vincular_sku"
    _garantir_colunas_produto_ml_extra(cur)
    sql, extra = _sql_produtos_vitrine_ml(ids)
    cur.execute(sql, [id_tenant, *extra])
    linhas = cur.fetchall()
    if not linhas:
        raise RuntimeError("Nenhuma variação ativa encontrada nos produtos selecionados.")

    if modo == "criar_anuncio":
        return _criar_anuncios_ml_lote(cur, id_tenant, cfg, linhas)

    ml_user_id = cfg.get("ml_user_id")
    if not ml_user_id:
        raise RuntimeError("Perfil Mercado Livre sem user_id. Reconecte a conta.")

    vinculados = 0
    atualizados = 0
    nao_encontrados = 0
    sem_sku = 0
    erros: list[str] = []
    resultados: list[dict] = []
    for row in linhas:
        d = _desempacotar_linha_vitrine_ml(row)
        sku = d["sku"]
        nome = _titulo_exibicao_ml(d["titulo"] or "", sku)
        ml_item = _item_ja_vinculado_ml(cur, id_tenant, int(d["id_variante"]))
        if not ml_item:
            if not sku:
                sem_sku += 1
                resultados.append(
                    {
                        "id_produto": int(d["id_produto"]),
                        "titulo": nome,
                        "sku": sku,
                        "status": "erro",
                        "mensagem": "Produto sem SKU para vincular ao Mercado Livre.",
                    }
                )
                continue
            ml_item = _buscar_item_ml_por_sku(cur, id_tenant, int(ml_user_id), sku)
        if not ml_item:
            nao_encontrados += 1
            resultados.append(
                {
                    "id_produto": int(d["id_produto"]),
                    "titulo": nome,
                    "sku": sku,
                    "status": "erro",
                    "mensagem": "Nenhum anúncio encontrado no ML com este SKU.",
                }
            )
            continue
        try:
            _atualizar_anuncio_completo_ml(
                cur,
                id_tenant,
                ml_item,
                id_variante=int(d["id_variante"]),
                id_produto=int(d["id_produto"]),
                sku=sku,
                preco=float(d["preco"] or 0),
                descricao=d["descricao"] or "",
                imagem=d["imagem"] or "",
                estoque=int(d["estoque"] or 0),
                marca=d["marca"] or "",
                gtin=d["gtin"] or "",
                condicao=d["condicao"],
                altura_cm=d["altura_cm"],
                largura_cm=d["largura_cm"],
                profundidade_cm=d["profundidade_cm"],
                peso_kg=d["peso_kg"],
                titulo=d["titulo"] or "",
                attrs_variacao_dn=d.get("attrs_variacao_dn") or {},
                garantia_tipo=d.get("garantia_tipo") or "",
                garantia_tempo=d.get("garantia_tempo") or "",
                video_youtube=d.get("video_youtube") or "",
                cfg=cfg,
                **_kwargs_fiscais_ml(d),
            )
            atualizados += 1
            vinculados += 1
            resultados.append(
                {
                    "id_produto": int(d["id_produto"]),
                    "titulo": nome,
                    "sku": sku,
                    "status": "ok",
                    "acao": "atualizado",
                    "mensagem": (
                        "Anúncio atualizado no Mercado Livre "
                        "(fotos, preço, estoque, variação, garantia e descrição)."
                    ),
                    "ml_item_id": ml_item,
                }
            )
        except RuntimeError as e:
            msg_user = _erro_ml_para_usuario(str(e)[:400])
            if msg_user not in erros:
                erros.append(msg_user)
            resultados.append(
                {
                    "id_produto": int(d["id_produto"]),
                    "titulo": nome,
                    "sku": sku,
                    "status": "erro",
                    "mensagem": msg_user,
                }
            )

    total = len(linhas)
    msg = (
        f"{atualizados} de {total} variação(ões) atualizada(s) no Mercado Livre "
        "(fotos, preço, estoque e descrição)."
    )
    if nao_encontrados:
        msg += f" {nao_encontrados} sem anúncio com o mesmo SKU no ML."
    if sem_sku:
        msg += f" {sem_sku} sem SKU."
    if erros:
        msg += f" {len(erros)} com erro."
    out = {
        "message": msg,
        "total_produtos": total,
        "modo": modo,
        "exportados": 0,
        "atualizados": atualizados,
        "vinculados": vinculados,
        "nao_encontrados": nao_encontrados,
        "erros": len([r for r in resultados if r.get("status") == "erro"]),
        "resultados": resultados,
    }
    if erros:
        out["detalhes_erros"] = erros[:8]
    return out


def sincronizar_estoque_ml(cur, id_tenant: int) -> dict:
    from api.mercado_livre.sync_runtime import sincronizar_todos_estoques_ml

    return sincronizar_todos_estoques_ml(cur, id_tenant)
