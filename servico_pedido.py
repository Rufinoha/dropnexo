# servico_pedido.py — pedidos B2B vendedor → fornecedor (Fase 0)
from __future__ import annotations

from datetime import datetime
from typing import Any

from fornecedor.requisitos_vendedor import carregar_requisitos_raw
from global_utils import agora_utc
from servico_estoque_reserva import (
    liberar_itens_pedido,
    reservar_itens_pedido,
)

STATUS_RASCUNHO = "rascunho"
STATUS_AGUARDANDO = "aguardando_pagamento"
STATUS_PAGO = "pago"
STATUS_CANCELADO = "cancelado"


def _float(v) -> float:
    return float(v or 0)


def _gerar_numero(cur, prefixo: str, id_tenant: int, tabela: str, col_tenant: str) -> str:
    ano = datetime.now().year
    base = f"{prefixo}-{ano}-"
    cur.execute(
        f"""
        SELECT numero FROM {tabela}
        WHERE {col_tenant} = %s AND numero LIKE %s
        ORDER BY id DESC LIMIT 1
        """,
        (id_tenant, base + "%"),
    )
    row = cur.fetchone()
    seq = 1
    if row and row[0]:
        try:
            seq = int(str(row[0]).split("-")[-1]) + 1
        except ValueError:
            seq = 1
    return f"{base}{seq:05d}"


