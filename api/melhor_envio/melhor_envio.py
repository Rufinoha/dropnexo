# api/melhor_envio/melhor_envio.py — cliente OAuth Melhor Envio e frete nos pedidos
from __future__ import annotations

# ── cliente ───────────────────────────────────────────

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

from core.tokens import criptografar_token, descriptografar_token
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


def _probe_me_client_ambiente(auth_base: str) -> dict[str, Any]:
    """Verifica se o client_id atual é reconhecido nesse host ME (sem expor secret)."""
    client_id, client_secret = credenciais_me()
    redirect_uri = redirect_uri_oauth()
    auth_url = (
        f"{auth_base.rstrip('/')}/oauth/authorize?"
        f"client_id={quote(client_id)}&response_type=code"
        f"&redirect_uri={quote(redirect_uri, safe='')}&state=dropnexo-probe&scope=cart-read"
    )
    auth_ok = False
    auth_status = 0
    try:
        r_auth = requests.get(auth_url, allow_redirects=False, timeout=ME_OAUTH_TIMEOUT)
        auth_status = r_auth.status_code
        auth_ok = r_auth.status_code in (302, 303) or (
            r_auth.status_code == 200 and "login" in (r_auth.text or "").lower()
        )
    except requests.RequestException:
        pass

    token_ok = False
    token_status = 0
    token_erro = ""
    try:
        r_tok = requests.post(
            f"{auth_base.rstrip('/')}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": "dropnexo-probe-credencial",
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "client_secret": client_secret,
            },
            headers={"Accept": "application/json", "User-Agent": me_user_agent()},
            timeout=ME_OAUTH_TIMEOUT,
        )
        token_status = r_tok.status_code
        body = (r_tok.text or "").lower()
        token_erro = (r_tok.json().get("error") if r_tok.content else "") or ""
        token_ok = "invalid_client" not in body and "client authentication failed" not in body
    except (requests.RequestException, ValueError):
        pass

    reconhecido = auth_ok or token_ok
    return {
        "auth_base": auth_base,
        "client_id_reconhecido": reconhecido,
        "auth_status": auth_status,
        "token_status": token_status,
        "token_erro": token_erro,
    }


