# Ajuste de status de pedido pelo desenvolvedor, com as consequências locais.
from __future__ import annotations

from typing import Any

from core.pedidos.servico import (
    STATUS_AGUARDANDO,
    STATUS_AGUARDANDO_CONFIRMACAO,
    STATUS_CANCELADO,
    STATUS_EM_EXPEDICAO,
    STATUS_ENTREGUE,
    STATUS_IMPORTADO,
    STATUS_PAGO,
    STATUS_RASCUNHO,
    STATUS_VENDEDOR_VALIDOS,
    _pedido_colunas,
    _sql_set_status_vendedor,
    agora_utc,
    baixar_estoque_do_pedido,
    col_status_vendedor,
    estornar_estoque_do_pedido,
    obter_pedido,
    pedido_tem_estoque_baixado,
    registrar_historico,
    status_vendedor_pedido,
)

ROTULOS = {
    STATUS_RASCUNHO: "Rascunho",
    STATUS_IMPORTADO: "Importado",
    STATUS_AGUARDANDO: "Aguardando pagamento",
    STATUS_AGUARDANDO_CONFIRMACAO: "Aguardando confirmação",
    STATUS_PAGO: "Pago",
    STATUS_EM_EXPEDICAO: "Em expedição",
    STATUS_ENTREGUE: "Entregue",
    STATUS_CANCELADO: "Cancelado",
}

_COM_BAIXA = {STATUS_PAGO, STATUS_EM_EXPEDICAO, STATUS_ENTREGUE}
_SEM_BAIXA = {
    STATUS_RASCUNHO,
    STATUS_IMPORTADO,
    STATUS_AGUARDANDO,
    STATUS_AGUARDANDO_CONFIRMACAO,
    STATUS_CANCELADO,
}
_PAGO_DE_VERDADE = {STATUS_PAGO, STATUS_EM_EXPEDICAO, STATUS_ENTREGUE}


def _reenviar_saldo_sem_deposito(cur, id_pedido: int) -> None:
    """Itens com depósito já reenviam o saldo dentro do estorno. Os sem depósito, não."""
    try:
        cur.execute(
            """
            SELECT DISTINCT id_variante
            FROM tbl_pedido_item
            WHERE id_pedido = %s AND id_deposito_fornecedor IS NULL AND id_variante IS NOT NULL
            """,
            (int(id_pedido),),
        )
        ids = [int(r[0]) for r in cur.fetchall() if r and r[0]]
    except Exception:
        return
    for id_var in ids:
        try:
            from api.mercado_livre.eco_estoque import ml_sync_suprimido
            from api.mercado_livre.sync_runtime import propagar_estoque_variante_ml

            if not ml_sync_suprimido():
                propagar_estoque_variante_ml(cur, id_var)
        except Exception:
            pass
        try:
            from api.amazon.eco_estoque import amazon_sync_suprimido
            from api.amazon.sync_runtime import propagar_estoque_variante_amazon

            if not amazon_sync_suprimido():
                propagar_estoque_variante_amazon(cur, id_var)
        except Exception:
            pass


def rotulo_status(st: str) -> str:
    return ROTULOS.get(st, st or "—")


def plano_status(atual: str, novo: str, *, baixado: bool) -> list[str]:
    linhas = [f"Status passa de {rotulo_status(atual)} para {rotulo_status(novo)}."]
    if novo in _COM_BAIXA and not baixado:
        linhas.append(
            "Baixa o estoque físico do fornecedor e reenvia o saldo da variante para Mercado Livre e Amazon, se a integração estiver ativa. Não baixa de novo se já estiver baixado."
        )
    elif novo in _SEM_BAIXA and baixado:
        linhas.append(
            "Devolve ao fornecedor a quantidade que já tinha sido baixada e reenvia o saldo para Mercado Livre e Amazon, se a integração estiver ativa."
        )
    else:
        linhas.append("Estoque não muda.")
    if novo in _PAGO_DE_VERDADE:
        linhas.append("Pagamento fica pago. Se pago em estiver vazio, grava agora.")
    elif novo == STATUS_CANCELADO:
        linhas.append(
            "Pagamento fica cancelado e grava cancelado em. O número do pedido permanece. Vale mesmo se já estiver pago ou em expedição."
        )
    else:
        linhas.append("Pagamento volta para pendente e pago em é limpo.")
    if novo == STATUS_EM_EXPEDICAO:
        linhas.append("Grava expedido em, se ainda estiver vazio, e limpa entregue em.")
        linhas.append("Não exige etiqueta de frete nem NF. O fluxo do fornecedor exige.")
    elif novo == STATUS_ENTREGUE:
        linhas.append("Grava entregue em e, se faltar, expedido em.")
        linhas.append("Não exige etiqueta de frete nem NF.")
    else:
        linhas.append("Limpa expedido em e entregue em.")
    if novo == STATUS_RASCUNHO:
        linhas.append("Limpa confirmado em.")
    elif novo == STATUS_AGUARDANDO and atual == STATUS_RASCUNHO:
        linhas.append("Grava confirmado em.")
    linhas.append("Grava no histórico quem alterou e o motivo.")
    linhas.append(
        "Não altera o status do pedido no Bling, Mercado Livre, TikTok, Amazon ou Melhor Envio, não gera etiqueta e não dispara e-mail."
    )
    return linhas


