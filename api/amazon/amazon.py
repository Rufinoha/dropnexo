# api/amazon/amazon.py — OAuth LWA, API e sync Amazon SP-API
from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import requests

from core.tokens import criptografar_token, descriptografar_token
from global_utils import agora_utc, obter_base_url, url_imagem_produto

_log = logging.getLogger(__name__)

AMAZON_LWA_TOKEN_URL = "https://api.amazon.com/auth/o2/token"
AMAZON_AUTH_CONSENT_DEFAULT = "https://sellercentral.amazon.com.br/apps/authorize/consent"
AMAZON_API_BASES = {
    "na": "https://sellingpartnerapi-na.amazon.com",
    "eu": "https://sellingpartnerapi-eu.amazon.com",
    "fe": "https://sellingpartnerapi-fe.amazon.com",
}
AMAZON_OAUTH_TIMEOUT = (5, 25)
AMAZON_API_TIMEOUT = (10, 60)
_AMAZON_MAX_CRIAR_POR_SYNC = 20

_TABELA_OK: bool | None = None


def _env(key: str) -> str:
    return (os.getenv(key) or "").strip()


def amazon_lwa_client_id() -> str:
    return _env("AMAZON_LWA_CLIENT_ID")


def amazon_lwa_client_secret() -> str:
    return _env("AMAZON_LWA_CLIENT_SECRET")


def amazon_app_id() -> str:
    return _env("AMAZON_APP_ID")


def marketplace_id_padrao() -> str:
    return _env("AMAZON_MARKETPLACE_ID") or "A2Q3Y263D00KWC"


def amazon_region() -> str:
    return (_env("AMAZON_REGION") or "na").lower()


def amazon_api_base() -> str:
    custom = _env("AMAZON_API_BASE")
    if custom:
        return custom.rstrip("/")
    return AMAZON_API_BASES.get(amazon_region(), AMAZON_API_BASES["na"])


def amazon_configurado() -> bool:
    return bool(amazon_lwa_client_id() and amazon_lwa_client_secret() and amazon_app_id())


def credenciais_amazon() -> tuple[str, str, str]:
    client_id = amazon_lwa_client_id()
    client_secret = amazon_lwa_client_secret()
    app_id = amazon_app_id()
    if not client_id or not client_secret or not app_id:
        raise RuntimeError(
            "Credenciais Amazon incompletas. Configure AMAZON_LWA_CLIENT_ID, "
            "AMAZON_LWA_CLIENT_SECRET e AMAZON_APP_ID no .env do servidor."
        )
    return client_id, client_secret, app_id


def redirect_uri_oauth() -> str:
    return f"{obter_base_url().rstrip('/')}/api/integracoes/amazon/oauth/callback"


def gerar_state_oauth() -> str:
    return secrets.token_urlsafe(24)


def url_autorizacao(state: str) -> str:
    _, _, app_id = credenciais_amazon()
    qs = urlencode(
        {
            "application_id": app_id,
            "state": state,
            "redirect_uri": redirect_uri_oauth(),
            "version": "beta",
        }
    )
    base = _env("AMAZON_AUTH_CONSENT") or AMAZON_AUTH_CONSENT_DEFAULT
    return f"{base.rstrip('/')}?{qs}"


def _formatar_erro_amazon(status: int, text: str) -> str:
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            errors = data.get("errors")
            if isinstance(errors, list) and errors:
                first = errors[0] if isinstance(errors[0], dict) else {}
                msg = (first.get("message") or first.get("details") or "").strip()
                code = first.get("code") or ""
                if msg:
                    return f"Amazon ({status}, {code}): {msg[:280]}"
            msg = (data.get("error_description") or data.get("error") or data.get("message") or "").strip()
            if msg:
                return f"Amazon ({status}): {msg[:280]}"
    except (TypeError, ValueError, json.JSONDecodeError):
        pass
    return f"Amazon SP-API ({status}): {(text or '')[:280]}"


