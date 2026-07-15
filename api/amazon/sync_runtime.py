"""Sincronização DropNexo → Amazon (estoque e dados do produto)."""
from __future__ import annotations

import logging
from typing import Any

from api.amazon.eco_estoque import amazon_sync_suprimido

_log = logging.getLogger(__name__)


def variante_por_amazon_sku(cur, id_tenant: int, seller_sku: str, asin: str = "") -> int | None:
    seller_sku = (seller_sku or "").strip()
    asin = (asin or "").strip()
    chaves = []
    if asin and seller_sku:
        chaves.append(f"{asin}:{seller_sku}")
    if seller_sku:
        chaves.append(seller_sku)
    for chave in chaves:
        cur.execute(
            """
            SELECT id_dropnexo FROM tbl_integracao_map
            WHERE id_tenant = %s AND provedor = 'amazon' AND contexto = 'vendedor'
              AND entidade = 'produto' AND id_bling = %s
            LIMIT 1
            """,
            (id_tenant, chave),
        )
        row = cur.fetchone()
        if row and row[0]:
            return int(row[0])
    if asin:
        cur.execute(
            """
            SELECT id_dropnexo FROM tbl_integracao_map
            WHERE id_tenant = %s AND provedor = 'amazon' AND contexto = 'vendedor'
              AND entidade = 'produto' AND id_bling LIKE %s
            LIMIT 1
            """,
            (id_tenant, f"{asin}:%"),
        )
        row = cur.fetchone()
        if row and row[0]:
            return int(row[0])
    if seller_sku:
        cur.execute(
            """
            SELECT id_dropnexo FROM tbl_integracao_map
            WHERE id_tenant = %s AND provedor = 'amazon' AND contexto = 'vendedor'
              AND entidade = 'produto' AND sku = %s
            LIMIT 1
            """,
            (id_tenant, seller_sku),
        )
        row = cur.fetchone()
        if row and row[0]:
            return int(row[0])
    return None


def _amazon_map_por_variante(cur, id_tenant: int, id_variante: int) -> str | None:
    cur.execute(
        """
        SELECT id_bling FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'amazon' AND contexto = 'vendedor'
          AND entidade = 'produto' AND id_dropnexo = %s
        LIMIT 1
        """,
        (id_tenant, int(id_variante)),
    )
    row = cur.fetchone()
    return str(row[0]) if row and row[0] else None


def _ler_estoque_variante(cur, id_variante: int) -> int:
    cur.execute(
        "SELECT COALESCE(quantidade, 0) FROM tbl_produto_variante_estoque WHERE id_variante = %s",
        (int(id_variante),),
    )
    row = cur.fetchone()
    return int(row[0] or 0) if row else 0


def _tenants_vendedor_para_variante(cur, id_variante: int) -> list[int]:
    cur.execute(
        """
        SELECT DISTINCT pv.id_tenant_vendedor
        FROM tbl_produto_vendedor pv
        WHERE pv.id_variante = %s
        """,
        (int(id_variante),),
    )
    tenants = [int(r[0]) for r in cur.fetchall() if r and r[0]]
    cur.execute(
        """
        SELECT p.id_tenant FROM tbl_produto_variante v
        JOIN tbl_produto p ON p.id = v.id_produto
        WHERE v.id = %s
        """,
        (int(id_variante),),
    )
    row = cur.fetchone()
    if row and row[0]:
        tid = int(row[0])
        if tid not in tenants:
            tenants.append(tid)
    return tenants