def listar_tenants_pedido(cur, q: str) -> list[dict]:
    termo = (q or "").strip()
    where = [
        """(
            t.tipo_negocio IN ('vendedor', 'hibrido')
            OR EXISTS (SELECT 1 FROM tbl_pedido p WHERE p.id_tenant_vendedor = t.id)
        )"""
    ]
    params: list[Any] = []
    if termo:
        where.append(
            "(t.nome ILIKE %s OR COALESCE(t.nome_fantasia, '') ILIKE %s OR CAST(t.id AS TEXT) = %s)"
        )
        like = f"%{termo}%"
        params.extend([like, like, termo])
    cur.execute(
        f"""
        SELECT t.id, COALESCE(NULLIF(TRIM(t.nome_fantasia), ''), t.nome), t.tipo_negocio
        FROM tbl_tenant t
        WHERE {' AND '.join(where)}
        ORDER BY 2
        LIMIT 40
        """,
        params,
    )
    return [
        {"id": int(r[0]), "nome": r[1] or "", "tipo": r[2] or ""}
        for r in cur.fetchall()
    ]


def listar_pedidos_tenant(cur, id_vendedor: int, q: str) -> list[dict]:
    cv = col_status_vendedor(cur)
    termo = (q or "").strip()
    where = ["p.id_tenant_vendedor = %s"]
    params: list[Any] = [id_vendedor]
    if termo:
        where.append("(p.numero ILIKE %s OR COALESCE(p.cliente_nome, '') ILIKE %s OR CAST(p.id AS TEXT) = %s)")
        like = f"%{termo}%"
        params.extend([like, like, termo])
    cur.execute(
        f"""
        SELECT p.id, p.numero, p.{cv}, COALESCE(p.cliente_nome, ''),
               COALESCE(NULLIF(TRIM(tf.nome_fantasia), ''), tf.nome, ''),
               p.criado_em
        FROM tbl_pedido p
        LEFT JOIN tbl_tenant tf ON tf.id = p.id_tenant_fornecedor
        WHERE {' AND '.join(where)}
        ORDER BY p.id DESC
        LIMIT 50
        """,
        params,
    )
    out = []
    for r in cur.fetchall():
        st = (r[2] or "").strip()
        out.append(
            {
                "id": int(r[0]),
                "numero": r[1] or "",
                "status": st,
                "status_rotulo": rotulo_status(st),
                "cliente": r[3] or "",
                "fornecedor": r[4] or "",
                "criado_em": r[5].isoformat() if r[5] else None,
            }
        )
    return out


def detalhe_pedido_status(cur, id_pedido: int) -> dict:
    ped = obter_pedido(cur, id_pedido)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    atual = status_vendedor_pedido(ped)
    baixado = pedido_tem_estoque_baixado(cur, id_pedido)
    destinos = []
    for st in STATUS_VENDEDOR_VALIDOS:
        if st == atual:
            continue
        destinos.append(
            {
                "status": st,
                "rotulo": rotulo_status(st),
                "efeitos": plano_status(atual, st, baixado=baixado),
            }
        )
    return {
        "id": ped["id"],
        "numero": ped.get("numero") or "",
        "id_tenant_vendedor": ped.get("id_tenant_vendedor"),
        "cliente": ped.get("cliente_nome") or "",
        "fornecedor": ped.get("fornecedor_nome") or "",
        "origem": ped.get("origem") or "manual",
        "status": atual,
        "status_rotulo": rotulo_status(atual),
        "estoque_baixado": baixado,
        "destinos": destinos,
    }