def _post_token(data: dict[str, str]) -> dict[str, Any]:
    client_id, client_secret, _ = credenciais_amazon()
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        **data,
    }
    try:
        r = requests.post(
            AMAZON_LWA_TOKEN_URL,
            data=payload,
            headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
            timeout=AMAZON_OAUTH_TIMEOUT,
        )
    except requests.Timeout as e:
        raise RuntimeError("Amazon demorou para responder. Tente novamente.") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Falha de rede ao contactar Amazon LWA: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(_formatar_erro_amazon(r.status_code, r.text))
    out = r.json() if r.content else {}
    if not isinstance(out, dict) or not out.get("access_token"):
        raise RuntimeError("Amazon não retornou access_token.")
    return out


def trocar_code_por_tokens(code: str) -> dict[str, Any]:
    return _post_token(
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri_oauth(),
        }
    )


def renovar_access_token(refresh_token: str) -> dict[str, Any]:
    return _post_token(
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        }
    )


def _expires_em(expires_in: int | None) -> datetime | None:
    if not expires_in:
        return None
    return datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))


def _garantir_tabela_amazon(cur) -> bool:
    """Cria tbl_integracao_amazon se ausente (SQL 082)."""
    global _TABELA_OK
    if _TABELA_OK is True:
        return True
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tbl_integracao_amazon (
                id_tenant INTEGER PRIMARY KEY REFERENCES tbl_tenant(id) ON DELETE CASCADE,
                status VARCHAR(32) NOT NULL DEFAULT 'desconectado',
                access_token_enc TEXT,
                refresh_token_enc TEXT,
                token_expires_em TIMESTAMPTZ,
                seller_id VARCHAR(64),
                marketplace_id VARCHAR(32) DEFAULT 'A2Q3Y263D00KWC',
                seller_info JSONB NOT NULL DEFAULT '{}',
                pedidos_importar_auto BOOLEAN NOT NULL DEFAULT FALSE,
                produtos_exportar_auto BOOLEAN NOT NULL DEFAULT FALSE,
                produtos_modo VARCHAR(32) NOT NULL DEFAULT 'vincular_sku',
                estoque_sync_ativo BOOLEAN NOT NULL DEFAULT FALSE,
                ultima_sync_pedidos TIMESTAMPTZ,
                conectado_em TIMESTAMPTZ,
                ultimo_erro TEXT,
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
            )
            """
        )
        _TABELA_OK = True
        return True
    except Exception:
        _TABELA_OK = None
        return False


def _tem_tabela_amazon(cur) -> bool:
    global _TABELA_OK
    if _TABELA_OK is True:
        return True
    cur.execute("SELECT to_regclass(%s)", ("tbl_integracao_amazon",))
    row = cur.fetchone()
    ok = bool(row and row[0])
    if ok:
        _TABELA_OK = True
        return True
    return _garantir_tabela_amazon(cur)


def salvar_tokens(
    cur,
    id_tenant: int,
    tokens: dict[str, Any],
    *,
    seller_id: str | None = None,
) -> None:
    if not _tem_tabela_amazon(cur):
        raise RuntimeError("Tabela tbl_integracao_amazon não existe. Aplique o SQL 082.")
    access = tokens.get("access_token") or ""
    refresh = tokens.get("refresh_token") or ""
    expires = _expires_em(tokens.get("expires_in"))
    mp = marketplace_id_padrao()
    cur.execute(
        """
        INSERT INTO tbl_integracao_amazon (
            id_tenant, status, access_token_enc, refresh_token_enc,
            token_expires_em, seller_id, marketplace_id,
            conectado_em, ultimo_erro, atualizado_em
        ) VALUES (%s, 'conectado', %s, %s, %s, %s, %s, %s, NULL, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            status = 'conectado',
            access_token_enc = EXCLUDED.access_token_enc,
            refresh_token_enc = COALESCE(EXCLUDED.refresh_token_enc, tbl_integracao_amazon.refresh_token_enc),
            token_expires_em = EXCLUDED.token_expires_em,
            seller_id = COALESCE(EXCLUDED.seller_id, tbl_integracao_amazon.seller_id),
            marketplace_id = COALESCE(EXCLUDED.marketplace_id, tbl_integracao_amazon.marketplace_id),
            conectado_em = COALESCE(tbl_integracao_amazon.conectado_em, EXCLUDED.conectado_em),
            ultimo_erro = NULL,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            criptografar_token(access),
            criptografar_token(refresh) if refresh else None,
            expires,
            (seller_id or "").strip() or None,
            mp,
            agora_utc(),
            agora_utc(),
        ),
    )


