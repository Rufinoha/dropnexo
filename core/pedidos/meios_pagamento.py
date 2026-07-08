# core/pedidos/meios_pagamento.py — meios de pagamento por fornecedor (MP + PIX manual)
from __future__ import annotations

from api.mercadopago.cliente import meios_pagamento_fornecedor
from api.pix_manual.pedido import meio_pix_manual_fornecedor


def listar_meios_fornecedor(cur, id_fornecedor: int, *, icone_mp: str = "") -> list[dict]:
    out: list[dict] = []
    mp = meios_pagamento_fornecedor(cur, id_fornecedor)
    if mp.get("conectado"):
        out.append(
            {
                "integracao": "mercado-pago",
                "integracao_nome": "Mercado Pago",
                "icone_url": icone_mp,
                "conectado": True,
                "pix": bool(mp.get("pix")),
                "cartao": bool(mp.get("cartao")),
                "pix_manual": False,
            }
        )
    pix_m = meio_pix_manual_fornecedor(cur, id_fornecedor)
    if pix_m.get("pix_manual"):
        out.append({**pix_m, "icone_url": ""})
    return out
