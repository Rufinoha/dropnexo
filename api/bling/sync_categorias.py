# api/bling/sync_categorias.py — categorias Bling → DropNexo
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from api.bling.cliente import listar_categorias_produtos, obter_categoria_produto
from global_utils import agora_utc

MAX_NIVEL = 3


def _buscar_mapa_categoria(cur, id_tenant: int, contexto: str, id_bling: str) -> int | None:
    cur.execute(
        """
        SELECT id_dropnexo FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND contexto = %s
          AND entidade = 'categoria' AND id_bling = %s
        """,
        (id_tenant, contexto, id_bling),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] else None


def _upsert_mapa_categoria(
    cur,
    id_tenant: int,
    contexto: str,
    id_bling: str,
    id_dropnexo: int,
    meta: dict,
) -> None:
    cur.execute(
        """
        INSERT INTO tbl_integracao_map (
            id_tenant, provedor, contexto, entidade, id_bling, id_dropnexo, sku, meta, atualizado_em
        ) VALUES (%s, 'bling', %s, 'categoria', %s, %s, NULL, %s::jsonb, %s)
        ON CONFLICT (id_tenant, provedor, contexto, entidade, id_bling) DO UPDATE SET
            id_dropnexo = EXCLUDED.id_dropnexo,
            meta = EXCLUDED.meta,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (id_tenant, contexto, id_bling, id_dropnexo, json.dumps(meta), agora_utc()),
    )


def _id_pai_bling(cat: dict) -> str | None:
    pai = cat.get("categoriaPai") or {}
    pid = str(pai.get("id") or "").strip()
    if not pid or pid == "0":
        return None
    return pid


def garantir_categoria_bling(
    cur,
    id_tenant: int,
    contexto: str,
    id_bling: str,
    *,
    cache_api: dict[str, dict] | None = None,
) -> int | None:
    """Cria ou atualiza categoria no DropNexo a partir do ID Bling (com pais recursivos)."""
    id_bling = str(id_bling or "").strip()
    if not id_bling:
        return None

    existente = _buscar_mapa_categoria(cur, id_tenant, contexto, id_bling)
    if existente:
        return existente

    if cache_api and id_bling in cache_api:
        cat = cache_api[id_bling]
    else:
        cat = obter_categoria_produto(id_tenant, id_bling)
        if cache_api is not None:
            cache_api[id_bling] = cat

    nome = (cat.get("descricao") or f"Categoria Bling {id_bling}").strip()[:120]
    if not nome:
        return None

    parent_bling = _id_pai_bling(cat)
    parent_dropnexo = None
    nivel = 1
    if parent_bling:
        parent_dropnexo = garantir_categoria_bling(
            cur, id_tenant, contexto, parent_bling, cache_api=cache_api
        )
        if parent_dropnexo:
            cur.execute("SELECT nivel FROM tbl_categoria WHERE id = %s", (parent_dropnexo,))
            row = cur.fetchone()
            nivel = min(int(row[0] or 1) + 1, MAX_NIVEL) if row else 2

    cur.execute(
        """
        SELECT c.id FROM tbl_categoria c
        WHERE c.id_tenant = %s
          AND COALESCE(c.id_segmento, 0) = 0
          AND COALESCE(c.parent_id, 0) = COALESCE(%s, 0)
          AND LOWER(c.nome) = LOWER(%s)
        LIMIT 1
        """,
        (id_tenant, parent_dropnexo, nome),
    )
    row = cur.fetchone()
    if row:
        cat_id = int(row[0])
        cur.execute(
            "UPDATE tbl_categoria SET ativo = TRUE, nivel = %s WHERE id = %s",
            (nivel, cat_id),
        )
    else:
        cur.execute(
            """
            INSERT INTO tbl_categoria (
                id_tenant, id_segmento, parent_id, nome, ordem, nivel, ativo
            ) VALUES (%s, NULL, %s, %s, 0, %s, TRUE)
            RETURNING id
            """,
            (id_tenant, parent_dropnexo, nome, nivel),
        )
        cat_id = int(cur.fetchone()[0])

    _upsert_mapa_categoria(
        cur,
        id_tenant,
        contexto,
        id_bling,
        cat_id,
        {"nome": nome, "id_bling_pai": parent_bling},
    )
    return cat_id


def listar_categorias_bling_flat(id_tenant: int) -> list[dict[str, Any]]:
    """Lista categorias do Bling em ordem de árvore para o select da UI."""
    todas: list[dict] = []
    pagina = 1
    while True:
        lote = listar_categorias_produtos(id_tenant, pagina=pagina, limite=100)
        if not lote:
            break
        todas.extend(lote)
        if len(lote) < 100:
            break
        pagina += 1

    by_id: dict[str, dict] = {}
    for c in todas:
        cid = str(c.get("id") or "").strip()
        if cid:
            by_id[cid] = c

    filhos: dict[str, list[str]] = defaultdict(list)
    raizes: list[str] = []
    for cid, c in by_id.items():
        pai = _id_pai_bling(c)
        if pai and pai in by_id:
            filhos[pai].append(cid)
        else:
            raizes.append(cid)

    def ordenar(ids: list[str]) -> list[str]:
        return sorted(ids, key=lambda i: (by_id[i].get("descricao") or "").lower())

    def percorrer(cid: str, profundidade: int) -> list[dict[str, Any]]:
        cat = by_id[cid]
        nome = (cat.get("descricao") or f"Categoria {cid}").strip()
        prefixo = "— " * profundidade if profundidade else ""
        out = [
            {
                "id": cid,
                "nome": nome,
                "label": f"{prefixo}{nome}",
                "nivel": profundidade + 1,
            }
        ]
        for filho in ordenar(filhos.get(cid, [])):
            out.extend(percorrer(filho, profundidade + 1))
        return out

    resultado: list[dict[str, Any]] = []
    for rid in ordenar(raizes):
        resultado.extend(percorrer(rid, 0))
    return resultado


def ids_categoria_bling_com_descendentes(
    id_tenant: int,
    id_raiz: str,
    *,
    incluir_subcategorias: bool,
) -> set[str]:
    raiz = str(id_raiz or "").strip()
    if not raiz:
        return set()

    permitidos = {raiz}
    if not incluir_subcategorias:
        return permitidos

    todas: list[dict] = []
    pagina = 1
    while True:
        lote = listar_categorias_produtos(id_tenant, pagina=pagina, limite=100)
        if not lote:
            break
        todas.extend(lote)
        if len(lote) < 100:
            break
        pagina += 1

    filhos: dict[str, list[str]] = defaultdict(list)
    for c in todas:
        cid = str(c.get("id") or "").strip()
        if not cid:
            continue
        pai = _id_pai_bling(c)
        if pai:
            filhos[pai].append(cid)

    fila = [raiz]
    while fila:
        atual = fila.pop(0)
        for ch in filhos.get(atual, []):
            if ch not in permitidos:
                permitidos.add(ch)
                fila.append(ch)
    return permitidos


def extrair_id_categoria_produto(produto: dict) -> str | None:
    cat = produto.get("categoria")
    if not isinstance(cat, dict):
        return None
    cid = str(cat.get("id") or "").strip()
    return cid or None
