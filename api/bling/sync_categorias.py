# api/bling/sync_categorias.py — categorias Bling → DropNexo
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

from api.bling.cliente import listar_categorias_produtos, obter_categoria_produto
from fornecedor.segmentos.servico_segmentos import ids_segmentos_fornecedor
from global_utils import agora_utc

MAX_NIVEL = 3


def resolver_id_segmento_import(
    cur,
    id_tenant: int,
    id_segmento: int | None = None,
) -> int | None:
    """Um segmento ativo → usa direto; vários → None (associar depois na tela)."""
    if id_segmento:
        cur.execute(
            """
            SELECT 1 FROM tbl_fornecedor_segmento fs
            JOIN tbl_segmento s ON s.id = fs.id_segmento AND s.ativo = TRUE
            WHERE fs.id_tenant = %s AND fs.id_segmento = %s
            """,
            (id_tenant, int(id_segmento)),
        )
        if not cur.fetchone():
            raise ValueError("Segmento não está ativo para esta conta.")
        return int(id_segmento)
    ids = ids_segmentos_fornecedor(cur, id_tenant)
    if len(ids) == 1:
        return ids[0]
    return None


def _segmento_sql_val(id_segmento: int | None) -> int:
    return int(id_segmento) if id_segmento else 0


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


def _buscar_mapa_categoria_row(cur, id_tenant: int, contexto: str, id_bling: str) -> tuple[int | None, dict] | None:
    cur.execute(
        """
        SELECT id_dropnexo, meta FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND contexto = %s
          AND entidade = 'categoria' AND id_bling = %s
        """,
        (id_tenant, contexto, id_bling),
    )
    row = cur.fetchone()
    if not row:
        return None
    meta_raw = row[1]
    if isinstance(meta_raw, dict):
        meta = meta_raw
    elif meta_raw:
        try:
            meta = json.loads(meta_raw)
        except Exception:
            meta = {}
    else:
        meta = {}
    id_drop = int(row[0]) if row[0] else None
    return id_drop, meta


def categoria_bling_ignorada(cur, id_tenant: int, contexto: str, id_bling: str) -> bool:
    row = _buscar_mapa_categoria_row(cur, id_tenant, contexto, id_bling)
    if not row:
        return False
    _id_drop, meta = row
    return (meta.get("acao") or "").strip().lower() == "ignorar"


def obter_estado_mapeamento_categoria(
    cur,
    id_tenant: int,
    contexto: str,
    id_bling: str,
) -> dict[str, Any]:
    """Estado persistido do mapa: pendente | mapeada | ignorada."""
    row = _buscar_mapa_categoria_row(cur, id_tenant, contexto, id_bling)
    if not row:
        return {"status": "pendente", "acao": None, "id_dropnexo": None, "id_segmento": None}

    id_drop, meta = row
    acao = (meta.get("acao") or "").strip().lower()
    if acao == "ignorar":
        return {"status": "ignorada", "acao": "ignorar", "id_dropnexo": None, "id_segmento": None}

    if id_drop and _categoria_dropnexo_existe(cur, id_tenant, id_drop):
        cur.execute(
            "SELECT id_segmento, nome FROM tbl_categoria WHERE id = %s",
            (int(id_drop),),
        )
        cat_row = cur.fetchone()
        id_seg = int(cat_row[0]) if cat_row and cat_row[0] else None
        nome_dn = (cat_row[1] or "").strip() if cat_row else ""
        if not id_seg:
            return {
                "status": "pendente",
                "acao": acao or "vincular",
                "id_dropnexo": id_drop,
                "id_segmento": None,
                "nome_dropnexo": nome_dn,
                "motivo": "sem_segmento",
            }
        return {
            "status": "mapeada",
            "acao": acao or "vincular",
            "id_dropnexo": id_drop,
            "id_segmento": id_seg,
            "nome_dropnexo": nome_dn,
        }

    return {"status": "pendente", "acao": None, "id_dropnexo": None, "id_segmento": None}


