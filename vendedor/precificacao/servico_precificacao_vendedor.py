# vendedor/precificacao/servico_precificacao_vendedor.py — regras de preço do vendedor
from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from fornecedor.parametros.servico_precificacao import (
    buscar_regra_fornecedor,
    calcular_preco_sugerido_revenda,
    pct_margem_revenda_efetiva,
)

MODO_SUGESTAO_FORNECEDOR = "sugestao_fornecedor"
MODO_MARGEM_DROP = "margem_drop"
MARGEM_MINIMA_PADRAO = 30.0


def aplicar_arredondamento(preco: float | Decimal, centavos: int | None) -> float:
    """Ex.: centavos=90 → floor(preço) + 0,90."""
    if centavos is None:
        return round(float(preco or 0), 2)
    base = math.floor(float(preco or 0))
    return round(base + int(centavos) / 100.0, 2)


def calcular_margem_pct(preco_venda: float | Decimal, valor_drop: float | Decimal) -> float | None:
    drop = float(valor_drop or 0)
    if drop <= 0:
        return None
    venda = float(preco_venda or 0)
    return round((venda - drop) / drop * 100.0, 2)


def preco_sugerido_fornecedor(
    cur,
    id_fornecedor: int,
    id_categoria: int | None,
    valor_drop: float | Decimal,
) -> float:
    regra_fn = buscar_regra_fornecedor(cur, id_fornecedor, id_categoria)
    pct = pct_margem_revenda_efetiva(regra_fn)
    return float(calcular_preco_sugerido_revenda(valor_drop, pct))


def _row_regra(row) -> dict:
    return {
        "pct_marketplace": float(row[0] or 0),
        "pct_impostos": float(row[1] or 0),
        "pct_taxas": float(row[2] or 0),
        "pct_margem_lucro": float(row[3] or 0),
        "modo": row[4] or MODO_SUGESTAO_FORNECEDOR,
        "arredondamento_centavos": int(row[5]) if row[5] is not None else None,
        "margem_minima_alerta": float(row[6] if row[6] is not None else MARGEM_MINIMA_PADRAO),
    }


def _select_regra_cols() -> str:
    return """
        pct_marketplace, pct_impostos, pct_taxas, pct_margem_lucro,
        modo, arredondamento_centavos, margem_minima_alerta
    """


def buscar_regra_precificacao(
    cur,
    id_vendedor: int,
    id_segmento: int | None,
    id_categoria: int | None,
) -> dict | None:
    cols = _select_regra_cols()
    if id_categoria:
        cur.execute(
            f"""
            SELECT {cols}
            FROM tbl_vendedor_precificacao
            WHERE id_tenant_vendedor = %s AND escopo = 'categoria'
              AND id_categoria = %s AND ativo = TRUE
            LIMIT 1
            """,
            (id_vendedor, id_categoria),
        )
        row = cur.fetchone()
        if row:
            return _row_regra(row)
    if id_segmento:
        cur.execute(
            f"""
            SELECT {cols}
            FROM tbl_vendedor_precificacao
            WHERE id_tenant_vendedor = %s AND escopo = 'segmento'
              AND id_segmento = %s AND ativo = TRUE
            LIMIT 1
            """,
            (id_vendedor, id_segmento),
        )
        row = cur.fetchone()
        if row:
            return _row_regra(row)
    cur.execute(
        f"""
        SELECT {cols}
        FROM tbl_vendedor_precificacao
        WHERE id_tenant_vendedor = %s AND escopo = 'global' AND ativo = TRUE
        LIMIT 1
        """,
        (id_vendedor,),
    )
    row = cur.fetchone()
    return _row_regra(row) if row else None


def calcular_preco_venda_vendedor(
    valor_drop: float | Decimal,
    preco_sugerido_forn: float | Decimal,
    regra: dict | None,
) -> float:
    """Calcula preço de venda conforme modo do vendedor."""
    drop = float(valor_drop or 0)
    sugestao = float(preco_sugerido_forn or 0)
    modo = (regra or {}).get("modo") or MODO_SUGESTAO_FORNECEDOR

    if modo == MODO_MARGEM_DROP:
        if drop <= 0:
            return 0.0
        pct = float((regra or {}).get("pct_margem_lucro") or 0)
        bruto = drop * (1 + pct / 100.0)
        cent = (regra or {}).get("arredondamento_centavos")
        return aplicar_arredondamento(bruto, cent)

    return round(sugestao, 2) if sugestao > 0 else 0.0