def carregar_tokens_armazenados(cur, id_tenant: int) -> dict[str, Any]:
    if not _tem_tabela_amazon(cur):
        return {"status": "desconectado"}
    cur.execute(
        """
        SELECT status, access_token_enc, refresh_token_enc, token_expires_em,
               seller_id, marketplace_id
        FROM tbl_integracao_amazon WHERE id_tenant = %s
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
        "seller_id": row[4],
        "marketplace_id": row[5],
    }


def desconectar_amazon(cur, id_tenant: int) -> None:
    if not _tem_tabela_amazon(cur):
        return
    cur.execute(
        """
        UPDATE tbl_integracao_amazon SET
            status = 'desconectado',
            access_token_enc = NULL,
            refresh_token_enc = NULL,
            token_expires_em = NULL,
            seller_id = NULL,
            seller_info = '{}',
            ultimo_erro = NULL,
            atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (agora_utc(), id_tenant),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO tbl_integracao_amazon (id_tenant, status, atualizado_em)
            VALUES (%s, 'desconectado', %s)
            ON CONFLICT (id_tenant) DO NOTHING
            """,
            (id_tenant, agora_utc()),
        )


def amazon_conectado(cur, id_tenant: int) -> bool:
    if not _tem_tabela_amazon(cur):
        return False
    cur.execute(
        "SELECT status FROM tbl_integracao_amazon WHERE id_tenant = %s",
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
        raise RuntimeError("Amazon não conectada.")
    access = dados.get("access_token") or ""
    if access and not _token_expirado(dados.get("token_expires_em")):
        return access
    refresh = dados.get("refresh_token") or ""
    if not refresh:
        raise RuntimeError("Token Amazon expirado. Reconecte a conta.")
    novos = renovar_access_token(refresh)
    salvar_tokens(cur, id_tenant, novos, seller_id=dados.get("seller_id"))
    return novos.get("access_token") or ""


def _seller_id(cur, id_tenant: int) -> str:
    cur.execute(
        "SELECT seller_id FROM tbl_integracao_amazon WHERE id_tenant = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    return (row[0] or "").strip() if row else ""


def _marketplace_id(cur, id_tenant: int) -> str:
    cur.execute(
        "SELECT marketplace_id FROM tbl_integracao_amazon WHERE id_tenant = %s",
        (id_tenant,),
    )
    row = cur.fetchone()
    return ((row[0] if row else None) or marketplace_id_padrao()).strip()


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
    api_path = path if path.startswith("/") else f"/{path}"
    url = api_path if api_path.startswith("http") else f"{amazon_api_base()}{api_path}"

    headers = {
        "x-amz-access-token": token,
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": "DropNexo/1.0 (Language=Python)",
    }

    try:
        r = requests.request(
            method.upper(),
            url,
            headers=headers,
            params=params or None,
            json=json_body if json_body is not None else None,
            timeout=AMAZON_API_TIMEOUT,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Falha na API Amazon: {e}") from e

    if r.status_code >= 400:
        raise RuntimeError(_formatar_erro_amazon(r.status_code, r.text))

    if not r.content:
        return {}
    try:
        return r.json()
    except ValueError:
        return {"raw": r.text}


def atualizar_seller_info(
    cur,
    id_tenant: int,
    *,
    seller_id: str | None = None,
) -> dict[str, Any]:
    if not _tem_tabela_amazon(cur):
        return {}
    sid = (seller_id or _seller_id(cur, id_tenant) or "").strip()
    mp = _marketplace_id(cur, id_tenant)
    info: dict[str, Any] = {
        "seller_id": sid,
        "marketplace_id": mp,
        "region": amazon_region(),
    }
    if sid:
        try:
            data = api_request(
                cur,
                id_tenant,
                "GET",
                "/sellers/v1/marketplaceParticipations",
            )
            payload = data.get("payload") if isinstance(data, dict) else None
            if isinstance(payload, list):
                info["marketplaces"] = [
                    {
                        "id": (p.get("marketplace") or {}).get("id"),
                        "name": (p.get("marketplace") or {}).get("name"),
                        "country": (p.get("marketplace") or {}).get("countryCode"),
                    }
                    for p in payload
                    if isinstance(p, dict)
                ]
        except RuntimeError as e:
            _log.info("Amazon seller info (opcional): %s", e)
            info["aviso"] = str(e)[:200]

    cur.execute(
        """
        UPDATE tbl_integracao_amazon SET
            seller_id = COALESCE(%s, seller_id),
            marketplace_id = COALESCE(%s, marketplace_id),
            seller_info = %s::jsonb,
            atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (
            sid or None,
            mp,
            json.dumps(info, ensure_ascii=False),
            agora_utc(),
            id_tenant,
        ),
    )
    return info


