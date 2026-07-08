# api/mercado_livre/mercado_livre.py — OAuth, API e sync de pedidos ML
from __future__ import annotations

import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
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
        raise RuntimeError(f"Mercado Livre API ({r.status_code}): {r.text[:500]}")
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
    if _tem_colunas_config_ext(cur):
        return True
    global _ML_COLS_EXT_OK
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
        _ML_COLS_EXT_OK = True
        return True
    except Exception:
        return False


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
    if ext:
        cur.execute(
            """
            SELECT status, ml_user_id, ml_site_id, ml_conta_info,
                   pedidos_importar_auto, ultima_sync_pedidos, conectado_em, ultimo_erro,
                   produtos_exportar_auto, produtos_modo, estoque_sync_ativo
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
    return out


def salvar_config_ml(
    cur,
    id_tenant: int,
    *,
    pedidos_importar_auto: bool | None = None,
    produtos_exportar_auto: bool | None = None,
    produtos_modo: str | None = None,
    estoque_sync_ativo: bool | None = None,
) -> None:
    if not _tem_tabela_ml(cur):
        raise RuntimeError("Tabela tbl_integracao_mercado_livre não existe.")
    updates: dict[str, Any] = {}
    if pedidos_importar_auto is not None:
        updates["pedidos_importar_auto"] = bool(pedidos_importar_auto)
    precisa_ext = any(v is not None for v in (produtos_exportar_auto, produtos_modo, estoque_sync_ativo))
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
    """
    Lista pedidos pagos recentes no ML e prepara importação.
    A gravação em tbl_pedido (origem mercado_livre) será expandida na próxima etapa.
    """
    cfg = carregar_config_ml(cur, id_tenant)
    ml_user_id = cfg.get("ml_user_id")
    if not ml_user_id:
        raise RuntimeError("Perfil Mercado Livre sem user_id. Reconecte a conta.")

    desde = datetime.now(timezone.utc) - timedelta(days=max(1, min(dias, 60)))
    params = {
        "seller": ml_user_id,
        "order.status": "paid",
        "sort": "date_desc",
        "order.date_created.from": desde.strftime("%Y-%m-%dT%H:%M:%S.000-00:00"),
        "limit": 50,
    }
    data = api_request(cur, id_tenant, "GET", "/orders/search", params=params)
    resultados = data.get("results") or []
    ids = [str(o.get("id")) for o in resultados if o.get("id")]

    return {
        "message": (
            f"{len(ids)} pedido(s) pago(s) encontrado(s) nos últimos {dias} dia(s). "
            "A importação automática para DropNexo será habilitada na próxima etapa."
        ),
        "total_encontrados": len(ids),
        "ids_amostra": ids[:10],
        "importados": 0,
        "ignorados": len(ids),
    }


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


def _listing_type_ml(cur, id_tenant: int, ml_user_id: int, category_id: str) -> str:
    try:
        data = api_request(
            cur,
            id_tenant,
            "GET",
            f"/users/{int(ml_user_id)}/available_listing_types",
            params={"category_id": category_id},
        )
        disponiveis = data.get("available") or []
        for prefer in ("gold_special", "gold_pro", "gold_premium", "free"):
            if prefer in disponiveis:
                return prefer
        if disponiveis:
            return str(disponiveis[0])
    except RuntimeError:
        pass
    return "gold_special"


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
) -> str:
    titulo = (titulo or "Produto").strip()[:60]
    if preco <= 0:
        raise RuntimeError(f"Preço inválido para «{titulo}».")
    img_url = _imagem_publica_ml(imagem)
    if not img_url:
        raise RuntimeError(f"«{titulo}»: imagem pública obrigatória para novo anúncio no ML.")

    category_id = _prever_categoria_ml(cur, id_tenant, site_id, titulo)
    if not category_id:
        raise RuntimeError(f"«{titulo}»: não foi possível sugerir categoria no Mercado Livre.")

    listing_type = _listing_type_ml(cur, id_tenant, ml_user_id, category_id)
    payload: dict[str, Any] = {
        "title": titulo,
        "category_id": category_id,
        "price": round(float(preco), 2),
        "currency_id": _moeda_site(site_id),
        "available_quantity": max(1, int(estoque or 0)),
        "buying_mode": "buy_it_now",
        "listing_type_id": listing_type,
        "condition": _condicao_ml(condicao),
        "pictures": [{"source": img_url}],
        "shipping": {"mode": "me2", "local_pick_up": False, "free_shipping": False},
    }
    attrs: list[dict[str, str]] = []
    if sku:
        payload["seller_custom_field"] = sku[:100]
        attrs.append({"id": "SELLER_SKU", "value_name": sku[:60]})
    if attrs:
        payload["attributes"] = attrs

    resp = api_request(cur, id_tenant, "POST", "/items", json_body=payload)
    item_id = str(resp.get("id") or "").strip()
    if not item_id:
        raise RuntimeError(f"«{titulo}»: ML não retornou id do anúncio.")

    texto = (descricao or "").strip()
    if texto:
        try:
            api_request(
                cur,
                id_tenant,
                "POST",
                f"/items/{item_id}/description",
                json_body={"plain_text": texto[:50000]},
            )
        except RuntimeError:
            pass

    _salvar_map_produto_ml(cur, id_tenant, id_variante, id_produto, sku, item_id)
    return item_id


def _sql_produtos_vitrine_ml() -> str:
    return """
        SELECT pv.id, pv.id_variante, pv.id_produto,
               TRIM(COALESCE(NULLIF(v.sku, ''), p.sku, '')) AS sku,
               COALESCE(NULLIF(TRIM(pv.nome_vitrine), ''), NULLIF(TRIM(v.nome_exibicao), ''), p.nome) AS titulo,
               COALESCE(pv.preco_venda, v.preco, p.preco, 0) AS preco,
               LEFT(COALESCE(NULLIF(TRIM(pv.descricao_vitrine), ''), p.descricao, ''), 5000) AS descricao,
               COALESCE(NULLIF(TRIM(pv.imagem_url_vitrine), ''), v.imagem_url, p.imagem_url) AS imagem,
               COALESCE(ve.quantidade, 0) AS estoque,
               p.condicao
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = v.id
        WHERE pv.id_tenant_vendedor = %s AND pv.ativo = TRUE
        ORDER BY pv.id
    """


def _criar_anuncios_ml_lote(cur, id_tenant: int, cfg: dict, linhas: list) -> dict:
    ml_user_id = int(cfg.get("ml_user_id") or 0)
    site_id = (cfg.get("ml_site_id") or "MLB").upper()
    if not ml_user_id:
        raise RuntimeError("Perfil Mercado Livre sem user_id. Reconecte a conta.")

    exportados = 0
    ignorados = 0
    erros: list[str] = []
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
        ) = row
        processados += 1

        if _item_ja_vinculado_ml(cur, id_tenant, int(id_variante)):
            ignorados += 1
            continue
        if sku and _buscar_item_ml_por_sku(cur, id_tenant, ml_user_id, sku):
            ignorados += 1
            continue

        try:
            _criar_anuncio_ml(
                cur,
                id_tenant,
                ml_user_id,
                site_id,
                id_variante=int(id_variante),
                id_produto=int(id_produto),
                sku=sku or "",
                titulo=titulo or "",
                preco=float(preco or 0),
                descricao=descricao or "",
                imagem=imagem or "",
                estoque=int(estoque or 0),
                condicao=condicao,
            )
            exportados += 1
        except RuntimeError as e:
            erros.append(str(e)[:200])

    total = len(linhas)
    if exportados > 0:
        msg = f"{exportados} anúncio(s) criado(s) no Mercado Livre."
        if ignorados:
            msg += f" {ignorados} já vinculado(s) ou existente(s) no ML."
        if erros:
            msg += f" {len(erros)} com erro."
        if total > _ML_MAX_CRIAR_POR_SYNC:
            msg += f" Limite de {_ML_MAX_CRIAR_POR_SYNC} por sincronização — execute novamente para continuar."
    elif erros:
        msg = f"Nenhum anúncio criado. {erros[0]}"
    else:
        msg = "Nenhum produto novo para publicar (todos já estão no ML ou na vitrine)."

    out = {
        "message": msg,
        "total_produtos": total,
        "modo": "criar_anuncio",
        "exportados": exportados,
        "vinculados": 0,
        "ignorados": ignorados,
        "erros": len(erros),
    }
    if erros:
        out["detalhes_erros"] = erros[:5]
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
    cur.execute(_sql_produtos_vitrine_ml(), (id_tenant,))
    linhas = cur.fetchall()

    if modo == "criar_anuncio":
        return _criar_anuncios_ml_lote(cur, id_tenant, cfg, linhas)

    ml_user_id = cfg.get("ml_user_id")
    if not ml_user_id:
        raise RuntimeError("Perfil Mercado Livre sem user_id. Reconecte a conta.")

    vinculados = 0
    nao_encontrados = 0
    sem_sku = 0
    for row in linhas:
        _pv_id, id_variante, id_produto, sku, *_rest = row
        sku = (sku or "").strip()
        if not sku:
            sem_sku += 1
            continue
        ml_item = _buscar_item_ml_por_sku(cur, id_tenant, int(ml_user_id), sku)
        if not ml_item:
            nao_encontrados += 1
            continue
        _salvar_map_produto_ml(cur, id_tenant, int(id_variante), int(id_produto), sku, ml_item)
        vinculados += 1

    total = len(linhas)
    if vinculados <= 0:
        msg = (
            f"Nenhum dos {total} produto(s) foi vinculado. "
            "Confira se o SKU no DropNexo é igual ao do anúncio no Mercado Livre."
        )
        if sem_sku:
            msg += f" {sem_sku} sem SKU."
    else:
        msg = f"{vinculados} de {total} produto(s) vinculado(s) ao Mercado Livre pelo SKU."
        if nao_encontrados > 0:
            msg += f" {nao_encontrados} sem anúncio correspondente no ML."
        if sem_sku:
            msg += f" {sem_sku} ignorado(s) sem SKU."

    return {
        "message": msg,
        "total_produtos": total,
        "modo": modo,
        "exportados": 0,
        "vinculados": vinculados,
        "nao_encontrados": nao_encontrados,
    }


def sincronizar_estoque_ml(cur, id_tenant: int) -> dict:
    """Fase 2: enviar estoque DropNexo → anúncios ML."""
    cfg = carregar_config_ml(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("Mercado Livre não conectado.")
    if not cfg.get("estoque_sync_ativo"):
        raise RuntimeError("Ative a sincronização de estoque antes de enviar.")
    return {
        "message": (
            "Sincronização de estoque com o Mercado Livre será habilitada na próxima etapa. "
            "As preferências já foram salvas."
        ),
        "atualizados": 0,
    }
