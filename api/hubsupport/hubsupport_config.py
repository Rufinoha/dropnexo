# api/hubsupport/hubsupport_config.py — credenciais e painel (Configurações)
from __future__ import annotations

import json
import os
from typing import Any

from dotenv import load_dotenv

load_dotenv()

DEFAULT_BASE_URL = "https://hubsupport.com.br/api/v1/integration"

CHAVE_API_TOKEN = "hubsupport_api_token"
CHAVE_WEBHOOK_SECRET = "hubsupport_webhook_secret"
CHAVE_BASE_URL = "hubsupport_base_url"


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


def obter_credenciais(conn=None) -> dict:
    """Prioridade: tbl_config_sistema → variáveis de ambiente."""
    db_token = db_secret = db_base = ""
    fechar = False
    if conn is None:
        from global_utils import Var_ConectarBanco

        conn = Var_ConectarBanco()
        fechar = True
    try:
        db_token = _ler_chave_db(conn, CHAVE_API_TOKEN)
        db_secret = _ler_chave_db(conn, CHAVE_WEBHOOK_SECRET)
        db_base = _ler_chave_db(conn, CHAVE_BASE_URL)
    finally:
        if fechar:
            conn.close()

    env_token = (os.getenv("HUBSUPPORT_API_TOKEN") or "").strip()
    env_secret = (os.getenv("HUBSUPPORT_WEBHOOK_SECRET") or "").strip()
    env_base = (
        (os.getenv("HUBSUPPORT_API_BASE") or "").strip()
        or (os.getenv("HUBSUPPORT_BASE_URL") or "").strip()
    )

    api_token = db_token or env_token
    webhook_secret = db_secret or env_secret
    base_url = (db_base or env_base or DEFAULT_BASE_URL).rstrip("/")

    return {
        "api_token": api_token,
        "webhook_secret": webhook_secret,
        "base_url": base_url,
        "fonte_token": "banco" if db_token else ("env" if env_token else ""),
        "fonte_webhook": "banco" if db_secret else ("env" if env_secret else ""),
        "fonte_base_url": "banco" if db_base else ("env" if env_base else "padrao"),
    }


def url_webhook_publica(base_url_app: str = "") -> str:
    from global_utils import obter_base_url

    base = (base_url_app or obter_base_url() or "").strip().rstrip("/")
    if not base:
        return "/webhooks/hubsupport"
    return f"{base}/webhooks/hubsupport"


def webhook_habilitado() -> bool:
    v = (os.getenv("HUBSUPPORT_WEBHOOK_ENABLED") or "true").strip().lower()
    return v not in ("0", "false", "no", "off")


def salvar_config_admin(conn, payload: dict) -> None:
    base_url = (payload.get("base_url") or "").strip()
    api_token = payload.get("api_token")
    webhook_secret = payload.get("webhook_secret")

    if base_url:
        _salvar_chave_db(conn, CHAVE_BASE_URL, base_url.rstrip("/"))
    elif payload.get("limpar_base_url"):
        _salvar_chave_db(conn, CHAVE_BASE_URL, "")

    if isinstance(api_token, str) and api_token.strip():
        _salvar_chave_db(conn, CHAVE_API_TOKEN, api_token.strip())

    if isinstance(webhook_secret, str) and webhook_secret.strip():
        _salvar_chave_db(conn, CHAVE_WEBHOOK_SECRET, webhook_secret.strip())


def registrar_log_webhook(conn, evento: str, external_id: str | None, payload: Any) -> None:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            INSERT INTO tbl_hubsupport_webhook_log (evento, external_id, payload)
            VALUES (%s, %s, %s::jsonb)
            """,
            (
                evento,
                external_id,
                json.dumps(payload, ensure_ascii=False) if not isinstance(payload, str) else payload,
            ),
        )
    except Exception:
        pass


def listar_logs_webhook(conn, limit: int = 40) -> list:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT id, evento, external_id, payload, processado_em
            FROM tbl_hubsupport_webhook_log
            ORDER BY processado_em DESC
            LIMIT %s
            """,
            (max(1, min(int(limit), 200)),),
        )
        cols = [c[0] for c in cur.description]
        out = []
        for row in cur.fetchall():
            item = dict(zip(cols, row))
            if item.get("processado_em"):
                item["processado_em"] = item["processado_em"].isoformat()
            out.append(item)
        return out
    except Exception:
        return []


