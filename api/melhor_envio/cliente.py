# api/melhor_envio/cliente.py — OAuth e cliente HTTP Melhor Envio
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

import requests

from api.bling.tokens import criptografar_token, descriptografar_token
from global_utils import agora_utc, is_modo_producao, obter_base_url

_log = logging.getLogger(__name__)

ME_OAUTH_TIMEOUT = (5, 20)
ME_API_TIMEOUT = (10, 60)

ME_OAUTH_SCOPES = (
    "shipping-calculate cart-read cart-write shipping-checkout "
    "shipping-generate shipping-print shipping-tracking orders-read users-read"
)


def _env(key: str) -> str:
    return (os.getenv(key) or "").strip()


def _me_env(sufixo: str) -> str:
    if is_modo_producao():
        return _env(f"ME_{sufixo}_PROD") or _env(f"ME_{sufixo}_DEV")
    return _env(f"ME_{sufixo}_DEV") or _env(f"ME_{sufixo}_PROD")


def me_client_id() -> str:
    return (
        _me_env("CLIENT_ID")
        or _env("Client_Id")
        or _env("ME_CLIENT_ID")
    )


def me_client_secret() -> str:
    return (
        _me_env("CLIENT_SECRET")
        or _env("Secret_Key")
        or _env("ME_CLIENT_SECRET")
    )


def me_auth_base() -> str:
    return (
        _me_env("AUTH_BASE")
        or ("https://melhorenvio.com.br" if is_modo_producao() else "https://sandbox.melhorenvio.com.br")
    ).rstrip("/")


def me_api_base() -> str:
    custom = _me_env("API_BASE")
    if custom:
        return custom.rstrip("/")
    return f"{me_auth_base()}/api/v2"


def me_user_agent() -> str:
    return _env("ME_USER_AGENT") or "DropNexo (integracoes@dropnexo.com.br)"


def me_configurado() -> bool:
    return bool(me_client_id() and me_client_secret())


def credenciais_me() -> tuple[str, str]:
    client_id = me_client_id()
    client_secret = me_client_secret()
    if not client_id or not client_secret:
        raise RuntimeError(
            "Credenciais Melhor Envio incompletas. Configure ME_CLIENT_ID_PROD e "
            "ME_CLIENT_SECRET_PROD no .env."
        )
    return client_id, client_secret


def redirect_uri_oauth() -> str:
    return f"{obter_base_url().rstrip('/')}/api/integracoes/melhor-envio/oauth/callback"


def webhook_url() -> str:
    return f"{obter_base_url().rstrip('/')}/api/integracoes/melhor-envio/webhook"


def gerar_state_oauth() -> str:
    return secrets.token_urlsafe(24)


def url_autorizacao(state: str) -> str:
    client_id, _ = credenciais_me()
    redirect_uri = redirect_uri_oauth()
    params = urlencode(
        {
            "client_id": client_id,
            "response_type": "code",
            "redirect_uri": redirect_uri,
            "state": state,
        }
    )
    # ME documenta scopes separados por espaço; %20 evita '+' que alguns parsers rejeitam.
    scope_qs = f"scope={quote(ME_OAUTH_SCOPES, safe='')}"
    return f"{me_auth_base()}/oauth/authorize?{params}&{scope_qs}"


def diagnostico_oauth_me() -> dict[str, Any]:
    """Dados para conferir configuração (sem expor o secret)."""
    from global_utils import is_modo_producao, obter_base_url

    out: dict[str, Any] = {
        "modo_producao": is_modo_producao(),
        "base_url": obter_base_url(),
        "auth_base": me_auth_base(),
        "api_base": me_api_base(),
        "client_id": me_client_id(),
        "redirect_uri": redirect_uri_oauth(),
        "user_agent": me_user_agent(),
        "configurado": me_configurado(),
        "scopes": ME_OAUTH_SCOPES,
    }
    if me_configurado():
        out["teste_credenciais"] = testar_credenciais_me_oauth()
    return out