def registrar_historico(
    cur,
    id_pedido: int,
    evento: str,
    detalhe: str | None = None,
    id_usuario: int | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO tbl_pedido_historico (id_pedido, evento, detalhe, id_usuario)
        VALUES (%s, %s, %s, %s)
        """,
        (id_pedido, evento, detalhe, id_usuario),
    )


def vinculo_ativo(cur, id_vendedor: int, id_fornecedor: int) -> bool:
    cur.execute(
        """
        SELECT 1 FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_vendedor = %s AND id_tenant_fornecedor = %s AND status = 'ativo'
        """,
        (id_vendedor, id_fornecedor),
    )
    return cur.fetchone() is not None


def _buscar_item_vitrine(cur, id_vendedor: int, id_variante: int) -> dict | None:
    cur.execute(
        """
        SELECT pv.id, pv.id_tenant_fornecedor, pv.id_produto, pv.preco_fornecedor, pv.preco_venda,
               COALESCE(pv.nome_vitrine, p.nome), v.sku, p.id_deposito_expedicao
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        WHERE pv.id_tenant_vendedor = %s AND pv.id_variante = %s AND pv.ativo = TRUE
          AND v.ativo = TRUE AND p.ativo = TRUE
        """,
        (id_vendedor, id_variante),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {
        "id_produto_vendedor": row[0],
        "id_fornecedor": int(row[1]),
        "id_produto": int(row[2]),
        "valor_drop": _float(row[3]),
        "preco_venda": _float(row[4]),
        "nome": row[5] or "",
        "sku": row[6] or "",
        "id_deposito": row[7],
    }


def _taxa_pedido_fornecedor(cur, id_fornecedor: int) -> float:
    req, _ = carregar_requisitos_raw(cur, id_fornecedor)
    if req.get("cobra_taxa_pedido") and _float(req.get("valor_taxa_pedido")) > 0:
        return _float(req["valor_taxa_pedido"])
    return 0.0


def _pedido_dict(row, fornecedor_nome: str | None = None, vendedor_nome: str | None = None) -> dict:
    return {
        "id": row[0],
        "id_grupo": row[1],
        "numero": row[2],
        "id_tenant_vendedor": row[3],
        "id_tenant_fornecedor": row[4],
        "origem": row[5],
        "status": row[6],
        "status_pagamento": row[7],
        "cliente_nome": row[8] or "",
        "cliente_email": row[9] or "",
        "cliente_telefone": row[10] or "",
        "cliente_documento": row[11] or "",
        "entrega_cep": row[12] or "",
        "entrega_logradouro": row[13] or "",
        "entrega_numero": row[14] or "",
        "entrega_complemento": row[15] or "",
        "entrega_bairro": row[16] or "",
        "entrega_cidade": row[17] or "",
        "entrega_uf": row[18] or "",
        "subtotal_produtos": _float(row[19]),
        "valor_taxa_pedido": _float(row[20]),
        "valor_frete": _float(row[21]),
        "valor_total": _float(row[22]),
        "observacoes": row[23] or "",
        "confirmado_em": row[24].isoformat() if row[24] else None,
        "pago_em": row[25].isoformat() if row[25] else None,
        "criado_em": row[26].isoformat() if row[26] else None,
        "numero_grupo": row[27] if len(row) > 27 else None,
        "fornecedor_nome": fornecedor_nome,
        "vendedor_nome": vendedor_nome,
    }


_PEDIDO_COLS = """
    p.id, p.id_grupo, p.numero, p.id_tenant_vendedor, p.id_tenant_fornecedor,
    p.origem, p.status, p.status_pagamento,
    p.cliente_nome, p.cliente_email, p.cliente_telefone, p.cliente_documento,
    p.entrega_cep, p.entrega_logradouro, p.entrega_numero, p.entrega_complemento,
    p.entrega_bairro, p.entrega_cidade, p.entrega_uf,
    p.subtotal_produtos, p.valor_taxa_pedido, p.valor_frete, p.valor_total,
    p.observacoes, p.confirmado_em, p.pago_em, p.criado_em, g.numero
"""


def listar_itens_pedido(cur, id_pedido: int) -> list[dict]:
    cur.execute(
        """
        SELECT id, id_variante, id_produto, sku, nome_produto, quantidade,
               valor_drop, preco_venda, subtotal_drop
        FROM tbl_pedido_item
        WHERE id_pedido = %s
        ORDER BY id
        """,
        (id_pedido,),
    )
    return [
        {
            "id": r[0],
            "id_variante": r[1],
            "id_produto": r[2],
            "sku": r[3] or "",
            "nome_produto": r[4],
            "quantidade": int(r[5]),
            "valor_drop": _float(r[6]),
            "preco_venda": _float(r[7]),
            "subtotal_drop": _float(r[8]),
        }
        for r in cur.fetchall()
    ]


def obter_pedido(cur, id_pedido: int, *, id_vendedor: int | None = None, id_fornecedor: int | None = None) -> dict | None:
    where = ["p.id = %s"]
    params: list[Any] = [id_pedido]
    if id_vendedor:
        where.append("p.id_tenant_vendedor = %s")
        params.append(id_vendedor)
    if id_fornecedor:
        where.append("p.id_tenant_fornecedor = %s")
        params.append(id_fornecedor)
    cur.execute(
        f"""
        SELECT {_PEDIDO_COLS},
               COALESCE(tf.nome_fantasia, tf.nome),
               COALESCE(tv.nome_fantasia, tv.nome)
        FROM tbl_pedido p
        LEFT JOIN tbl_pedido_grupo g ON g.id = p.id_grupo
        LEFT JOIN tbl_tenant tf ON tf.id = p.id_tenant_fornecedor
        LEFT JOIN tbl_tenant tv ON tv.id = p.id_tenant_vendedor
        WHERE {' AND '.join(where)}
        """,
        params,
    )
    row = cur.fetchone()
    if not row:
        return None
    ped = _pedido_dict(row[:28], fornecedor_nome=row[28], vendedor_nome=row[29])
    ped["itens"] = listar_itens_pedido(cur, id_pedido)
    return ped


def listar_pedidos_vendedor(cur, id_vendedor: int, status: str | None = None) -> list[dict]:
    where = ["p.id_tenant_vendedor = %s"]
    params: list[Any] = [id_vendedor]
    if status:
        where.append("p.status = %s")
        params.append(status)
    cur.execute(
        f"""
        SELECT {_PEDIDO_COLS},
               COALESCE(tf.nome_fantasia, tf.nome),
               NULL
        FROM tbl_pedido p
        LEFT JOIN tbl_pedido_grupo g ON g.id = p.id_grupo
        LEFT JOIN tbl_tenant tf ON tf.id = p.id_tenant_fornecedor
        WHERE {' AND '.join(where)}
        ORDER BY p.criado_em DESC, p.id DESC
        """,
        params,
    )
    return [_pedido_dict(r[:28], fornecedor_nome=r[28]) for r in cur.fetchall()]


def listar_pedidos_fornecedor(cur, id_fornecedor: int, status: str | None = None) -> list[dict]:
    where = ["p.id_tenant_fornecedor = %s", "p.status <> 'rascunho'"]
    params: list[Any] = [id_fornecedor]
    if status:
        where.append("p.status = %s")
        params.append(status)
    cur.execute(
        f"""
        SELECT {_PEDIDO_COLS},
               NULL,
               COALESCE(tv.nome_fantasia, tv.nome)
        FROM tbl_pedido p
        LEFT JOIN tbl_pedido_grupo g ON g.id = p.id_grupo
        LEFT JOIN tbl_tenant tv ON tv.id = p.id_tenant_vendedor
        WHERE {' AND '.join(where)}
        ORDER BY p.criado_em DESC, p.id DESC
        """,
        params,
    )
    return [_pedido_dict(r[:28], vendedor_nome=r[29]) for r in cur.fetchall()]


def buscar_produtos_pedido(cur, id_vendedor: int, termo: str = "", id_fornecedor: int | None = None) -> list[dict]:
    termo = (termo or "").strip()
    where = [
        "pv.id_tenant_vendedor = %s",
        "pv.ativo = TRUE",
        "v.ativo = TRUE",
        "p.ativo = TRUE",
    ]
    params: list[Any] = [id_vendedor]
    if id_fornecedor:
        where.append("pv.id_tenant_fornecedor = %s")
        params.append(id_fornecedor)
    if termo:
        where.append("(p.nome ILIKE %s OR v.sku ILIKE %s OR COALESCE(pv.nome_vitrine, '') ILIKE %s)")
        like = f"%{termo}%"
        params.extend([like, like, like])
    cur.execute(
        f"""
        SELECT pv.id_variante, pv.id_produto, pv.id_tenant_fornecedor,
               COALESCE(pv.nome_vitrine, p.nome), v.sku,
               pv.preco_fornecedor, pv.preco_venda,
               COALESCE(tf.nome_fantasia, tf.nome),
               GREATEST(0, COALESCE(ve.quantidade, 0) - COALESCE(ve.reservado, 0))
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        JOIN tbl_tenant tf ON tf.id = pv.id_tenant_fornecedor
        LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = v.id
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(pv.nome_vitrine, p.nome), v.sku
        LIMIT 40
        """,
        params,
    )
    return [
        {
            "id_variante": r[0],
            "id_produto": r[1],
            "id_fornecedor": r[2],
            "nome": r[3],
            "sku": r[4] or "",
            "valor_drop": _float(r[5]),
            "preco_venda": _float(r[6]),
            "fornecedor_nome": r[7],
            "estoque_disponivel": int(r[8] or 0),
        }
        for r in cur.fetchall()
    ]


def listar_fornecedores_pedido(cur, id_vendedor: int) -> list[dict]:
    cur.execute(
        """
        SELECT DISTINCT t.id, COALESCE(t.nome_fantasia, t.nome)
        FROM tbl_vinculo_vendedor_fornecedor v
        JOIN tbl_tenant t ON t.id = v.id_tenant_fornecedor
        WHERE v.id_tenant_vendedor = %s AND v.status = 'ativo'
        ORDER BY 2
        """,
        (id_vendedor,),
    )
    return [{"id": r[0], "nome": r[1]} for r in cur.fetchall()]


def taxas_fornecedores_vendedor(cur, id_vendedor: int) -> dict[int, float]:
    out: dict[int, float] = {}
    for f in listar_fornecedores_pedido(cur, id_vendedor):
        out[int(f["id"])] = _taxa_pedido_fornecedor(cur, int(f["id"]))
    return out


def _parse_cliente_entrega(body: dict) -> dict:
    c = body.get("cliente") or body
    e = body.get("entrega") or body
    return {
        "cliente_nome": (c.get("nome") or body.get("cliente_nome") or "").strip(),
        "cliente_email": (c.get("email") or body.get("cliente_email") or "").strip() or None,
        "cliente_telefone": (c.get("telefone") or body.get("cliente_telefone") or "").strip() or None,
        "cliente_documento": (c.get("documento") or body.get("cliente_documento") or "").strip() or None,
        "entrega_cep": (e.get("cep") or body.get("entrega_cep") or "").strip() or None,
        "entrega_logradouro": (e.get("logradouro") or body.get("entrega_logradouro") or "").strip() or None,
        "entrega_numero": (e.get("numero") or body.get("entrega_numero") or "").strip() or None,
        "entrega_complemento": (e.get("complemento") or body.get("entrega_complemento") or "").strip() or None,
        "entrega_bairro": (e.get("bairro") or body.get("entrega_bairro") or "").strip() or None,
        "entrega_cidade": (e.get("cidade") or body.get("entrega_cidade") or "").strip() or None,
        "entrega_uf": ((e.get("uf") or body.get("entrega_uf") or "").strip() or None),
        "observacoes": (body.get("observacoes") or "").strip() or None,
    }


def salvar_rascunho(
    cur,
    id_vendedor: int,
    body: dict,
    id_usuario: int | None = None,
) -> dict:
    dados_cli = _parse_cliente_entrega(body)
    if not dados_cli["cliente_nome"]:
        raise ValueError("Informe o nome do cliente.")

    itens_raw = body.get("itens") or []
    if not itens_raw:
        raise ValueError("Adicione ao menos um produto ao pedido.")

    por_fornecedor: dict[int, list[dict]] = {}
    for raw in itens_raw:
        try:
            id_var = int(raw.get("id_variante"))
            qtd = int(raw.get("quantidade") or 0)
        except (TypeError, ValueError):
            raise ValueError("Item de produto inválido.")
        if qtd <= 0:
            raise ValueError("Quantidade deve ser maior que zero.")
        vit = _buscar_item_vitrine(cur, id_vendedor, id_var)
        if not vit:
            raise ValueError(f"Produto variante {id_var} não está ativo em Meus produtos.")
        id_forn = vit["id_fornecedor"]
        if not vinculo_ativo(cur, id_vendedor, id_forn):
            raise ValueError("Fornecedor não está com vínculo ativo.")
        por_fornecedor.setdefault(id_forn, []).append({**vit, "id_variante": id_var, "quantidade": qtd})

    id_grupo = body.get("id_grupo")
    if id_grupo:
        cur.execute(
            "SELECT id FROM tbl_pedido_grupo WHERE id = %s AND id_tenant_vendedor = %s",
            (int(id_grupo), id_vendedor),
        )
        if not cur.fetchone():
            raise ValueError("Grupo de pedido não encontrado.")
    else:
        numero_grupo = _gerar_numero(cur, "GRP", id_vendedor, "tbl_pedido_grupo", "id_tenant_vendedor")
        cur.execute(
            "INSERT INTO tbl_pedido_grupo (id_tenant_vendedor, numero) VALUES (%s, %s) RETURNING id",
            (id_vendedor, numero_grupo),
        )
        id_grupo = int(cur.fetchone()[0])

    ids_fornecedores_ativos = set(por_fornecedor.keys())
    cur.execute(
        """
        SELECT id, id_tenant_fornecedor, status FROM tbl_pedido
        WHERE id_grupo = %s AND id_tenant_vendedor = %s
        """,
        (id_grupo, id_vendedor),
    )
    existentes = cur.fetchall()
    for pid, id_forn, st in existentes:
        if int(id_forn) not in ids_fornecedores_ativos and st == STATUS_RASCUNHO:
            cur.execute("DELETE FROM tbl_pedido WHERE id = %s", (pid,))
        elif int(id_forn) not in ids_fornecedores_ativos:
            raise ValueError("Não é possível remover fornecedor de pedido já confirmado.")

    pedidos_ids: list[int] = []
    for id_forn, itens in por_fornecedor.items():
        subtotal = sum(i["valor_drop"] * i["quantidade"] for i in itens)
        taxa = _taxa_pedido_fornecedor(cur, id_forn)
        total = subtotal + taxa

        cur.execute(
            """
            SELECT id FROM tbl_pedido
            WHERE id_grupo = %s AND id_tenant_fornecedor = %s AND id_tenant_vendedor = %s
            """,
            (id_grupo, id_forn, id_vendedor),
        )
        row_ped = cur.fetchone()
        if row_ped:
            id_pedido = int(row_ped[0])
            cur.execute(
                "SELECT status FROM tbl_pedido WHERE id = %s",
                (id_pedido,),
            )
            if cur.fetchone()[0] != STATUS_RASCUNHO:
                raise ValueError("Pedido já confirmado não pode ser editado.")
            cur.execute(
                """
                UPDATE tbl_pedido SET
                    cliente_nome = %s, cliente_email = %s, cliente_telefone = %s, cliente_documento = %s,
                    entrega_cep = %s, entrega_logradouro = %s, entrega_numero = %s, entrega_complemento = %s,
                    entrega_bairro = %s, entrega_cidade = %s, entrega_uf = %s,
                    subtotal_produtos = %s, valor_taxa_pedido = %s, valor_total = %s,
                    observacoes = %s, atualizado_em = %s
                WHERE id = %s
                """,
                (
                    dados_cli["cliente_nome"],
                    dados_cli["cliente_email"],
                    dados_cli["cliente_telefone"],
                    dados_cli["cliente_documento"],
                    dados_cli["entrega_cep"],
                    dados_cli["entrega_logradouro"],
                    dados_cli["entrega_numero"],
                    dados_cli["entrega_complemento"],
                    dados_cli["entrega_bairro"],
                    dados_cli["entrega_cidade"],
                    dados_cli["entrega_uf"],
                    subtotal,
                    taxa,
                    total,
                    dados_cli["observacoes"],
                    agora_utc(),
                    id_pedido,
                ),
            )
            cur.execute("DELETE FROM tbl_pedido_item WHERE id_pedido = %s", (id_pedido,))
        else:
            numero = _gerar_numero(cur, "PED", id_vendedor, "tbl_pedido", "id_tenant_vendedor")
            cur.execute(
                """
                INSERT INTO tbl_pedido (
                    id_grupo, numero, id_tenant_vendedor, id_tenant_fornecedor,
                    cliente_nome, cliente_email, cliente_telefone, cliente_documento,
                    entrega_cep, entrega_logradouro, entrega_numero, entrega_complemento,
                    entrega_bairro, entrega_cidade, entrega_uf,
                    subtotal_produtos, valor_taxa_pedido, valor_total, observacoes
                ) VALUES (
                    %s, %s, %s, %s,
                    %s, %s, %s, %s,
                    %s, %s, %s, %s, %s, %s, %s,
                    %s, %s, %s, %s
                ) RETURNING id
                """,
                (
                    id_grupo,
                    numero,
                    id_vendedor,
                    id_forn,
                    dados_cli["cliente_nome"],
                    dados_cli["cliente_email"],
                    dados_cli["cliente_telefone"],
                    dados_cli["cliente_documento"],
                    dados_cli["entrega_cep"],
                    dados_cli["entrega_logradouro"],
                    dados_cli["entrega_numero"],
                    dados_cli["entrega_complemento"],
                    dados_cli["entrega_bairro"],
                    dados_cli["entrega_cidade"],
                    dados_cli["entrega_uf"],
                    subtotal,
                    taxa,
                    total,
                    dados_cli["observacoes"],
                ),
            )
            id_pedido = int(cur.fetchone()[0])
            registrar_historico(cur, id_pedido, "criado", "Pedido criado em rascunho.", id_usuario)

        for item in itens:
            sub = item["valor_drop"] * item["quantidade"]
            cur.execute(
                """
                INSERT INTO tbl_pedido_item (
                    id_pedido, id_variante, id_produto, id_produto_vendedor,
                    sku, nome_produto, quantidade, valor_drop, preco_venda, subtotal_drop,
                    id_deposito_fornecedor
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    id_pedido,
                    item["id_variante"],
                    item["id_produto"],
                    item["id_produto_vendedor"],
                    item["sku"],
                    item["nome"],
                    item["quantidade"],
                    item["valor_drop"],
                    item["preco_venda"],
                    sub,
                    item["id_deposito"],
                ),
            )
        pedidos_ids.append(id_pedido)

    cur.execute("SELECT numero FROM tbl_pedido_grupo WHERE id = %s", (id_grupo,))
    num_grupo = cur.fetchone()[0]
    return {"id_grupo": id_grupo, "numero_grupo": num_grupo, "pedidos_ids": pedidos_ids}