def _dados_vitrine_variante_amazon(cur, id_tenant: int, id_variante: int) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT COALESCE(pv.preco_venda, v.preco, p.preco, 0),
               COALESCE(ve.quantidade, 0)
        FROM tbl_produto_variante v
        JOIN tbl_produto p ON p.id = v.id_produto
        LEFT JOIN tbl_produto_vendedor pv
            ON pv.id_variante = v.id AND pv.id_tenant_vendedor = %s
        LEFT JOIN tbl_produto_variante_estoque ve ON ve.id_variante = v.id
        WHERE v.id = %s
        LIMIT 1
        """,
        (id_tenant, int(id_variante)),
    )
    row = cur.fetchone()
    if not row:
        return None
    return {"preco": float(row[0] or 0), "estoque": int(row[1] or 0)}


def atualizar_estoque_amazon(
    cur,
    id_tenant: int,
    map_id: str,
    *,
    preco: float | None = None,
    quantidade: int | None = None,
) -> tuple[bool, str]:
    from api.amazon.amazon import _atualizar_estoque_map_amazon, amazon_conectado

    if not amazon_conectado(cur, id_tenant):
        return False, "Amazon não conectada."
    map_id = (map_id or "").strip()
    if not map_id:
        return False, "Produto Amazon não informado."
    if quantidade is None and preco is None:
        return True, ""
    try:
        _atualizar_estoque_map_amazon(
            cur,
            id_tenant,
            map_id,
            quantidade=int(quantidade or 0),
            preco=preco,
        )
        return True, ""
    except RuntimeError as e:
        return False, str(e)[:300]


def enviar_estoque_variante_amazon(
    cur,
    id_tenant: int,
    id_variante: int,
    *,
    quantidade: int | None = None,
) -> tuple[bool, str]:
    if amazon_sync_suprimido():
        return True, ""
    map_id = _amazon_map_por_variante(cur, id_tenant, int(id_variante))
    if not map_id:
        return True, ""
    qtd = int(quantidade) if quantidade is not None else _ler_estoque_variante(cur, int(id_variante))
    dados = _dados_vitrine_variante_amazon(cur, id_tenant, int(id_variante))
    preco = dados["preco"] if dados and dados.get("preco", 0) > 0 else None
    return atualizar_estoque_amazon(cur, id_tenant, map_id, quantidade=qtd, preco=preco)


def propagar_estoque_variante_amazon(
    cur,
    id_variante: int,
    *,
    id_tenant: int | None = None,
    quantidade: int | None = None,
) -> list[str]:
    """Envia estoque à Amazon para todos os vendedores com esta variante integrada."""
    if amazon_sync_suprimido():
        return []
    avisos: list[str] = []
    tenants = [int(id_tenant)] if id_tenant else _tenants_vendedor_para_variante(cur, int(id_variante))
    for tid in tenants:
        map_id = _amazon_map_por_variante(cur, tid, int(id_variante))
        if not map_id:
            continue
        ok, msg = enviar_estoque_variante_amazon(
            cur, tid, int(id_variante), quantidade=quantidade
        )
        if not ok and msg:
            avisos.append(msg)
    return avisos


def propagar_produto_amazon_apos_salvar(
    cur,
    id_tenant: int,
    id_produto: int,
    *,
    id_variante: int | None = None,
) -> str | None:
    """Atualiza preço e estoque na Amazon após salvar produto/variação na vitrine."""
    from api.amazon.amazon import amazon_conectado, carregar_config_amazon

    cfg = carregar_config_amazon(cur, id_tenant)
    if amazon_sync_suprimido() or not amazon_conectado(cur, id_tenant):
        return None
    if not cfg.get("estoque_sync_ativo") and not cfg.get("produtos_exportar_auto"):
        return None

    variantes: list[int] = []
    if id_variante:
        variantes = [int(id_variante)]
    else:
        cur.execute(
            """
            SELECT pv.id_variante FROM tbl_produto_vendedor pv
            WHERE pv.id_tenant_vendedor = %s AND pv.id_produto = %s
            """,
            (id_tenant, int(id_produto)),
        )
        variantes = [int(r[0]) for r in cur.fetchall() if r and r[0]]
        if not variantes:
            cur.execute(
                "SELECT id_variante_padrao FROM tbl_produto WHERE id = %s",
                (int(id_produto),),
            )
            row = cur.fetchone()
            if row and row[0]:
                variantes = [int(row[0])]

    erros: list[str] = []
    for vid in variantes:
        map_id = _amazon_map_por_variante(cur, id_tenant, vid)
        if not map_id:
            continue
        dados = _dados_vitrine_variante_amazon(cur, id_tenant, vid)
        if not dados:
            continue
        ok, msg = atualizar_estoque_amazon(
            cur,
            id_tenant,
            map_id,
            preco=dados["preco"] if dados["preco"] > 0 else None,
            quantidade=dados["estoque"],
        )
        if not ok and msg:
            erros.append(msg)

    if not erros:
        return None
    return erros[0][:300]


def sincronizar_todos_estoques_amazon(cur, id_tenant: int) -> dict:
    from api.amazon.amazon import amazon_conectado, carregar_config_amazon

    if not amazon_conectado(cur, id_tenant):
        raise RuntimeError("Amazon não conectada.")
    cfg = carregar_config_amazon(cur, id_tenant)
    if not cfg.get("estoque_sync_ativo"):
        raise RuntimeError("Ative a sincronização de estoque em Integrações → Amazon.")

    cur.execute(
        """
        SELECT m.id_dropnexo, m.id_bling
        FROM tbl_integracao_map m
        WHERE m.id_tenant = %s AND m.provedor = 'amazon'
          AND m.contexto = 'vendedor' AND m.entidade = 'produto'
        ORDER BY m.id_dropnexo
        """,
        (id_tenant,),
    )
    rows = cur.fetchall()
    atualizados = 0
    erros: list[str] = []
    for id_variante, map_id in rows:
        ok, msg = enviar_estoque_variante_amazon(cur, id_tenant, int(id_variante))
        if ok:
            atualizados += 1
        elif msg:
            erros.append(msg)

    msg = f"{atualizados} produto(s) com estoque atualizado na Amazon."
    if erros:
        msg += f" {len(erros)} falha(s)."
    return {
        "message": msg,
        "atualizados": atualizados,
        "total_mapeados": len(rows),
        "detalhes_erros": erros[:5],
    }


def baixar_estoque_pedido_amazon(
    cur,
    id_tenant: int,
    id_variante: int,
    quantidade: int,
) -> None:
    """Reduz estoque local por venda na Amazon — sem reenviar à Amazon (anti-eco)."""
    from api.amazon.eco_estoque import suprimir_sync_amazon

    if quantidade <= 0:
        return
    with suprimir_sync_amazon():
        cur.execute(
            """
            INSERT INTO tbl_produto_variante_estoque (id_variante, quantidade, atualizado_em)
            VALUES (%s, 0, NOW())
            ON CONFLICT (id_variante) DO NOTHING
            """,
            (int(id_variante),),
        )
        cur.execute(
            """
            UPDATE tbl_produto_variante_estoque
            SET quantidade = GREATEST(0, quantidade - %s),
                atualizado_em = NOW()
            WHERE id_variante = %s
            """,
            (int(quantidade), int(id_variante)),
        )
