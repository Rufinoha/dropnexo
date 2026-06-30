# api/bling/webhook_estoque.py — recebimento de webhooks Bling (estoque)
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
from typing import Any

from flask import Flask, Request

from api.bling.cliente import credenciais_bling
from api.bling.conta_empresa import resolver_tenant_por_company
from api.bling.sync_estoque import processar_webhook_estoque_bling
from global_utils import Var_ConectarBanco, agora_utc

_log = logging.getLogger(__name__)


def validar_assinatura_webhook(body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not str(signature_header).startswith("sha256="):
        return False
    esperado = str(signature_header)[7:].strip().lower()
    _, client_secret = credenciais_bling()
    calculado = hmac.new(client_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, calculado)


def _extrair_company_id(envelope: dict[str, Any]) -> str:
    for chave in ("companyId", "company_id"):
        val = envelope.get(chave)
        if val:
            return str(val).strip()
    data = envelope.get("data")
    if isinstance(data, dict):
        for chave in ("companyId", "company_id"):
            val = data.get(chave)
            if val:
                return str(val).strip()
    return ""


def _extrair_recurso_acao(envelope: dict[str, Any]) -> tuple[str, str]:
    # Bling API v3 documenta os campos como $resource e $action (com cifrão).
    recurso = str(
        envelope.get("resource")
        or envelope.get("recurso")
        or envelope.get("$resource")
        or ""
    ).strip().lower()
    acao = str(
        envelope.get("action")
        or envelope.get("acao")
        or envelope.get("$action")
        or ""
    ).strip().lower()
    return recurso, acao


def _payload_estoque(envelope: dict[str, Any]) -> dict[str, Any]:
    candidatos: list[Any] = [
        envelope.get("data"),
        envelope.get("$payload"),
        envelope.get("payload"),
    ]
    for bloco in candidatos:
        if isinstance(bloco, dict) and (bloco.get("produto") or bloco.get("deposito")):
            return bloco
    if envelope.get("produto") or envelope.get("deposito"):
        return envelope
    return {}


def enfileirar_webhook(cur, *, id_tenant: int | None, company_id: str, envelope: dict) -> int:
    recurso, acao = _extrair_recurso_acao(envelope)
    cur.execute(
        """
        INSERT INTO tbl_integracao_bling_webhook_fila (
            id_tenant, company_id, recurso, acao, payload, status, criado_em
        ) VALUES (%s, %s, %s, %s, %s::jsonb, 'pendente', %s)
        RETURNING id
        """,
        (
            id_tenant,
            company_id or None,
            recurso or None,
            acao or None,
            json.dumps(envelope, ensure_ascii=False),
            agora_utc(),
        ),
    )
    return int(cur.fetchone()[0])


def processar_fila_webhook(cur, fila_id: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT id_tenant, company_id, recurso, acao, payload
        FROM tbl_integracao_bling_webhook_fila WHERE id = %s
        """,
        (fila_id,),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "motivo": "fila_inexistente"}

    id_tenant, company_id, recurso, acao, payload_raw = row
    envelope = payload_raw if isinstance(payload_raw, dict) else {}
    if isinstance(payload_raw, str):
        try:
            envelope = json.loads(payload_raw) or {}
        except json.JSONDecodeError:
            envelope = {}

    recurso = (recurso or _extrair_recurso_acao(envelope)[0]).lower()
    if recurso not in ("stock", "virtual_stock", "estoque", "estoque_virtual"):
        cur.execute(
            """
            UPDATE tbl_integracao_bling_webhook_fila
            SET status = 'ignorado', processado_em = %s, erro = %s
            WHERE id = %s
            """,
            (agora_utc(), f"recurso_nao_estoque:{recurso}", fila_id),
        )
        return {"ok": True, "ignorado": True, "motivo": "recurso_nao_estoque"}

    if not id_tenant and company_id:
        id_tenant = resolver_tenant_por_company(cur, company_id)
    if not id_tenant:
        cur.execute(
            """
            UPDATE tbl_integracao_bling_webhook_fila
            SET status = 'erro', processado_em = %s, erro = %s
            WHERE id = %s
            """,
            (agora_utc(), "tenant_nao_encontrado", fila_id),
        )
        return {"ok": False, "motivo": "tenant_nao_encontrado"}

    cur.execute(
        "UPDATE tbl_integracao_bling_webhook_fila SET status = 'processando' WHERE id = %s",
        (fila_id,),
    )

    try:
        resultado = processar_webhook_estoque_bling(
            cur,
            int(id_tenant),
            _payload_estoque(envelope),
            contexto="fornecedor",
        )
        status = "ignorado" if resultado.get("ignorado") else ("ok" if resultado.get("ok") else "erro")
        cur.execute(
            """
            UPDATE tbl_integracao_bling_webhook_fila
            SET id_tenant = %s, status = %s, processado_em = %s, erro = %s
            WHERE id = %s
            """,
            (
                id_tenant,
                status,
                agora_utc(),
                None if status in ("ok", "ignorado") else resultado.get("motivo"),
                fila_id,
            ),
        )
        return resultado
    except Exception as e:
        cur.execute(
            """
            UPDATE tbl_integracao_bling_webhook_fila
            SET status = 'erro', processado_em = %s, erro = %s
            WHERE id = %s
            """,
            (agora_utc(), str(e)[:500], fila_id),
        )
        raise


def receber_webhook_http(app: Flask, request: Request) -> tuple[dict, int]:
    body = request.get_data(cache=True)
    if not validar_assinatura_webhook(body, request.headers.get("X-Bling-Signature-256")):
        return {"success": False, "message": "Assinatura inválida."}, 401

    try:
        envelope = json.loads(body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return {"success": False, "message": "JSON inválido."}, 400

    if not isinstance(envelope, dict):
        return {"success": False, "message": "Payload inválido."}, 400

    company_id = _extrair_company_id(envelope)
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        id_tenant = resolver_tenant_por_company(cur, company_id) if company_id else None
        fila_id = enfileirar_webhook(
            cur, id_tenant=id_tenant, company_id=company_id, envelope=envelope
        )
        conn.commit()
    finally:
        conn.close()

    def _worker() -> None:
        with app.app_context():
            c = Var_ConectarBanco()
            try:
                cur = c.cursor()
                processar_fila_webhook(cur, fila_id)
                c.commit()
            except Exception:
                _log.exception("Erro ao processar webhook Bling fila=%s", fila_id)
                c.rollback()
            finally:
                c.close()

    threading.Thread(target=_worker, daemon=True, name=f"bling-wh-{fila_id}").start()
    return {"success": True}, 200