def testar_credenciais_me_oauth() -> dict[str, Any]:
    """
    POST /oauth/token com code inválido.
    invalid_grant → client_id + secret OK; invalid_client → credencial errada.
    """
    try:
        _post_token(
            {
                "grant_type": "authorization_code",
                "code": "dropnexo-teste-credencial-invalido",
                "redirect_uri": redirect_uri_oauth(),
            }
        )
        return {"ok": True, "mensagem": "Resposta inesperada, mas credenciais foram aceitas."}
    except RuntimeError as e:
        msg = str(e).lower()
        if "invalid_grant" in msg or "invalid_code" in msg or "code" in msg:
            return {"ok": True, "mensagem": "Client ID e Secret aceitos pelo Melhor Envio."}
        if "invalid_client" in msg or "client authentication failed" in msg:
            return {
                "ok": False,
                "mensagem": "Client ID ou Secret rejeitados. Confira o .env do servidor e o app no painel ME.",
            }
        return {"ok": None, "mensagem": str(e)[:240]}


def _post_token(body: dict[str, str]) -> dict[str, Any]:
    client_id, client_secret = credenciais_me()
    payload = {"client_id": client_id, "client_secret": client_secret, **body}
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": me_user_agent(),
    }
    try:
        r = requests.post(
            f"{me_auth_base()}/oauth/token",
            headers=headers,
            json=payload,
            timeout=ME_OAUTH_TIMEOUT,
        )
    except requests.Timeout as e:
        raise RuntimeError("Melhor Envio demorou para responder. Tente novamente.") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Falha de rede ao contactar Melhor Envio: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(f"Melhor Envio OAuth falhou ({r.status_code}): {r.text[:500]}")
    data = r.json()
    if not data.get("access_token"):
        raise RuntimeError("Melhor Envio não retornou access_token.")
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
    me_user = tokens.get("user_id") or tokens.get("id")
    expires = _expires_em(tokens.get("expires_in"))
    cur.execute(
        """
        INSERT INTO tbl_integracao_melhor_envio (
            id_tenant, status, access_token_enc, refresh_token_enc,
            token_expires_em, me_user_id, conectado_em, ultimo_erro, atualizado_em
        ) VALUES (%s, 'conectado', %s, %s, %s, %s, %s, NULL, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            status = 'conectado',
            access_token_enc = EXCLUDED.access_token_enc,
            refresh_token_enc = EXCLUDED.refresh_token_enc,
            token_expires_em = EXCLUDED.token_expires_em,
            me_user_id = EXCLUDED.me_user_id,
            conectado_em = COALESCE(tbl_integracao_melhor_envio.conectado_em, EXCLUDED.conectado_em),
            ultimo_erro = NULL,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            id_tenant,
            criptografar_token(access),
            criptografar_token(refresh),
            expires,
            int(me_user) if me_user else None,
            agora_utc(),
            agora_utc(),
        ),
    )


def carregar_tokens_armazenados(cur, id_tenant: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT status, access_token_enc, refresh_token_enc, token_expires_em, me_user_id
        FROM tbl_integracao_melhor_envio WHERE id_tenant = %s
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
        "me_user_id": row[4],
    }


def desconectar_me(cur, id_tenant: int) -> None:
    cur.execute(
        """
        UPDATE tbl_integracao_melhor_envio SET
            status = 'desconectado',
            access_token_enc = NULL,
            refresh_token_enc = NULL,
            token_expires_em = NULL,
            me_user_id = NULL,
            me_conta_info = '{}',
            ultimo_erro = NULL,
            atualizado_em = %s
        WHERE id_tenant = %s
        """,
        (agora_utc(), id_tenant),
    )
    if cur.rowcount == 0:
        cur.execute(
            """
            INSERT INTO tbl_integracao_melhor_envio (id_tenant, status, atualizado_em)
            VALUES (%s, 'desconectado', %s)
            ON CONFLICT (id_tenant) DO NOTHING
            """,
            (id_tenant, agora_utc()),
        )


def me_conectado(cur, id_tenant: int) -> bool:
    cur.execute(
        "SELECT status FROM tbl_integracao_melhor_envio WHERE id_tenant = %s",
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
        raise RuntimeError("Melhor Envio não conectado.")
    access = dados.get("access_token") or ""
    if access and not _token_expirado(dados.get("token_expires_em")):
        return access
    refresh = dados.get("refresh_token") or ""
    if not refresh:
        raise RuntimeError("Token Melhor Envio expirado. Reconecte a conta.")
    novos = renovar_access_token(refresh)
    salvar_tokens(cur, id_tenant, novos)
    return novos.get("access_token") or ""


def buscar_usuario_me(access_token: str) -> dict[str, Any]:
    try:
        r = requests.get(
            f"{me_api_base()}/me",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
                "User-Agent": me_user_agent(),
            },
            timeout=ME_OAUTH_TIMEOUT,
        )
        if r.status_code >= 400:
            return {}
        return r.json() or {}
    except Exception as e:
        _log.warning("ME /me falhou: %s", e)
        return {}


def atualizar_conta_info(cur, id_tenant: int, access_token: str) -> dict:
    info = buscar_usuario_me(access_token)
    if info:
        cur.execute(
            """
            UPDATE tbl_integracao_melhor_envio
            SET me_conta_info = %s::jsonb, atualizado_em = %s
            WHERE id_tenant = %s
            """,
            (json.dumps(info, ensure_ascii=False), agora_utc(), id_tenant),
        )
    return info


_COLUNAS_PREFS_ME_OK: bool | None = None


def _tem_colunas_preferencias_me(cur) -> bool:
    global _COLUNAS_PREFS_ME_OK
    if _COLUNAS_PREFS_ME_OK is not None:
        return _COLUNAS_PREFS_ME_OK
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'tbl_integracao_melhor_envio'
          AND column_name = 'opcao_recebimento'
        LIMIT 1
        """
    )
    _COLUNAS_PREFS_ME_OK = cur.fetchone() is not None
    return _COLUNAS_PREFS_ME_OK


