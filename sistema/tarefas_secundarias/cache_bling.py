# sistema/tarefas_secundarias/cache_bling.py — cache de categorias Bling (doador)
from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from global_utils import agora_utc

_log = logging.getLogger(__name__)

CODIGO_BLING_CATEGORIAS = "bling_categorias_cache"


def garantir_tabela_bling_categoria_cache(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_bling_categoria_cache (
            id SERIAL PRIMARY KEY,
            category_id VARCHAR(64) NOT NULL,
            nome VARCHAR(255) NOT NULL,
            path_nomes TEXT NOT NULL DEFAULT '',
            parent_id VARCHAR(64) NOT NULL DEFAULT '',
            is_leaf BOOLEAN NOT NULL DEFAULT TRUE,
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (category_id)
        )
        """
    )


def _id_pai(cat: dict) -> str:
    for key in ("categoriaPai", "categoria_pai", "parent"):
        raw = cat.get(key)
        if isinstance(raw, dict):
            return str(raw.get("id") or "").strip()
        if raw not in (None, ""):
            return str(raw).strip()
    return ""


def sincronizar_cache_categorias_bling(
    cur,
    *,
    id_tenant: int | None = None,
    conn=None,
    id_exec: int | None = None,
    atualizar_progresso=None,
) -> dict:
    from api.bling.categorias_bling import carregar_mapa_categorias_bling_listagem
    from sistema.tarefas_secundarias.doador import obter_ou_promover_doador

    garantir_tabela_bling_categoria_cache(cur)
    tid = int(id_tenant) if id_tenant else obter_ou_promover_doador(cur, CODIGO_BLING_CATEGORIAS)
    if not tid:
        raise RuntimeError(
            "Nenhuma conta Bling conectada. O cache será preenchido quando o 1º vendedor conectar."
        )
    if conn is not None:
        conn.commit()

    log: list[str] = [f"=== Bling doador tenant #{tid} ==="]

    def prog(meta: dict, mensagem: str) -> None:
        if atualizar_progresso:
            atualizar_progresso(cur, conn, id_exec, mensagem, meta)

    prog({"fase": "inicio", "pct": 5, "id_tenant": tid}, "Baixando categorias Bling…")

    by_id = carregar_mapa_categorias_bling_listagem(tid)
    log.append(f"API retornou {len(by_id)} categoria(s).")

    filhos: dict[str, list[str]] = defaultdict(list)
    for cid, cat in by_id.items():
        pai = _id_pai(cat)
        if pai and pai in by_id:
            filhos[pai].append(cid)

    def path_of(cid: str) -> tuple[str, str]:
        nomes: list[str] = []
        ids: list[str] = []
        cur_id = cid
        guard = 0
        while cur_id and guard < 30:
            cat = by_id.get(cur_id)
            if not cat:
                break
            nome = (cat.get("descricao") or cat.get("nome") or cur_id).strip()
            nomes.insert(0, nome)
            ids.insert(0, cur_id)
            cur_id = _id_pai(cat)
            if cur_id and cur_id not in by_id:
                break
            guard += 1
        return " > ".join(nomes), " / ".join(ids)

    folhas: list[tuple[str, str, str, str, bool]] = []
    for i, (cid, cat) in enumerate(by_id.items()):
        nome = (cat.get("descricao") or cat.get("nome") or cid).strip()
        if not nome:
            continue
        pn, _pi = path_of(cid)
        is_leaf = not filhos.get(cid)
        folhas.append((cid, nome[:255], pn, _id_pai(cat), is_leaf))
        if i % 40 == 0:
            prog(
                {"fase": "baixando", "pct": min(80, 10 + int(i / max(len(by_id), 1) * 70)), "folhas": len(folhas)},
                f"Bling: processando {i}/{len(by_id)}…",
            )

    prog(
        {"fase": "gravando", "pct": 90, "folhas": len(folhas)},
        f"Gravando {len(folhas)} categorias no cache…",
    )
    cur.execute("DELETE FROM tbl_bling_categoria_cache")
    agora = agora_utc()
    for cid, nome, path_n, parent_id, is_leaf in folhas:
        cur.execute(
            """
            INSERT INTO tbl_bling_categoria_cache (
                category_id, nome, path_nomes, parent_id, is_leaf, atualizado_em
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (category_id) DO UPDATE SET
                nome = EXCLUDED.nome,
                path_nomes = EXCLUDED.path_nomes,
                parent_id = EXCLUDED.parent_id,
                is_leaf = EXCLUDED.is_leaf,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (cid, nome, path_n, parent_id or "", is_leaf, agora),
        )
    if conn is not None:
        conn.commit()

    msg = f"{len(folhas)} categorias Bling em cache (doador #{tid})."
    log.append(msg)
    if len(folhas) <= 0:
        from sistema.tarefas_secundarias.servico import TarefaSecundariaErro

        raise TarefaSecundariaErro(msg, log_texto="\n".join(log))
    prog({"fase": "ok", "pct": 100, "folhas": len(folhas)}, msg)
    return {
        "folhas": len(folhas),
        "ignoradas_sem_nome": 0,
        "erros_site": 0,
        "sites": [str(tid)],
        "mensagem": msg,
        "log_texto": "\n".join(log),
    }


def buscar_categorias_cache_bling(cur, termo: str, limit: int = 40) -> list[dict]:
    garantir_tabela_bling_categoria_cache(cur)
    termo = (termo or "").strip()
    lim = max(1, min(int(limit or 40), 80))
    if len(termo) < 2:
        cur.execute(
            """
            SELECT category_id, nome, path_nomes
            FROM tbl_bling_categoria_cache
            WHERE is_leaf = TRUE
            ORDER BY nome
            LIMIT %s
            """,
            (lim,),
        )
    else:
        like = f"%{termo}%"
        cur.execute(
            """
            SELECT category_id, nome, path_nomes
            FROM tbl_bling_categoria_cache
            WHERE (nome ILIKE %s OR path_nomes ILIKE %s OR category_id ILIKE %s)
            ORDER BY
              CASE WHEN lower(nome) = lower(%s) THEN 0
                   WHEN lower(nome) LIKE lower(%s) THEN 1
                   ELSE 2 END,
              nome
            LIMIT %s
            """,
            (like, like, like, termo, f"{termo}%", lim),
        )
    return [
        {"category_id": str(r[0]), "nome": r[1], "path_nomes": r[2] or ""}
        for r in cur.fetchall()
        if r[1]
    ]
