# sistema/dashboard/servico_dashboard_fornecedor.py — painel operacional do fornecedor
from __future__ import annotations

from core.pedidos.servico import col_status_vendedor


def _fmt_brl(v) -> str:
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        n = 0.0
    return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _mes_rotulo(ym: str) -> str:
    """'2026-03' → 'mar/26'."""
    meses = (
        "jan",
        "fev",
        "mar",
        "abr",
        "mai",
        "jun",
        "jul",
        "ago",
        "set",
        "out",
        "nov",
        "dez",
    )
    try:
        y, m = ym.split("-")
        return f"{meses[int(m) - 1]}/{y[-2:]}"
    except Exception:
        return ym


def montar_dashboard_fornecedor(cur, id_fornecedor: int) -> dict:
    cv = col_status_vendedor(cur)
    excluidos = f"COALESCE({cv}, '') NOT IN ('rascunho', 'importado', 'cancelado')"

    # Pedidos do dia
    cur.execute(
        f"""
        SELECT COUNT(*)::int
        FROM tbl_pedido
        WHERE id_tenant_fornecedor = %s
          AND criado_em >= date_trunc('day', NOW())
          AND criado_em < date_trunc('day', NOW()) + INTERVAL '1 day'
          AND {excluidos}
        """,
        (id_fornecedor,),
    )
    pedidos_hoje = int(cur.fetchone()[0] or 0)

    # Pedidos aguardando aprovação do fornecedor (PIX / confirmação)
    cur.execute(
        f"""
        SELECT COUNT(*)::int
        FROM tbl_pedido
        WHERE id_tenant_fornecedor = %s
          AND (
            COALESCE({cv}, '') = 'aguardando_confirmacao'
            OR (
              COALESCE(status_pagamento, '') = 'comprovante_enviado'
              AND COALESCE({cv}, '') IN ('aguardando_pagamento', 'aguardando_confirmacao')
            )
          )
        """,
        (id_fornecedor,),
    )
    pedidos_aguardando = int(cur.fetchone()[0] or 0)

    # Vínculos
    cur.execute(
        """
        SELECT status, COUNT(*)::int
        FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_fornecedor = %s
          AND status IN ('ativo', 'aguardando', 'pausado')
        GROUP BY status
        """,
        (id_fornecedor,),
    )
    vinculos = {"ativo": 0, "aguardando": 0, "pausado": 0}
    for st, qtd in cur.fetchall():
        vinculos[(st or "").strip()] = int(qtd or 0)

    # Catálogo: total × publicados
    cur.execute(
        """
        SELECT COUNT(*)::int,
               COUNT(*) FILTER (WHERE publicado = TRUE)::int
        FROM tbl_produto
        WHERE id_tenant = %s
        """,
        (id_fornecedor,),
    )
    row_prod = cur.fetchone() or (0, 0)
    produtos_total = int(row_prod[0] or 0)
    produtos_publicados = int(row_prod[1] or 0)
    pct_pub = round((produtos_publicados / produtos_total) * 100) if produtos_total else 0

    # Faturamento mês a mês (12 meses)
    cur.execute(
        f"""
        WITH meses AS (
          SELECT generate_series(
            date_trunc('month', NOW()) - INTERVAL '11 months',
            date_trunc('month', NOW()),
            INTERVAL '1 month'
          )::date AS mes
        )
        SELECT to_char(m.mes, 'YYYY-MM') AS ym,
               COALESCE(SUM(p.valor_total), 0) AS total
        FROM meses m
        LEFT JOIN tbl_pedido p
          ON p.id_tenant_fornecedor = %s
         AND date_trunc('month', p.criado_em) = m.mes
         AND {excluidos}
        GROUP BY m.mes
        ORDER BY m.mes
        """,
        (id_fornecedor,),
    )
    faturamento_mensal = []
    max_fat = 0.0
    for ym, total in cur.fetchall():
        val = float(total or 0)
        max_fat = max(max_fat, val)
        faturamento_mensal.append(
            {
                "mes": ym,
                "rotulo": _mes_rotulo(ym),
                "valor": val,
                "valor_fmt": _fmt_brl(val),
            }
        )
    for item in faturamento_mensal:
        item["pct"] = round((item["valor"] / max_fat) * 100) if max_fat > 0 else 0

    # Top 5 vendedores (12 meses)
    cur.execute(
        f"""
        SELECT p.id_tenant_vendedor,
               COALESCE(NULLIF(TRIM(t.nome_fantasia), ''), NULLIF(TRIM(t.nome), ''), 'Vendedor') AS nome,
               COUNT(*)::int AS qtd,
               COALESCE(SUM(p.valor_total), 0) AS total
        FROM tbl_pedido p
        LEFT JOIN tbl_tenant t ON t.id = p.id_tenant_vendedor
        WHERE p.id_tenant_fornecedor = %s
          AND p.criado_em >= date_trunc('month', NOW()) - INTERVAL '11 months'
          AND {excluidos}
          AND p.id_tenant_vendedor IS NOT NULL
        GROUP BY p.id_tenant_vendedor, t.nome_fantasia, t.nome
        ORDER BY total DESC, qtd DESC
        LIMIT 5
        """,
        (id_fornecedor,),
    )
    top_vendedores = []
    max_vd = 0.0
    for i, row in enumerate(cur.fetchall(), start=1):
        total = float(row[3] or 0)
        max_vd = max(max_vd, total)
        top_vendedores.append(
            {
                "rank": i,
                "id": int(row[0]) if row[0] else None,
                "nome": row[1] or "Vendedor",
                "pedidos": int(row[2] or 0),
                "valor": total,
                "valor_fmt": _fmt_brl(total),
            }
        )
    for item in top_vendedores:
        item["pct"] = round((item["valor"] / max_vd) * 100) if max_vd > 0 else 0

    # Top 5 produtos (12 meses)
    cur.execute(
        f"""
        SELECT COALESCE(i.id_produto, 0),
               COALESCE(NULLIF(TRIM(MAX(i.nome_produto)), ''), 'Produto') AS nome,
               COALESCE(SUM(i.quantidade), 0)::int AS qtd,
               COALESCE(SUM(i.subtotal_drop), 0) AS total
        FROM tbl_pedido_item i
        JOIN tbl_pedido p ON p.id = i.id_pedido
        WHERE p.id_tenant_fornecedor = %s
          AND p.criado_em >= date_trunc('month', NOW()) - INTERVAL '11 months'
          AND {excluidos}
        GROUP BY COALESCE(i.id_produto, 0)
        ORDER BY qtd DESC, total DESC
        LIMIT 5
        """,
        (id_fornecedor,),
    )
    top_produtos = []
    max_qtd = 0
    for i, row in enumerate(cur.fetchall(), start=1):
        qtd = int(row[2] or 0)
        max_qtd = max(max_qtd, qtd)
        top_produtos.append(
            {
                "rank": i,
                "id": int(row[0]) if row[0] else None,
                "nome": row[1] or "Produto",
                "quantidade": qtd,
                "valor": float(row[3] or 0),
                "valor_fmt": _fmt_brl(row[3]),
            }
        )
    for item in top_produtos:
        item["pct"] = round((item["quantidade"] / max_qtd) * 100) if max_qtd > 0 else 0

    fat_12m = sum(x["valor"] for x in faturamento_mensal)

    return {
        "kpis": {
            "pedidos_hoje": pedidos_hoje,
            "pedidos_aguardando": pedidos_aguardando,
            "vendedores_ativos": vinculos["ativo"],
            "vendedores_aguardando": vinculos["aguardando"],
            "produtos_total": produtos_total,
            "produtos_publicados": produtos_publicados,
            "produtos_pct": pct_pub,
            "faturamento_12m": fat_12m,
            "faturamento_12m_fmt": _fmt_brl(fat_12m),
        },
        "faturamento_mensal": faturamento_mensal,
        "top_vendedores": top_vendedores,
        "top_produtos": top_produtos,
    }