def carregar_config_me(cur, id_tenant: int) -> dict:
    cols = "status, me_user_id, me_conta_info, conectado_em, ultimo_erro"
    if _tem_colunas_preferencias_me(cur):
        cols += ", opcao_recebimento, opcao_maos_proprias"
    cur.execute(
        f"""
        SELECT {cols}
        FROM tbl_integracao_melhor_envio WHERE id_tenant = %s
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        return {
            "status": "desconectado",
            "me_user_id": None,
            "conta": {},
            "opcao_recebimento": False,
            "opcao_maos_proprias": False,
        }
    raw_conta = row[2]
    if isinstance(raw_conta, dict):
        conta = raw_conta
    elif isinstance(raw_conta, str) and raw_conta.strip():
        try:
            conta = json.loads(raw_conta)
        except json.JSONDecodeError:
            conta = {}
    else:
        conta = {}
    out = {
        "status": row[0],
        "me_user_id": row[1],
        "conta": conta,
        "conectado_em": row[3].isoformat() if row[3] else None,
        "ultimo_erro": row[4],
        "opcao_recebimento": False,
        "opcao_maos_proprias": False,
    }
    if _tem_colunas_preferencias_me(cur) and len(row) > 5:
        out["opcao_recebimento"] = bool(row[5])
        out["opcao_maos_proprias"] = bool(row[6])
    return out


def salvar_preferencias_me(
    cur,
    id_tenant: int,
    *,
    opcao_recebimento: bool,
    opcao_maos_proprias: bool,
) -> None:
    if not _tem_colunas_preferencias_me(cur):
        raise RuntimeError(
            "Preferências indisponíveis. Execute a migração SQL 067_me_preferencias no banco."
        )
    cur.execute(
        """
        INSERT INTO tbl_integracao_melhor_envio (
            id_tenant, status, opcao_recebimento, opcao_maos_proprias, atualizado_em
        ) VALUES (%s, 'desconectado', %s, %s, %s)
        ON CONFLICT (id_tenant) DO UPDATE SET
            opcao_recebimento = EXCLUDED.opcao_recebimento,
            opcao_maos_proprias = EXCLUDED.opcao_maos_proprias,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, opcao_recebimento, opcao_maos_proprias, agora_utc()),
    )


def opcoes_cotacao_me(cur, id_tenant: int) -> dict[str, bool]:
    cfg = carregar_config_me(cur, id_tenant)
    return {
        "receipt": bool(cfg.get("opcao_recebimento")),
        "own_hand": bool(cfg.get("opcao_maos_proprias")),
    }


def _headers_me(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": me_user_agent(),
    }


