# api/pix_manual/pedido.py — PIX manual B2B (QR estático + comprovante)
from __future__ import annotations

from api.pix_manual.cliente import carregar_config_pix_manual, pix_manual_ativo
from api.pix_manual.payload import gerar_payload_pix, normalizar_txid
from global_utils import agora_utc
from core.pedidos.servico import (
    STATUS_AGUARDANDO,
    STATUS_IMPORTADO,
    STATUS_PAGO,
    _status_vendedor_pagavel,
    marcar_pedido_pago,
    obter_pedido,
    registrar_historico,
    status_vendedor_pedido,
)


def meio_pix_manual_fornecedor(cur, id_fornecedor: int) -> dict:
    ativo = pix_manual_ativo(cur, id_fornecedor)
    return {
        "integracao": "pix-manual",
        "integracao_nome": "PIX Manual",
        "conectado": ativo,
        "pix_manual": ativo,
        "pix": False,
        "cartao": False,
    }


def iniciar_pix_manual(cur, id_vendedor: int, id_pedido: int) -> dict:
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if not _status_vendedor_pagavel(status_vendedor_pedido(ped)):
        raise ValueError("Somente pedidos importados ou aguardando pagamento podem usar PIX manual.")

    id_forn = int(ped["id_tenant_fornecedor"])
    if not pix_manual_ativo(cur, id_forn):
        raise ValueError("Fornecedor não configurou PIX manual.")

    cfg = carregar_config_pix_manual(cur, id_forn)
    txid = normalizar_txid(ped.get("numero") or f"PED{id_pedido}")
    payload = gerar_payload_pix(
        chave=cfg["chave_pix"],
        nome_beneficiario=cfg["nome_beneficiario"],
        cidade=cfg["cidade_beneficiario"],
        valor=float(ped["valor_total"]),
        txid=txid,
    )

    cur.execute(
        """
        UPDATE tbl_pedido SET
            meio_pagamento = 'pix_manual',
            pix_manual_payload = %s,
            pix_manual_txid = %s,
            atualizado_em = %s
        WHERE id = %s
        """,
        (payload, txid, agora_utc(), id_pedido),
    )
    registrar_historico(
        cur,
        id_pedido,
        "pix_manual",
        f"PIX manual gerado. Referência: {txid}.",
        None,
    )
    return {
        "payload": payload,
        "txid": txid,
        "valor_total": ped["valor_total"],
        "numero_pedido": ped.get("numero"),
        "nome_beneficiario": cfg.get("nome_beneficiario"),
        "status_pagamento": ped.get("status_pagamento") or "pendente",
    }


def marcar_comprovante_enviado(cur, id_pedido: int, *, id_vendedor: int | None = None) -> None:
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped.get("meio_pagamento") != "pix_manual":
        raise ValueError("Pedido não usa PIX manual.")
    if not _status_vendedor_pagavel(status_vendedor_pedido(ped)):
        raise ValueError("Pedido não está aguardando pagamento.")
    cur.execute(
        """
        UPDATE tbl_pedido SET
            status_pagamento = 'comprovante_enviado',
            atualizado_em = %s
        WHERE id = %s
        """,
        (agora_utc(), id_pedido),
    )
    registrar_historico(cur, id_pedido, "comprovante", "Vendedor anexou comprovante PIX.", None)


def confirmar_pix_manual(
    cur,
    id_pedido: int,
    *,
    id_fornecedor: int,
    id_usuario: int | None = None,
) -> None:
    ped = obter_pedido(cur, id_pedido, id_fornecedor=id_fornecedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped.get("meio_pagamento") != "pix_manual":
        raise ValueError("Este pedido não foi pago via PIX manual.")
    if not _status_vendedor_pagavel(status_vendedor_pedido(ped)):
        raise ValueError("Pedido não está aguardando confirmação de pagamento.")
    if ped.get("status_pagamento") not in ("comprovante_enviado", "pendente"):
        raise ValueError("Situação de pagamento inválida para confirmação.")

    marcar_pedido_pago(cur, id_pedido, id_usuario=id_usuario)
    registrar_historico(
        cur,
        id_pedido,
        "pago_manual",
        "Fornecedor confirmou recebimento do PIX manual.",
        id_usuario,
    )


def rejeitar_comprovante_pix(
    cur,
    id_pedido: int,
    *,
    id_fornecedor: int,
    id_usuario: int | None = None,
    motivo: str | None = None,
) -> None:
    ped = obter_pedido(cur, id_pedido, id_fornecedor=id_fornecedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped.get("meio_pagamento") != "pix_manual":
        raise ValueError("Este pedido não usa PIX manual.")
    cur.execute(
        """
        UPDATE tbl_pedido SET
            status_pagamento = 'pendente',
            atualizado_em = %s
        WHERE id = %s
        """,
        (agora_utc(), id_pedido),
    )
    registrar_historico(
        cur,
        id_pedido,
        "comprovante_rejeitado",
        motivo or "Fornecedor rejeitou o comprovante. Envie novamente.",
        id_usuario,
    )