def carregar_config_amazon(cur, id_tenant: int) -> dict[str, Any]:
    base = {
        "status": "desconectado",
        "conectado": False,
        "seller_id": None,
        "marketplace_id": marketplace_id_padrao(),
        "loja": {},
        "pedidos_importar_auto": False,
        "produtos_exportar_auto": False,
        "produtos_modo": "vincular_sku",
        "estoque_sync_ativo": False,
        "ultima_sync_pedidos": None,
        "conectado_em": None,
        "ultimo_erro": None,
        "redirect_uri": redirect_uri_oauth(),
    }
    if not _tem_tabela_amazon(cur):
        return base
    cur.execute(
        """
        SELECT status, seller_id, marketplace_id, seller_info,
               pedidos_importar_auto, produtos_exportar_auto, produtos_modo,
               estoque_sync_ativo, ultima_sync_pedidos, conectado_em, ultimo_erro
        FROM tbl_integracao_amazon WHERE id_tenant = %s
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
        "seller_id": row[1],
        "marketplace_id": row[2] or marketplace_id_padrao(),
        "loja": loja,
        "pedidos_importar_auto": bool(row[4]),
        "produtos_exportar_auto": bool(row[5]),
        "produtos_modo": modo,
        "estoque_sync_ativo": bool(row[7]),
        "ultima_sync_pedidos": row[8].isoformat() if row[8] else None,
        "conectado_em": row[9].isoformat() if row[9] else None,
        "ultimo_erro": row[10],
    }


def salvar_config_amazon(
    cur,
    id_tenant: int,
    *,
    pedidos_importar_auto: bool | None = None,
    produtos_exportar_auto: bool | None = None,
    produtos_modo: str | None = None,
    estoque_sync_ativo: bool | None = None,
) -> None:
    if not _tem_tabela_amazon(cur):
        raise RuntimeError("Tabela tbl_integracao_amazon não existe. Aplique o SQL 082.")
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
        f"UPDATE tbl_integracao_amazon SET {', '.join(set_parts)} WHERE id_tenant = %s",
        vals,
    )
    if cur.rowcount == 0:
        cols = ["id_tenant", *updates.keys(), "atualizado_em"]
        placeholders = ", ".join(["%s"] * len(cols))
        set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in updates) + ", atualizado_em = EXCLUDED.atualizado_em"
        cur.execute(
            f"""
            INSERT INTO tbl_integracao_amazon ({", ".join(cols)})
            VALUES ({placeholders})
            ON CONFLICT (id_tenant) DO UPDATE SET {set_clause}
            """,
            [id_tenant, *updates.values(), agora_utc()],
        )


def _garantir_tabela_amazon_categoria_map(cur) -> bool:
    try:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS tbl_integracao_amazon_categoria_map (
                id SERIAL PRIMARY KEY,
                id_tenant INTEGER NOT NULL REFERENCES tbl_tenant(id) ON DELETE CASCADE,
                id_categoria INTEGER NOT NULL REFERENCES tbl_categoria(id) ON DELETE CASCADE,
                amazon_product_type VARCHAR(128) NOT NULL,
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


def _mapa_product_type_amazon(cur, id_tenant: int, id_categoria: int | None) -> str:
    if not id_categoria:
        return ""
    _garantir_tabela_amazon_categoria_map(cur)
    try:
        cur.execute(
            """
            SELECT amazon_product_type
            FROM tbl_integracao_amazon_categoria_map
            WHERE id_tenant = %s AND id_categoria = %s
            """,
            (id_tenant, int(id_categoria)),
        )
        row = cur.fetchone()
        return str(row[0]).strip() if row and row[0] else ""
    except Exception:
        return ""


def listar_mapeamento_categorias_amazon(cur, id_tenant: int) -> list[dict]:
    _garantir_tabela_amazon_categoria_map(cur)
    cur.execute(
        """
        SELECT c.id, c.nome, COALESCE(m.amazon_product_type, '')
        FROM tbl_categoria c
        LEFT JOIN tbl_integracao_amazon_categoria_map m
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
            "amazon_product_type": r[2] or "",
        }
        for r in cur.fetchall()
    ]


