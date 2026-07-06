"""Categoria do vendedor em produtos da vitrine (integrados e próprios)."""

from __future__ import annotations

from global_utils import agora_utc


def categoria_pertence_vendedor(cur, id_vendedor: int, id_categoria: int) -> bool:
    cur.execute(
        "SELECT 1 FROM tbl_categoria WHERE id = %s AND id_tenant = %s AND ativo = TRUE",
        (id_categoria, id_vendedor),
    )
    return bool(cur.fetchone())


def associar_categoria_produtos(
    cur,
    id_vendedor: int,
    ids: list[int],
    id_categoria: int | None,
) -> int:
    """Associa categoria do vendedor a produtos próprios ou integrados. Retorna qtd de produtos."""
    if id_categoria is not None and not categoria_pertence_vendedor(cur, id_vendedor, id_categoria):
        raise ValueError("Categoria inválida.")

    atualizados = 0
    agora = agora_utc()
    for pid in ids:
        if pid < 0:
            continue
        cur.execute("SELECT id_tenant FROM tbl_produto WHERE id = %s", (pid,))
        row = cur.fetchone()
        if not row:
            continue
        if int(row[0]) == id_vendedor:
            cur.execute(
                """
                UPDATE tbl_produto
                SET id_categoria = %s, atualizado_em = %s
                WHERE id = %s AND id_tenant = %s
                """,
                (id_categoria, agora, pid, id_vendedor),
            )
        else:
            cur.execute(
                """
                UPDATE tbl_produto_vendedor
                SET id_categoria_vendedor = %s, atualizado_em = %s
                WHERE id_tenant_vendedor = %s AND id_produto = %s
                """,
                (id_categoria, agora, id_vendedor, pid),
            )
        if cur.rowcount:
            atualizados += 1
    return atualizados
