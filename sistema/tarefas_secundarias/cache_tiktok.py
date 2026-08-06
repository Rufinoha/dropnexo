# sistema/tarefas_secundarias/cache_tiktok.py — cache de categorias folha TikTok Shop
from __future__ import annotations

import logging
import time
from typing import Any, Callable

from global_utils import agora_utc

_log = logging.getLogger(__name__)

CODIGO_TIKTOK_CATEGORIAS = "tiktok_categorias_cache"


def garantir_tabela_tiktok_categoria_cache(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_tiktok_categoria_cache (
            id SERIAL PRIMARY KEY,
            region VARCHAR(16) NOT NULL DEFAULT 'BR',
            category_id VARCHAR(64) NOT NULL,
            nome VARCHAR(255) NOT NULL,
            path_nomes TEXT NOT NULL DEFAULT '',
            path_ids TEXT NOT NULL DEFAULT '',
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (region, category_id)
        )
        """
    )


def tenant_tiktok_conectado(cur) -> int:
    cur.execute(
        """
        SELECT id_tenant
        FROM tbl_integracao_tiktok
        WHERE status = 'conectado'
        ORDER BY atualizado_em DESC NULLS LAST
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            "Nenhuma conta TikTok Shop conectada. Conecte uma conta e tente de novo."
        )
    return int(row[0])


def region_tiktok_para_cache(cur, id_tenant: int) -> str:
    cur.execute(
        """
        SELECT shop_info FROM tbl_integracao_tiktok
        WHERE id_tenant = %s
        LIMIT 1
        """,
        (id_tenant,),
    )
    row = cur.fetchone()
    info = row[0] if row else None
    if isinstance(info, str):
        import json

        try:
            info = json.loads(info)
        except Exception:
            info = {}
    if isinstance(info, dict):
        for key in ("region", "shop_region", "country", "country_code"):
            val = str(info.get(key) or "").strip().upper()
            if val:
                return val[:16]
    return "BR"


def _nome_cat(node: dict) -> str:
    return str(
        node.get("local_name")
        or node.get("name")
        or node.get("category_name")
        or ""
    ).strip()


def _id_cat(node: dict) -> str:
    return str(node.get("id") or node.get("category_id") or "").strip()


def _is_leaf(node: dict) -> bool:
    if "is_leaf" in node:
        return bool(node.get("is_leaf"))
    children = node.get("children") or node.get("child_categories") or []
    return not children


def _coletar_folhas_de_lista(
    cats: list,
    log: list[str],
    *,
    on_progress: Callable | None = None,
) -> list[tuple[str, str, str, str]]:
    """Aceita lista plana (parent_id) ou árvore aninhada."""
    folhas: list[tuple[str, str, str, str]] = []
    by_id: dict[str, dict] = {}
    children_map: dict[str, list[str]] = {}
    nested = False

    for raw in cats:
        if not isinstance(raw, dict):
            continue
        # Formato aninhado {self, children} ou nó com children
        node = raw.get("self") if isinstance(raw.get("self"), dict) else raw
        if not isinstance(node, dict):
            continue
        cid = _id_cat(node)
        if not cid:
            continue
        by_id[cid] = node
        kids = raw.get("children") or node.get("children") or node.get("child_categories")
        if isinstance(kids, list) and kids:
            nested = True
            # processa recursivo depois
            pass

    if nested or any(
        isinstance(c, dict)
        and (c.get("children") or (isinstance(c.get("self"), dict) and c.get("children")))
        for c in cats
    ):

        def walk(nodes: list, path_n: list[str], path_i: list[str]) -> None:
            for raw in nodes or []:
                if not isinstance(raw, dict):
                    continue
                node = raw.get("self") if isinstance(raw.get("self"), dict) else raw
                if not isinstance(node, dict):
                    continue
                cid = _id_cat(node)
                nome = _nome_cat(node)
                if not cid:
                    continue
                if not nome:
                    log.append(f"IGNORADO sem nome: {cid}")
                    continue
                pn = path_n + [nome]
                pi = path_i + [cid]
                kids = raw.get("children") or node.get("children") or node.get("child_categories") or []
                if not isinstance(kids, list):
                    kids = []
                if kids and not _is_leaf(node):
                    walk(kids, pn, pi)
                else:
                    folhas.append((cid, nome, " > ".join(pn), " / ".join(pi)))

        walk(cats, [], [])
        if on_progress:
            on_progress(
                {"fase": "baixando", "folhas": len(folhas), "pct": 80},
                f"TikTok: {len(folhas)} categorias folha coletadas",
            )
        return folhas

    # Lista plana com parent_id
    for node in by_id.values():
        pid = str(node.get("parent_id") or node.get("parent_category_id") or "0").strip()
        children_map.setdefault(pid, []).append(_id_cat(node))

    def path_of(cid: str) -> tuple[list[str], list[str]]:
        nomes: list[str] = []
        ids: list[str] = []
        cur_id = cid
        guard = 0
        while cur_id and cur_id not in ("0", "") and guard < 20:
            n = by_id.get(cur_id)
            if not n:
                break
            nomes.insert(0, _nome_cat(n) or cur_id)
            ids.insert(0, cur_id)
            cur_id = str(n.get("parent_id") or n.get("parent_category_id") or "0").strip()
            guard += 1
        return nomes, ids

    for cid, node in by_id.items():
        if not _is_leaf(node) and children_map.get(cid):
            continue
        # folha: is_leaf True ou sem filhos no mapa
        if children_map.get(cid):
            continue
        nome = _nome_cat(node)
        if not nome:
            log.append(f"IGNORADO sem nome: {cid}")
            continue
        pn, pi = path_of(cid)
        folhas.append((cid, nome, " > ".join(pn), " / ".join(pi)))

    if on_progress:
        on_progress(
            {"fase": "baixando", "folhas": len(folhas), "pct": 80},
            f"TikTok: {len(folhas)} categorias folha coletadas",
        )
    return folhas


