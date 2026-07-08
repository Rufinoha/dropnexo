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
from global_utils import agora_utc, is_modo_producao, obter_base_url

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
    ext = _tem_colunas_config_ext(cur)
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
    elif any(v is not None for v in (produtos_exportar_auto, produtos_modo, estoque_sync_ativo)):
        raise RuntimeError(
            "Preferências de produtos/estoque indisponíveis. Aplique o SQL 072 no banco."
        )
    if not updates:
        return
    cols = ["id_tenant", *updates.keys(), "atualizado_em"]
    placeholders = ", ".join(["%s"] * len(cols))
    set_clause = ", ".join(f"{c} = EXCLUDED.{c}" for c in updates) + ", atualizado_em = EXCLUDED.atualizado_em"
    vals = [id_tenant, *updates.values(), agora_utc()]
    cur.execute(
        f"""
        INSERT INTO tbl_integracao_mercado_livre ({", ".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT (id_tenant) DO UPDATE SET {set_clause}
        """,
        vals,
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


def exportar_produtos_ml(cur, id_tenant: int) -> dict:
    """Fase 2: publicar/vincular Meus produtos no ML. Por ora valida config e conta."""
    cfg = carregar_config_ml(cur, id_tenant)
    if not cfg.get("conectado"):
        raise RuntimeError("Mercado Livre não conectado.")
    if not cfg.get("produtos_exportar_auto"):
        raise RuntimeError("Ative a exportação de produtos antes de sincronizar.")
    cur.execute(
        """
        SELECT COUNT(*)::int
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto p ON p.id = pv.id_produto
        WHERE pv.id_tenant_vendedor = %s AND pv.ativo = TRUE AND COALESCE(p.sku, '') <> ''
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    com_sku = int(row[0] or 0) if row else 0
    modo = cfg.get("produtos_modo") or "vincular_sku"
    acao = "vincular anúncios pelo SKU" if modo == "vincular_sku" else "criar novos anúncios"
    return {
        "message": (
            f"{com_sku} produto(s) com SKU na vitrine prontos para {acao}. "
            "A publicação automática no Mercado Livre será habilitada na próxima etapa."
        ),
        "total_produtos": com_sku,
        "modo": modo,
        "exportados": 0,
        "vinculados": 0,
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
