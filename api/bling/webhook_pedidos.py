# api/bling/webhook_pedidos.py — webhook Bling → importação automática de pedidos
from __future__ import annotations

import logging
from typing import Any

from api.bling.sync_pedidos import importar_pedido_bling_por_id, pedidos_importacao_auto_ativa
from api.bling.webhook_estoque import _blocos_aninhados, _resolver_tenant_webhook
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
