"""Sincronização DropNexo → Mercado Livre (estoque e dados do anúncio)."""
from __future__ import annotations

import logging
from typing import Any

from api.mercado_livre.eco_estoque import ml_sync_suprimido, registrar_eco_ml_pendente

_log = logging.getLogger(__name__)


def _variante_por_ml_item(cur, id_tenant: int, ml_item_id: str) -> int | None:
    cur.execute(
        """
        SELECT id_dropnexo FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'mercado_livre' AND contexto = 'vendedor'
          AND entidade = 'produto' AND id_bling = %s
        LIMIT 1
        """,
        (id_tenant, str(ml_item_id)),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] else None


def _ml_item_por_variante(cur, id_tenant: int, id_variante: int) -> str | None:
    from api.mercado_livre.mercado_livre import _item_ja_vinculado_ml

    return _item_ja_vinculado_ml(cur, id_tenant, int(id_variante))


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


def _dados_vitrine_variante_ml(cur, id_tenant: int, id_variante: int) -> dict[str, Any] | None:
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


def atualizar_anuncio_ml(
    cur,
    id_tenant: int,
    ml_item_id: str,
    *,
    preco: float | None = None,
    quantidade: int | None = None,
) -> tuple[bool, str]:
    from api.mercado_livre.mercado_livre import api_request, ml_conectado

    if not ml_conectado(cur, id_tenant):
        return False, "Mercado Livre não conectado."
    ml_item_id = (ml_item_id or "").strip()
    if not ml_item_id:
        return False, "Anúncio ML não informado."

    payload: dict[str, Any] = {}
    if preco is not None and float(preco) > 0:
        payload["price"] = round(float(preco), 2)
    if quantidade is not None:
        payload["available_quantity"] = max(0, int(quantidade))

    if not payload:
        return True, ""

    if quantidade is not None:
        registrar_eco_ml_pendente(
            cur,
            id_tenant,
            ml_item_id=ml_item_id,
            quantidade_esperada=max(0, int(quantidade)),
            origem="dropnexo_estoque",
        )

    try:
        api_request(cur, id_tenant, "PUT", f"/items/{ml_item_id}", json_body=payload)
        return True, ""
    except RuntimeError as e:
        return False, str(e)[:300]


def enviar_estoque_variante_ml(
    cur,
    id_tenant: int,
    id_variante: int,
    *,
    quantidade: int | None = None,
) -> tuple[bool, str]:
    if ml_sync_suprimido():
        return True, ""
    ml_item = _ml_item_por_variante(cur, id_tenant, int(id_variante))
    if not ml_item:
        return True, ""
    qtd = int(quantidade) if quantidade is not None else _ler_estoque_variante(cur, int(id_variante))
    return atualizar_anuncio_ml(cur, id_tenant, ml_item, quantidade=qtd)


def propagar_estoque_variante_ml(
    cur,
    id_variante: int,
    *,
    id_tenant: int | None = None,
    quantidade: int | None = None,
) -> list[str]:
    """Envia estoque ao ML para todos os vendedores com esta variante integrada."""
    if ml_sync_suprimido():
        return []
    avisos: list[str] = []
    tenants = [int(id_tenant)] if id_tenant else _tenants_vendedor_para_variante(cur, int(id_variante))
    for tid in tenants:
        ml_item = _ml_item_por_variante(cur, tid, int(id_variante))
        if not ml_item:
            continue
        ok, msg = enviar_estoque_variante_ml(
            cur, tid, int(id_variante), quantidade=quantidade
        )
        if not ok and msg:
            avisos.append(msg)
    return avisos


def propagar_produto_ml_apos_salvar(
    cur,
    id_tenant: int,
    id_produto: int,
    *,
    id_variante: int | None = None,
) -> str | None:
    """Atualiza preço e estoque no ML após salvar produto/variação na vitrine."""
    from api.mercado_livre.mercado_livre import ml_conectado

    if ml_sync_suprimido() or not ml_conectado(cur, id_tenant):
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
        ml_item = _ml_item_por_variante(cur, id_tenant, vid)
        if not ml_item:
            continue
        dados = _dados_vitrine_variante_ml(cur, id_tenant, vid)
        if not dados:
            continue
        ok, msg = atualizar_anuncio_ml(
            cur,
            id_tenant,
            ml_item,
            preco=dados["preco"] if dados["preco"] > 0 else None,
            quantidade=dados["estoque"],
        )
        if not ok and msg:
            erros.append(msg)

    if not erros:
        return None
    return erros[0][:300]


def sincronizar_todos_estoques_ml(cur, id_tenant: int) -> dict:
    from api.mercado_livre.mercado_livre import carregar_config_ml, ml_conectado

    if not ml_conectado(cur, id_tenant):
        raise RuntimeError("Mercado Livre não conectado.")

    cur.execute(
        """
        SELECT m.id_dropnexo, m.id_bling
        FROM tbl_integracao_map m
        WHERE m.id_tenant = %s AND m.provedor = 'mercado_livre'
          AND m.contexto = 'vendedor' AND m.entidade = 'produto'
        ORDER BY m.id_dropnexo
        """,
        (id_tenant,),
    )
    rows = cur.fetchall()
    atualizados = 0
    erros: list[str] = []
    for id_variante, ml_item in rows:
        ok, msg = enviar_estoque_variante_ml(cur, id_tenant, int(id_variante))
        if ok:
            atualizados += 1
        elif msg:
            erros.append(msg)

    cfg = carregar_config_ml(cur, id_tenant)
    msg = f"{atualizados} anúncio(s) com estoque atualizado no Mercado Livre."
    if erros:
        msg += f" {len(erros)} falha(s)."
    return {
        "message": msg,
        "atualizados": atualizados,
        "total_mapeados": len(rows),
        "detalhes_erros": erros[:5],
    }


def baixar_estoque_pedido_ml(
    cur,
    id_tenant: int,
    id_variante: int,
    quantidade: int,
) -> None:
    """Reduz estoque local por venda no ML — sem reenviar ao ML (anti-eco)."""
    from api.mercado_livre.eco_estoque import suprimir_sync_ml

    if quantidade <= 0:
        return
    with suprimir_sync_ml():
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
