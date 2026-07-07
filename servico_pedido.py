# servico_pedido.py — pedidos B2B vendedor → fornecedor (Fase 0)
from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from fornecedor.requisitos_vendedor import carregar_requisitos_raw
from global_utils import agora_utc
from servico_estoque_reserva import (
    baixar_itens_pedido,
    liberar_itens_pedido,
    reservar_itens_pedido,
)

STATUS_RASCUNHO = "rascunho"
STATUS_AGUARDANDO = "aguardando_pagamento"
STATUS_PAGO = "pago"
STATUS_EM_EXPEDICAO = "em_expedicao"
STATUS_ENTREGUE = "entregue"
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

_COLUNAS_EXPEDICAO_OK: bool | None = None


def _pedido_tem_colunas_expedicao(cur) -> bool:
    global _COLUNAS_EXPEDICAO_OK
    if _COLUNAS_EXPEDICAO_OK is not None:
        return _COLUNAS_EXPEDICAO_OK
    cur.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = 'tbl_pedido'
          AND column_name = 'id_bling_pedido'
        LIMIT 1
        """
    )
    _COLUNAS_EXPEDICAO_OK = cur.fetchone() is not None
    return _COLUNAS_EXPEDICAO_OK


def _enriquecer_pedido_expedicao(cur, id_pedido: int, ped: dict) -> None:
    ped.setdefault("origem", "manual")
    ped.setdefault("id_bling_pedido", None)
    ped.setdefault("codigo_rastreio", "")
    ped.setdefault("transportadora", "")
    ped.setdefault("expedido_em", None)
    ped.setdefault("entregue_em", None)
    if not _pedido_tem_colunas_expedicao(cur):
        return
    cur.execute(
        """
        SELECT id_bling_pedido, codigo_rastreio, transportadora,
               expedido_em, entregue_em
        FROM tbl_pedido WHERE id = %s
        """,
        (id_pedido,),
    )
    ex = cur.fetchone()
    if not ex:
        return
    ped["id_bling_pedido"] = ex[0]
    ped["codigo_rastreio"] = ex[1] or ""
    ped["transportadora"] = ex[2] or ""
    ped["expedido_em"] = ex[3].isoformat() if ex[3] else None
    ped["entregue_em"] = ex[4].isoformat() if ex[4] else None


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
    _enriquecer_pedido_expedicao(cur, id_pedido, ped)
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


def _parse_atributos_variante(raw) -> dict[str, str]:
    if isinstance(raw, dict):
        data = raw
    elif raw:
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except (TypeError, ValueError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
    else:
        return {}
    out: dict[str, str] = {}
    for chave, valor in data.items():
        nome = str(chave or "").strip()
        val = str(valor or "").strip()
        if nome and val:
            out[nome] = val
    return out


def _rotulo_variacao(formato: str, nome_exibicao: str, atributos: dict[str, str]) -> str:
    if atributos:
        return ", ".join(f"{k}: {v}" for k, v in atributos.items())
    if (formato or "S") == "E" and nome_exibicao and nome_exibicao.strip().lower() not in ("padrão", "padrao", ""):
        return nome_exibicao.strip()
    return ""


def _fmt_moeda_br(valor: float) -> str:
    return f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def combobox_produtos_pedido(
    cur,
    id_vendedor: int,
    termo: str = "",
    *,
    limite: int = 20,
    id_fornecedor: int | None = None,
) -> list[dict]:
    """Variantes vendáveis (filhos) em Meus produtos — formato ComboBusca."""
    termo = (termo or "").strip()
    if len(termo) < 3:
        return []

    where = [
        "pv.id_tenant_vendedor = %s",
        "pv.ativo = TRUE",
        "v.ativo = TRUE",
        "p.ativo = TRUE",
        # Somente filhos vendáveis: simples (S) ou variações (E), nunca o pai placeholder
        """(
            p.formato = 'S'
            OR (
                p.formato = 'E'
                AND NOT (
                    v.id = p.id_variante_padrao
                    AND EXISTS (
                        SELECT 1 FROM tbl_produto_variante v2
                        WHERE v2.id_produto = p.id AND v2.ativo AND v2.id <> v.id
                    )
                )
            )
        )""",
    ]
    params: list[Any] = [id_vendedor]
    if id_fornecedor:
        where.append("pv.id_tenant_fornecedor = %s")
        params.append(id_fornecedor)
    where.append("(p.nome ILIKE %s OR v.sku ILIKE %s OR COALESCE(pv.nome_vitrine, '') ILIKE %s OR v.nome_exibicao ILIKE %s)")
    like = f"%{termo}%"
    params.extend([like, like, like, like])

    cur.execute(
        f"""
        SELECT pv.id_variante, pv.id_produto, pv.id_tenant_fornecedor,
               COALESCE(NULLIF(TRIM(pv.nome_vitrine), ''), p.nome),
               v.sku, v.nome_exibicao, v.atributos, p.formato,
               pv.preco_fornecedor, pv.preco_venda,
               COALESCE(tf.nome_fantasia, tf.nome),
               GREATEST(0, COALESCE(ve.quantidade, 0) - COALESCE(ve.reservado, 0))
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        JOIN tbl_tenant tf ON tf.id = pv.id_tenant_fornecedor
        LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = v.id
        WHERE {' AND '.join(where)}
        ORDER BY COALESCE(pv.nome_vitrine, p.nome), v.nome_exibicao, v.sku
        LIMIT %s
        """,
        params + [limite],
    )

    out: list[dict] = []
    for r in cur.fetchall():
        atributos = _parse_atributos_variante(r[6])
        formato = r[7] or "S"
        preco_venda = _float(r[9])
        out.append(
            {
                "id": r[0],
                "id_variante": r[0],
                "id_produto": r[1],
                "id_fornecedor": r[2],
                "nome": r[3] or "",
                "variacao": _rotulo_variacao(formato, r[5] or "", atributos),
                "sku": r[4] or "",
                "preco_venda": preco_venda,
                "preco_venda_label": _fmt_moeda_br(preco_venda),
                "valor_drop": _float(r[8]),
                "fornecedor_nome": r[10] or "",
                "estoque_disponivel": int(r[11] or 0),
            }
        )
    return out


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
            try:
                from servico_melhor_envio import limpar_frete_pedido

                limpar_frete_pedido(cur, id_pedido)
            except Exception:
                pass
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


def _pedido_ja_importado_bling(
    cur, id_vendedor: int, id_bling: str, id_fornecedor: int
) -> int | None:
    cur.execute(
        """
        SELECT id FROM tbl_pedido
        WHERE id_tenant_vendedor = %s AND id_bling_pedido = %s
          AND id_tenant_fornecedor = %s
        LIMIT 1
        """,
        (id_vendedor, id_bling, id_fornecedor),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def importar_pedido_bling(
    cur,
    id_vendedor: int,
    id_bling_pedido: str,
    dados: dict,
    *,
    id_usuario: int | None = None,
) -> list[int]:
    """Cria pedido(s) a partir do Bling (já pago). Retorna IDs criados."""
    itens_parsed = dados.get("itens") or []
    if not itens_parsed:
        raise ValueError("Pedido Bling sem itens.")

    por_fornecedor: dict[int, list[dict]] = {}
    for raw in itens_parsed:
        sku = (raw.get("sku") or "").strip()
        qtd = int(raw.get("quantidade") or 0)
        cur.execute(
            """
            SELECT pv.id, pv.id_tenant_fornecedor, pv.id_produto, pv.id_variante,
                   pv.preco_fornecedor, pv.preco_venda,
                   COALESCE(pv.nome_vitrine, p.nome), v.sku, p.id_deposito_expedicao
            FROM tbl_produto_vendedor pv
            JOIN tbl_produto_variante v ON v.id = pv.id_variante
            JOIN tbl_produto p ON p.id = pv.id_produto
            WHERE pv.id_tenant_vendedor = %s AND v.sku = %s AND pv.ativo = TRUE
              AND v.ativo = TRUE AND p.ativo = TRUE
            LIMIT 1
            """,
            (id_vendedor, sku),
        )
        vit = cur.fetchone()
        if not vit:
            raise ValueError(f"SKU {sku} não encontrado em Meus produtos.")
        id_forn = int(vit[1])
        if not vinculo_ativo(cur, id_vendedor, id_forn):
            raise ValueError(f"Fornecedor do SKU {sku} sem vínculo ativo.")
        por_fornecedor.setdefault(id_forn, []).append(
            {
                "id_produto_vendedor": vit[0],
                "id_fornecedor": id_forn,
                "id_produto": int(vit[2]),
                "id_variante": int(vit[3]),
                "valor_drop": _float(vit[4]),
                "preco_venda": _float(vit[5]),
                "nome": vit[6] or raw.get("nome") or sku,
                "sku": vit[7] or sku,
                "id_deposito": vit[8],
                "quantidade": qtd,
            }
        )

    cliente = dados.get("cliente") or {}
    entrega = dados.get("entrega") or {}
    obs_base = dados.get("observacoes") or ""
    numero_bling = dados.get("numero_bling") or id_bling_pedido
    ids_criados: list[int] = []

    for id_forn, itens in por_fornecedor.items():
        existente = _pedido_ja_importado_bling(cur, id_vendedor, id_bling_pedido, id_forn)
        if existente:
            continue

        subtotal = sum(i["valor_drop"] * i["quantidade"] for i in itens)
        taxa = _taxa_pedido_fornecedor(cur, id_forn)
        total = subtotal + taxa
        agora = agora_utc()
        numero = _gerar_numero(cur, "PED", id_vendedor, "tbl_pedido", "id_tenant_vendedor")
        obs = obs_base
        if numero_bling:
            prefix = f"Importado do Bling #{numero_bling}."
            obs = f"{prefix} {obs}".strip() if obs else prefix

        cur.execute(
            """
            INSERT INTO tbl_pedido (
                numero, id_tenant_vendedor, id_tenant_fornecedor, origem,
                status, status_pagamento,
                cliente_nome, cliente_email, cliente_telefone, cliente_documento,
                entrega_cep, entrega_logradouro, entrega_numero, entrega_complemento,
                entrega_bairro, entrega_cidade, entrega_uf,
                subtotal_produtos, valor_taxa_pedido, valor_frete, valor_total,
                observacoes, confirmado_em, pago_em, id_bling_pedido
            ) VALUES (
                %s, %s, %s, 'bling',
                %s, 'pago',
                %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s,
                %s, %s, %s, %s
            ) RETURNING id
            """,
            (
                numero,
                id_vendedor,
                id_forn,
                STATUS_PAGO,
                cliente.get("nome") or "Cliente Bling",
                cliente.get("email"),
                cliente.get("telefone"),
                cliente.get("documento"),
                entrega.get("cep"),
                entrega.get("logradouro"),
                entrega.get("numero"),
                entrega.get("complemento"),
                entrega.get("bairro"),
                entrega.get("cidade"),
                entrega.get("uf"),
                subtotal,
                taxa,
                _float(dados.get("valor_frete")),
                total,
                obs,
                agora,
                agora,
                id_bling_pedido,
            ),
        )
        id_pedido = int(cur.fetchone()[0])

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

        itens_reserva = [(i["id_variante"], i["quantidade"]) for i in itens]
        reservar_itens_pedido(cur, itens_reserva)

        cur.execute(
            """
            INSERT INTO tbl_integracao_map (
                id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta
            ) VALUES (%s, 'bling', 'vendedor', 'pedido', %s, %s, NULL, %s::jsonb)
            ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling)
            DO UPDATE SET id_dropnexo = EXCLUDED.id_dropnexo, atualizado_em = NOW()
            """,
            (
                id_vendedor,
                f"{id_bling_pedido}:{id_forn}",
                id_pedido,
                json.dumps({"numero_bling": numero_bling, "id_bling_pedido": id_bling_pedido}, ensure_ascii=False),
            ),
        )

        registrar_historico(
            cur,
            id_pedido,
            "importado_bling",
            f"Pedido importado do Bling (#{numero_bling}). Estoque reservado.",
            id_usuario,
        )
        ids_criados.append(id_pedido)

    return ids_criados


def marcar_em_expedicao(
    cur,
    id_pedido: int,
    *,
    id_fornecedor: int,
    codigo_rastreio: str | None = None,
    transportadora: str | None = None,
    id_usuario: int | None = None,
) -> None:
    ped = obter_pedido(cur, id_pedido, id_fornecedor=id_fornecedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped["status"] != STATUS_PAGO:
        raise ValueError("Somente pedidos pagos podem ser expedidos.")

    itens_baixa: list[tuple[int, int, int | None]] = []
    for item in ped["itens"]:
        id_dep = None
        cur.execute(
            """
            SELECT id_deposito_fornecedor FROM tbl_pedido_item
            WHERE id_pedido = %s AND id_variante = %s LIMIT 1
            """,
            (id_pedido, item["id_variante"]),
        )
        dep_row = cur.fetchone()
        if dep_row and dep_row[0]:
            id_dep = int(dep_row[0])
        itens_baixa.append((item["id_variante"], item["quantidade"], id_dep))

    baixar_itens_pedido(cur, itens_baixa)

    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_pedido SET
            status = %s,
            codigo_rastreio = COALESCE(%s, codigo_rastreio),
            transportadora = COALESCE(%s, transportadora),
            expedido_em = %s,
            atualizado_em = %s
        WHERE id = %s
        """,
        (
            STATUS_EM_EXPEDICAO,
            (codigo_rastreio or "").strip() or None,
            (transportadora or "").strip() or None,
            agora,
            agora,
            id_pedido,
        ),
    )
    det = "Pedido em expedição."
    if codigo_rastreio:
        det += f" Rastreio: {codigo_rastreio}."
    registrar_historico(cur, id_pedido, "expedido", det, id_usuario)


