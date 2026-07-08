# api/bling/webhooks.py — webhooks Bling (estoque e pedidos)
from __future__ import annotations

# ── webhook_estoque ───────────────────────────────────

import hashlib
import hmac
import json
import logging
import threading
from typing import Any

from flask import Flask, Request

from api.bling.cliente import credenciais_bling
from api.bling.config import resolver_tenant_por_company
from api.bling.estoque import processar_webhook_estoque_bling
from global_utils import Var_ConectarBanco, agora_utc

_log = logging.getLogger(__name__)


def validar_assinatura_webhook(body: bytes, signature_header: str | None) -> bool:
    if not signature_header or not str(signature_header).startswith("sha256="):
        return False
    esperado = str(signature_header)[7:].strip().lower()
    _, client_secret = credenciais_bling()
    calculado = hmac.new(client_secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(esperado, calculado)


_RECURSOS_ESTOQUE = frozenset({"stock", "virtual_stock", "estoque", "estoque_virtual"})
_CHAVES_RECURSO = ("$resource", "resource", "recurso", "eventType", "tipo", "type")
_CHAVES_ACAO = ("$action", "action", "acao", "eventAction")
_CHAVES_COMPANY = ("companyId", "company_id", "companyid")


def _blocos_aninhados(envelope: dict[str, Any], *, max_depth: int = 5) -> list[dict[str, Any]]:
    blocos: list[dict[str, Any]] = []

    def _walk(obj: Any, depth: int) -> None:
        if depth > max_depth or not isinstance(obj, dict):
            return
        blocos.append(obj)
        for val in obj.values():
            if isinstance(val, dict):
                _walk(val, depth + 1)

    _walk(envelope, 0)
    return blocos


def _valor_dict(bloco: dict[str, Any], chaves: tuple[str, ...]) -> str:
    for chave in chaves:
        val = bloco.get(chave)
        if val is not None and str(val).strip():
            return str(val).strip().lower()
    return ""


def _extrair_company_id(envelope: dict[str, Any]) -> str:
    for bloco in _blocos_aninhados(envelope):
        cid = _valor_dict(bloco, _CHAVES_COMPANY)
        if cid:
            return cid
    return ""


def _inferir_recurso_evento(envelope: dict[str, Any]) -> str:
    for bloco in _blocos_aninhados(envelope):
        evento = str(bloco.get("event") or bloco.get("evento") or "").strip().lower()
        if not evento:
            continue
        if "virtual_stock" in evento or "estoque_virtual" in evento:
            return "virtual_stock"
        if "stock" in evento or "estoque" in evento:
            return "stock"
        if "." in evento:
            prefixo = evento.split(".", 1)[0]
            if prefixo in _RECURSOS_ESTOQUE:
                return prefixo
    return ""


def _parece_payload_estoque(bloco: dict[str, Any]) -> bool:
    if bloco.get("produto") or bloco.get("deposito"):
        return True
    if bloco.get("produtoId") or bloco.get("depositoId"):
        return True
    if any(chave in bloco for chave in ("saldoFisico", "saldoVirtual", "saldoFisicoTotal")):
        return bool(bloco.get("produto") or bloco.get("produtoId") or bloco.get("idProduto"))
    return False


def _extrair_recurso_acao(envelope: dict[str, Any]) -> tuple[str, str]:
    recurso = ""
    acao = ""
    for bloco in _blocos_aninhados(envelope):
        if not recurso:
            recurso = _valor_dict(bloco, _CHAVES_RECURSO)
        if not acao:
            acao = _valor_dict(bloco, _CHAVES_ACAO)
        if recurso and acao:
            break
    if not recurso:
        recurso = _inferir_recurso_evento(envelope)
    if not recurso:
        for bloco in _blocos_aninhados(envelope):
            if _parece_payload_estoque(bloco):
                recurso = "stock"
                break
    return recurso, acao


def _normalizar_payload_estoque(bloco: dict[str, Any]) -> dict[str, Any]:
    produto = bloco.get("produto")
    deposito = bloco.get("deposito")
    if not isinstance(produto, dict):
        produto = {"id": produto} if produto is not None else {}
    if not isinstance(deposito, dict):
        deposito = {"id": deposito} if deposito is not None else {}

    if not produto.get("id"):
        for chave in ("produtoId", "idProduto", "id_produto"):
            if bloco.get(chave) is not None:
                produto["id"] = bloco.get(chave)
                break
    if not deposito.get("id"):
        for chave in ("depositoId", "idDeposito", "id_deposito"):
            if bloco.get(chave) is not None:
                deposito["id"] = bloco.get(chave)
                break
    for chave in ("saldoFisico", "saldoVirtual", "quantidade", "saldoFisicoTotal"):
        if chave in bloco and deposito.get(chave) is None:
            deposito[chave] = bloco.get(chave)
    return {"produto": produto, "deposito": deposito}


def _payload_estoque(envelope: dict[str, Any]) -> dict[str, Any]:
    for bloco in _blocos_aninhados(envelope):
        for cand in (
            bloco,
            bloco.get("$payload"),
            bloco.get("payload"),
            bloco.get("data"),
        ):
            if isinstance(cand, dict) and _parece_payload_estoque(cand):
                return _normalizar_payload_estoque(cand)
    return {}


def _eh_recurso_estoque(recurso: str, envelope: dict[str, Any]) -> bool:
    if recurso in _RECURSOS_ESTOQUE:
        return True
    return bool(_payload_estoque(envelope))


def _resolver_tenant_webhook(cur, company_id: str | None) -> int | None:
    cid = str(company_id or "").strip()
    if cid:
        tid = resolver_tenant_por_company(cur, cid)
        if tid:
            return tid
    cur.execute(
        """
        SELECT id_tenant FROM tbl_integracao_bling
        WHERE status = 'conectado'
        ORDER BY id_tenant
        """
    )
    rows = cur.fetchall()
    if len(rows) == 1:
        return int(rows[0][0])
    return None


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
    acao = (acao or _extrair_recurso_acao(envelope)[1]).lower()

    from api.bling.webhooks import eh_recurso_pedido, processar_webhook_pedido_fila

    if eh_recurso_pedido(recurso, envelope):
        return processar_webhook_pedido_fila(
            cur,
            fila_id,
            id_tenant=int(id_tenant) if id_tenant else None,
            company_id=company_id,
            envelope=envelope,
            recurso=recurso,
            acao=acao,
        )

    if not _eh_recurso_estoque(recurso, envelope):
        chaves = ",".join(sorted(envelope.keys()))[:120]
        cur.execute(
            """
            UPDATE tbl_integracao_bling_webhook_fila
            SET status = 'ignorado', processado_em = %s, erro = %s
            WHERE id = %s
            """,
            (agora_utc(), f"recurso_nao_estoque:{recurso or '?'}|keys={chaves}", fila_id),
        )
        return {"ok": True, "ignorado": True, "motivo": "recurso_nao_estoque"}

    if not id_tenant:
        id_tenant = _resolver_tenant_webhook(cur, company_id)
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
        id_tenant = _resolver_tenant_webhook(cur, company_id)
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


# ── webhook_pedidos ───────────────────────────────────

import logging
from typing import Any

from api.bling.pedidos import importar_pedido_bling_por_id, pedidos_importacao_auto_ativa
from api.bling.webhooks import _blocos_aninhados, _resolver_tenant_webhook
from global_utils import agora_utc

_log = logging.getLogger(__name__)

_RECURSOS_PEDIDO = frozenset(
    {
        "order",
        "orders",
        "pedido",
        "pedidos",
        "pedidos_vendas",
        "pedido_venda",
        "pedidos-vendas",
        "sales_order",
        "salesorder",
        "venda",
        "vendas",
    }
)
_ACOES_IGNORAR = frozenset({"delete", "deleted", "exclusao", "excluir", "removed", "remove"})
_CHAVES_ID_PEDIDO = (
    "id",
    "idPedido",
    "id_pedido",
    "orderId",
    "order_id",
    "idPedidoVenda",
    "id_pedido_venda",
    "numeroPedido",
)


def _inferir_recurso_pedido(envelope: dict[str, Any]) -> str:
    for bloco in _blocos_aninhados(envelope):
        evento = str(bloco.get("event") or bloco.get("evento") or "").strip().lower()
        if not evento:
            continue
        if "pedido" in evento or "order" in evento or "venda" in evento:
            if "pedido" in evento or "venda" in evento:
                return "pedidos_vendas"
            return "order"
    return ""


def eh_recurso_pedido(recurso: str, envelope: dict[str, Any]) -> bool:
    r = (recurso or "").strip().lower()
    if r in _RECURSOS_PEDIDO:
        return True
    if r and ("pedido" in r or "order" in r or "venda" in r):
        return True
    return bool(_inferir_recurso_pedido(envelope))


def extrair_id_pedido_bling(envelope: dict[str, Any]) -> str:
    for bloco in _blocos_aninhados(envelope):
        for cand in (
            bloco,
            bloco.get("data"),
            bloco.get("$data"),
            bloco.get("payload"),
            bloco.get("$payload"),
            bloco.get("pedido"),
            bloco.get("order"),
        ):
            if not isinstance(cand, dict):
                continue
            for chave in _CHAVES_ID_PEDIDO:
                val = cand.get(chave)
                if val is not None and str(val).strip():
                    return str(val).strip()
    return ""


def processar_webhook_pedido_fila(
    cur,
    fila_id: int,
    *,
    id_tenant: int | None,
    company_id: str | None,
    envelope: dict[str, Any],
    recurso: str,
    acao: str,
) -> dict[str, Any]:
    acao_l = (acao or "").strip().lower()
    if acao_l in _ACOES_IGNORAR:
        cur.execute(
            """
            UPDATE tbl_integracao_bling_webhook_fila
            SET status = 'ignorado', processado_em = %s, erro = %s
            WHERE id = %s
            """,
            (agora_utc(), "acao_exclusao", fila_id),
        )
        return {"ok": True, "ignorado": True, "motivo": "acao_exclusao"}

    if not id_tenant:
        id_tenant = _resolver_tenant_webhook(cur, company_id)
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

    if not pedidos_importacao_auto_ativa(cur, int(id_tenant)):
        cur.execute(
            """
            UPDATE tbl_integracao_bling_webhook_fila
            SET id_tenant = %s, status = 'ignorado', processado_em = %s, erro = %s
            WHERE id = %s
            """,
            (id_tenant, agora_utc(), "importacao_auto_desligada", fila_id),
        )
        return {"ok": True, "ignorado": True, "motivo": "importacao_auto_desligada"}

    id_bling = extrair_id_pedido_bling(envelope)
    if not id_bling:
        cur.execute(
            """
            UPDATE tbl_integracao_bling_webhook_fila
            SET id_tenant = %s, status = 'ignorado', processado_em = %s, erro = %s
            WHERE id = %s
            """,
            (id_tenant, agora_utc(), f"sem_id_pedido:{recurso}", fila_id),
        )
        return {"ok": True, "ignorado": True, "motivo": "sem_id_pedido"}

    cur.execute(
        "UPDATE tbl_integracao_bling_webhook_fila SET status = 'processando' WHERE id = %s",
        (fila_id,),
    )

    try:
        resultado = importar_pedido_bling_por_id(cur, int(id_tenant), id_bling)
        status = "ok" if resultado.get("importados") else "ignorado"
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
                None if status == "ok" else (resultado.get("message") or "")[:500],
                fila_id,
            ),
        )
        return {"ok": True, **resultado}
    except Exception as e:
        _log.exception("Webhook pedido Bling fila=%s id=%s", fila_id, id_bling)
        cur.execute(
            """
            UPDATE tbl_integracao_bling_webhook_fila
            SET id_tenant = %s, status = 'erro', processado_em = %s, erro = %s
            WHERE id = %s
            """,
            (id_tenant, agora_utc(), str(e)[:500], fila_id),
        )
        raise
