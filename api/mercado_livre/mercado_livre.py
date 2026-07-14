# api/mercado_livre/mercado_livre.py — OAuth, API e sync de pedidos ML
from __future__ import annotations

import json
import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests

from core.tokens import criptografar_token, descriptografar_token
from global_utils import agora_utc, is_modo_producao, obter_base_url, url_imagem_produto

_log = logging.getLogger(__name__)

ML_AUTH_URL = "https://auth.mercadolivre.com.br/authorization"
ML_TOKEN_URL = "https://api.mercadolibre.com/oauth/token"
ML_API_BASE = "https://api.mercadolibre.com"
ML_OAUTH_TIMEOUT = (5, 25)
ML_API_TIMEOUT = (10, 60)

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
    return f"{obter_base_url().rstrip('/')}/api/integracoes/mercado-livre/webhook"


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
) -> Any:
    token = obter_access_token_valido(cur, id_tenant)
    url = path if path.startswith("http") else f"{ML_API_BASE}{path}"
    headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
    try:
        r = requests.request(
            method.upper(),
            url,
            headers=headers,
            params=params,
            json=json_body,
            timeout=ML_API_TIMEOUT,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Falha na API Mercado Livre: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(_formatar_erro_ml(r.status_code, r.text))
    if not r.content:
        return {}
    return r.json()


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
        _ML_COLS_ANUNCIO_OK = True
        return True
    except Exception:
        _rollback_cur(cur)
        _ML_COLS_ANUNCIO_OK = None
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
    cols_ext = ""
    if anuncio_cfg:
        cols_ext = ", listing_type_padrao, frete_gratis"
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
) -> None:
    if not _tem_tabela_ml(cur):
        raise RuntimeError("Tabela tbl_integracao_mercado_livre não existe.")
    updates: dict[str, Any] = {}
    if pedidos_importar_auto is not None:
        updates["pedidos_importar_auto"] = bool(pedidos_importar_auto)
    precisa_ext = any(
        v is not None
        for v in (produtos_exportar_auto, produtos_modo, estoque_sync_ativo, listing_type_padrao, frete_gratis)
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
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in updates) + ", atualizado_em = EXCLUDED.atualizado_em"
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
    if "family_name" in low and ("length" in low or "caracter" in low):
        return (
            f"Nome da família muito longo (máx. {_ML_FAMILY_NAME_MAX} caracteres). "
            "Encurte em Integrações → Mercado Livre → Mapear categorias."
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
    if "mapeie" in low or "mapear categorias" in low:
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
    if id_tenant in _SELLER_UP_CACHE:
        return _SELLER_UP_CACHE[id_tenant]
    usa_up = False
    try:
        info = api_request(cur, id_tenant, "GET", f"/users/{int(ml_user_id)}")
        tags = info.get("tags") or []
        usa_up = "user_product_seller" in tags
    except RuntimeError:
        pass
    # Novos anúncios no Brasil já seguem User Products (family_name, sem title).
    if not usa_up and (site_id or "MLB").upper() == "MLB":
        usa_up = True
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


_ML_MAX_PICTURES = 12


def _raiz_projeto_ml() -> Path:
    return Path(__file__).resolve().parents[2]


def _arquivo_local_imagem_ml(imagem_path: str | None) -> Path | None:
    """Resolve caminho de disco para foto de produto (static/imge ou upload/tenant)."""
    raw = (imagem_path or "").strip().replace("\\", "/")
    if not raw or raw.lower().startswith(("http://", "https://")):
        return None
    rel = raw.lstrip("/")
    if rel.lower().startswith("static/"):
        rel = rel[7:]
    if ".." in rel.split("/"):
        return None
    root = _raiz_projeto_ml()
    candidatos: list[Path] = []
    if rel.lower().startswith("imge/"):
        candidatos.append(root / "static" / rel.replace("/", os.sep))
    candidatos.append(root / rel.replace("/", os.sep))
    if rel.lower().startswith("upload/"):
        candidatos.append(root / "static" / rel.replace("/", os.sep))
    for p in candidatos:
        if p.is_file():
            return p
    return None


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
    """
    Lista caminhos da galeria para o ML.
    Usa seleção explícita da variação; se não houver, usa a galeria completa do pai.
    (Antes caía em id_imagem_principal → só 1 foto.)
    """
    from fornecedor.catalogo.catalogo import listar_imagens_galeria_pai

    caminhos: list[str] = []
    cur.execute(
        """
        SELECT i.caminho
        FROM tbl_produto_variante_imagem vi
        JOIN tbl_produto_imagem i ON i.id = vi.id_imagem
        WHERE vi.id_variante = %s
        ORDER BY vi.ordem ASC, vi.id_imagem ASC
        """,
        (int(id_variante),),
    )
    for row in cur.fetchall():
        c = (row[0] or "").strip()
        if c:
            caminhos.append(c)

    if not caminhos:
        try:
            for img in listar_imagens_galeria_pai(cur, int(id_produto)):
                c = (img.get("caminho") or "").strip()
                if c:
                    caminhos.append(c)
        except Exception:
            caminhos = []

    fb = (imagem_fallback or "").strip()
    if fb and fb not in caminhos:
        caminhos.insert(0, fb)
    return caminhos


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
    Prefere upload multipart (arquivo local) — ML não depende de URL pública/login.
    Fallback: source com URL absoluta.
    """
    pictures: list[dict[str, str]] = []
    vistos: set[str] = set()
    for caminho in _caminhos_galeria_ml(
        cur,
        id_produto=int(id_produto),
        id_variante=int(id_variante),
        imagem_fallback=imagem_fallback or "",
    ):
        chave = caminho.strip().lower()
        if not chave or chave in vistos:
            continue
        vistos.add(chave)

        local = _arquivo_local_imagem_ml(caminho)
        if local is not None:
            pic_id = _upload_picture_ml(cur, id_tenant, local)
            if pic_id:
                pictures.append({"id": pic_id})
                if len(pictures) >= _ML_MAX_PICTURES:
                    break
                continue

        url = _imagem_publica_ml(caminho)
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
) -> None:
    """Atualiza anúncio já vinculado: preço, estoque, fotos, descrição e atributos básicos."""
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

    attrs = _montar_atributos_obrigatorios_ml(
        [],
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
    )
    if attrs:
        payload["attributes"] = attrs

    registrar_eco_ml_pendente(
        cur,
        id_tenant,
        ml_item_id=ml_item_id,
        quantidade_esperada=max(0, int(estoque or 0)),
        origem="dropnexo_export",
    )
    if payload:
        api_request(cur, id_tenant, "PUT", f"/items/{ml_item_id}", json_body=payload)

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
    if (override or "").strip():
        return _normalizar_titulo_ml(override, max_len=_ML_FAMILY_NAME_MAX)
    marca = (marca or "").strip()
    titulo = _normalizar_titulo_ml(titulo or "", max_len=_ML_FAMILY_NAME_MAX)
    if marca and titulo and not titulo.lower().startswith(marca.lower()):
        fam = f"{marca} {titulo}"
    else:
        fam = titulo or marca or "Produto"
    return _normalizar_titulo_ml(fam, max_len=_ML_FAMILY_NAME_MAX)


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
        familia = (item.get("family_name") or "").strip()[:_ML_FAMILY_NAME_MAX] or None
        cur.execute(
            """
            INSERT INTO tbl_integracao_ml_categoria_map (
                id_tenant, id_categoria, ml_category_id, family_name, atualizado_em
            ) VALUES (%s, %s, %s, %s, %s)
            ON CONFLICT (id_tenant, id_categoria) DO UPDATE SET
                ml_category_id = EXCLUDED.ml_category_id,
                family_name = EXCLUDED.family_name,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_tenant, id_cat, ml_cat, familia, agora),
        )
        salvos += 1
    return salvos