def salvar_mapeamento_categorias_amazon(cur, id_tenant: int, itens: list[dict]) -> int:
    if not _garantir_tabela_amazon_categoria_map(cur):
        raise RuntimeError("Tabela de mapeamento Amazon indisponível. Aplique o SQL 083.")
    salvos = 0
    agora = agora_utc()
    for item in itens:
        try:
            id_cat = int(item.get("id_categoria") or 0)
        except (TypeError, ValueError):
            continue
        amz_type = (item.get("amazon_product_type") or "").strip()
        if not id_cat or not amz_type:
            continue
        cur.execute(
            "SELECT 1 FROM tbl_categoria WHERE id = %s AND id_tenant = %s AND ativo = TRUE",
            (id_cat, id_tenant),
        )
        if not cur.fetchone():
            continue
        cur.execute(
            """
            INSERT INTO tbl_integracao_amazon_categoria_map (
                id_tenant, id_categoria, amazon_product_type, atualizado_em
            ) VALUES (%s, %s, %s, %s)
            ON CONFLICT (id_tenant, id_categoria) DO UPDATE SET
                amazon_product_type = EXCLUDED.amazon_product_type,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (id_tenant, id_cat, amz_type, agora),
        )
        salvos += 1
    return salvos


def buscar_product_types_amazon(cur, id_tenant: int, keywords: str) -> list[dict]:
    """Busca Product Types Amazon via Product Type Definitions API."""
    kw = (keywords or "").strip()
    if not kw:
        return []
    mp = _marketplace_id(cur, id_tenant)
    data = api_request(
        cur,
        id_tenant,
        "GET",
        "/definitions/2020-09-01/productTypes",
        params={"marketplaceIds": mp, "keywords": kw},
    )
    tipos = []
    payload = data.get("productTypes") if isinstance(data, dict) else None
    if not isinstance(payload, list) and isinstance(data, dict):
        payload = (data.get("payload") or {}).get("productTypes") if isinstance(data.get("payload"), dict) else data.get("productTypes")
    if not isinstance(payload, list):
        payload = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = (item.get("name") or item.get("productType") or "").strip()
        display = (item.get("displayName") or name).strip()
        if name:
            tipos.append({"product_type": name, "display_name": display, "raw": item})
    return tipos


def _sql_produtos_vitrine_amazon(ids_produtos: list[int] | None = None) -> tuple[str, list]:
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


def _imagem_publica_amazon(imagem_path: str | None) -> str:
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


def _item_ja_vinculado_amazon(cur, id_tenant: int, id_variante: int) -> str | None:
    cur.execute(
        """
        SELECT id_bling FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'amazon' AND contexto = 'vendedor'
          AND entidade = 'produto' AND id_dropnexo = %s
        LIMIT 1
        """,
        (id_tenant, id_variante),
    )
    row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _parse_map_amazon(id_bling: str) -> tuple[str, str]:
    """Retorna (seller_sku, asin). id_bling = sku ou asin:sku."""
    raw = (id_bling or "").strip()
    if ":" in raw:
        asin, sku = raw.split(":", 1)
        return sku.strip(), asin.strip()
    return raw, ""


def _salvar_map_produto_amazon(
    cur,
    id_tenant: int,
    id_variante: int,
    id_produto: int,
    sku: str,
    *,
    asin: str = "",
) -> None:
    id_bling = f"{asin}:{sku}" if asin and sku else str(sku)
    cur.execute(
        """
        DELETE FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'amazon' AND contexto = 'vendedor'
          AND entidade = 'produto' AND id_dropnexo = %s
        """,
        (id_tenant, id_variante),
    )
    meta = json.dumps(
        {
            "id_produto": id_produto,
            "seller_sku": sku,
            "asin": asin or None,
        },
        ensure_ascii=False,
    )
    cur.execute(
        """
        INSERT INTO tbl_integracao_map (
            id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta, atualizado_em
        ) VALUES (%s, 'amazon', 'vendedor', 'produto', %s, %s, %s, %s::jsonb, %s)
        ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling) DO UPDATE SET
            id_dropnexo = EXCLUDED.id_dropnexo,
            sku = EXCLUDED.sku,
            meta = EXCLUDED.meta,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, id_bling, id_variante, sku, meta, agora_utc()),
    )