def marcar_entregue(
    cur,
    id_pedido: int,
    *,
    id_fornecedor: int | None = None,
    id_vendedor: int | None = None,
    id_usuario: int | None = None,
) -> None:
    ped = obter_pedido(cur, id_pedido, id_fornecedor=id_fornecedor, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped["status"] not in (STATUS_EM_EXPEDICAO, STATUS_PAGO):
        raise ValueError("Pedido deve estar pago ou em expedição.")

    if ped["status"] == STATUS_PAGO:
        marcar_em_expedicao(
            cur,
            id_pedido,
            id_fornecedor=id_fornecedor or ped["id_tenant_fornecedor"],
            id_usuario=id_usuario,
        )

    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_pedido SET
            status = %s,
            entregue_em = %s,
            expedido_em = COALESCE(expedido_em, %s),
            atualizado_em = %s
        WHERE id = %s
        """,
        (STATUS_ENTREGUE, agora, agora, agora, id_pedido),
    )
    registrar_historico(cur, id_pedido, "entregue", "Pedido marcado como entregue.", id_usuario)


def listar_pedidos_expedicao_vendedor(cur, id_vendedor: int) -> list[dict]:
    cur.execute(
        f"""
        SELECT {_PEDIDO_COLS},
               COALESCE(tf.nome_fantasia, tf.nome),
               NULL
        FROM tbl_pedido p
        LEFT JOIN tbl_pedido_grupo g ON g.id = p.id_grupo
        LEFT JOIN tbl_tenant tf ON tf.id = p.id_tenant_fornecedor
        WHERE p.id_tenant_vendedor = %s
          AND p.status IN (%s, %s, %s)
        ORDER BY COALESCE(p.expedido_em, p.pago_em, p.criado_em) DESC, p.id DESC
        """,
        (id_vendedor, STATUS_PAGO, STATUS_EM_EXPEDICAO, STATUS_ENTREGUE),
    )
    rows = cur.fetchall()
    out = []
    for r in rows:
        ped = _pedido_dict(r[:28], fornecedor_nome=r[28])
        cur.execute(
            """
            SELECT codigo_rastreio, transportadora, expedido_em, entregue_em, origem
            FROM tbl_pedido WHERE id = %s
            """,
            (ped["id"],),
        )
        ex = cur.fetchone()
        if ex:
            ped["codigo_rastreio"] = ex[0] or ""
            ped["transportadora"] = ex[1] or ""
            ped["expedido_em"] = ex[2].isoformat() if ex[2] else None
            ped["entregue_em"] = ex[3].isoformat() if ex[3] else None
            ped["origem"] = ex[4] or "manual"
        out.append(ped)
    return out


def obter_grupo_pedido(cur, id_vendedor: int, id_grupo: int) -> dict | None:
    cur.execute(
        "SELECT id, numero FROM tbl_pedido_grupo WHERE id = %s AND id_tenant_vendedor = %s",
        (id_grupo, id_vendedor),
    )
    row_grupo = cur.fetchone()
    if not row_grupo:
        return None

    cur.execute(
        """
        SELECT p.id, p.status, p.status_pagamento, p.meio_pagamento, p.origem, p.valor_total,
               p.id_tenant_fornecedor, COALESCE(tf.nome_fantasia, tf.nome), p.numero, p.pago_em,
               p.pix_manual_payload, p.pix_manual_txid
        FROM tbl_pedido p
        LEFT JOIN tbl_tenant tf ON tf.id = p.id_tenant_fornecedor
        WHERE p.id_grupo = %s AND p.id_tenant_vendedor = %s
        ORDER BY p.id
        """,
        (id_grupo, id_vendedor),
    )
    pedidos_rows = cur.fetchall()
    if not pedidos_rows:
        return None

    ref = obter_pedido(cur, int(pedidos_rows[0][0]), id_vendedor=id_vendedor)
    if not ref:
        return None

    itens: list[dict] = []
    pedidos: list[dict] = []
    for pid, status, status_pag, meio_pag, origem, valor_total, id_forn, forn_nome, numero, pago_em, pix_payload, pix_txid in pedidos_rows:
        frete_info = {}
        try:
            from servico_melhor_envio import frete_resumo_pedido

            frete_info = frete_resumo_pedido(cur, int(pid))
        except Exception:
            frete_info = {}
        pedidos.append(
            {
                "id": int(pid),
                "numero": numero,
                "status": status,
                "status_pagamento": status_pag or "",
                "meio_pagamento": meio_pag or "",
                "origem": origem or "manual",
                "valor_total": _float(valor_total),
                "id_fornecedor": int(id_forn),
                "fornecedor_nome": forn_nome or "",
                "pago_em": pago_em.isoformat() if pago_em else None,
                "pix_manual_payload": pix_payload or "",
                "pix_manual_txid": pix_txid or "",
                **frete_info,
            }
        )
        for item in listar_itens_pedido(cur, int(pid)):
            itens.append(
                {
                    "id_variante": item["id_variante"],
                    "id_fornecedor": int(id_forn),
                    "fornecedor_nome": forn_nome or "",
                    "nome": item["nome_produto"],
                    "sku": item["sku"],
                    "valor_drop": item["valor_drop"],
                    "quantidade": item["quantidade"],
                }
            )

    statuses = {p["status"] for p in pedidos}
    editavel = statuses == {STATUS_RASCUNHO}
    bloqueado_total = any(
        (p.get("origem") or "manual") != "manual"
        or p["status"] in (STATUS_PAGO, STATUS_EM_EXPEDICAO, STATUS_ENTREGUE, STATUS_CANCELADO)
        for p in pedidos
    )

    return {
        "id_grupo": int(id_grupo),
        "numero_grupo": row_grupo[1],
        "editavel": editavel,
        "bloqueado_total": bloqueado_total,
        "status": next(iter(statuses)) if len(statuses) == 1 else "misto",
        "cliente": {
            "nome": ref["cliente_nome"],
            "documento": ref["cliente_documento"],
            "email": ref["cliente_email"],
            "telefone": ref["cliente_telefone"],
        },
        "entrega": {
            "cep": ref["entrega_cep"],
            "logradouro": ref["entrega_logradouro"],
            "numero": ref["entrega_numero"],
            "complemento": ref["entrega_complemento"],
            "bairro": ref["entrega_bairro"],
            "cidade": ref["entrega_cidade"],
            "uf": ref["entrega_uf"],
        },
        "itens": itens,
        "pedidos": pedidos,
    }


_TABELA_ANEXO_OK: bool | None = None


def _tem_tabela_anexo(cur) -> bool:
    global _TABELA_ANEXO_OK
    if _TABELA_ANEXO_OK is not None:
        return _TABELA_ANEXO_OK
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'tbl_pedido_anexo'
        LIMIT 1
        """
    )
    _TABELA_ANEXO_OK = cur.fetchone() is not None
    return _TABELA_ANEXO_OK


