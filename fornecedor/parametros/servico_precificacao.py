# fornecedor/parametros/servico_precificacao.py — regras de preço Drop (fornecedor → vendedor)
from __future__ import annotations

from decimal import Decimal
from typing import Any

from global_utils import agora_utc


def calcular_valor_drop(
    preco_base: float | Decimal,
    *,
    pct_ajuste: float = 0,
    pct_taxas: float = 0,
    pct_comissao: float = 0,
) -> float:
    """preco × (1 + ajuste%) × (1 + (taxas + comissão)%). Ajuste negativo = desconto."""
    base = float(preco_base or 0)
    if base <= 0:
        return 0.0
    apos_ajuste = base * (1 + float(pct_ajuste or 0) / 100)
    pct_extra = float(pct_taxas or 0) + float(pct_comissao or 0)
    return round(apos_ajuste * (1 + pct_extra / 100), 2)


def _row_regra(row) -> dict:
    return {
        "id": row[0],
        "escopo": row[1],
        "id_categoria": row[2],
        "pct_ajuste": float(row[3] or 0),
        "pct_taxas": float(row[4] or 0),
        "pct_comissao": float(row[5] or 0),
    }


def buscar_regra_fornecedor(
    cur,
    id_tenant: int,
    id_categoria: int | None = None,
) -> dict | None:
    if id_categoria:
        cur.execute(
            """
            SELECT id, escopo, id_categoria, pct_ajuste, pct_taxas, pct_comissao
            FROM tbl_fornecedor_precificacao
            WHERE id_tenant = %s AND escopo = 'categoria' AND id_categoria = %s AND ativo = TRUE
            LIMIT 1
            """,
            (id_tenant, id_categoria),
        )
        row = cur.fetchone()
        if row:
            return _row_regra(row)
    cur.execute(
        """
        SELECT id, escopo, id_categoria, pct_ajuste, pct_taxas, pct_comissao
        FROM tbl_fornecedor_precificacao
        WHERE id_tenant = %s AND escopo = 'global' AND ativo = TRUE
        LIMIT 1
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    return _row_regra(row) if row else None


def listar_regras_fornecedor(cur, id_tenant: int) -> list[dict]:
    cur.execute(
        """
        SELECT fp.id, fp.escopo, fp.id_categoria, c.nome,
               fp.pct_ajuste, fp.pct_taxas, fp.pct_comissao, fp.ativo
        FROM tbl_fornecedor_precificacao fp
        LEFT JOIN tbl_categoria c ON c.id = fp.id_categoria
        WHERE fp.id_tenant = %s AND fp.ativo = TRUE
        ORDER BY CASE fp.escopo WHEN 'global' THEN 0 ELSE 1 END, c.nome NULLS FIRST
        """,
        (id_tenant,),
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": r[0],
                "escopo": r[1],
                "id_categoria": r[2],
                "categoria_nome": r[3],
                "pct_ajuste": float(r[4] or 0),
                "pct_taxas": float(r[5] or 0),
                "pct_comissao": float(r[6] or 0),
                "ativo": bool(r[7]),
            }
        )
    return out


def salvar_regra_fornecedor(
    cur,
    id_tenant: int,
    *,
    escopo: str,
    id_categoria: int | None,
    pct_ajuste: float,
    pct_taxas: float,
    pct_comissao: float,
) -> int:
    escopo = (escopo or "global").strip().lower()
    if escopo not in ("global", "categoria"):
        raise ValueError("Escopo inválido.")
    if escopo == "categoria" and not id_categoria:
        raise ValueError("Selecione uma categoria.")

    cur.execute(
        """
        UPDATE tbl_fornecedor_precificacao SET ativo = FALSE
        WHERE id_tenant = %s AND escopo = %s
          AND (%s IS NULL OR id_categoria IS NOT DISTINCT FROM %s)
        """,
        (id_tenant, escopo, id_categoria, id_categoria),
    )
    cur.execute(
        """
        INSERT INTO tbl_fornecedor_precificacao (
            id_tenant, escopo, id_categoria, pct_ajuste, pct_taxas, pct_comissao, ativo, atualizado_em
        ) VALUES (%s, %s, %s, %s, %s, %s, TRUE, %s)
        RETURNING id
        """,
        (
            id_tenant,
            escopo,
            id_categoria if escopo == "categoria" else None,
            pct_ajuste,
            pct_taxas,
            pct_comissao,
            agora_utc(),
        ),
    )
    return int(cur.fetchone()[0])


def valor_drop_para_produto(
    cur,
    id_tenant: int,
    *,
    preco: float,
    id_categoria: int | None,
) -> float | None:
    regra = buscar_regra_fornecedor(cur, id_tenant, id_categoria)
    if not regra:
        return None
    return calcular_valor_drop(
        preco,
        pct_ajuste=regra["pct_ajuste"],
        pct_taxas=regra["pct_taxas"],
        pct_comissao=regra["pct_comissao"],
    )


def aplicar_valor_drop_variante(
    cur,
    id_tenant: int,
    id_variante: int,
    *,
    preco: float | None = None,
    id_categoria: int | None = None,
) -> bool:
    if preco is None or id_categoria is None:
        cur.execute(
            """
            SELECT v.preco, p.id_categoria FROM tbl_produto_variante v
            JOIN tbl_produto p ON p.id = v.id_produto
            WHERE v.id = %s AND p.id_tenant = %s
            """,
            (id_variante, id_tenant),
        )
        row = cur.fetchone()
        if not row:
            return False
        preco, id_categoria = float(row[0] or 0), row[1]
    vd = valor_drop_para_produto(cur, id_tenant, preco=preco, id_categoria=id_categoria)
    if vd is None:
        return False
    cur.execute(
        """
        UPDATE tbl_produto_variante SET valor_drop = %s, atualizado_em = %s
        WHERE id = %s
        """,
        (vd, agora_utc(), id_variante),
    )
    return True


def aplicar_valor_drop_produto_e_variantes(
    cur,
    id_tenant: int,
    id_produto: int,
    *,
    publicar: bool = False,
    forcar: bool = False,
) -> None:
    if not forcar:
        cur.execute(
            """
            SELECT valor_drop_manual FROM tbl_produto
            WHERE id = %s AND id_tenant = %s
            """,
            (id_produto, id_tenant),
        )
        row = cur.fetchone()
        if row and row[0]:
            return
    aplicar_valor_drop_produto(cur, id_tenant, id_produto, publicar=publicar)
    cur.execute(
        """
        SELECT v.id, v.preco, p.id_categoria FROM tbl_produto_variante v
        JOIN tbl_produto p ON p.id = v.id_produto
        WHERE p.id = %s AND p.id_tenant = %s AND COALESCE(v.preco, 0) > 0
        """,
        (id_produto, id_tenant),
    )
    for vid, preco, id_cat in cur.fetchall():
        aplicar_valor_drop_variante(
            cur, id_tenant, int(vid), preco=float(preco or 0), id_categoria=id_cat
        )


def aplicar_valor_drop_produto(
    cur,
    id_tenant: int,
    id_produto: int,
    *,
    publicar: bool = False,
) -> bool:
    cur.execute(
        """
        SELECT preco, id_categoria FROM tbl_produto
        WHERE id = %s AND id_tenant = %s
        """,
        (id_produto, id_tenant),
    )
    row = cur.fetchone()
    if not row:
        return False
    preco, id_cat = float(row[0] or 0), row[1]
    vd = valor_drop_para_produto(cur, id_tenant, preco=preco, id_categoria=id_cat)
    if vd is None:
        return False
    if publicar:
        cur.execute(
            """
            UPDATE tbl_produto SET
                valor_drop = %s,
                valor_dropshipping = %s,
                valor_drop_manual = FALSE,
                publicado = TRUE,
                atualizado_em = %s
            WHERE id = %s AND id_tenant = %s
            """,
            (vd, vd, agora_utc(), id_produto, id_tenant),
        )
    else:
        cur.execute(
            """
            UPDATE tbl_produto SET
                valor_drop = %s,
                valor_dropshipping = %s,
                valor_drop_manual = FALSE,
                atualizado_em = %s
            WHERE id = %s AND id_tenant = %s
            """,
            (vd, vd, agora_utc(), id_produto, id_tenant),
        )
    cur.execute(
        """
        SELECT id FROM tbl_produto_variante
        WHERE id_produto = %s AND id = (
            SELECT id_variante_padrao FROM tbl_produto WHERE id = %s
        )
        """,
        (id_produto, id_produto),
    )
    vrow = cur.fetchone()
    if vrow:
        cur.execute(
            """
            UPDATE tbl_produto_variante SET valor_drop = %s, atualizado_em = %s WHERE id = %s
            """,
            (vd, agora_utc(), vrow[0]),
        )
    return True


def salvar_valor_drop_manual(
    cur,
    id_tenant: int,
    id_produto: int,
    valor_drop: float,
) -> float:
    """Define valor_drop manualmente; permanece até reaplicar precificação."""
    vd = round(max(0.0, float(valor_drop or 0)), 2)
    agora = agora_utc()
    cur.execute(
        """
        UPDATE tbl_produto SET
            valor_drop = %s,
            valor_dropshipping = %s,
            valor_drop_manual = TRUE,
            atualizado_em = %s
        WHERE id = %s AND id_tenant = %s
        RETURNING id_variante_padrao
        """,
        (vd, vd, agora, id_produto, id_tenant),
    )
    row = cur.fetchone()
    if not row:
        raise ValueError("Produto não encontrado.")
    if row[0]:
        cur.execute(
            """
            UPDATE tbl_produto_variante SET valor_drop = %s, atualizado_em = %s
            WHERE id = %s
            """,
            (vd, agora, row[0]),
        )
    return vd


def aplicar_precificacao_catalogo(
    cur,
    id_tenant: int,
    *,
    marcar_publicado: bool = True,
) -> dict[str, int]:
    """Recalcula valor_drop em todos os produtos com preço > 0."""
    regra_global = buscar_regra_fornecedor(cur, id_tenant, None)
    if not regra_global:
        return {"atualizados": 0, "ignorados": 0}

    cur.execute(
        """
        SELECT id, preco, id_categoria FROM tbl_produto
        WHERE id_tenant = %s AND COALESCE(preco, 0) > 0
        """,
        (id_tenant,),
    )
    atualizados = 0
    ignorados = 0
    agora = agora_utc()
    for pid, preco, id_cat in cur.fetchall():
        regra = buscar_regra_fornecedor(cur, id_tenant, id_cat)
        if not regra:
            ignorados += 1
            continue
        vd = calcular_valor_drop(
            float(preco or 0),
            pct_ajuste=regra["pct_ajuste"],
            pct_taxas=regra["pct_taxas"],
            pct_comissao=regra["pct_comissao"],
        )
        if marcar_publicado:
            cur.execute(
                """
                UPDATE tbl_produto SET
                    valor_drop = %s, valor_dropshipping = %s,
                    valor_drop_manual = FALSE,
                    publicado = TRUE, ativo = TRUE, atualizado_em = %s
                WHERE id = %s AND id_tenant = %s
                """,
                (vd, vd, agora, pid, id_tenant),
            )
        else:
            cur.execute(
                """
                UPDATE tbl_produto SET
                    valor_drop = %s, valor_dropshipping = %s,
                    valor_drop_manual = FALSE, atualizado_em = %s
                WHERE id = %s AND id_tenant = %s
                """,
                (vd, vd, agora, pid, id_tenant),
            )
        atualizados += 1

    cur.execute(
        """
        SELECT v.id, v.preco, p.id_categoria
        FROM tbl_produto_variante v
        JOIN tbl_produto p ON p.id = v.id_produto
        WHERE p.id_tenant = %s AND COALESCE(v.preco, 0) > 0
        """,
        (id_tenant,),
    )
    for vid, preco, id_cat in cur.fetchall():
        regra = buscar_regra_fornecedor(cur, id_tenant, id_cat)
        if not regra:
            continue
        vd = calcular_valor_drop(
            float(preco or 0),
            pct_ajuste=regra["pct_ajuste"],
            pct_taxas=regra["pct_taxas"],
            pct_comissao=regra["pct_comissao"],
        )
        cur.execute(
            """
            UPDATE tbl_produto_variante SET valor_drop = %s, atualizado_em = %s
            WHERE id = %s
            """,
            (vd, agora, vid),
        )

    return {"atualizados": atualizados, "ignorados": ignorados}