def _categoria_dropnexo_existe(cur, id_tenant: int, cat_id: int) -> bool:
    cur.execute(
        "SELECT 1 FROM tbl_categoria WHERE id = %s AND id_tenant = %s AND ativo = TRUE",
        (int(cat_id), id_tenant),
    )
    return bool(cur.fetchone())


def _resolver_mapa_categoria_valido(cur, id_tenant: int, contexto: str, id_bling: str) -> int | None:
    """Mapa salvo cujo id_dropnexo ainda existe (ignora mapas órfãos)."""
    mapped = _buscar_mapa_categoria(cur, id_tenant, contexto, id_bling)
    if not mapped:
        return None
    if _categoria_dropnexo_existe(cur, id_tenant, mapped):
        return mapped
    return None


def _obter_nome_categoria_dropnexo(cur, cat_id: int) -> str:
    cur.execute("SELECT nome FROM tbl_categoria WHERE id = %s", (int(cat_id),))
    row = cur.fetchone()
    return (row[0] or "").strip() if row else ""


def _buscar_match_por_nome(
    cur,
    id_tenant: int,
    *,
    nome: str,
    parent_dropnexo: int | None,
    id_segmento: int | None,
) -> int | None:
    seg_val = _segmento_sql_val(id_segmento)
    cur.execute(
        """
        SELECT c.id FROM tbl_categoria c
        WHERE c.id_tenant = %s
          AND COALESCE(c.id_segmento, 0) = %s
          AND COALESCE(c.parent_id, 0) = COALESCE(%s, 0)
          AND LOWER(c.nome) = LOWER(%s)
          AND c.ativo = TRUE
        LIMIT 1
        """,
        (id_tenant, seg_val, parent_dropnexo, nome),
    )
    row = cur.fetchone()
    return int(row[0]) if row else None


def _fetch_categoria_bling(
    id_tenant: int,
    id_bling: str,
    cache_api: dict[str, dict],
) -> dict:
    id_bling = str(id_bling or "").strip()
    if id_bling in cache_api:
        return cache_api[id_bling]
    cat = obter_categoria_produto(id_tenant, id_bling)
    cache_api[id_bling] = cat
    return cat


