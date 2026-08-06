# core/pedidos/status_integracao.py — avanço de status entre DropNexo e integrações
from __future__ import annotations

from core.pedidos.servico import (
    STATUS_AGUARDANDO,
    STATUS_AGUARDANDO_CONFIRMACAO,
    STATUS_CANCELADO,
    STATUS_EM_EXPEDICAO,
    STATUS_ENTREGUE,
    STATUS_IMPORTADO,
    STATUS_PAGO,
    STATUS_RASCUNHO,
    col_status_vendedor,
    obter_pedido,
    registrar_historico,
    status_vendedor_pedido,
)

# Origens de marketplace: pedido fica no DropNexo; não auto-exporta ao ERP do fornecedor.
ORIGENS_MARKETPLACE = frozenset({"mercado_livre", "tiktok", "amazon"})

# Ordem operacional (maior = mais avançado). cancelado é terminal especial.
_RANK: dict[str, int] = {
    STATUS_RASCUNHO: 0,
    STATUS_IMPORTADO: 1,
    STATUS_AGUARDANDO: 2,
    STATUS_AGUARDANDO_CONFIRMACAO: 3,
    STATUS_PAGO: 4,
    STATUS_EM_EXPEDICAO: 5,
    STATUS_ENTREGUE: 6,
}


def rank_status(status: str | None) -> int:
    return _RANK.get((status or "").strip().lower(), -1)


def status_mais_avancado(atual: str | None, novo: str | None) -> str | None:
    """Retorna o status que deve prevalecer (nunca regride; cancelado ganha se ainda não entregue)."""
    a = (atual or "").strip().lower() or None
    n = (novo or "").strip().lower() or None
    if not n:
        return a
    if not a:
        return n
    if a == STATUS_CANCELADO:
        return a
    if n == STATUS_CANCELADO:
        return a if a == STATUS_ENTREGUE else n
    if a == STATUS_ENTREGUE:
        return a
    return n if rank_status(n) > rank_status(a) else a


def mapear_situacao_bling_para_dn(nome_situacao: str | None) -> str | None:
    """Converte rótulo de situação Bling → status_vendedor DropNexo (best-effort)."""
    n = (nome_situacao or "").strip().lower()
    if not n:
        return None
    if "cancel" in n:
        return STATUS_CANCELADO
    if "entregue" in n or "entregue ao cliente" in n:
        return STATUS_ENTREGUE
    if any(
        x in n
        for x in (
            "em transporte",
            "transporte",
            "enviado",
            "despach",
            "expedi",
            "em separação",
            "em separacao",
            "separado",
        )
    ):
        return STATUS_EM_EXPEDICAO
    if any(x in n for x in ("pago", "aprovad", "atendid", "faturad", "verificado")):
        return STATUS_PAGO
    if "aguardando pagamento" in n or n == "em aberto":
        return STATUS_AGUARDANDO
    return None


def mapear_status_ml_para_dn(status_ml: str | None, *, shipping_status: str | None = None) -> str | None:
    """Converte status de pedido/shipment ML → status_vendedor DropNexo."""
    o = (status_ml or "").strip().lower()
    s = (shipping_status or "").strip().lower()
    if o in ("cancelled", "canceled") or s in ("cancelled", "canceled"):
        return STATUS_CANCELADO
    if s in ("delivered",) or o in ("delivered",):
        return STATUS_ENTREGUE
    if s in ("shipped", "ready_to_ship", "handling") or o in ("shipped",):
        return STATUS_EM_EXPEDICAO
    if o in ("paid", "confirmed"):
        return STATUS_PAGO
    if o in ("payment_required", "pending"):
        return STATUS_AGUARDANDO
    return None


def aplicar_status_avancado(
    cur,
    id_pedido: int,
    novo_status: str,
    *,
    id_usuario: int | None = None,
    origem_evento: str = "integracao",
    detalhe: str | None = None,
) -> bool:
    """Avança status do pedido se `novo_status` for mais avançado. Retorna True se alterou."""
    ped = obter_pedido(cur, int(id_pedido))
    if not ped:
        return False
    atual = status_vendedor_pedido(ped)
    alvo = status_mais_avancado(atual, novo_status)
    if not alvo or alvo == atual:
        return False

    from global_utils import agora_utc

    agora = agora_utc()
    cv = col_status_vendedor(cur)
    sets = [f"{cv} = %s", "atualizado_em = %s"]
    params: list = [alvo, agora]

    if alvo == STATUS_PAGO:
        sets.append("pago_em = COALESCE(pago_em, %s)")
        params.append(agora)
        sets.append("status_pagamento = COALESCE(NULLIF(status_pagamento, ''), 'pago')")
    elif alvo == STATUS_EM_EXPEDICAO:
        sets.append("expedido_em = COALESCE(expedido_em, %s)")
        params.append(agora)
    elif alvo == STATUS_ENTREGUE:
        sets.append("entregue_em = COALESCE(entregue_em, %s)")
        params.append(agora)
        sets.append("expedido_em = COALESCE(expedido_em, %s)")
        params.append(agora)
    elif alvo == STATUS_CANCELADO:
        sets.append("cancelado_em = COALESCE(cancelado_em, %s)")
        params.append(agora)
        sets.append("status_pagamento = 'cancelado'")

    params.append(int(id_pedido))
    cur.execute(
        f"UPDATE tbl_pedido SET {', '.join(sets)} WHERE id = %s",
        params,
    )
    registrar_historico(
        cur,
        int(id_pedido),
        f"status_{origem_evento}",
        detalhe
        or f"Status avançado por integração: {atual} → {alvo}.",
        id_usuario,
    )
    return True