def confirmar_grupo(cur, id_vendedor: int, id_grupo: int, id_usuario: int | None = None) -> list[int]:
    cur.execute(
        """
        SELECT id FROM tbl_pedido
        WHERE id_grupo = %s AND id_tenant_vendedor = %s AND status = %s
        """,
        (id_grupo, id_vendedor, STATUS_RASCUNHO),
    )
    ids = [int(r[0]) for r in cur.fetchall()]
    if not ids:
        raise ValueError("Nenhum pedido em rascunho para confirmar.")
    for id_pedido in ids:
        confirmar_pedido(cur, id_vendedor, id_pedido, id_usuario=id_usuario)
    return ids


def confirmar_pedido(cur, id_vendedor: int, id_pedido: int, id_usuario: int | None = None) -> None:
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped["status"] != STATUS_RASCUNHO:
        raise ValueError("Somente pedidos em rascunho podem ser confirmados.")
    if not ped["itens"]:
        raise ValueError("Pedido sem itens.")

    itens_reserva = [(i["id_variante"], i["quantidade"]) for i in ped["itens"]]
    reservar_itens_pedido(cur, itens_reserva)

    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_pedido SET
            status = %s,
            status_pagamento = 'pendente',
            confirmado_em = %s,
            atualizado_em = %s
        WHERE id = %s
        """,
        (STATUS_AGUARDANDO, agora, agora, id_pedido),
    )
    registrar_historico(
        cur,
        id_pedido,
        "confirmado",
        "Pedido confirmado; estoque reservado. Aguardando pagamento.",
        id_usuario,
    )


def cancelar_pedido(
    cur,
    id_pedido: int,
    *,
    id_vendedor: int | None = None,
    id_fornecedor: int | None = None,
    id_usuario: int | None = None,
    motivo: str | None = None,
) -> None:
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor, id_fornecedor=id_fornecedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped["status"] == STATUS_CANCELADO:
        return
    if ped["status"] == STATUS_PAGO:
        raise ValueError("Pedido pago não pode ser cancelado por aqui.")

    if ped["status"] in (STATUS_AGUARDANDO,):
        itens = [(i["id_variante"], i["quantidade"]) for i in ped["itens"]]
        liberar_itens_pedido(cur, itens)

    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_pedido SET
            status = %s,
            status_pagamento = 'cancelado',
            cancelado_em = %s,
            atualizado_em = %s
        WHERE id = %s
        """,
        (STATUS_CANCELADO, agora, agora, id_pedido),
    )
    registrar_historico(cur, id_pedido, "cancelado", motivo or "Pedido cancelado.", id_usuario)


def marcar_pedido_pago(
    cur,
    id_pedido: int,
    *,
    id_usuario: int | None = None,
    mp_payment_id: int | None = None,
    mp_status: str | None = None,
    detalhe: str | None = None,
) -> bool:
    """Marca pedido como pago. Retorna False se já estava pago."""
    cur.execute(
        "SELECT status, status_pagamento FROM tbl_pedido WHERE id = %s",
        (id_pedido,),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Pedido não encontrado.")
    if row[0] == STATUS_PAGO:
        return False
    if row[0] != STATUS_AGUARDANDO:
        raise ValueError("Somente pedidos aguardando pagamento podem ser marcados como pagos.")

    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_pedido SET
            status = %s,
            status_pagamento = 'pago',
            pago_em = %s,
            mp_payment_id = COALESCE(%s, mp_payment_id),
            mp_payment_status = COALESCE(%s, mp_payment_status),
            atualizado_em = %s
        WHERE id = %s
        """,
        (STATUS_PAGO, agora, mp_payment_id, mp_status, agora, id_pedido),
    )
    registrar_historico(
        cur,
        id_pedido,
        "pago",
        detalhe or "Pagamento confirmado via Mercado Pago.",
        id_usuario,
    )
    return True