def _ler_meta_mapa_categoria(cur, id_tenant: int, contexto: str, id_bling: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT meta FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND contexto = %s
          AND entidade = 'categoria' AND id_bling = %s
        """,
        (id_tenant, contexto, str(id_bling or "").strip()),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return {}
    raw = row[0]
    if isinstance(raw, dict):
        return raw
    try:
        return json.loads(raw)
    except Exception:
        return {}


def _fetch_categoria_bling_opcional(
    id_tenant: int,
    id_bling: str,
    cache_api: dict[str, dict],
) -> tuple[dict, str | None]:
    """Retorna (categoria, erro) — não interrompe o lote se o Bling responder 404."""
    id_bling = str(id_bling or "").strip()
    try:
        return _fetch_categoria_bling(id_tenant, id_bling, cache_api), None
    except Exception as exc:
        msg = str(exc).strip()
        low = msg.lower()
        if id_bling in cache_api:
            return cache_api[id_bling], None
        if "não encontrado" in low or "nao encontrado" in low or "404" in low or "not found" in low:
            return {}, msg
        raise


def _nome_categoria_bling(cat: dict, id_bling: str) -> str:
    return (cat.get("descricao") or f"Categoria Bling {id_bling}").strip()[:120]


def _caminho_categoria_bling_local(id_bling: str, by_id: dict[str, dict]) -> str:
    """Monta caminho usando apenas dados já carregados (sem GET por id)."""
    partes: list[str] = []
    atual = str(id_bling or "").strip()
    vistos: set[str] = set()
    while atual and atual not in vistos:
        vistos.add(atual)
        cat = by_id.get(atual) or {}
        partes.insert(0, _nome_categoria_bling(cat, atual))
        atual = _id_pai_bling(cat) or ""
    return " › ".join(partes)


def _caminho_categoria_bling(
    id_bling: str,
    cache_api: dict[str, dict],
    id_tenant: int,
) -> str:
    partes: list[str] = []
    atual = str(id_bling or "").strip()
    vistos: set[str] = set()
    while atual and atual not in vistos:
        vistos.add(atual)
        cat = cache_api.get(atual) if atual in cache_api else _fetch_categoria_bling(id_tenant, atual, cache_api)
        partes.insert(0, _nome_categoria_bling(cat, atual))
        atual = _id_pai_bling(cat) or ""
    return " › ".join(partes)


def expandir_ancestrais_categorias_bling(
    id_tenant: int,
    ids: set[str],
    cache_api: dict[str, dict],
) -> set[str]:
    out = set(ids)
    fila = list(ids)
    while fila:
        cid = fila.pop()
        cat = _fetch_categoria_bling(id_tenant, cid, cache_api)
        pai = _id_pai_bling(cat)
        if pai and pai not in out:
            out.add(pai)
            fila.append(pai)
    return out


def _ordenar_ids_categoria_bling(
    ids: set[str],
    cache_api: dict[str, dict],
    id_tenant: int,
) -> list[str]:
    niveis: dict[str, int] = {}

    def nivel(cid: str) -> int:
        if cid in niveis:
            return niveis[cid]
        cat = _fetch_categoria_bling(id_tenant, cid, cache_api)
        pai = _id_pai_bling(cat)
        n = 1 + (nivel(pai) if pai and pai in ids else 0) if pai else 1
        niveis[cid] = n
        return n

    for cid in ids:
        nivel(cid)
    return sorted(ids, key=lambda c: (niveis.get(c, 99), _nome_categoria_bling(cache_api.get(c, {}), c).lower()))


def _vincular_categoria_bling(
    cur,
    id_tenant: int,
    contexto: str,
    id_bling: str,
    id_dropnexo: int,
    *,
    meta: dict,
) -> None:
    _upsert_mapa_categoria(cur, id_tenant, contexto, id_bling, int(id_dropnexo), meta)


def _criar_categoria_do_bling(
    cur,
    id_tenant: int,
    contexto: str,
    id_bling: str,
    *,
    id_segmento: int | None,
    parent_dropnexo: int | None,
    cache_api: dict[str, dict] | None = None,
    meta_extra: dict | None = None,
) -> int | None:
    """Cria categoria DropNexo a partir do Bling e grava mapa."""
    cache = cache_api if cache_api is not None else {}
    id_bling = str(id_bling or "").strip()
    if not id_bling:
        return None

    cat = _fetch_categoria_bling(id_tenant, id_bling, cache)
    nome = _nome_categoria_bling(cat, id_bling)
    if not nome:
        return None

    parent_bling = _id_pai_bling(cat)
    nivel = 1
    if parent_dropnexo:
        cur.execute("SELECT nivel FROM tbl_categoria WHERE id = %s", (parent_dropnexo,))
        row = cur.fetchone()
        nivel = min(int(row[0] or 1) + 1, MAX_NIVEL) if row else 2

    cur.execute(
        """
        INSERT INTO tbl_categoria (
            id_tenant, id_segmento, parent_id, nome, ordem, nivel, ativo
        ) VALUES (%s, %s, %s, %s, 0, %s, TRUE)
        RETURNING id
        """,
        (id_tenant, id_segmento, parent_dropnexo, nome, nivel),
    )
    cat_id = int(cur.fetchone()[0])
    meta = {"nome": nome, "id_bling_pai": parent_bling, "origem": "criacao_importacao"}
    if meta_extra:
        meta.update(meta_extra)
    _upsert_mapa_categoria(
        cur,
        id_tenant,
        contexto,
        id_bling,
        cat_id,
        meta,
    )
    return cat_id


def _cadeia_ancestrais_bling(
    id_tenant: int,
    id_bling: str,
    cache_api: dict[str, dict],
) -> list[str]:
    """Raiz → folha na árvore Bling."""
    cadeia: list[str] = []
    atual = str(id_bling or "").strip()
    vistos: set[str] = set()
    while atual and atual not in vistos:
        vistos.add(atual)
        cadeia.insert(0, atual)
        cat = _fetch_categoria_bling(id_tenant, atual, cache_api)
        atual = _id_pai_bling(cat) or ""
    return cadeia


def criar_categoria_bling_com_arvore(
    cur,
    id_tenant: int,
    contexto: str,
    id_bling: str,
    *,
    id_segmento: int,
    cache_api: dict[str, dict] | None = None,
) -> int:
    """
    Cria a categoria e todos os ancestrais Bling ainda não mapeados,
    preservando a hierarquia do Bling (ex.: Carros › Acessórios › …).
    """
    cache = cache_api if cache_api is not None else {}
    id_bling = str(id_bling or "").strip()
    if not id_bling:
        raise ValueError("Categoria Bling inválida.")

    cadeia = _cadeia_ancestrais_bling(id_tenant, id_bling, cache)
    if not cadeia:
        raise ValueError("Categoria Bling inválida.")

    parent_drop: int | None = None
    cat_id: int | None = None
    meta_criar = {"acao": "criar", "origem": "integracao_ui"}

    for cid in cadeia:
        if categoria_bling_ignorada(cur, id_tenant, contexto, cid):
            cat = _fetch_categoria_bling(id_tenant, cid, cache)
            nome = _nome_categoria_bling(cat, cid)
            raise ValueError(
                f'Categoria Bling "{nome}" está marcada como Não importar — '
                "não é possível criar a árvore abaixo dela."
            )

        existente = _resolver_mapa_categoria_valido(cur, id_tenant, contexto, cid)
        if existente:
            cat = _fetch_categoria_bling(id_tenant, cid, cache)
            nome = _nome_categoria_bling(cat, cid)
            parent_bling = _id_pai_bling(cat)
            cur.execute("SELECT nivel FROM tbl_categoria WHERE id = %s", (parent_drop,))
            row = cur.fetchone()
            nivel = min(int(row[0] or 1) + 1, MAX_NIVEL) if parent_drop and row else 1
            _atualizar_categoria_local(
                cur,
                existente,
                nome=nome,
                nivel=nivel,
                parent_dropnexo=parent_drop,
                id_segmento=id_segmento,
            )
            _upsert_mapa_categoria(
                cur,
                id_tenant,
                contexto,
                cid,
                existente,
                {
                    "nome": nome,
                    "id_bling_pai": parent_bling,
                    **meta_criar,
                },
            )
            parent_drop = existente
            cat_id = existente
            continue

        cat_id = _criar_categoria_do_bling(
            cur,
            id_tenant,
            contexto,
            cid,
            id_segmento=id_segmento,
            parent_dropnexo=parent_drop,
            cache_api=cache,
            meta_extra=meta_criar,
        )
        if not cat_id:
            cat = _fetch_categoria_bling(id_tenant, cid, cache)
            raise ValueError(f'Não foi possível criar "{_nome_categoria_bling(cat, cid)}".')
        parent_drop = cat_id

    if not cat_id:
        raise ValueError("Não foi possível criar a categoria.")
    return cat_id


def _upsert_mapa_categoria(
    cur,
    id_tenant: int,
    contexto: str,
    id_bling: str,
    id_dropnexo: int | None,
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
    pai = cat.get("categoriaPai")
    if pai is None:
        pai = cat.get("idCategoriaPai") or cat.get("categoria_pai") or cat.get("id_categoria_pai")
    if isinstance(pai, dict):
        pid = str(pai.get("id") or "").strip()
    elif pai is not None and pai != "":
        pid = str(pai).strip()
    else:
        return None
    if not pid or pid == "0":
        return None
    return pid


def _cache_precisa_detalhe_pai(cat: dict) -> bool:
    if not cat:
        return True
    if "categoriaPai" in cat or "idCategoriaPai" in cat or "categoria_pai" in cat:
        return False
    return True


def enriquecer_cache_pais_categorias_bling(
    id_tenant: int,
    cache: dict[str, dict],
    *,
    on_progresso=None,
) -> int:
    """Completa categoriaPai via GET quando a listagem não trouxe hierarquia."""
    import time

    from api.bling.cliente import obter_categoria_produto
    from api.bling.sync_estoque import BLING_INTERVALO_SYNC_SEG, BLING_SYNC_MAX_TENTATIVAS

    com_pai = sum(1 for c in cache.values() if _id_pai_bling(c))
    if com_pai == 0 and len(cache) > 1:
        ids = list(cache.keys())
    else:
        ids = [cid for cid, cat in cache.items() if _cache_precisa_detalhe_pai(cat)]

    total = len(ids)
    if not total:
        return 0

    for i, cid in enumerate(ids):
        ultimo_erro: Exception | None = None
        for tentativa in range(BLING_SYNC_MAX_TENTATIVAS):
            try:
                det = obter_categoria_produto(id_tenant, cid)
                if det:
                    cache[cid] = {**(cache.get(cid) or {}), **det}
                ultimo_erro = None
                break
            except Exception as exc:
                ultimo_erro = exc
                msg = str(exc).lower()
                if "limite" in msg or "too_many" in msg or "429" in msg:
                    time.sleep(min(8.0, 1.5 * (tentativa + 1)))
                    continue
                break
        if ultimo_erro:
            _log = __import__("logging").getLogger(__name__)
            _log.warning("Falha ao enriquecer categoria Bling %s: %s", cid, ultimo_erro)
        if on_progresso:
            on_progresso(
                total=total,
                processados=i + 1,
                mensagem=f"Consultando hierarquia Bling ({i + 1}/{total})…",
            )
        time.sleep(BLING_INTERVALO_SYNC_SEG)
    return total


def _atualizar_categoria_local(
    cur,
    cat_id: int,
    *,
    nome: str,
    nivel: int,
    parent_dropnexo: int | None,
    id_segmento: int | None,
) -> None:
    cur.execute(
        """
        UPDATE tbl_categoria
        SET nome = %s, nivel = %s, parent_id = %s, ativo = TRUE,
            id_segmento = COALESCE(id_segmento, %s)
        WHERE id = %s
        """,
        (nome, nivel, parent_dropnexo, id_segmento, cat_id),
    )


def garantir_categoria_bling(
    cur,
    id_tenant: int,
    contexto: str,
    id_bling: str,
    *,
    id_segmento: int | None = None,
    cache_api: dict[str, dict] | None = None,
    somente_mapa: bool = False,
) -> int | None:
    """Resolve categoria DropNexo para ID Bling. Modo legado cria/atualiza; somente_mapa só consulta mapa."""
    id_bling = str(id_bling or "").strip()
    if not id_bling:
        return None

    cache = cache_api if cache_api is not None else {}
    cat = _fetch_categoria_bling(id_tenant, id_bling, cache)
    nome = _nome_categoria_bling(cat, id_bling)
    if not nome:
        return None

    parent_bling = _id_pai_bling(cat)
    parent_dropnexo = None
    nivel = 1
    if parent_bling:
        parent_dropnexo = garantir_categoria_bling(
            cur,
            id_tenant,
            contexto,
            parent_bling,
            id_segmento=id_segmento,
            cache_api=cache,
            somente_mapa=somente_mapa,
        )
        if parent_dropnexo:
            cur.execute("SELECT nivel FROM tbl_categoria WHERE id = %s", (parent_dropnexo,))
            row = cur.fetchone()
            nivel = min(int(row[0] or 1) + 1, MAX_NIVEL) if row else 2

    existente = _resolver_mapa_categoria_valido(cur, id_tenant, contexto, id_bling)
    if existente:
        if not somente_mapa:
            _atualizar_categoria_local(
                cur,
                existente,
                nome=nome,
                nivel=nivel,
                parent_dropnexo=parent_dropnexo,
                id_segmento=id_segmento,
            )
            _upsert_mapa_categoria(
                cur,
                id_tenant,
                contexto,
                id_bling,
                existente,
                {"nome": nome, "id_bling_pai": parent_bling},
            )
        return existente

    if somente_mapa:
        return None

    id_match = _buscar_match_por_nome(
        cur,
        id_tenant,
        nome=nome,
        parent_dropnexo=parent_dropnexo,
        id_segmento=id_segmento,
    )
    if id_match:
        cat_id = id_match
        _atualizar_categoria_local(
            cur,
            cat_id,
            nome=nome,
            nivel=nivel,
            parent_dropnexo=parent_dropnexo,
            id_segmento=id_segmento,
        )
        _upsert_mapa_categoria(
            cur,
            id_tenant,
            contexto,
            id_bling,
            cat_id,
            {"nome": nome, "id_bling_pai": parent_bling},
        )
    else:
        cat_id = _criar_categoria_do_bling(
            cur,
            id_tenant,
            contexto,
            id_bling,
            id_segmento=id_segmento,
            parent_dropnexo=parent_dropnexo,
            cache_api=cache,
        )
        if not cat_id:
            return None

    return cat_id


def sincronizar_arvore_categorias_bling(
    cur,
    id_tenant: int,
    contexto: str,
    *,
    id_segmento: int | None = None,
) -> int:
    """Importa toda a árvore de categorias do Bling (sem produtos)."""
    cache_api: dict[str, dict] = {}
    n = 0
    for item in listar_categorias_bling_flat(id_tenant):
        cid = str(item.get("id") or "").strip()
        if not cid:
            continue
        if garantir_categoria_bling(
            cur,
            id_tenant,
            contexto,
            cid,
            id_segmento=id_segmento,
            cache_api=cache_api,
        ):
            n += 1
    return n


def contar_categorias_bling_sem_segmento(cur, id_tenant: int) -> int:
    cur.execute(
        """
        SELECT COUNT(*)::int
        FROM tbl_categoria c
        JOIN tbl_integracao_map m
          ON m.id_dropnexo = c.id AND m.provedor = 'bling' AND m.entidade = 'categoria'
        WHERE c.id_tenant = %s AND c.id_segmento IS NULL AND c.ativo = TRUE
        """,
        (id_tenant,),
    )
    return int(cur.fetchone()[0] or 0)


def listar_categorias_bling_sem_segmento(cur, id_tenant: int) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT c.id, c.nome, c.nivel, c.parent_id, m.id_bling
        FROM tbl_categoria c
        JOIN tbl_integracao_map m
          ON m.id_dropnexo = c.id AND m.provedor = 'bling' AND m.entidade = 'categoria'
        WHERE c.id_tenant = %s AND c.id_segmento IS NULL AND c.ativo = TRUE
        ORDER BY c.nivel, c.nome
        """,
        (id_tenant,),
    )
    return [
        {
            "id": r[0],
            "nome": r[1],
            "nivel": int(r[2] or 1),
            "parent_id": r[3],
            "id_bling": r[4],
        }
        for r in cur.fetchall()
    ]