def listar_logs_api(conn, limit: int = 20) -> list:
    cur = conn.cursor()
    try:
        cur.execute(
            """
            SELECT operacao, sucesso, mensagem, http_status, criado_em
            FROM tbl_hubsupport_api_log
            ORDER BY criado_em DESC
            LIMIT %s
            """,
            (max(1, min(int(limit), 100)),),
        )
        cols = [c[0] for c in cur.description]
        out = []
        for row in cur.fetchall():
            item = dict(zip(cols, row))
            if item.get("criado_em"):
                item["criado_em"] = item["criado_em"].isoformat()
            out.append(item)
        return out
    except Exception:
        return []


def obter_painel_config(conn, base_url_app: str = "") -> dict:
    cred = obter_credenciais(conn)
    cur = conn.cursor()
    stats = {
        "chamados_locais": 0,
        "map_empresa": 0,
        "map_usuario": 0,
        "webhooks_ok": 0,
    }
    try:
        cur.execute("SELECT COUNT(*) FROM tbl_hubsupport_chamado")
        stats["chamados_locais"] = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM tbl_hubsupport_map WHERE tipo = 'empresa'")
        stats["map_empresa"] = int(cur.fetchone()[0] or 0)
        cur.execute("SELECT COUNT(*) FROM tbl_hubsupport_map WHERE tipo = 'usuario'")
        stats["map_usuario"] = int(cur.fetchone()[0] or 0)
        cur.execute(
            """
            SELECT COUNT(*) FROM tbl_hubsupport_webhook_log
            WHERE evento NOT LIKE 'webhook.%%'
            """
        )
        stats["webhooks_ok"] = int(cur.fetchone()[0] or 0)
    except Exception:
        pass

    return {
        "configurado": bool(cred["api_token"]),
        "webhook_configurado": bool(cred["webhook_secret"]),
        "base_url": cred["base_url"],
        "webhook_url": url_webhook_publica(base_url_app),
        "token_mascara": mascarar_segredo(cred["api_token"]),
        "webhook_mascara": mascarar_segredo(cred["webhook_secret"]),
        "fonte_token": cred["fonte_token"],
        "fonte_webhook": cred["fonte_webhook"],
        "fonte_base_url": cred["fonte_base_url"],
        "portal": (os.getenv("HUBSUPPORT_PORTAL") or "h74").strip() or "h74",
        "stats": stats,
        "logs": listar_logs_webhook(conn, limit=40),
        "api_logs": listar_logs_api(conn, limit=20),
    }


def testar_conexao(conn) -> dict:
    from api.hubsupport.hubsupport_client import HubSupportClient, HubSupportError

    cred = obter_credenciais(conn)
    if not cred["api_token"]:
        return {"ok": False, "message": "Token da API não configurado."}

    client = HubSupportClient(token=cred["api_token"], base_url=cred["base_url"])
    try:
        client.listar_chamados("dropnexo:usuario:0", page=1, per_page=1)
        return {
            "ok": True,
            "message": "Conexão OK — API respondeu com autenticação válida.",
            "base_url": cred["base_url"],
        }
    except HubSupportError as e:
        if e.status_code == 401:
            return {"ok": False, "message": "Token recusado (401). Verifique a chave de API."}
        if e.status_code in (404, 400):
            return {
                "ok": True,
                "message": "Autenticação aceita (endpoint respondeu).",
                "base_url": cred["base_url"],
            }
        return {"ok": False, "message": str(e)}
