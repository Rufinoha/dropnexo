"""Espelha depósitos do fornecedor na conta do vendedor ao integrar produtos."""

from __future__ import annotations

from global_utils import agora_utc

_DEP_COLS = """
    nome, cep, logradouro, numero, complemento, bairro, cidade, uf,
    remetente_nome, remetente_documento, principal
"""


def _depositos_do_produto(cur, id_fornecedor: int, id_produto: int) -> list[int]:
    """Depósitos do fornecedor usados pelo produto (estoque, expedição ou principal)."""
    ids: set[int] = set()
    cur.execute(
        """
        SELECT DISTINCT ped.id_deposito
        FROM tbl_produto_estoque_deposito ped
        JOIN tbl_produto_variante v ON v.id = ped.id_variante
        WHERE v.id_produto = %s
        """,
        (id_produto,),
    )
    ids.update(int(r[0]) for r in cur.fetchall() if r and r[0])

    cur.execute(
        "SELECT id_deposito_expedicao FROM tbl_produto WHERE id = %s AND id_tenant = %s",
        (id_produto, id_fornecedor),
    )
    row = cur.fetchone()
    if row and row[0]:
        ids.add(int(row[0]))

    if not ids:
        cur.execute(
            """
            SELECT id FROM tbl_deposito_expedicao
            WHERE id_tenant = %s AND ativo = TRUE
            ORDER BY principal DESC, id
            LIMIT 1
            """,
            (id_fornecedor,),
        )
        principal = cur.fetchone()
        if principal and principal[0]:
            ids.add(int(principal[0]))

    return sorted(ids)


def espelhar_depositos_fornecedor(
    cur,
    id_vendedor: int,
    id_fornecedor: int,
    *,
    id_produto: int | None = None,
) -> int:
    """
    Cria depósitos espelho (somente leitura) no vendedor.
    Se id_produto informado, espelha depósitos usados pelo produto
    (estoque por filial, depósito de expedição ou principal do fornecedor).
    """
    if id_produto:
        ids_dep = _depositos_do_produto(cur, id_fornecedor, id_produto)
        if not ids_dep:
            return 0
        cur.execute(
            f"""
            SELECT d.id, {_DEP_COLS}
            FROM tbl_deposito_expedicao d
            WHERE d.id_tenant = %s AND d.ativo = TRUE AND d.id = ANY(%s)
            ORDER BY d.principal DESC, d.nome
            """,
            (id_fornecedor, ids_dep),
        )
        rows = cur.fetchall()
    else:
        cur.execute(
            f"""
            SELECT d.id, {_DEP_COLS}
            FROM tbl_deposito_expedicao d
            WHERE d.id_tenant = %s AND d.ativo = TRUE
            ORDER BY d.principal DESC, d.nome
            """,
            (id_fornecedor,),
        )
        rows = cur.fetchall()
    criados = 0
    for row in rows:
        id_dep_forn = int(row[0])
        cur.execute(
            """
            SELECT id FROM tbl_deposito_expedicao
            WHERE id_tenant = %s AND id_deposito_espelho = %s
            LIMIT 1
            """,
            (id_vendedor, id_dep_forn),
        )
        if cur.fetchone():
            continue
        cur.execute(
            f"""
            INSERT INTO tbl_deposito_expedicao (
                id_tenant, nome, cep, logradouro, numero, complemento, bairro, cidade, uf,
                remetente_nome, remetente_documento, principal, ativo,
                id_deposito_espelho, id_tenant_espelho, espelho_somente_leitura, atualizado_em
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, TRUE,
                %s, %s, TRUE, %s
            )
            """,
            (
                id_vendedor,
                row[1],
                row[2],
                row[3],
                row[4],
                row[5],
                row[6],
                row[7],
                row[8],
                row[9],
                row[10],
                bool(row[11]),
                id_dep_forn,
                id_fornecedor,
                agora_utc(),
            ),
        )
        criados += 1
    return criados


def sincronizar_espelhos_integrados(cur, id_vendedor: int) -> int:
    """Garante espelhos para produtos já integrados (idempotente)."""
    cur.execute(
        """
        SELECT DISTINCT pv.id_tenant_fornecedor, pv.id_produto
        FROM tbl_produto_vendedor pv
        WHERE pv.id_tenant_vendedor = %s AND pv.ativo = TRUE
        """,
        (id_vendedor,),
    )
    total = 0
    for id_forn, id_prod in cur.fetchall():
        total += espelhar_depositos_fornecedor(
            cur, id_vendedor, int(id_forn), id_produto=int(id_prod)
        )
    return total