def associar_segmento_categorias_bling(
    cur,
    id_tenant: int,
    id_segmento: int,
    *,
    ids_categorias: list[int] | None = None,
) -> int:
    """Associa segmento às categorias importadas do Bling ainda sem segmento."""
    if not resolver_id_segmento_import(cur, id_tenant, id_segmento):
        raise ValueError("Segmento inválido.")

    if ids_categorias:
        ids = [int(i) for i in ids_categorias if i]
        if not ids:
            return 0
        cur.execute(
            """
            UPDATE tbl_categoria c
            SET id_segmento = %s
            FROM tbl_integracao_map m
            WHERE m.id_dropnexo = c.id
              AND m.provedor = 'bling' AND m.entidade = 'categoria'
              AND c.id_tenant = %s AND c.id_segmento IS NULL
              AND c.id = ANY(%s)
            """,
            (id_segmento, id_tenant, ids),
        )
        return int(cur.rowcount or 0)

    cur.execute(
        """
        UPDATE tbl_categoria c
        SET id_segmento = %s
        FROM tbl_integracao_map m
        WHERE m.id_dropnexo = c.id
          AND m.provedor = 'bling' AND m.entidade = 'categoria'
          AND c.id_tenant = %s AND c.id_segmento IS NULL
        """,
        (id_segmento, id_tenant),
    )
    return int(cur.rowcount or 0)