def listar_anexos_pedido(
    cur,
    id_pedido: int,
    *,
    id_vendedor: int | None = None,
    id_fornecedor: int | None = None,
) -> list[dict]:
    if not _tem_tabela_anexo(cur):
        return []
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor, id_fornecedor=id_fornecedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    cur.execute(
        """
        SELECT id, tipo, nome_original, caminho, tamanho_bytes, criado_em
        FROM tbl_pedido_anexo
        WHERE id_pedido = %s
        ORDER BY tipo, criado_em DESC, id DESC
        """,
        (id_pedido,),
    )
    return [
        {
            "id": r[0],
            "tipo": r[1],
            "nome_original": r[2],
            "caminho": r[3],
            "tamanho_bytes": int(r[4] or 0),
            "criado_em": r[5].isoformat() if r[5] else None,
        }
        for r in cur.fetchall()
    ]


def registrar_anexo_pedido(
    cur,
    id_vendedor: int,
    id_pedido: int,
    tipo: str,
    nome_original: str,
    caminho: str,
    tamanho_bytes: int,
    id_usuario: int | None = None,
) -> dict:
    if not _tem_tabela_anexo(cur):
        raise ValueError("Anexos ainda não disponíveis. Execute a migração SQL 063_pedido_anexo.")
    tipo = (tipo or "").strip().lower()
    if tipo not in ("nf", "etiqueta", "comprovante_pix"):
        raise ValueError("Tipo de anexo inválido.")
    ped = obter_pedido(cur, id_pedido, id_vendedor=id_vendedor)
    if not ped:
        raise ValueError("Pedido não encontrado.")
    if ped["status"] == STATUS_CANCELADO:
        raise ValueError("Pedido cancelado não aceita anexos.")
    cur.execute(
        """
        INSERT INTO tbl_pedido_anexo (id_pedido, tipo, nome_original, caminho, tamanho_bytes, id_usuario)
        VALUES (%s, %s, %s, %s, %s, %s)
        RETURNING id, tipo, nome_original, caminho, tamanho_bytes, criado_em
        """,
        (id_pedido, tipo, nome_original, caminho, tamanho_bytes, id_usuario),
    )
    row = cur.fetchone()
    return {
        "id": row[0],
        "tipo": row[1],
        "nome_original": row[2],
        "caminho": row[3],
        "tamanho_bytes": int(row[4] or 0),
        "criado_em": row[5].isoformat() if row[5] else None,
    }


def excluir_anexo_pedido(cur, id_vendedor: int, id_anexo: int) -> dict:
    if not _tem_tabela_anexo(cur):
        raise ValueError("Anexos ainda não disponíveis.")
    cur.execute(
        """
        SELECT a.id, a.id_pedido, a.caminho
        FROM tbl_pedido_anexo a
        JOIN tbl_pedido p ON p.id = a.id_pedido
        WHERE a.id = %s AND p.id_tenant_vendedor = %s
        """,
        (id_anexo, id_vendedor),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Anexo não encontrado.")
    cur.execute("DELETE FROM tbl_pedido_anexo WHERE id = %s", (id_anexo,))
    return {"id": row[0], "id_pedido": row[1], "caminho": row[2]}