def _buscar_listing_amazon_por_sku(cur, id_tenant: int, sku: str) -> tuple[str, str] | None:
    sku = (sku or "").strip()
    if not sku:
        return None
    seller_id = _seller_id(cur, id_tenant)
    if not seller_id:
        raise RuntimeError("Seller ID Amazon ausente. Reconecte a conta.")
    mp = _marketplace_id(cur, id_tenant)
    sku_enc = quote(sku, safe="")
    try:
        data = api_request(
            cur,
            id_tenant,
            "GET",
            f"/listings/2021-08-01/items/{seller_id}/{sku_enc}",
            params={
                "marketplaceIds": mp,
                "includedData": "summaries,attributes,offers,fulfillmentAvailability",
            },
        )
    except RuntimeError:
        return None
    if not isinstance(data, dict):
        return None
    asin = ""
    summaries = data.get("summaries") or []
    if summaries and isinstance(summaries[0], dict):
        asin = str(summaries[0].get("asin") or "").strip()
    sku_ret = str(data.get("sku") or sku).strip()
    if sku_ret:
        return sku_ret, asin
    return None


def _attr_list(value: Any, marketplace_id: str) -> list[dict]:
    return [{"value": value, "marketplace_id": marketplace_id}]


def _criar_listing_amazon(
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
    marca: str,
    gtin: str,
    id_categoria_vendedor: int | None,
) -> tuple[str, str]:
    product_type = _mapa_product_type_amazon(cur, id_tenant, id_categoria_vendedor)
    if not product_type:
        raise RuntimeError(
            f"«{titulo}»: mapeie o Product Type Amazon em Integrações → Amazon → Mapear categorias."
        )
    if preco <= 0:
        raise RuntimeError(f"Preço inválido para «{titulo}».")
    img_url = _imagem_publica_amazon(imagem)
    if not img_url:
        raise RuntimeError(f"«{titulo}»: foto pública obrigatória para publicar na Amazon.")

    seller_id = _seller_id(cur, id_tenant)
    if not seller_id:
        raise RuntimeError("Seller ID Amazon ausente. Reconecte a conta.")
    mp = _marketplace_id(cur, id_tenant)

    attributes: dict[str, Any] = {
        "item_name": _attr_list((titulo or sku or "Produto")[:200], mp),
        "brand": _attr_list((marca or "Generic")[:100], mp),
        "main_product_image_locator": [{"media_location": img_url, "marketplace_id": mp}],
        "purchasable_offer": [
            {
                "currency": "BRL",
                "our_price": [{"schedule": [{"value_with_tax": round(float(preco), 2)}]}],
                "marketplace_id": mp,
            }
        ],
        "fulfillment_availability": [
            {
                "fulfillment_channel_code": "DEFAULT",
                "quantity": max(0, int(estoque or 0)),
            }
        ],
    }
    if gtin:
        attributes["externally_assigned_product_identifier"] = [
            {"type": "gtin", "value": gtin, "marketplace_id": mp}
        ]
    if descricao:
        attributes["product_description"] = _attr_list(descricao[:2000], mp)

    body = {
        "productType": product_type,
        "requirements": "LISTING",
        "attributes": attributes,
    }
    sku_enc = quote(sku, safe="")
    try:
        data = api_request(
            cur,
            id_tenant,
            "PUT",
            f"/listings/2021-08-01/items/{seller_id}/{sku_enc}",
            params={"marketplaceIds": mp},
            json_body=body,
        )
    except RuntimeError as e:
        msg = str(e)
        if any(x in msg.lower() for x in ("attribute", "required", "missing", "validation")):
            raise RuntimeError(
                f"«{titulo}»: Amazon rejeitou atributos obrigatórios do Product Type "
                f"«{product_type}». Complete o anúncio no Seller Central ou ajuste o "
                "mapeamento de Product Type."
            ) from e
        raise

    asin = ""
    if isinstance(data, dict):
        issues = data.get("issues") or []
        if issues and data.get("status") in ("INVALID", "INVALIDATED"):
            first = issues[0] if isinstance(issues[0], dict) else {}
            detail = (first.get("message") or first.get("code") or str(first))[:200]
            raise RuntimeError(
                f"«{titulo}»: Amazon rejeitou o anúncio ({detail}). "
                "Complete o listing no Seller Central ou revise o Product Type."
            )
        summaries = data.get("summaries") or []
        if summaries and isinstance(summaries[0], dict):
            asin = str(summaries[0].get("asin") or "").strip()

    _salvar_map_produto_amazon(
        cur, id_tenant, id_variante, id_produto, sku, asin=asin
    )
    return sku, asin