def aplicar_status_pedido_dev(
    cur,
    id_pedido: int,
    status_novo: str,
    *,
    id_usuario: int | None,
    motivo: str,
) -> dict:
    novo = (status_novo or "").strip()
    if novo not in STATUS_VENDEDOR_VALIDOS:
        raise ValueError("Status inválido.")
    texto = (motivo or "").strip()
    if len(texto) < 5:
        raise ValueError("Informe o motivo (mínimo 5 caracteres).")

    ped = obter_pedido(cur, id_pedido)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    atual = status_vendedor_pedido(ped)
    if atual == novo:
        raise ValueError("O pedido já está neste status.")

    baixado = pedido_tem_estoque_baixado(cur, id_pedido)
    efeitos = plano_status(atual, novo, baixado=baixado)

    if novo in _COM_BAIXA and not baixado:
        baixar_estoque_do_pedido(cur, id_pedido, ped=ped)
    elif novo in _SEM_BAIXA and baixado:
        estornar_estoque_do_pedido(cur, id_pedido, ped=ped)
        _reenviar_saldo_sem_deposito(cur, id_pedido)

    agora = agora_utc()
    cols = _pedido_colunas(cur)
    set_sv, dup = _sql_set_status_vendedor(cur)
    params: list[Any] = [novo]
    if dup:
        params.append(novo)
    extras: list[str] = []

    if "status_pagamento" in cols:
        if novo in _PAGO_DE_VERDADE:
            extras.append("status_pagamento = 'pago'")
        elif novo == STATUS_CANCELADO:
            extras.append("status_pagamento = 'cancelado'")
        else:
            extras.append("status_pagamento = 'pendente'")
    if "status_comprador" in cols:
        if novo == STATUS_CANCELADO:
            extras.append("status_comprador = 'cancelado'")
        elif novo in _PAGO_DE_VERDADE:
            extras.append("status_comprador = 'pago'")
        else:
            extras.append("status_comprador = 'pendente'")
    if "pago_em" in cols:
        if novo in _PAGO_DE_VERDADE:
            extras.append("pago_em = COALESCE(pago_em, %s)")
            params.append(agora)
        elif novo != STATUS_CANCELADO:
            extras.append("pago_em = NULL")
    if "cancelado_em" in cols:
        if novo == STATUS_CANCELADO:
            extras.append("cancelado_em = COALESCE(cancelado_em, %s)")
            params.append(agora)
        else:
            extras.append("cancelado_em = NULL")
    if "expedido_em" in cols:
        if novo in (STATUS_EM_EXPEDICAO, STATUS_ENTREGUE):
            extras.append("expedido_em = COALESCE(expedido_em, %s)")
            params.append(agora)
        else:
            extras.append("expedido_em = NULL")
    if "entregue_em" in cols:
        if novo == STATUS_ENTREGUE:
            extras.append("entregue_em = COALESCE(entregue_em, %s)")
            params.append(agora)
        else:
            extras.append("entregue_em = NULL")
    if "confirmado_em" in cols:
        if novo == STATUS_RASCUNHO:
            extras.append("confirmado_em = NULL")
        elif novo == STATUS_AGUARDANDO and atual == STATUS_RASCUNHO:
            extras.append("confirmado_em = COALESCE(confirmado_em, %s)")
            params.append(agora)

    extras.append("atualizado_em = %s")
    params.append(agora)
    params.append(id_pedido)
    extra_sql = (", " + ", ".join(extras)) if extras else ""
    cur.execute(
        f"UPDATE tbl_pedido SET {set_sv}{extra_sql} WHERE id = %s",
        params,
    )
    registrar_historico(
        cur,
        id_pedido,
        "ajuste_status",
        f"Desenvolvedor: {rotulo_status(atual)} → {rotulo_status(novo)}. {texto}",
        id_usuario,
    )
    return {
        "id": id_pedido,
        "numero": ped.get("numero") or "",
        "status_anterior": atual,
        "status": novo,
        "efeitos": efeitos,
    }