def precificar_na_integracao(
    cur,
    id_vendedor: int,
    id_fornecedor: int,
    id_categoria: int | None,
    valor_drop: float | Decimal,
) -> float:
    """Preço ao ativar produto no catálogo — usa regra vigente do vendedor."""
    sugestao = preco_sugerido_fornecedor(cur, id_fornecedor, id_categoria, valor_drop)
    id_segmento = None
    if id_categoria:
        cur.execute("SELECT id_segmento FROM tbl_categoria WHERE id = %s", (id_categoria,))
        seg = cur.fetchone()
        id_segmento = int(seg[0]) if seg and seg[0] else None
    regra = buscar_regra_precificacao(cur, id_vendedor, id_segmento, id_categoria)
    return calcular_preco_venda_vendedor(valor_drop, sugestao, regra)


def aplicar_precificacao_tenant(
    cur,
    id_vendedor: int,
    escopo: str,
    id_segmento: int | None,
    id_categoria: int | None,
) -> int:
    regra = None
    if escopo == "global":
        regra = buscar_regra_precificacao(cur, id_vendedor, None, None)
    elif escopo == "segmento" and id_segmento:
        regra = buscar_regra_precificacao(cur, id_vendedor, id_segmento, None)
    elif escopo == "categoria" and id_categoria:
        regra = buscar_regra_precificacao(cur, id_vendedor, None, id_categoria)
    if not regra:
        return 0

    where = ["pv.id_tenant_vendedor = %s", "pv.ativo = TRUE", "pv.preco_manual = FALSE"]
    params: list[Any] = [id_vendedor]
    if escopo == "segmento":
        where.append("c.id_segmento = %s")
        params.append(id_segmento)
    elif escopo == "categoria":
        where.append("p.id_categoria = %s")
        params.append(id_categoria)

    cur.execute(
        f"""
        SELECT pv.id, pv.preco_fornecedor, p.id_tenant, p.id_categoria
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        LEFT JOIN tbl_categoria c ON c.id = p.id_categoria
        WHERE {' AND '.join(where)}
        """,
        params,
    )
    rows = cur.fetchall()
    n = 0
    for pid, valor_drop, id_forn, id_cat in rows:
        sugestao = preco_sugerido_fornecedor(cur, int(id_forn), id_cat, float(valor_drop or 0))
        novo = calcular_preco_venda_vendedor(valor_drop, sugestao, regra)
        cur.execute(
            "UPDATE tbl_produto_vendedor SET preco_venda = %s, atualizado_em = NOW() WHERE id = %s",
            (novo, pid),
        )
        n += 1
    return n


def _tipo_alerta(modo: str, valor_drop: float, preco_sug: float, margem: float | None, minima: float) -> str | None:
    if modo == MODO_MARGEM_DROP:
        if valor_drop <= 0:
            return "sem_valor_drop"
        return None

    if preco_sug <= 0:
        return "sem_preco"
    if margem is not None and margem < minima:
        return "margem_baixa"
    return None


def listar_alertas(cur, id_vendedor: int, regra: dict | None = None) -> dict:
    """Alertas de produtos ativos em Meus produtos."""
    if regra is None:
        regra = buscar_regra_precificacao(cur, id_vendedor, None, None) or {
            "modo": MODO_SUGESTAO_FORNECEDOR,
            "margem_minima_alerta": MARGEM_MINIMA_PADRAO,
        }
    modo = regra.get("modo") or MODO_SUGESTAO_FORNECEDOR
    minima = float(regra.get("margem_minima_alerta") or MARGEM_MINIMA_PADRAO)

    cur.execute(
        """
        SELECT pv.id, pv.id_variante, p.nome, v.sku,
               pv.preco_fornecedor, p.id_tenant, p.id_categoria,
               COALESCE(pv.nome_vitrine, p.nome) AS nome_exibicao
        FROM tbl_produto_vendedor pv
        JOIN tbl_produto_variante v ON v.id = pv.id_variante
        JOIN tbl_produto p ON p.id = pv.id_produto
        WHERE pv.id_tenant_vendedor = %s AND pv.ativo = TRUE
        ORDER BY nome_exibicao, v.sku
        """,
        (id_vendedor,),
    )
    itens: list[dict] = []
    resumo = {"sem_preco": 0, "margem_baixa": 0, "sem_valor_drop": 0, "total": 0}

    for row in cur.fetchall():
        valor_drop = float(row[4] or 0)
        preco_sug = preco_sugerido_fornecedor(cur, int(row[5]), row[6], valor_drop)
        margem = calcular_margem_pct(preco_sug, valor_drop)
        tipo = _tipo_alerta(modo, valor_drop, preco_sug, margem, minima)
        if not tipo:
            continue
        resumo[tipo] = resumo.get(tipo, 0) + 1
        resumo["total"] += 1
        itens.append({
            "id_produto_vendedor": row[0],
            "id_variante": row[1],
            "nome": row[7] or row[2],
            "sku": row[3] or "",
            "valor_drop": valor_drop,
            "preco_sugerido": preco_sug,
            "margem_pct": margem,
            "tipo": tipo,
        })

    return {
        "modo": modo,
        "margem_minima_alerta": minima,
        "resumo": resumo,
        "itens": itens,
    }