def _atualizar_estoque_map_amazon(
    cur,
    id_tenant: int,
    id_bling: str,
    *,
    quantidade: int,
    preco: float | None = None,
) -> None:
    from api.amazon.eco_estoque import registrar_eco_amazon_pendente

    seller_sku, _asin = _parse_map_amazon(id_bling)
    if not seller_sku:
        raise RuntimeError("Produto Amazon não mapeado.")
    seller_id = _seller_id(cur, id_tenant)
    if not seller_id:
        raise RuntimeError("Seller ID Amazon ausente. Reconecte a conta.")
    mp = _marketplace_id(cur, id_tenant)

    registrar_eco_amazon_pendente(
        cur,
        id_tenant,
        amazon_sku_key=seller_sku,
        quantidade_esperada=max(0, int(quantidade)),
        origem="dropnexo_export",
    )

    # Product type necessário no PATCH — tenta PRODUCT genérico se desconhecido
    product_type = "PRODUCT"
    cur.execute(
        """
        SELECT meta FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'amazon' AND contexto = 'vendedor'
          AND entidade = 'produto' AND id_bling = %s
        LIMIT 1
        """,
        (id_tenant, id_bling),
    )
    row = cur.fetchone()
    if row and row[0]:
        meta = row[0]
        if isinstance(meta, str):
            try:
                meta = json.loads(meta)
            except (TypeError, ValueError):
                meta = {}
        if isinstance(meta, dict) and meta.get("product_type"):
            product_type = str(meta["product_type"])

    patches = [
        {
            "op": "replace",
            "path": "/attributes/fulfillment_availability",
            "value": [
                {
                    "fulfillment_channel_code": "DEFAULT",
                    "quantity": max(0, int(quantidade)),
                }
            ],
        }
    ]
    if preco is not None and float(preco) > 0:
        patches.append(
            {
                "op": "replace",
                "path": "/attributes/purchasable_offer",
                "value": [
                    {
                        "currency": "BRL",
                        "our_price": [
                            {"schedule": [{"value_with_tax": round(float(preco), 2)}]}
                        ],
                        "marketplace_id": mp,
                    }
                ],
            }
        )

    sku_enc = quote(seller_sku, safe="")
    api_request(
        cur,
        id_tenant,
        "PATCH",
        f"/listings/2021-08-01/items/{seller_id}/{sku_enc}",
        params={"marketplaceIds": mp},
        json_body={"productType": product_type, "patches": patches},
    )