def buscar_categorias_ml(cur, id_tenant: int, termo: str, limit: int = 10) -> list[dict]:
    """Sugere categorias ML pelo título (domain_discovery)."""
    termo = (termo or "").strip()
    if len(termo) < 3:
        return []
    cfg = carregar_config_ml(cur, id_tenant)
    if not cfg.get("conectado"):
        return []
    site_id = (cfg.get("ml_site_id") or "MLB").upper()
    try:
        data = api_request(
            cur,
            id_tenant,
            "GET",
            f"/sites/{site_id}/domain_discovery/search",
            params={"q": termo[:120], "limit": max(1, min(int(limit), 20))},
        )
    except RuntimeError:
        return []
    out: list[dict] = []
    vistos: set[str] = set()
    for item in data or []:
        if not isinstance(item, dict):
            continue
        cat_id = str(item.get("category_id") or "").strip().upper()
        if not cat_id or cat_id in vistos:
            continue
        vistos.add(cat_id)
        nome = (
            item.get("category_name")
            or item.get("domain_name")
            or item.get("category_id")
            or ""
        )
        out.append({"category_id": cat_id, "nome": str(nome).strip() or cat_id})
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
    """Dimensões/peso do pacote (ML espera peso em gramas)."""
    out: list[dict] = []
    if altura_cm is not None and float(altura_cm) > 0:
        out.append(_attr_valor_texto("SELLER_PACKAGE_HEIGHT", str(round(float(altura_cm), 2))))
    if largura_cm is not None and float(largura_cm) > 0:
        out.append(_attr_valor_texto("SELLER_PACKAGE_WIDTH", str(round(float(largura_cm), 2))))
    if profundidade_cm is not None and float(profundidade_cm) > 0:
        out.append(_attr_valor_texto("SELLER_PACKAGE_LENGTH", str(round(float(profundidade_cm), 2))))
    if peso_kg is not None and float(peso_kg) > 0:
        gramas = max(1, int(round(float(peso_kg) * 1000)))
        out.append(_attr_valor_texto("SELLER_PACKAGE_WEIGHT", str(gramas)))
    return out


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
) -> str:
    titulo = _normalizar_titulo_ml(titulo or "Produto", max_len=60)
    if preco <= 0:
        raise RuntimeError(f"Preço inválido para «{titulo}».")
    pictures = _coletar_pictures_ml(
        cur,
        id_tenant,
        id_produto=int(id_produto),
        id_variante=int(id_variante),
        imagem_fallback=imagem or "",
    )
    if not pictures:
        raise RuntimeError(
            f"«{titulo}»: nenhuma foto disponível para o anúncio no ML "
            "(verifique a galeria do produto)."
        )

    category_id, familia_map = _mapa_categoria_ml(cur, id_tenant, id_categoria_vendedor)
    if not category_id and id_categoria_vendedor:
        raise RuntimeError(
            f"«{titulo}»: mapeie a categoria em Integrações → Mercado Livre → Mapear categorias."
        )
    if not category_id:
        category_id = _prever_categoria_ml(cur, id_tenant, site_id, titulo) or ""
    if not category_id:
        raise RuntimeError(
            f"«{titulo}»: associe uma categoria ao produto e mapeie-a ao Mercado Livre."
        )

    cfg = cfg or {}
    listing_pref = (cfg.get("listing_type_padrao") or "auto").strip()
    frete_gratis = bool(cfg.get("frete_gratis"))

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
    )

    family_name = _family_name_ml(titulo, marca, familia_map)
    usa_up = _seller_usa_user_products_ml(cur, id_tenant, ml_user_id, site_id)

    payload: dict[str, Any] = {
        "category_id": category_id,
        "price": round(float(preco), 2),
        "currency_id": _moeda_site(site_id),
        "available_quantity": max(1, int(estoque or 0)),
        "buying_mode": "buy_it_now",
        "listing_type_id": listing_type,
        "condition": _condicao_ml(condicao),
        "pictures": pictures,
    }
    if usa_up:
        # User Products: family_name obrigatório; title é gerado pelo ML.
        payload["family_name"] = family_name
        payload["shipping"] = _montar_shipping_ml(frete_gratis)
    else:
        payload["title"] = titulo
        payload["channels"] = ["marketplace"]
        payload["shipping"] = _montar_shipping_ml(frete_gratis)
        if sku:
            payload["seller_custom_field"] = sku[:100]
    if attrs:
        payload["attributes"] = attrs

    resp = api_request(cur, id_tenant, "POST", "/items", json_body=payload)
    item_id = str(resp.get("id") or "").strip()
    if not item_id:
        raise RuntimeError(f"«{titulo}»: ML não retornou id do anúncio.")

    _tentar_ativar_anuncio_ml(cur, id_tenant, item_id)
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
               COALESCE(v.peso_bruto_kg, p.peso_bruto_kg, v.peso_liquido_kg, p.peso_liquido_kg) AS peso_kg
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