def cache_categorias_precisa_enriquecer(cache: dict[str, dict]) -> bool:
    """Listagem Bling sem nenhum pai indica hierarquia incompleta."""
    if len(cache) <= 1:
        return False
    com_pai = sum(1 for c in cache.values() if _id_pai_bling(c))
    return com_pai == 0


PAINEL_ENRIQUECER_ASYNC_MIN = 12


def obter_cache_categorias_bling_enriquecido(
    id_tenant: int,
    *,
    cache_api: dict[str, dict] | None = None,
    on_progresso=None,
) -> dict[str, dict]:
    """Carrega listagem e completa categoriaPai via GET quando necessário."""
    cache = dict(cache_api) if cache_api is not None else carregar_mapa_categorias_bling_listagem(id_tenant)
    if cache_categorias_precisa_enriquecer(cache):
        enriquecer_cache_pais_categorias_bling(id_tenant, cache, on_progresso=on_progresso)
    return cache


def carregar_mapa_categorias_bling_listagem(id_tenant: int) -> dict[str, dict]:
    """Mapa id → categoria a partir da listagem paginada Bling (1 req/página)."""
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
    return by_id


def reparar_hierarquia_categorias_mapeadas(
    cur,
    id_tenant: int,
    contexto: str,
    *,
    on_progresso=None,
    cache_api: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Reorganiza parent_id/nivel das categorias já mapeadas conforme árvore Bling."""
    cache = dict(cache_api) if cache_api is not None else carregar_mapa_categorias_bling_listagem(id_tenant)

    def _emit(**kwargs) -> None:
        if on_progresso:
            on_progresso(**kwargs)

    _emit(total=0, processados=0, sincronizados=0, falhas=0, mensagem="Consultando hierarquia no Bling…")
    enriquecer_cache_pais_categorias_bling(id_tenant, cache, on_progresso=_emit)

    cur.execute(
        """
        SELECT id_bling, id_dropnexo
        FROM tbl_integracao_map
        WHERE id_tenant = %s AND provedor = 'bling' AND contexto = %s
          AND entidade = 'categoria' AND id_dropnexo IS NOT NULL
        """,
        (id_tenant, contexto),
    )
    bling_to_drop: dict[str, int] = {str(r[0]): int(r[1]) for r in cur.fetchall() if r[0] and r[1]}
    if not bling_to_drop:
        return {
            "total": 0,
            "processados": 0,
            "sincronizados": 0,
            "falhas": 0,
            "erros": [],
            "mensagem": "Nenhuma categoria mapeada encontrada.",
        }

    ordenados = _ordenar_ids_categoria_bling(set(bling_to_drop.keys()), cache, id_tenant)
    total = len(ordenados)
    processados = atualizados = falhas = 0
    erros: list[str] = []

    for id_bling in ordenados:
        id_drop = bling_to_drop[id_bling]
        cat, err_cat = _fetch_categoria_bling_opcional(id_tenant, id_bling, cache)
        meta_mapa = _ler_meta_mapa_categoria(cur, id_tenant, contexto, id_bling)
        if err_cat:
            nome = meta_mapa.get("nome") or f"Categoria Bling {id_bling}"
            erros.append(f"{nome}: não existe mais no Bling (mapeamento antigo).")
            falhas += 1
            processados += 1
            _emit(
                total=total,
                processados=processados,
                sincronizados=atualizados,
                falhas=falhas,
                mensagem=f"Reorganizando {processados}/{total}",
            )
            continue

        nome = _nome_categoria_bling(cat, id_bling)
        parent_bling = _id_pai_bling(cat) or meta_mapa.get("id_bling_pai")
        if parent_bling:
            parent_bling = str(parent_bling).strip() or None
        parent_drop: int | None = None

        if parent_bling:
            parent_drop = bling_to_drop.get(parent_bling)
            if not parent_drop:
                cur.execute(
                    "SELECT id_segmento FROM tbl_categoria WHERE id = %s AND id_tenant = %s",
                    (id_drop, id_tenant),
                )
                seg_row = cur.fetchone()
                id_seg = int(seg_row[0]) if seg_row and seg_row[0] else None
                if id_seg:
                    try:
                        parent_drop = criar_categoria_bling_com_arvore(
                            cur,
                            id_tenant,
                            contexto,
                            parent_bling,
                            id_segmento=id_seg,
                            cache_api=cache,
                        )
                        bling_to_drop[parent_bling] = parent_drop
                    except Exception as exc:
                        erros.append(f"{nome}: pai Bling não resolvido ({exc})")

        cur.execute(
            """
            SELECT nome, id_segmento, parent_id, nivel
            FROM tbl_categoria WHERE id = %s AND id_tenant = %s
            """,
            (id_drop, id_tenant),
        )
        row = cur.fetchone()
        if not row:
            falhas += 1
            processados += 1
            _emit(
                total=total,
                processados=processados,
                sincronizados=atualizados,
                falhas=falhas,
                mensagem=f"Reorganizando {processados}/{total}",
            )
            continue

        nome_db, id_seg, pid_atual, nivel_atual = row[0], row[1], row[2], row[3]
        nivel = 1
        if parent_drop:
            cur.execute("SELECT nivel FROM tbl_categoria WHERE id = %s", (parent_drop,))
            pr = cur.fetchone()
            nivel = min(int(pr[0] or 1) + 1, MAX_NIVEL) if pr else 2

        pid_novo = int(parent_drop) if parent_drop else None
        pid_atual_n = int(pid_atual) if pid_atual else None

        if pid_atual_n != pid_novo or int(nivel_atual or 1) != nivel:
            _atualizar_categoria_local(
                cur,
                id_drop,
                nome=nome_db or nome,
                nivel=nivel,
                parent_dropnexo=pid_novo,
                id_segmento=int(id_seg) if id_seg else None,
            )
            _upsert_mapa_categoria(
                cur,
                id_tenant,
                contexto,
                id_bling,
                id_drop,
                {
                    "nome": nome,
                    "id_bling_pai": parent_bling,
                    "acao": "criar",
                    "origem": "reparo_hierarquia",
                },
            )
            atualizados += 1

        processados += 1
        _emit(
            total=total,
            processados=processados,
            sincronizados=atualizados,
            falhas=falhas,
            mensagem=f"Reorganizando {processados}/{total}",
        )

    return {
        "total": total,
        "processados": processados,
        "sincronizados": atualizados,
        "falhas": falhas,
        "erros": erros[:20],
        "mensagem": f"{atualizados} categoria(s) reorganizada(s).",
    }


def listar_categorias_bling_flat(
    id_tenant: int,
    *,
    by_id: dict[str, dict] | None = None,
) -> list[dict[str, Any]]:
    """Lista categorias do Bling em ordem de árvore para o select da UI."""
    by_id = by_id if by_id is not None else carregar_mapa_categorias_bling_listagem(id_tenant)

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
                "id_bling_pai": _id_pai_bling(cat),
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
