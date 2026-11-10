# api/fiscal/hub_nfe_config.py — Hub H74 NF-e (credenciais em banco + fallback .env)
from __future__ import annotations

import base64
import logging
import os

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

CHAVE_URL = "hub_nfe_url"
CHAVE_TOKEN = "hub_nfe_token"
CHAVE_TOKEN_ENC = "hub_nfe_token_enc"
PREFIXO_ENC = "fernet:"

_X_SISTEMA = "dropnexo"


def garantir_tabela_config_sistema(conn) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_config_sistema (
            chave TEXT PRIMARY KEY,
            valor TEXT NOT NULL DEFAULT '',
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )


def _ler_chave_db(conn, chave: str) -> str:
    cur = conn.cursor()
    try:
        cur.execute(
            "SELECT valor FROM tbl_config_sistema WHERE chave = %s LIMIT 1",
            (chave,),
        )
        row = cur.fetchone()
        return (row[0] or "").strip() if row else ""
    except Exception:
        return ""


def _salvar_chave_db(conn, chave: str, valor: str) -> None:
    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO tbl_config_sistema (chave, valor, atualizado_em)
        VALUES (%s, %s, NOW())
        ON CONFLICT (chave) DO UPDATE SET
            valor = EXCLUDED.valor,
            atualizado_em = NOW()
        """,
        (chave, valor),
    )


def mascarar_segredo(valor: str) -> str:
    v = (valor or "").strip()
    if not v:
        return ""
    if len(v) <= 8:
        return "••••••••"
    return f"{v[:7]}…{v[-4:]}"


def _cifrar_token(token: str) -> str:
    from sistema.fiscal.nfse.crypto_certificado import criptografar

    bruto = criptografar(token.encode("utf-8"))
    return PREFIXO_ENC + base64.urlsafe_b64encode(bruto).decode("ascii")


def _decifrar_token(valor: str) -> str:
    v = (valor or "").strip()
    if not v:
        return ""
    if not v.startswith(PREFIXO_ENC):
        # legado / plaintext no banco
        return v
    from sistema.fiscal.nfse.crypto_certificado import descriptografar

    blob = base64.urlsafe_b64decode(v[len(PREFIXO_ENC) :].encode("ascii"))
    return descriptografar(blob).decode("utf-8")


def _token_do_banco(conn) -> str:
    enc = _ler_chave_db(conn, CHAVE_TOKEN_ENC)
    if enc:
        try:
            return _decifrar_token(enc)
        except Exception:
            log.exception("Falha ao decifrar hub_nfe_token_enc")
            return ""
    # compat: token em texto puro (se alguém gravou na chave antiga)
    return _ler_chave_db(conn, CHAVE_TOKEN)


def obter_credenciais(conn=None) -> dict:
    """Prioridade: tbl_config_sistema → variáveis de ambiente."""
    db_url = db_token = ""
    fechar = False
    if conn is None:
        from global_utils import Var_ConectarBanco

        conn = Var_ConectarBanco()
        fechar = True
    try:
        try:
            garantir_tabela_config_sistema(conn)
        except Exception:
            pass
        db_url = _ler_chave_db(conn, CHAVE_URL)
        db_token = _token_do_banco(conn)
    finally:
        if fechar:
            conn.close()

    env_url = (os.getenv("HUB_NFE_URL") or "").strip().rstrip("/")
    env_token = (os.getenv("HUB_NFE_TOKEN") or "").strip()

    url = (db_url or env_url).rstrip("/")
    token = db_token or env_token

    return {
        "base_url": url,
        "token": token,
        "x_sistema": _X_SISTEMA,
        "fonte_url": "banco" if db_url else ("env" if env_url else ""),
        "fonte_token": "banco" if db_token else ("env" if env_token else ""),
    }


def salvar_config_admin(conn, payload: dict) -> None:
    garantir_tabela_config_sistema(conn)

    base_url = (payload.get("base_url") or "").strip()
    if base_url:
        _salvar_chave_db(conn, CHAVE_URL, base_url.rstrip("/"))
    elif payload.get("limpar_base_url"):
        _salvar_chave_db(conn, CHAVE_URL, "")

    token = payload.get("token")
    if isinstance(token, str) and token.strip():
        _salvar_chave_db(conn, CHAVE_TOKEN_ENC, _cifrar_token(token.strip()))
        # limpa legado plaintext, se existir
        _salvar_chave_db(conn, CHAVE_TOKEN, "")
    elif payload.get("limpar_token"):
        _salvar_chave_db(conn, CHAVE_TOKEN_ENC, "")
        _salvar_chave_db(conn, CHAVE_TOKEN, "")


def obter_painel_config(conn) -> dict:
    cred = obter_credenciais(conn)
    return {
        "configurado": bool(cred["base_url"] and cred["token"]),
        "url_configurada": bool(cred["base_url"]),
        "token_configurado": bool(cred["token"]),
        "base_url": cred["base_url"],
        "token_mascara": mascarar_segredo(cred["token"]),
        "fonte_url": cred["fonte_url"],
        "fonte_token": cred["fonte_token"],
        "x_sistema": cred["x_sistema"],
        "dica": (
            "No H74 Painel → HUB → Painel NF-e, o código do sistema deve ser "
            f"«{_X_SISTEMA}». Cole o token gerado aqui (aparece uma vez só no H74)."
        ),
    }


def testar_conexao(conn=None) -> dict:
    from api.fiscal.focus_nfe import FocusNfeError, request_json

    cred = obter_credenciais(conn)
    if not cred["base_url"]:
        return {"ok": False, "message": "URL do Hub H74 não configurada."}
    if not cred["token"]:
        return {"ok": False, "message": "Token do Hub H74 não configurado."}
    try:
        status, body = request_json("homologacao", "GET", "/v2/empresas", timeout=20)
        qtd = 0
        if isinstance(body, list):
            qtd = len(body)
        elif isinstance(body, dict):
            dados = body.get("dados") or body.get("empresas") or body.get("items")
            if isinstance(dados, list):
                qtd = len(dados)
        return {
            "ok": True,
            "message": f"Conexão OK (HTTP {status}). Sistemas autenticados; empresas visíveis: {qtd}.",
            "base_url": cred["base_url"],
            "http_status": status,
        }
    except FocusNfeError as e:
        return {"ok": False, "message": str(e), "http_status": getattr(e, "status", 0)}
    except Exception as e:
        return {"ok": False, "message": str(e)}