def _me_request(
    access_token: str,
    method: str,
    path: str,
    *,
    json_body: dict | list | None = None,
    timeout: tuple[int, int] = ME_API_TIMEOUT,
) -> Any:
    url = f"{me_api_base()}/{path.lstrip('/')}"
    try:
        r = requests.request(
            method.upper(),
            url,
            headers=_headers_me(access_token),
            json=json_body,
            timeout=timeout,
        )
    except requests.Timeout as e:
        raise RuntimeError("Melhor Envio demorou para responder. Tente novamente.") from e
    except requests.RequestException as e:
        raise RuntimeError(f"Falha de rede ao contactar Melhor Envio: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(f"Melhor Envio falhou ({r.status_code}): {r.text[:500]}")
    if not r.content:
        return {}
    try:
        return r.json()
    except ValueError:
        return r.content


def calcular_frete(access_token: str, payload: dict[str, Any]) -> list[Any]:
    """POST /me/shipment/calculate — cotação por produtos."""
    data = _me_request(access_token, "POST", "/me/shipment/calculate", json_body=payload)
    if not isinstance(data, list):
        raise RuntimeError("Resposta inesperada do Melhor Envio na cotação.")
    return data


def adicionar_ao_carrinho(access_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    """POST /me/cart — insere etiqueta no carrinho."""
    data = _me_request(access_token, "POST", "/me/cart", json_body=payload)
    if not isinstance(data, dict):
        raise RuntimeError("Resposta inesperada ao adicionar frete ao carrinho.")
    return data


def checkout_etiquetas(access_token: str, order_ids: list[str]) -> dict[str, Any]:
    """POST /me/shipment/checkout — paga etiquetas com saldo ME."""
    ids = [str(x).strip() for x in order_ids if str(x).strip()]
    if not ids:
        raise ValueError("Nenhuma etiqueta para checkout.")
    data = _me_request(
        access_token,
        "POST",
        "/me/shipment/checkout",
        json_body={"orders": ids},
    )
    if not isinstance(data, dict):
        raise RuntimeError("Resposta inesperada no checkout Melhor Envio.")
    return data


def gerar_etiquetas(access_token: str, order_ids: list[str]) -> dict[str, Any]:
    """POST /me/shipment/generate — gera etiquetas pagas."""
    ids = [str(x).strip() for x in order_ids if str(x).strip()]
    if not ids:
        raise ValueError("Nenhuma etiqueta para gerar.")
    data = _me_request(
        access_token,
        "POST",
        "/me/shipment/generate",
        json_body={"orders": ids},
    )
    if not isinstance(data, dict):
        raise RuntimeError("Resposta inesperada na geração de etiquetas.")
    return data


def imprimir_etiquetas(
    access_token: str,
    order_ids: list[str],
    *,
    mode: str = "public",
) -> dict[str, Any]:
    """POST /me/shipment/print — retorna link de impressão."""
    ids = [str(x).strip() for x in order_ids if str(x).strip()]
    if not ids:
        raise ValueError("Nenhuma etiqueta para imprimir.")
    data = _me_request(
        access_token,
        "POST",
        "/me/shipment/print",
        json_body={"orders": ids, "mode": mode},
    )
    if not isinstance(data, dict):
        raise RuntimeError("Resposta inesperada na impressão de etiquetas.")
    return data


def baixar_url_me(access_token: str, url: str) -> bytes:
    """Baixa PDF da etiqueta (link retornado pelo /shipment/print)."""
    if not url:
        raise ValueError("URL de impressão vazia.")
    try:
        r = requests.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "User-Agent": me_user_agent(),
                "Accept": "application/pdf,*/*",
            },
            timeout=ME_API_TIMEOUT,
        )
    except requests.RequestException as e:
        raise RuntimeError(f"Falha ao baixar PDF da etiqueta: {e}") from e
    if r.status_code >= 400:
        raise RuntimeError(f"Download da etiqueta falhou ({r.status_code}).")
    return r.content


def obter_pedido_me(access_token: str, order_id: str) -> dict[str, Any]:
    """GET /me/orders/{id} — detalhes da etiqueta."""
    data = _me_request(access_token, "GET", f"/me/orders/{order_id}")
    if not isinstance(data, dict):
        return {}
    return data


def verificar_assinatura_webhook(corpo: bytes, assinatura: str) -> bool:
    """Valida X-ME-Signature (HMAC-SHA256 + base64)."""
    if not assinatura or not corpo:
        return False
    _, client_secret = credenciais_me()
    digest = hmac.new(client_secret.encode(), corpo, hashlib.sha256).digest()
    esperado = base64.b64encode(digest).decode()
    return hmac.compare_digest(esperado, assinatura.strip())
