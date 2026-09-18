# core/menu_badges.py — contadores de atenção no menu / seletor de módulo
from __future__ import annotations

from core.pedidos.servico import col_status_vendedor


def _count_vendedores_aguardando(cur, id_tenant: int) -> int:
    cur.execute(
        """
        SELECT COUNT(*)::int
        FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_fornecedor = %s
          AND status = 'aguardando'
        """,
        (id_tenant,),
    )
    return int(cur.fetchone()[0] or 0)


def _count_pedidos_aguardando(cur, id_tenant: int) -> int:
    try:
        cv = col_status_vendedor(cur)
    except Exception:
        return 0
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
        (id_tenant,),
    )
    return int(cur.fetchone()[0] or 0)


def _badges_modulo_fornecedor_ou_armazem(cur, id_tenant: int, prefix: str) -> dict[str, int]:
    """prefix: 'fn' | 'az' — mesmos contadores (tenant é o fornecedor/armazém)."""
    vd = _count_vendedores_aguardando(cur, id_tenant)
    pd = _count_pedidos_aguardando(cur, id_tenant)
    out: dict[str, int] = {}
    if vd > 0:
        out[f"{prefix}_vendedores"] = vd
    if pd > 0:
        out[f"{prefix}_pedidos"] = pd
    return out


def contagens_menu_badges(cur, *, id_tenant: int, modulos: list[str]) -> dict:
    """
    Retorna:
      nav: { nav_codigo: qtd }
      modulos: { codigo_modulo: qtd_total }
    """
    nav: dict[str, int] = {}
    mods: dict[str, int] = {}
    for m in modulos or []:
        codigo = (m or "").strip().lower()
        if codigo == "fornecedor":
            parcial = _badges_modulo_fornecedor_ou_armazem(cur, id_tenant, "fn")
        elif codigo == "armazem":
            parcial = _badges_modulo_fornecedor_ou_armazem(cur, id_tenant, "az")
        else:
            continue
        nav.update(parcial)
        total = sum(parcial.values())
        if total > 0:
            mods[codigo] = total
    return {"nav": nav, "modulos": mods}