def _criar_anuncios_ml_lote(cur, id_tenant: int, cfg: dict, linhas: list) -> dict:
    ml_user_id = int(cfg.get("ml_user_id") or 0)
    site_id = (cfg.get("ml_site_id") or "MLB").upper()
    if not ml_user_id:
        raise RuntimeError("Perfil Mercado Livre sem user_id. Reconecte a conta.")

    exportados = 0
    atualizados = 0
    erros: list[str] = []
    resultados: list[dict] = []
    processados = 0

    for row in linhas:
        if processados >= _ML_MAX_CRIAR_POR_SYNC:
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
            condicao,
            marca,
            gtin,
            id_cat_vd,
            altura_cm,
            largura_cm,
            profundidade_cm,
            peso_kg,
        ) = row
        processados += 1
        nome = _titulo_exibicao_ml(titulo or "", sku or "")
        sku_limpo = (sku or "").strip()
        alt = _float_ou_none(altura_cm)
        lar = _float_ou_none(largura_cm)
        pro = _float_ou_none(profundidade_cm)
        pes = _float_ou_none(peso_kg)

        ml_item_id = _item_ja_vinculado_ml(cur, id_tenant, int(id_variante))
        if not ml_item_id and sku_limpo:
            ml_item_id = _buscar_item_ml_por_sku(cur, id_tenant, ml_user_id, sku_limpo)

        if ml_item_id:
            try:
                _atualizar_anuncio_completo_ml(
                    cur,
                    id_tenant,
                    ml_item_id,
                    id_variante=int(id_variante),
                    id_produto=int(id_produto),
                    sku=sku_limpo,
                    preco=float(preco or 0),
                    descricao=descricao or "",
                    imagem=imagem or "",
                    estoque=int(estoque or 0),
                    marca=marca or "",
                    gtin=gtin or "",
                    condicao=condicao,
                    altura_cm=alt,
                    largura_cm=lar,
                    profundidade_cm=pro,
                    peso_kg=pes,
                    titulo=titulo or "",
                )
                atualizados += 1
                resultados.append(
                    {
                        "id_produto": int(id_produto),
                        "titulo": nome,
                        "sku": sku_limpo,
                        "status": "ok",
                        "acao": "atualizado",
                        "mensagem": (
                            "Anúncio atualizado no Mercado Livre "
                            "(fotos, preço, estoque e descrição)."
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
                        "id_produto": int(id_produto),
                        "titulo": nome,
                        "sku": sku_limpo,
                        "status": "erro",
                        "mensagem": msg_user,
                    }
                )
            continue

        try:
            ml_item_id = _criar_anuncio_ml(
                cur,
                id_tenant,
                ml_user_id,
                site_id,
                id_variante=int(id_variante),
                id_produto=int(id_produto),
                sku=sku_limpo,
                titulo=titulo or "",
                preco=float(preco or 0),
                descricao=descricao or "",
                imagem=imagem or "",
                estoque=int(estoque or 0),
                condicao=condicao,
                marca=marca or "",
                gtin=gtin or "",
                id_categoria_vendedor=int(id_cat_vd) if id_cat_vd else None,
                cfg=cfg,
                altura_cm=alt,
                largura_cm=lar,
                profundidade_cm=pro,
                peso_kg=pes,
            )
            exportados += 1
            estado = _estado_anuncio_ml(cur, id_tenant, ml_item_id)
            cat_usada = estado.get("category_id") or ""
            resultados.append(
                {
                    "id_produto": int(id_produto),
                    "titulo": nome,
                    "sku": sku_limpo,
                    "status": "ok",
                    "acao": "criado",
                    "mensagem": _mensagem_pos_publicacao_ml(estado, cat_usada),
                    "ml_item_id": ml_item_id,
                    "ml_category_id": cat_usada,
                    "ml_listing_type": estado.get("listing_type_id") or "",
                    "ml_status": estado.get("status") or "",
                }
            )
        except RuntimeError as e:
            msg_tec = str(e)[:400]
            msg_user = _erro_ml_para_usuario(msg_tec)
            if msg_user not in erros:
                erros.append(msg_user)
            resultados.append(
                {
                    "id_produto": int(id_produto),
                    "titulo": nome,
                    "sku": sku_limpo,
                    "status": "erro",
                    "mensagem": msg_user,
                }
            )

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
            condicao,
            marca,
            gtin,
            _id_cat,
            altura_cm,
            largura_cm,
            profundidade_cm,
            peso_kg,
        ) = row
        sku = (sku or "").strip()
        ml_item = _item_ja_vinculado_ml(cur, id_tenant, int(id_variante))
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
                id_variante=int(id_variante),
                id_produto=int(id_produto),
                sku=sku,
                preco=float(preco or 0),
                descricao=descricao or "",
                imagem=imagem or "",
                estoque=int(estoque or 0),
                marca=marca or "",
                gtin=gtin or "",
                condicao=condicao,
                altura_cm=_float_ou_none(altura_cm),
                largura_cm=_float_ou_none(largura_cm),
                profundidade_cm=_float_ou_none(profundidade_cm),
                peso_kg=_float_ou_none(peso_kg),
                titulo=titulo or "",
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
            condicao,
            marca,
            gtin,
            _id_cat,
            altura_cm,
            largura_cm,
            profundidade_cm,
            peso_kg,
        ) = row
        sku = (sku or "").strip()
        nome = _titulo_exibicao_ml(titulo or "", sku)
        ml_item = _item_ja_vinculado_ml(cur, id_tenant, int(id_variante))
        if not ml_item:
            if not sku:
                sem_sku += 1
                resultados.append(
                    {
                        "id_produto": int(id_produto),
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
                    "id_produto": int(id_produto),
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
                id_variante=int(id_variante),
                id_produto=int(id_produto),
                sku=sku,
                preco=float(preco or 0),
                descricao=descricao or "",
                imagem=imagem or "",
                estoque=int(estoque or 0),
                marca=marca or "",
                gtin=gtin or "",
                condicao=condicao,
                altura_cm=_float_ou_none(altura_cm),
                largura_cm=_float_ou_none(largura_cm),
                profundidade_cm=_float_ou_none(profundidade_cm),
                peso_kg=_float_ou_none(peso_kg),
                titulo=titulo or "",
            )
            atualizados += 1
            vinculados += 1
            resultados.append(
                {
                    "id_produto": int(id_produto),
                    "titulo": nome,
                    "sku": sku,
                    "status": "ok",
                    "acao": "atualizado",
                    "mensagem": (
                        "Anúncio atualizado no Mercado Livre "
                        "(fotos, preço, estoque e descrição)."
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
                    "id_produto": int(id_produto),
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
