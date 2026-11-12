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
CHAVE_TOKEN_NFSE = "hub_nfse_token"
CHAVE_TOKEN_NFSE_ENC = "hub_nfse_token_enc"
CHAVE_AMBIENTE = "hub_nfe_ambiente"
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


def _token_do_banco(conn, chave_enc: str, chave_plain: str) -> str:
    enc = _ler_chave_db(conn, chave_enc)
    if enc:
        try:
            return _decifrar_token(enc)
        except Exception:
            log.exception("Falha ao decifrar %s", chave_enc)
            return ""
    return _ler_chave_db(conn, chave_plain)


def obter_credenciais(conn=None) -> dict:
    """Prioridade: tbl_config_sistema → variáveis de ambiente."""
    db_url = db_token = db_token_nfse = db_ambiente = ""
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
        db_token = _token_do_banco(conn, CHAVE_TOKEN_ENC, CHAVE_TOKEN)
        db_token_nfse = _token_do_banco(conn, CHAVE_TOKEN_NFSE_ENC, CHAVE_TOKEN_NFSE)
        db_ambiente = _ler_chave_db(conn, CHAVE_AMBIENTE)
    finally:
        if fechar:
            conn.close()

    env_url = (os.getenv("HUB_NFE_URL") or "").strip().rstrip("/")
    env_token = (os.getenv("HUB_NFE_TOKEN") or "").strip()
    env_token_nfse = (os.getenv("HUB_NFSE_TOKEN") or "").strip()
    env_ambiente = (os.getenv("HUB_NFE_AMBIENTE") or "").strip().lower()

    url = (db_url or env_url).rstrip("/")
    token = db_token or env_token
    token_nfse = db_token_nfse or env_token_nfse
    ambiente = (db_ambiente or env_ambiente or "homologacao").strip().lower()
    if ambiente != "producao":
        ambiente = "homologacao"

    return {
        "base_url": url,
        "token": token,
        "token_nfse": token_nfse,
        "ambiente": ambiente,
        "x_sistema": _X_SISTEMA,
        "fonte_url": "banco" if db_url else ("env" if env_url else ""),
        "fonte_token": "banco" if db_token else ("env" if env_token else ""),
        "fonte_token_nfse": "banco" if db_token_nfse else ("env" if env_token_nfse else ""),
        "fonte_ambiente": "banco" if db_ambiente else ("env" if env_ambiente else "padrao"),
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
        _salvar_chave_db(conn, CHAVE_TOKEN, "")
    elif payload.get("limpar_token"):
        _salvar_chave_db(conn, CHAVE_TOKEN_ENC, "")
        _salvar_chave_db(conn, CHAVE_TOKEN, "")

    token_nfse = payload.get("token_nfse")
    if isinstance(token_nfse, str) and token_nfse.strip():
        _salvar_chave_db(conn, CHAVE_TOKEN_NFSE_ENC, _cifrar_token(token_nfse.strip()))
        _salvar_chave_db(conn, CHAVE_TOKEN_NFSE, "")
    elif payload.get("limpar_token_nfse"):
        _salvar_chave_db(conn, CHAVE_TOKEN_NFSE_ENC, "")
        _salvar_chave_db(conn, CHAVE_TOKEN_NFSE, "")

    ambiente = str(payload.get("ambiente") or "").strip().lower()
    if ambiente in {"homologacao", "producao"}:
        _salvar_chave_db(conn, CHAVE_AMBIENTE, ambiente)


def obter_painel_config(conn) -> dict:
    cred = obter_credenciais(conn)
    return {
        "configurado": bool(cred["base_url"] and cred["token"] and cred["token_nfse"]),
        "url_configurada": bool(cred["base_url"]),
        "token_configurado": bool(cred["token"]),
        "token_nfse_configurado": bool(cred["token_nfse"]),
        "base_url": cred["base_url"],
        "token_mascara": mascarar_segredo(cred["token"]),
        "token_nfse_mascara": mascarar_segredo(cred["token_nfse"]),
        "ambiente": cred["ambiente"],
        "fonte_url": cred["fonte_url"],
        "fonte_token": cred["fonte_token"],
        "fonte_token_nfse": cred["fonte_token_nfse"],
        "fonte_ambiente": cred["fonte_ambiente"],
        "x_sistema": cred["x_sistema"],
        "dica": (
            "No H74 Painel → HUB → Painel NF-e, o código do sistema deve ser "
            f"«{_X_SISTEMA}». Copie HUB_NFE_TOKEN e HUB_NFSE_TOKEN (aparecem uma vez). "
            "O emitente das notas é o CNPJ da sua empresa, nunca a H74."
        ),
    }


def testar_conexao(conn=None) -> dict:
    from api.fiscal.focus_nfe import FocusNfeError, request_json

    cred = obter_credenciais(conn)
    if not cred["base_url"]:
        return {"ok": False, "message": "URL do Hub H74 não configurada."}
    if not cred["token"]:
        return {"ok": False, "message": "Token NF-e (HUB_NFE_TOKEN) não configurado."}
    if not cred["token_nfse"]:
        return {"ok": False, "message": "Token NFS-e (HUB_NFSE_TOKEN) não configurado."}

    ambiente = cred.get("ambiente") or "homologacao"
    try:
        status_nfe, body = request_json(
            ambiente, "GET", "/v2/empresas", timeout=20, escopo="nfe"
        )
        qtd = 0
        if isinstance(body, list):
            qtd = len(body)
        elif isinstance(body, dict):
            dados = body.get("dados") or body.get("empresas") or body.get("items")
            if isinstance(dados, list):
                qtd = len(dados)

        # Token NFS-e: mesma rota de empresas costuma recusar escopo; validamos com
        # uma consulta leve a /v2/nfse/{ref} de uma ref inexistente (404/422 ≠ 401).
        try:
            request_json(
                ambiente,
                "GET",
                "/v2/nfse/__dropnexo_ping__",
                timeout=20,
                escopo="nfse",
            )
            status_nfse = 200
        except FocusNfeError as e:
            status_nfse = int(getattr(e, "status", 0) or 0)
            if status_nfse == 401:
                return {
                    "ok": False,
                    "message": (
                        "Token NF-e OK, mas o token NFS-e foi recusado (401). "
                        "Confira HUB_NFSE_TOKEN e o escopo no painel H74."
                    ),
                    "http_status": 401,
                    "nfe_ok": True,
                    "nfse_ok": False,
                }

        return {
            "ok": True,
            "message": (
                f"Conexão OK (NF-e HTTP {status_nfe}, NFS-e autenticado; "
                f"ambiente={ambiente}; empresas: {qtd})."
            ),
            "base_url": cred["base_url"],
            "http_status": status_nfe,
            "http_status_nfse": status_nfse,
            "ambiente": ambiente,
            "nfe_ok": True,
            "nfse_ok": True,
        }
    except FocusNfeError as e:
        return {"ok": False, "message": str(e), "http_status": getattr(e, "status", 0)}
    except Exception as e:
        return {"ok": False, "message": str(e)}
