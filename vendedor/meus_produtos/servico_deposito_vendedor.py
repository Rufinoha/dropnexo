"""Espelha depósitos do fornecedor na conta do vendedor ao integrar produtos."""

from __future__ import annotations

from global_utils import agora_utc

_DEP_COLS = """
    nome, cep, logradouro, numero, complemento, bairro, cidade, uf,
    remetente_nome, remetente_documento, principal
"""


def espelhar_depositos_fornecedor(
    cur,
    id_vendedor: int,
    id_fornecedor: int,
    *,
    id_produto: int | None = None,
) -> int:
    """
    Cria depósitos espelho (somente leitura) no vendedor.
    Se id_produto informado, espelha só depósitos com estoque das variantes do produto.
  """
    params: list = [id_fornecedor]
    filtro_prod = ""
    if id_produto:
        filtro_prod = """
            AND d.id IN (
                SELECT DISTINCT ped.id_deposito
                FROM tbl_produto_estoque_deposito ped
                JOIN tbl_produto_variante v ON v.id = ped.id_variante
                WHERE v.id_produto = %s
            )
        """
        params.append(id_produto)

    cur.execute(
        f"""
        SELECT d.id, {_DEP_COLS}
        FROM tbl_deposito_expedicao d
        WHERE d.id_tenant = %s AND d.ativo = TRUE
        {filtro_prod}
        ORDER BY d.principal DESC, d.nome
        """,
        params,
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