def _gravar_folhas(cur, region: str, folhas: list[tuple[str, str, str, str]]) -> None:
    region = (region or "BR").upper()[:16]
    cur.execute("DELETE FROM tbl_tiktok_categoria_cache WHERE region = %s", (region,))
    agora = agora_utc()
    for cat_id, nome, path_n, path_i in folhas:
        cur.execute(
            """
            INSERT INTO tbl_tiktok_categoria_cache (
                region, category_id, nome, path_nomes, path_ids, atualizado_em
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (region, category_id) DO UPDATE SET
                nome = EXCLUDED.nome,
                path_nomes = EXCLUDED.path_nomes,
                path_ids = EXCLUDED.path_ids,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (region, cat_id, nome[:255], path_n, path_i, agora),
        )


def sincronizar_cache_categorias_tiktok(
    cur,
    *,
    conn=None,
    id_exec: int | None = None,
    atualizar_progresso=None,
) -> dict:
    from api.tiktok.tiktok import api_request

    garantir_tabela_tiktok_categoria_cache(cur)
    id_tenant = tenant_tiktok_conectado(cur)
    region = region_tiktok_para_cache(cur, id_tenant)
    if conn is not None:
        conn.commit()

    log: list[str] = [f"=== TikTok region {region} (tenant #{id_tenant}) ==="]

    def prog(meta: dict, mensagem: str) -> None:
        if atualizar_progresso:
            atualizar_progresso(cur, conn, id_exec, mensagem, meta)

    prog({"fase": "inicio", "pct": 5, "region": region}, "Baixando categorias TikTok Shop…")

    try:
        data = api_request(
            cur,
            id_tenant,
            "GET",
            "/product/202309/categories",
            params={"locale": "pt-BR"},
        )
    except Exception as e:
        raise RuntimeError(f"Falha ao listar categorias TikTok: {e}") from e

    cats: list = []
    if isinstance(data, dict):
        cats = data.get("categories") or data.get("category_list") or []
    elif isinstance(data, list):
        cats = data
    if not isinstance(cats, list):
        cats = []

    log.append(f"API retornou {len(cats)} nó(s) raiz/itens.")
    folhas = _coletar_folhas_de_lista(cats, log, on_progress=lambda m, msg: prog(m, msg))
    prog(
        {"fase": "gravando", "pct": 90, "folhas": len(folhas), "region": region},
        f"Gravando {len(folhas)} categorias no cache…",
    )
    _gravar_folhas(cur, region, folhas)
    if conn is not None:
        conn.commit()

    msg = f"{len(folhas)} categorias TikTok em cache (region {region})."
    log.append(msg)
    log_texto = "\n".join(log)
    if len(folhas) <= 0:
        from sistema.tarefas_secundarias.servico import TarefaSecundariaErro

        raise TarefaSecundariaErro(
            "Cache de categorias TikTok ficou vazio. Confira a conta conectada.",
            log_texto=log_texto,
        )
    prog({"fase": "ok", "pct": 100, "folhas": len(folhas)}, msg)
    time.sleep(0.01)
    return {
        "folhas": len(folhas),
        "ignoradas_sem_nome": 0,
        "erros_site": 0,
        "sites": [region],
        "mensagem": msg,
        "log_texto": log_texto,
    }


def buscar_categorias_cache_tiktok(
    cur, region: str, termo: str, limit: int = 40
) -> list[dict]:
    garantir_tabela_tiktok_categoria_cache(cur)
    region = (region or "BR").upper()[:16]
    termo = (termo or "").strip()
    lim = max(1, min(int(limit or 40), 80))
    if len(termo) < 2:
        cur.execute(
            """
            SELECT category_id, nome, path_nomes
            FROM tbl_tiktok_categoria_cache
            WHERE region = %s
            ORDER BY nome
            LIMIT %s
            """,
            (region, lim),
        )
    else:
        like = f"%{termo}%"
        cur.execute(
            """
            SELECT category_id, nome, path_nomes
            FROM tbl_tiktok_categoria_cache
            WHERE region = %s
              AND (nome ILIKE %s OR path_nomes ILIKE %s OR category_id ILIKE %s)
            ORDER BY
              CASE WHEN lower(nome) = lower(%s) THEN 0
                   WHEN lower(nome) LIKE lower(%s) THEN 1
                   ELSE 2 END,
              nome
            LIMIT %s
            """,
            (region, like, like, like, termo, f"{termo}%", lim),
        )
    return [
        {"category_id": str(r[0]), "nome": r[1], "path_nomes": r[2] or ""}
        for r in cur.fetchall()
        if r[1]
    ]


def nome_categoria_cache_tiktok(cur, region: str, category_id: str) -> str:
    garantir_tabela_tiktok_categoria_cache(cur)
    cur.execute(
        """
        SELECT nome FROM tbl_tiktok_categoria_cache
        WHERE region = %s AND category_id = %s
        LIMIT 1
        """,
        ((region or "BR").upper()[:16], (category_id or "").strip()),
    )
    row = cur.fetchone()
    return (row[0] or "").strip() if row else ""
