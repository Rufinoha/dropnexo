# servico_estoque_reserva.py — reserva de estoque do fornecedor ao confirmar pedido
from __future__ import annotations


def estoque_disponivel_variante(cur, id_variante: int) -> int:
    cur.execute(
        """
        SELECT COALESCE(quantidade, 0) - COALESCE(reservado, 0)
        FROM tbl_produto_variante_estoque
        WHERE id_variante = %s
        """,
        (id_variante,),
    )
    row = cur.fetchone()
    if row:
        return max(0, int(row[0]))
    cur.execute(
        """
        SELECT COALESCE(SUM(quantidade), 0)
        FROM tbl_produto_estoque_deposito
        WHERE id_variante = %s
        """,
        (id_variante,),
    )
    dep = cur.fetchone()
    return max(0, int(dep[0] if dep else 0))


def _garantir_linha_estoque(cur, id_variante: int) -> None:
    cur.execute(
        """
        INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, reservado, atualizado_em)
        SELECT %s,
               COALESCE((
                   SELECT SUM(ped.quantidade)
                   FROM tbl_produto_estoque_deposito ped
                   WHERE ped.id_variante = %s
               ), 0),
               0, NOW()
        ON CONFLICT (id_variante) DO NOTHING
        """,
        (id_variante, id_variante),
    )


def reservar_estoque(cur, id_variante: int, quantidade: int) -> None:
    if quantidade <= 0:
        return
    disponivel = estoque_disponivel_variante(cur, id_variante)
    if disponivel < quantidade:
        raise ValueError(f"Estoque insuficiente para a variante {id_variante} (disponível: {disponivel}).")
    _garantir_linha_estoque(cur, id_variante)
    cur.execute(
        """
        UPDATE tbl_produto_variante_estoque
        SET reservado = reservado + %s, atualizado_em = NOW()
        WHERE id_variante = %s
        """,
        (quantidade, id_variante),
    )


def liberar_reserva(cur, id_variante: int, quantidade: int) -> None:
    if quantidade <= 0:
        return
    cur.execute(
        """
        UPDATE tbl_produto_variante_estoque
        SET reservado = GREATEST(0, reservado - %s), atualizado_em = NOW()
        WHERE id_variante = %s
        """,
        (quantidade, id_variante),
    )


def reservar_itens_pedido(cur, itens: list[tuple[int, int]]) -> None:
    """itens: lista de (id_variante, quantidade)."""
    for id_var, qtd in itens:
        reservar_estoque(cur, int(id_var), int(qtd))


def liberar_itens_pedido(cur, itens: list[tuple[int, int]]) -> None:
    for id_var, qtd in itens:
        liberar_reserva(cur, int(id_var), int(qtd))
