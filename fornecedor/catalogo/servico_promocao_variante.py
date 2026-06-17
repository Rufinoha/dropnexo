# fornecedor/catalogo/servico_promocao_variante.py — promoção por variante
from __future__ import annotations

from datetime import date, datetime

from global_utils import agora_utc


def _parse_date(val) -> date | None:
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    if isinstance(val, datetime):
        return val.date()
    s = str(val).strip()[:10]
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def promocao_variante_ativa(
    *,
    preco_promocional,
    promocao_validade=None,
    promocao_ate_zerar_estoque: bool = False,
    estoque: int = 0,
) -> bool:
    if preco_promocional in (None, ""):
        return False
    try:
        if float(preco_promocional) <= 0:
            return False
    except (TypeError, ValueError):
        return False
    fim = _parse_date(promocao_validade)
    if fim and date.today() > fim:
        return False
    if promocao_ate_zerar_estoque and int(estoque or 0) <= 0:
        return False
    return True


def encerrar_promocao_variante(cur, id_variante: int) -> None:
    cur.execute(
        """
        UPDATE tbl_produto_variante SET
            preco_promocional = NULL,
            promocao_validade = NULL,
            promocao_ate_zerar_estoque = FALSE,
            atualizado_em = %s
        WHERE id = %s
        """,
        (agora_utc(), id_variante),
    )


def reagir_estoque_promocao(cur, id_variante: int, total_antes: int, total_depois: int) -> bool:
    """Encerra promo 'até zerar estoque' ao esgotar ou ao repor estoque."""
    cur.execute(
        """
        SELECT promocao_ate_zerar_estoque, preco_promocional
        FROM tbl_produto_variante WHERE id = %s
        """,
        (id_variante,),
    )
    row = cur.fetchone()
    if not row or not row[0] or row[1] is None:
        return False
    if total_depois <= 0 or (total_antes <= 0 and total_depois > 0):
        encerrar_promocao_variante(cur, id_variante)
        return True
    return False