def detectar_ambiente_me_credenciais() -> dict[str, Any]:
    """Descobre se o par client_id/secret pertence a produção ou sandbox."""
    prod = _probe_me_client_ambiente("https://melhorenvio.com.br")
    sand = _probe_me_client_ambiente("https://sandbox.melhorenvio.com.br")
    ambiente_credencial = "desconhecido"
    if prod["client_id_reconhecido"] and not sand["client_id_reconhecido"]:
        ambiente_credencial = "producao"
    elif sand["client_id_reconhecido"] and not prod["client_id_reconhecido"]:
        ambiente_credencial = "sandbox"
    elif prod["client_id_reconhecido"] and sand["client_id_reconhecido"]:
        ambiente_credencial = "ambos"
    ambiente_ativo = "producao" if is_modo_producao() else "sandbox"
    mismatch = (
        ambiente_credencial in ("sandbox", "producao")
        and ambiente_credencial != ambiente_ativo
    )
    dica = ""
    if mismatch and ambiente_credencial == "sandbox":
        dica = (
            "Este Client ID foi criado no SANDBOX (sandbox.melhorenvio.com.br), mas o servidor "
            "está em modo produção. Crie um app novo em https://melhorenvio.com.br e use "
            "ME_CLIENT_ID_PROD / ME_CLIENT_SECRET_PROD, ou use as credenciais sandbox em DEV."
        )
    elif mismatch and ambiente_credencial == "producao":
        dica = (
            "Este Client ID é de PRODUÇÃO, mas o servidor está em modo desenvolvimento. "
            "Use ME_CLIENT_ID_DEV / ME_CLIENT_SECRET_DEV do sandbox para testes locais."
        )
    return {
        "ambiente_credencial": ambiente_credencial,
        "ambiente_servidor": ambiente_ativo,
        "incompativel": mismatch,
        "dica": dica,
        "producao": prod,
        "sandbox": sand,
    }


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
        out["ambiente_credenciais"] = detectar_ambiente_me_credenciais()
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
        if "invalid_grant" in msg:
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
        "User-Agent": me_user_agent(),
    }
    try:
        r = requests.post(
            f"{me_auth_base()}/oauth/token",
            headers=headers,
            data=payload,
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


# ── pedido ────────────────────────────────────────────

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from global_utils import agora_utc
from core.pedidos.servico import STATUS_RASCUNHO, _frete_editavel_status, obter_pedido, registrar_anexo_pedido, registrar_historico, status_vendedor_pedido

_log = logging.getLogger(__name__)
_RAIZ_UPLOAD = Path(__file__).resolve().parents[2]

_COLUNAS_ME_OK: bool | None = None


def _float(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _cep_digitos(cep: str | None) -> str:
    return re.sub(r"\D", "", cep or "")


def _pedido_tem_colunas_me(cur) -> bool:
    global _COLUNAS_ME_OK
    if _COLUNAS_ME_OK is not None:
        return _COLUNAS_ME_OK
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'tbl_pedido'
          AND column_name = 'me_service_id'
        LIMIT 1
        """
    )
    _COLUNAS_ME_OK = cur.fetchone() is not None
    return _COLUNAS_ME_OK


def _dimensoes_efetivas(variante: dict, produto: dict) -> dict[str, float]:
    out = {
        "peso_bruto_kg": variante.get("peso_bruto_kg"),
        "altura_cm": variante.get("altura_cm"),
        "largura_cm": variante.get("largura_cm"),
        "profundidade_cm": variante.get("profundidade_cm"),
    }
    if variante.get("herda_pai", True):
        for k in out:
            if out[k] in (None, "", 0) and produto.get(k) not in (None, "", 0):
                out[k] = produto.get(k)
    return {k: _float(v) for k, v in out.items()}


def _cep_origem_pedido(cur, id_pedido: int, id_fornecedor: int) -> str:
    cur.execute(
        """
        SELECT DISTINCT d.cep
        FROM tbl_pedido_item pi
        JOIN tbl_deposito_expedicao d ON d.id = pi.id_deposito_fornecedor
        WHERE pi.id_pedido = %s AND d.ativo = TRUE AND d.cep IS NOT NULL
        """,
        (id_pedido,),
    )
    ceps = {_cep_digitos(r[0]) for r in cur.fetchall() if _cep_digitos(r[0])}
    if len(ceps) > 1:
        raise ValueError("Itens do pedido usam depósitos com CEPs diferentes. Unifique a origem.")
    if len(ceps) == 1:
        return next(iter(ceps))

    cur.execute(
        """
        SELECT cep FROM tbl_deposito_expedicao
        WHERE id_tenant = %s AND ativo = TRUE AND principal = TRUE
        ORDER BY id LIMIT 1
        """,
        (id_fornecedor,),
    )
    row = cur.fetchone()
    cep = _cep_digitos(row[0]) if row else ""
    if cep:
        return cep

    cur.execute(
        """
        SELECT cep FROM tbl_deposito_expedicao
        WHERE id_tenant = %s AND ativo = TRUE
        ORDER BY principal DESC, id LIMIT 1
        """,
        (id_fornecedor,),
    )
    row = cur.fetchone()
    cep = _cep_digitos(row[0]) if row else ""
    if not cep:
        raise ValueError("Fornecedor sem depósito de expedição com CEP cadastrado.")
    return cep


def _produtos_me_pedido(cur, id_pedido: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT pi.sku, pi.nome_produto, pi.quantidade, pi.preco_venda, pi.valor_drop,
               v.herda_pai, v.peso_bruto_kg, v.altura_cm, v.largura_cm, v.profundidade_cm,
               p.peso_bruto_kg, p.altura_cm, p.largura_cm, p.profundidade_cm
        FROM tbl_pedido_item pi
        JOIN tbl_produto_variante v ON v.id = pi.id_variante
        JOIN tbl_produto p ON p.id = pi.id_produto
        WHERE pi.id_pedido = %s
        ORDER BY pi.id
        """,
        (id_pedido,),
    )
    produtos: list[dict[str, Any]] = []
    faltando: list[str] = []
    for row in cur.fetchall():
        variante = {
            "herda_pai": bool(row[5]),
            "peso_bruto_kg": row[6],
            "altura_cm": row[7],
            "largura_cm": row[8],
            "profundidade_cm": row[9],
        }
        produto = {
            "peso_bruto_kg": row[10],
            "altura_cm": row[11],
            "largura_cm": row[12],
            "profundidade_cm": row[13],
        }
        dims = _dimensoes_efetivas(variante, produto)
        sku = (row[0] or "").strip() or "item"
        nome = (row[1] or sku).strip()
        qtd = int(row[2] or 0)
        seguro = _float(row[3]) or _float(row[4])
        peso = dims["peso_bruto_kg"]
        alt = dims["altura_cm"]
        larg = dims["largura_cm"]
        comp = dims["profundidade_cm"]
        if qtd <= 0 or peso <= 0 or alt <= 0 or larg <= 0 or comp <= 0:
            faltando.append(sku)
            continue
        produtos.append(
            {
                "id": sku,
                "width": max(1, int(round(larg))),
                "height": max(1, int(round(alt))),
                "length": max(1, int(round(comp))),
                "weight": round(peso, 3),
                "insurance_value": round(max(seguro, 0.01), 2),
                "quantity": qtd,
                "nome": nome,
            }
        )
    if faltando:
        lista = ", ".join(faltando[:5])
        sufixo = "…" if len(faltando) > 5 else ""
        raise ValueError(
            f"Peso e dimensões obrigatórios para cotar frete. Revise: {lista}{sufixo}"
        )
    if not produtos:
        raise ValueError("Pedido sem itens para cotação de frete.")
    return produtos


def _extrair_erros_me(resposta: list[Any]) -> list[str]:
    erros: list[str] = []
    for item in resposta:
        if not isinstance(item, dict):
            continue
        err = item.get("error")
        if err:
            if isinstance(err, dict):
                txt = err.get("message") or err.get("description") or str(err)
            else:
                txt = str(err)
            nome = item.get("name") or item.get("company", {}).get("name") if isinstance(item.get("company"), dict) else ""
            erros.append(f"{nome}: {txt}".strip(": ") if nome else txt)
        elif not item.get("id") and item.get("message"):
            erros.append(str(item["message"]))
    return list(dict.fromkeys(erros))[:6]


def _normalizar_opcoes_me(resposta: list[Any]) -> list[dict[str, Any]]:
    opcoes: list[dict[str, Any]] = []
    for item in resposta:
        if not isinstance(item, dict) or item.get("error"):
            continue
        sid = item.get("id")
        preco = item.get("custom_price") or item.get("price")
        if sid is None or preco in (None, ""):
            continue
        prazo = item.get("custom_delivery_time")
        if prazo is None:
            prazo = item.get("delivery_time")
        empresa = item.get("company") if isinstance(item.get("company"), dict) else {}
        opcoes.append(
            {
                "id": int(sid),
                "nome": item.get("name") or "",
                "preco": round(_float(preco), 2),
                "prazo_dias": int(prazo) if prazo is not None else None,
                "transportadora": empresa.get("name") or "",
                "logo": empresa.get("picture") or "",
                "raw": item,
            }
        )
    opcoes.sort(key=lambda o: o["preco"])
    return opcoes


def _cotar_me_com_fallback_receipt(
    token: str,
    payload: dict[str, Any],
    *,
    receipt_ativo: bool,
) -> tuple[list[dict[str, Any]], list[Any], str | None]:
    """Cota no ME; se receipt ligado bloquear tudo, tenta sem aviso de recebimento."""
    resposta = calcular_frete(token, payload)
    opcoes = _normalizar_opcoes_me(resposta)
    if opcoes or not receipt_ativo:
        return opcoes, resposta, None

    opts = dict(payload.get("options") or {})
    if not opts.get("receipt"):
        return opcoes, resposta, None

    payload_sem_receipt = {**payload, "options": {**opts, "receipt": False}}
    resposta2 = calcular_frete(token, payload_sem_receipt)
    opcoes2 = _normalizar_opcoes_me(resposta2)
    if opcoes2:
        return (
            opcoes2,
            resposta2,
            "Nenhuma transportadora ofereceu aviso de recebimento nesta rota; exibindo cotações sem esse serviço.",
        )
    return opcoes, resposta2 or resposta, None


def _mensagem_sem_opcoes_me(resposta: list[Any], *, receipt_ativo: bool) -> str:
    erros = _extrair_erros_me(resposta)
    msg = "Nenhuma transportadora retornou preço para este pedido."
    if erros:
        msg += " " + " · ".join(erros)
    else:
        msg += (
            " Confira no painel Melhor Envio se há transportadoras habilitadas para a rota "
            "(Integrações → Transportadoras) e se peso/dimensões dos produtos estão em kg e cm."
        )
    if receipt_ativo:
        msg += " O aviso de recebimento estava ligado nas preferências; tente desativá-lo em Integrações → Melhor Envio."
    return msg


def status_melhor_envio_vendedor(cur, id_vendedor: int) -> dict:
    return {
        "conectado": me_conectado(cur, id_vendedor),
        "colunas_ok": _pedido_tem_colunas_me(cur),
    }


def cotar_frete_pedido(cur, id_vendedor: int, id_pedido: int) -> dict:
    if not _pedido_tem_colunas_me(cur):
        raise ValueError("Execute a migração SQL 066_pedido_melhor_envio no banco.")
    if not me_conectado(cur, id_vendedor):
        raise ValueError("Conecte sua conta Melhor Envio em Integrações → Frete.")

    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if not _frete_editavel_status(status_vendedor_pedido(ped)):
        raise ValueError("Só é possível cotar frete em pedidos em rascunho, importados ou aguardando pagamento.")

    cep_dest = _cep_digitos(ped.get("entrega_cep"))
    if len(cep_dest) != 8:
        raise ValueError("Informe o CEP de entrega no passo Endereço.")

    id_forn = int(ped["id_tenant_fornecedor"])
    cep_orig = _cep_origem_pedido(cur, id_pedido, id_forn)
    produtos = _produtos_me_pedido(cur, id_pedido)
    me_opts = opcoes_cotacao_me(cur, id_vendedor)
    payload = {
        "from": {"postal_code": cep_orig},
        "to": {"postal_code": cep_dest},
        "products": [
            {
                "id": p["id"],
                "width": p["width"],
                "height": p["height"],
                "length": p["length"],
                "weight": p["weight"],
                "insurance_value": p["insurance_value"],
                "quantity": p["quantity"],
            }
            for p in produtos
        ],
        "options": {"receipt": me_opts["receipt"], "own_hand": me_opts["own_hand"]},
    }

    token = obter_access_token_valido(cur, id_vendedor)
    receipt_ativo = bool(me_opts["receipt"])
    opcoes, resposta, aviso = _cotar_me_com_fallback_receipt(
        token, payload, receipt_ativo=receipt_ativo
    )
    if not opcoes:
        raise ValueError(_mensagem_sem_opcoes_me(resposta, receipt_ativo=receipt_ativo))

    out = {
        "id_pedido": id_pedido,
        "cep_origem": cep_orig,
        "cep_destino": cep_dest,
        "opcoes": opcoes,
    }
    if aviso:
        out["aviso"] = aviso
    return out


def escolher_frete_pedido(
    cur,
    id_vendedor: int,
    id_pedido: int,
    service_id: int,
    *,
    opcao_raw: dict | None = None,
) -> dict:
    if not _pedido_tem_colunas_me(cur):
        raise ValueError("Execute a migração SQL 066_pedido_melhor_envio no banco.")

    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if not _frete_editavel_status(status_vendedor_pedido(ped)):
        raise ValueError("Só é possível escolher frete em pedidos em rascunho, importados ou aguardando pagamento.")

    if opcao_raw:
        opcao = opcao_raw
    else:
        cot = cotar_frete_pedido(cur, id_vendedor, id_pedido)
        opcao = next((o["raw"] for o in cot["opcoes"] if int(o["id"]) == int(service_id)), None)
        if not opcao:
            raise ValueError("Opção de frete não encontrada. Cote novamente.")

    preco = round(_float(opcao.get("custom_price") or opcao.get("price")), 2)
    prazo = opcao.get("custom_delivery_time")
    if prazo is None:
        prazo = opcao.get("delivery_time")

    cur.execute(
        """
        UPDATE tbl_pedido SET
            valor_frete = %s,
            me_service_id = %s,
            me_preco_cotado = %s,
            me_prazo_dias = %s,
            me_cotacao_json = %s::jsonb,
            me_etiqueta_status = 'pendente',
            atualizado_em = %s
        WHERE id = %s AND id_tenant_vendedor = %s
        """,
        (
            preco,
            int(service_id),
            preco,
            int(prazo) if prazo is not None else None,
            json.dumps(opcao, ensure_ascii=False),
            agora_utc(),
            id_pedido,
            id_vendedor,
        ),
    )
    return {
        "id_pedido": id_pedido,
        "valor_frete": preco,
        "me_service_id": int(service_id),
        "me_prazo_dias": int(prazo) if prazo is not None else None,
        "nome": opcao.get("name") or "",
    }


def limpar_frete_pedido(cur, id_pedido: int) -> None:
    if not _pedido_tem_colunas_me(cur):
        return
    cur.execute(
        """
        UPDATE tbl_pedido SET
            valor_frete = 0,
            me_service_id = NULL,
            me_preco_cotado = NULL,
            me_prazo_dias = NULL,
            me_cotacao_json = NULL,
            me_etiqueta_status = NULL,
            atualizado_em = %s
        WHERE id = %s
        """,
        (agora_utc(), id_pedido),
    )


def definir_modo_frete_manual(
    cur,
    id_vendedor: int,
    id_pedido: int,
    *,
    valor_frete: float | None = None,
    codigo_rastreio: str | None = None,
    transportadora: str | None = None,
) -> dict:
    """Etiqueta própria (PDF) — não usa integração Melhor Envio."""
    if not _pedido_tem_colunas_me(cur):
        raise ValueError("Execute a migração SQL 066_pedido_melhor_envio no banco.")
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if not _frete_editavel_status(status_vendedor_pedido(ped)):
        raise ValueError("Só é possível alterar o frete em pedidos em rascunho, importados ou aguardando pagamento.")

    vf = round(_float(valor_frete), 2) if valor_frete is not None else _float(ped.get("valor_frete"))
    rastreio = (codigo_rastreio or "").strip() or None
    transp = (transportadora or "").strip() or None

    cur.execute(
        """
        UPDATE tbl_pedido SET
            valor_frete = %s,
            me_service_id = NULL,
            me_preco_cotado = NULL,
            me_prazo_dias = NULL,
            me_cotacao_json = NULL,
            me_order_id = NULL,
            me_protocol = NULL,
            me_etiqueta_status = 'manual',
            codigo_rastreio = COALESCE(%s, codigo_rastreio),
            transportadora = COALESCE(%s, transportadora),
            atualizado_em = %s
        WHERE id = %s AND id_tenant_vendedor = %s
        """,
        (vf, rastreio, transp, agora_utc(), id_pedido, id_vendedor),
    )
    return {
        "id_pedido": id_pedido,
        "frete_modo": "manual",
        "valor_frete": vf,
        "codigo_rastreio": rastreio or "",
        "transportadora": transp or "",
    }


def definir_modo_frete_melhor_envio(cur, id_vendedor: int, id_pedido: int) -> dict:
    """Volta ao fluxo Melhor Envio (cotação integrada)."""
    if not _pedido_tem_colunas_me(cur):
        raise ValueError("Execute a migração SQL 066_pedido_melhor_envio no banco.")
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if not _frete_editavel_status(status_vendedor_pedido(ped)):
        raise ValueError("Só é possível alterar o frete em pedidos em rascunho, importados ou aguardando pagamento.")

    cur.execute(
        """
        UPDATE tbl_pedido SET
            valor_frete = 0,
            me_service_id = NULL,
            me_preco_cotado = NULL,
            me_prazo_dias = NULL,
            me_cotacao_json = NULL,
            me_order_id = NULL,
            me_protocol = NULL,
            me_etiqueta_status = NULL,
            atualizado_em = %s
        WHERE id = %s AND id_tenant_vendedor = %s
        """,
        (agora_utc(), id_pedido, id_vendedor),
    )
    return {"id_pedido": id_pedido, "frete_modo": "melhor_envio"}


def salvar_frete_manual(
    cur,
    id_vendedor: int,
    id_pedido: int,
    *,
    valor_frete: float | None = None,
    codigo_rastreio: str | None = None,
    transportadora: str | None = None,
) -> dict:
    """Atualiza campos opcionais do frete manual (referência / rastreio)."""
    return definir_modo_frete_manual(
        cur,
        id_vendedor,
        id_pedido,
        valor_frete=valor_frete,
        codigo_rastreio=codigo_rastreio,
        transportadora=transportadora,
    )


def frete_resumo_pedido(cur, id_pedido: int) -> dict:
    if not _pedido_tem_colunas_me(cur):
        return {}
    cur.execute(
        """
        SELECT valor_frete, me_service_id, me_preco_cotado, me_prazo_dias, me_cotacao_json,
               me_etiqueta_status, me_order_id, me_protocol, codigo_rastreio, transportadora
        FROM tbl_pedido WHERE id = %s
        """,
        (id_pedido,),
    )
    row = cur.fetchone()
    if not row:
        return {}
    cotacao = row[4]
    if isinstance(cotacao, str) and cotacao.strip():
        try:
            cotacao = json.loads(cotacao)
        except json.JSONDecodeError:
            cotacao = {}
    elif not isinstance(cotacao, dict):
        cotacao = {}
    return {
        "valor_frete": _float(row[0]),
        "me_service_id": row[1],
        "me_preco_cotado": _float(row[2]) if row[2] is not None else None,
        "me_prazo_dias": row[3],
        "me_etiqueta_status": row[5] or "",
        "me_order_id": row[6] or "",
        "me_protocol": row[7] or "",
        "codigo_rastreio": row[8] or "",
        "transportadora": row[9] or "",
        "frete_nome": (cotacao.get("name") if cotacao else "") or "",
        "frete_transportadora": (
            cotacao.get("company", {}).get("name") if isinstance(cotacao.get("company"), dict) else ""
        ),
        "frete_modo": "manual" if (row[5] or "") == "manual" else ("melhor_envio" if row[1] else ""),
    }


def _so_digitos(val: str | None) -> str:
    return re.sub(r"\D", "", val or "")


def _telefone_me(val: str | None) -> str:
    d = _so_digitos(val)
    return d[:11] if d else "11999999999"


def _doc_pf_pj(documento: str | None) -> tuple[str, str]:
    d = _so_digitos(documento)
    if len(d) == 14:
        return "", d
    if len(d) == 11:
        return d, ""
    return d, ""


def _deposito_origem_pedido(cur, id_pedido: int, id_fornecedor: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT d.id, d.cep, d.logradouro, d.numero, d.complemento, d.bairro, d.cidade, d.uf,
               d.remetente_nome, d.remetente_documento,
               t.documento, t.razao_social, t.nome_fantasia, t.nome,
               t.email_comercial, t.telefone_comercial, t.celular_comercial,
               t.inscricao_estadual, t.ie_isento
        FROM tbl_pedido_item pi
        JOIN tbl_deposito_expedicao d ON d.id = pi.id_deposito_fornecedor
        JOIN tbl_tenant t ON t.id = d.id_tenant
        WHERE pi.id_pedido = %s AND d.ativo = TRUE
        LIMIT 1
        """,
        (id_pedido,),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            """
            SELECT d.id, d.cep, d.logradouro, d.numero, d.complemento, d.bairro, d.cidade, d.uf,
                   d.remetente_nome, d.remetente_documento,
                   t.documento, t.razao_social, t.nome_fantasia, t.nome,
                   t.email_comercial, t.telefone_comercial, t.celular_comercial,
                   t.inscricao_estadual, t.ie_isento
            FROM tbl_deposito_expedicao d
            JOIN tbl_tenant t ON t.id = d.id_tenant
            WHERE d.id_tenant = %s AND d.ativo = TRUE
            ORDER BY d.principal DESC, d.id
            LIMIT 1
            """,
            (id_fornecedor,),
        )
        row = cur.fetchone()
    if not row:
        raise ValueError("Depósito de expedição do fornecedor não encontrado.")
    doc_pf, doc_pj = _doc_pf_pj(row[9] or row[10])
    ie = (row[17] or "").strip()
    if row[18]:
        ie = "ISENTO"
    nome = (row[8] or row[12] or row[13] or row[11] or "Remetente").strip()
    return {
        "name": nome[:255],
        "email": (row[14] or "contato@dropnexo.com.br").strip(),
        "phone": _telefone_me(row[15] or row[16]),
        "document": doc_pf,
        "company_document": doc_pj,
        "state_register": ie or "ISENTO",
        "address": (row[2] or "").strip(),
        "complement": (row[4] or "").strip(),
        "number": (row[3] or "S/N").strip()[:20],
        "district": (row[5] or "").strip(),
        "city": (row[6] or "").strip(),
        "postal_code": _cep_digitos(row[1]),
        "state_abbr": (row[7] or "").strip()[:2].upper(),
        "country_id": "BR",
    }


def _destinatario_pedido(ped: dict) -> dict[str, Any]:
    doc_pf, doc_pj = _doc_pf_pj(ped.get("cliente_documento"))
    if not doc_pf and not doc_pj:
        doc_pf = "00000000000"
    return {
        "name": (ped.get("cliente_nome") or "Destinatário").strip()[:255],
        "email": (ped.get("cliente_email") or "cliente@email.com").strip(),
        "phone": _telefone_me(ped.get("cliente_telefone")),
        "document": doc_pf,
        "company_document": doc_pj,
        "state_register": "ISENTO",
        "address": (ped.get("entrega_logradouro") or "").strip(),
        "complement": (ped.get("entrega_complemento") or "").strip(),
        "number": (ped.get("entrega_numero") or "S/N").strip()[:20],
        "district": (ped.get("entrega_bairro") or "").strip(),
        "city": (ped.get("entrega_cidade") or "").strip(),
        "postal_code": _cep_digitos(ped.get("entrega_cep")),
        "state_abbr": (ped.get("entrega_uf") or "").strip()[:2].upper(),
        "country_id": "BR",
    }


def _montar_payload_carrinho(
    cur,
    id_pedido: int,
    ped: dict,
    *,
    service_id: int,
) -> dict[str, Any]:
    id_forn = int(ped["id_tenant_fornecedor"])
    produtos = _produtos_me_pedido(cur, id_pedido)
    me_opts = opcoes_cotacao_me(cur, int(ped["id_tenant_vendedor"]))
    insurance = round(sum(_float(p.get("insurance_value", 0)) * int(p.get("quantity", 1)) for p in produtos), 2)
    volumes = [
        {
            "height": p["height"],
            "width": p["width"],
            "length": p["length"],
            "weight": round(_float(p["weight"]) * int(p["quantity"]), 3),
        }
        for p in produtos
    ]
    if len(volumes) > 1:
        volumes = [
            {
                "height": max(v["height"] for v in volumes),
                "width": max(v["width"] for v in volumes),
                "length": max(v["length"] for v in volumes),
                "weight": round(sum(v["weight"] for v in volumes), 3),
            }
        ]
    decl_produtos = [
        {
            "name": (p.get("nome") or p.get("id") or "Produto")[:255],
            "quantity": str(int(p["quantity"])),
            "unitary_value": str(round(_float(p.get("insurance_value", 0.01)), 2)),
        }
        for p in produtos
    ]
    return {
        "service": int(service_id),
        "from": _deposito_origem_pedido(cur, id_pedido, id_forn),
        "to": _destinatario_pedido(ped),
        "products": decl_produtos,
        "volumes": volumes,
        "options": {
            "platform": "DropNexo",
            "reminder": f"Pedido {ped.get('numero') or id_pedido}",
            "insurance_value": max(insurance, 0.01),
            "receipt": me_opts["receipt"],
            "own_hand": me_opts["own_hand"],
            "reverse": False,
            "non_commercial": True,
            "tags": [{"tag": f"dropnexo-pedido-{id_pedido}", "url": ""}],
        },
    }


def _atualizar_status_etiqueta(
    cur,
    id_pedido: int,
    *,
    status: str,
    me_order_id: str | None = None,
    me_protocol: str | None = None,
    codigo_rastreio: str | None = None,
    transportadora: str | None = None,
) -> None:
    cur.execute(
        """
        UPDATE tbl_pedido SET
            me_etiqueta_status = %s,
            me_order_id = COALESCE(NULLIF(%s, ''), me_order_id),
            me_protocol = COALESCE(NULLIF(%s, ''), me_protocol),
            codigo_rastreio = COALESCE(NULLIF(%s, ''), codigo_rastreio),
            transportadora = COALESCE(NULLIF(%s, ''), transportadora),
            atualizado_em = %s
        WHERE id = %s
        """,
        (
            status,
            me_order_id or "",
            me_protocol or "",
            codigo_rastreio or "",
            transportadora or "",
            agora_utc(),
            id_pedido,
        ),
    )


def _salvar_pdf_etiqueta_anexo(
    cur,
    id_vendedor: int,
    id_pedido: int,
    pdf_bytes: bytes,
    *,
    id_usuario: int | None = None,
) -> dict | None:
    if not pdf_bytes or len(pdf_bytes) < 100:
        return None
    pasta = _RAIZ_UPLOAD / "upload" / f"tenant{id_vendedor}" / "pedidos"
    pasta.mkdir(parents=True, exist_ok=True)
    nome_arquivo = f"{id_pedido}_etiqueta_me_{int(time.time())}.pdf"
    destino = pasta / nome_arquivo
    destino.write_bytes(pdf_bytes)
    caminho_db = f"upload/tenant{id_vendedor}/pedidos/{nome_arquivo}"
    try:
        return registrar_anexo_pedido(
            cur,
            id_vendedor,
            id_pedido,
            "etiqueta",
            f"etiqueta_melhor_envio_{id_pedido}.pdf",
            caminho_db,
            len(pdf_bytes),
            id_usuario=id_usuario,
        )
    except ValueError as e:
        _log.warning("Anexo etiqueta ME pedido %s: %s", id_pedido, e)
        return None


def _extrair_url_impressao(resposta_print: dict) -> str:
    if not resposta_print:
        return ""
    if isinstance(resposta_print.get("url"), str):
        return resposta_print["url"].strip()
    link = resposta_print.get("link")
    if isinstance(link, str):
        return link.strip()
    for val in resposta_print.values():
        if isinstance(val, dict) and isinstance(val.get("url"), str):
            return val["url"].strip()
    return ""


def contratar_etiqueta_pedido(
    cur,
    id_vendedor: int,
    id_pedido: int,
    *,
    id_usuario: int | None = None,
    forcar: bool = False,
) -> dict[str, Any]:
    """Compra, gera e anexa etiqueta ME após pagamento do pedido."""
    if not _pedido_tem_colunas_me(cur):
        raise ValueError("Execute a migração SQL 066_pedido_melhor_envio no banco.")
    if not me_conectado(cur, id_vendedor):
        raise ValueError("Conecte sua conta Melhor Envio em Integrações → Frete.")

    cur.execute(
        """
        SELECT me_service_id, me_etiqueta_status, me_order_id, numero
        FROM tbl_pedido
        WHERE id = %s AND id_tenant_vendedor = %s
        """,
        (id_pedido, id_vendedor),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Pedido não encontrado.")
    service_id, etiq_status, me_order_existente, numero = row
    if not service_id:
        return {"ignorado": True, "message": "Pedido sem frete Melhor Envio selecionado."}
    if etiq_status == "gerada" and me_order_existente and not forcar:
        return {"ignorado": True, "message": "Etiqueta já gerada.", "me_order_id": me_order_existente}
    if etiq_status not in ("pendente", "erro", None, "") and not forcar:
        return {"ignorado": True, "message": f"Status de etiqueta: {etiq_status}."}

    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")

    token = obter_access_token_valido(cur, id_vendedor)
    order_id = str(me_order_existente or "").strip()

    try:
        if not order_id:
            payload = _montar_payload_carrinho(cur, id_pedido, ped, service_id=int(service_id))
            cart = adicionar_ao_carrinho(token, payload)
            order_id = str(cart.get("id") or "").strip()
            protocolo = str(cart.get("protocol") or "").strip()
            if not order_id:
                raise RuntimeError("Melhor Envio não retornou ID da etiqueta.")
            _atualizar_status_etiqueta(
                cur, id_pedido, status="pendente", me_order_id=order_id, me_protocol=protocolo
            )

        try:
            checkout_etiquetas(token, [order_id])
        except RuntimeError as e:
            msg_l = str(e).lower()
            if "pago" not in msg_l and "paid" not in msg_l and "checkout" not in msg_l:
                raise

        gerar_etiquetas(token, [order_id])
        detalhe = obter_pedido_me(token, order_id)
        tracking = (
            (detalhe.get("tracking") or detalhe.get("self_tracking") or "").strip()
            if detalhe
            else ""
        )
        protocolo = (detalhe.get("protocol") or "").strip() if detalhe else ""
        transportadora = ""
        if isinstance(detalhe.get("service"), dict):
            comp = detalhe["service"].get("company")
            if isinstance(comp, dict):
                transportadora = (comp.get("name") or "").strip()

        print_resp = imprimir_etiquetas(token, [order_id], mode="public")
        url_pdf = _extrair_url_impressao(print_resp)
        anexo = None
        if url_pdf:
            pdf = baixar_url_me(token, url_pdf)
            anexo = _salvar_pdf_etiqueta_anexo(cur, id_vendedor, id_pedido, pdf, id_usuario=id_usuario)

        _atualizar_status_etiqueta(
            cur,
            id_pedido,
            status="gerada",
            me_order_id=order_id,
            me_protocol=protocolo,
            codigo_rastreio=tracking,
            transportadora=transportadora or "Melhor Envio",
        )
        msg = f"Etiqueta Melhor Envio gerada para o pedido {numero or id_pedido}."
        if tracking:
            msg += f" Rastreio: {tracking}."
        registrar_historico(cur, id_pedido, "etiqueta_me", msg, id_usuario)
        return {
            "ok": True,
            "me_order_id": order_id,
            "me_protocol": protocolo,
            "codigo_rastreio": tracking,
            "anexo": anexo,
            "message": msg,
        }
    except Exception as e:
        _log.exception("Falha etiqueta ME pedido %s", id_pedido)
        _atualizar_status_etiqueta(cur, id_pedido, status="erro")
        registrar_historico(
            cur,
            id_pedido,
            "etiqueta_me_erro",
            f"Falha ao gerar etiqueta ME: {str(e)[:400]}",
            id_usuario,
        )
        raise


def tentar_contratar_etiqueta_apos_pagamento(
    cur,
    id_pedido: int,
    *,
    id_usuario: int | None = None,
) -> dict[str, Any] | None:
    """Chamado após pagamento confirmado — não interrompe o fluxo em caso de erro."""
    if not _pedido_tem_colunas_me(cur):
        return None
    cur.execute(
        """
        SELECT id_tenant_vendedor, me_service_id, me_etiqueta_status
        FROM tbl_pedido WHERE id = %s
        """,
        (id_pedido,),
    )
    row = cur.fetchone()
    if not row:
        return None
    id_vendedor, service_id, etiq_status = int(row[0]), row[1], row[2] or ""
    if not service_id or etiq_status in ("manual",):
        return None
    if etiq_status not in ("pendente", "erro", ""):
        return None
    if not me_conectado(cur, id_vendedor):
        _log.info("ME etiqueta: vendedor %s não conectado (pedido %s).", id_vendedor, id_pedido)
        return None
    try:
        return contratar_etiqueta_pedido(cur, id_vendedor, id_pedido, id_usuario=id_usuario)
    except Exception as e:
        _log.warning("ME etiqueta automática pedido %s: %s", id_pedido, e)
        return {"ok": False, "message": str(e)}