def publicar_produtos_amazon(cur, id_tenant: int, ids_produtos: list[int]) -> dict:
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

    cfg = carregar_config_amazon(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("Conecte a Amazon em Integrações.")
    if not cfg.get("produtos_exportar_auto"):
        raise RuntimeError(
            "Ative a exportação de produtos em Integrações → Amazon → Produtos."
        )

    modo = cfg.get("produtos_modo") or "vincular_sku"
    sql, extra = _sql_produtos_vitrine_amazon(ids)
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
        if processados >= _AMAZON_MAX_CRIAR_POR_SYNC:
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
            marca,
            gtin,
            id_cat_vd,
        ) = row
        processados += 1
        sku_limpo = (sku or "").strip()
        nome = (titulo or sku_limpo or "Produto")[:80]
        map_id = _item_ja_vinculado_amazon(cur, id_tenant, int(id_variante))

        if modo == "criar_anuncio" and not map_id:
            if not sku_limpo:
                sem_sku += 1
                resultados.append(
                    {
                        "id_produto": int(id_produto),
                        "titulo": nome,
                        "sku": sku_limpo,
                        "status": "erro",
                        "mensagem": "Produto sem SKU para publicar na Amazon.",
                    }
                )
                continue
            try:
                seller_sku, asin = _criar_listing_amazon(
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
                    marca=marca or "",
                    gtin=gtin or "",
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
                        "mensagem": "Produto publicado na Amazon.",
                        "seller_sku": seller_sku,
                        "asin": asin,
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
                        "mensagem": "Produto sem SKU para vincular à Amazon.",
                    }
                )
                continue
            found = _buscar_listing_amazon_por_sku(cur, id_tenant, sku_limpo)
            if not found:
                nao_encontrados += 1
                resultados.append(
                    {
                        "id_produto": int(id_produto),
                        "titulo": nome,
                        "sku": sku_limpo,
                        "status": "erro",
                        "mensagem": "Nenhum listing encontrado na Amazon com este SKU.",
                    }
                )
                continue
            seller_sku, asin = found
            _salvar_map_produto_amazon(
                cur,
                id_tenant,
                int(id_variante),
                int(id_produto),
                seller_sku,
                asin=asin,
            )
            map_id = f"{asin}:{seller_sku}" if asin else seller_sku
            vinculados += 1

        try:
            _atualizar_estoque_map_amazon(
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
                    "mensagem": "Estoque/preço atualizado na Amazon.",
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
    msg = " · ".join(partes) + " na Amazon." if partes else "Nenhum produto processado."
    if total > _AMAZON_MAX_CRIAR_POR_SYNC and processados >= _AMAZON_MAX_CRIAR_POR_SYNC:
        msg += (
            f" Limite de {_AMAZON_MAX_CRIAR_POR_SYNC} por sincronização — "
            "execute novamente para continuar."
        )
    if nao_encontrados:
        msg += f" {nao_encontrados} sem SKU correspondente na Amazon."
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


def sincronizar_estoque_amazon(cur, id_tenant: int) -> dict:
    from api.amazon.sync_runtime import sincronizar_todos_estoques_amazon

    return sincronizar_todos_estoques_amazon(cur, id_tenant)


def importar_pedidos_amazon(cur, id_tenant: int, *, dias: int = 7) -> dict:
    from api.amazon.pedidos_amazon import importar_pedidos_amazon as _importar

    return _importar(cur, id_tenant, dias=dias)
