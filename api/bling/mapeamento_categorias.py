# api/bling/mapeamento_categorias.py — pré-análise e aplicação de mapa Bling ↔ DropNexo
from __future__ import annotations

import json
from typing import Any

from api.bling.cliente import obter_categoria_produto, obter_produto
from api.bling.sync_categorias import (
    _buscar_mapa_categoria,
    _buscar_match_por_nome,
    _caminho_categoria_bling,
    _categoria_dropnexo_existe,
    _criar_categoria_do_bling,
    _fetch_categoria_bling,
    _id_pai_bling,
    _nome_categoria_bling,
    _obter_nome_categoria_dropnexo,
    _ordenar_ids_categoria_bling,
    _resolver_mapa_categoria_valido,
    _upsert_mapa_categoria,
    _vincular_categoria_bling,
    expandir_ancestrais_categorias_bling,
    extrair_id_categoria_produto,
    ids_categoria_bling_com_descendentes,
    resolver_id_segmento_import,
)
from api.bling.sync_produtos import _iterar_listas_produtos, _preparar_jobs_importacao
from srotas_negocio import flatten_arvore_com_caminho, montar_arvore_categorias


def _montar_filtro_categorias_api(
    id_tenant: int,
    *,
    ids_categorias_bling: list[str] | None,
    incluir_subcategorias: bool,
) -> tuple[set[str] | None, list[str | None]]:
    ids_filtro: set[str] | None = None
    ids_categoria_api: list[str | None] = [None]
    raizes: list[str] = []
    if ids_categorias_bling:
        raizes = [str(c).strip() for c in ids_categorias_bling if str(c or "").strip()]

    if raizes:
        ids_filtro = set()
        ids_categoria_api = []
        for cat_id in raizes:
            if incluir_subcategorias:
                ids_cat = ids_categoria_bling_com_descendentes(
                    id_tenant,
                    cat_id,
                    incluir_subcategorias=True,
                )
            else:
                ids_cat = {cat_id}
            ids_filtro |= ids_cat
            ids_categoria_api.extend(ids_cat)
        ids_categoria_api = sorted(set(ids_categoria_api))

    return ids_filtro, ids_categoria_api


def coletar_ids_categoria_bling_do_escopo(
    id_tenant: int,
    *,
    ids_categorias_bling: list[str] | None,
    incluir_subcategorias: bool,
) -> set[str]:
    """Categorias Bling usadas pelos produtos do lote (+ ancestrais)."""
    _, ids_categoria_api = _montar_filtro_categorias_api(
        id_tenant,
        ids_categorias_bling=ids_categorias_bling,
        incluir_subcategorias=incluir_subcategorias,
    )
    itens = _iterar_listas_produtos(id_tenant, ids_categoria_api=ids_categoria_api)
    jobs = _preparar_jobs_importacao(itens)
    ids_cats: set[str] = set()

    for job in jobs:
        id_bling = str(job.get("id_bling") or "")
        if not id_bling:
            continue
        item = job.get("item")
        cid = extrair_id_categoria_produto(item or {})
        if not cid:
            if job.get("tipo") == "grupo" and not item:
                detalhe = obter_produto(id_tenant, id_bling)
            else:
                detalhe = item if item else obter_produto(id_tenant, id_bling)
            cid = extrair_id_categoria_produto(detalhe or {})
        if cid:
            ids_cats.add(cid)

    cache_api: dict[str, dict] = {}
    return expandir_ancestrais_categorias_bling(id_tenant, ids_cats, cache_api)


def listar_categorias_dropnexo_tenant(cur, id_tenant: int) -> dict[str, Any]:
    cur.execute(
        """
        SELECT c.id, c.nome, c.parent_id, c.ordem, c.nivel, 0,
               COALESCE(s.nome, '')
        FROM tbl_categoria c
        LEFT JOIN tbl_segmento s ON s.id = c.id_segmento
        WHERE c.id_tenant = %s AND c.ativo = TRUE
        ORDER BY COALESCE(s.nome, ''), c.ordem, c.nome
        """,
        (id_tenant,),
    )
    rows = cur.fetchall()
    segmentos = {r[6] for r in rows if r[6]}
    multi_segmento = len(segmentos) > 1
    arvore = montar_arvore_categorias([(r[0], r[1], r[2], r[3], r[4], r[5]) for r in rows])
    flat = flatten_arvore_com_caminho(arvore)
    if multi_segmento:
        id_to_seg = {r[0]: (r[6] or "Sem segmento") for r in rows}
        for item in flat:
            item["caminho"] = f"{id_to_seg.get(item['id'], '')} › {item['caminho']}".strip(" ›")

    return {"arvore": arvore, "opcoes": flat, "multi_segmento": multi_segmento}


def pre_analisar_mapeamento_categorias(
    cur,
    id_tenant: int,
    contexto: str,
    *,
    ids_categorias_bling: list[str] | None = None,
    incluir_subcategorias: bool = True,
    id_segmento: int | None = None,
) -> dict[str, Any]:
    id_segmento_resolvido = resolver_id_segmento_import(cur, id_tenant, id_segmento)
    cache_api: dict[str, dict] = {}
    ids_escopo = coletar_ids_categoria_bling_do_escopo(
        id_tenant,
        ids_categorias_bling=ids_categorias_bling,
        incluir_subcategorias=incluir_subcategorias,
    )

    if not ids_escopo:
        drop = listar_categorias_dropnexo_tenant(cur, id_tenant)
        return {
            "exibir_modal": False,
            "mapeadas": [],
            "pendentes": [],
            "categorias_dropnexo": drop["opcoes"],
            "total_produtos_escopo": 0,
            "mensagem": "Nenhuma categoria Bling encontrada nos produtos do escopo.",
        }

    ordenadas = _ordenar_ids_categoria_bling(ids_escopo, cache_api, id_tenant)
    proposto: dict[str, int | None] = {}
    mapeadas: list[dict[str, Any]] = []
    pendentes: list[dict[str, Any]] = []

    for id_bling in ordenadas:
        cat = _fetch_categoria_bling(id_tenant, id_bling, cache_api)
        nome_bling = _nome_categoria_bling(cat, id_bling)
        parent_bling = _id_pai_bling(cat)
        caminho_bling = _caminho_categoria_bling(id_bling, cache_api, id_tenant)

        parent_drop = None
        if parent_bling:
            parent_drop = proposto.get(parent_bling)
            if parent_drop is None:
                parent_drop = _resolver_mapa_categoria_valido(cur, id_tenant, contexto, parent_bling)

        id_mapa = _resolver_mapa_categoria_valido(cur, id_tenant, contexto, id_bling)
        if id_mapa:
            proposto[id_bling] = id_mapa
            mapeadas.append(
                {
                    "id_bling": id_bling,
                    "nome_bling": nome_bling,
                    "caminho_bling": caminho_bling,
                    "id_bling_pai": parent_bling,
                    "origem": "mapa",
                    "id_dropnexo": id_mapa,
                    "nome_dropnexo": _obter_nome_categoria_dropnexo(cur, id_mapa),
                    "editavel": False,
                }
            )
            continue

        id_match = _buscar_match_por_nome(
            cur,
            id_tenant,
            nome=nome_bling,
            parent_dropnexo=parent_drop,
            id_segmento=id_segmento_resolvido,
        )
        if id_match:
            proposto[id_bling] = id_match
            mapeadas.append(
                {
                    "id_bling": id_bling,
                    "nome_bling": nome_bling,
                    "caminho_bling": caminho_bling,
                    "id_bling_pai": parent_bling,
                    "origem": "match_automatico",
                    "id_dropnexo": id_match,
                    "nome_dropnexo": _obter_nome_categoria_dropnexo(cur, id_match),
                    "editavel": True,
                    "motivo_match": "Nome, pai e segmento iguais",
                }
            )
            continue

        proposto[id_bling] = None
        pendentes.append(
            {
                "id_bling": id_bling,
                "nome_bling": nome_bling,
                "caminho_bling": caminho_bling,
                "id_bling_pai": parent_bling,
                "acao_default": "criar",
            }
        )

    exibir_modal = bool(pendentes) or any(m.get("editavel") for m in mapeadas)
    drop = listar_categorias_dropnexo_tenant(cur, id_tenant)
    _, ids_api = _montar_filtro_categorias_api(
        id_tenant,
        ids_categorias_bling=ids_categorias_bling,
        incluir_subcategorias=incluir_subcategorias,
    )
    total_produtos = len(_iterar_listas_produtos(id_tenant, ids_categoria_api=ids_api))

    return {
        "exibir_modal": exibir_modal,
        "mapeadas": mapeadas,
        "pendentes": pendentes,
        "categorias_dropnexo": drop["opcoes"],
        "multi_segmento": drop["multi_segmento"],
        "total_categorias": len(ordenadas),
        "total_produtos_escopo": total_produtos,
        "id_segmento_resolvido": id_segmento_resolvido,
    }


def _decisao_pendente(decisoes: dict[str, dict], id_bling: str) -> dict[str, Any]:
    raw = decisoes.get(id_bling) or {}
    acao = (raw.get("acao") or "criar").strip().lower()
    if acao not in ("criar", "vincular"):
        acao = "criar"
    id_drop = raw.get("id_dropnexo")
    try:
        id_drop = int(id_drop) if id_drop not in (None, "") else None
    except (TypeError, ValueError):
        id_drop = None
    return {"acao": acao, "id_dropnexo": id_drop}


def aplicar_mapeamento_categorias(
    cur,
    id_tenant: int,
    contexto: str,
    *,
    ids_categorias_bling: list[str] | None = None,
    incluir_subcategorias: bool = True,
    id_segmento: int | None = None,
    decisoes: list[dict[str, Any]] | None = None,
    correcoes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Grava mapas e categorias conforme pré-análise + escolhas do usuário."""
    pre = pre_analisar_mapeamento_categorias(
        cur,
        id_tenant,
        contexto,
        ids_categorias_bling=ids_categorias_bling,
        incluir_subcategorias=incluir_subcategorias,
        id_segmento=id_segmento,
    )
    id_segmento_resolvido = pre.get("id_segmento_resolvido")
    cache_api: dict[str, dict] = {}

    decisoes_map: dict[str, dict] = {}
    for d in decisoes or []:
        bid = str(d.get("id_bling") or "").strip()
        if bid:
            decisoes_map[bid] = _decisao_pendente({bid: d}, bid)

    correcoes_map: dict[str, dict] = {}
    for d in correcoes or []:
        bid = str(d.get("id_bling") or "").strip()
        if not bid:
            continue
        try:
            id_drop = int(d.get("id_dropnexo"))
        except (TypeError, ValueError):
            continue
        if not _categoria_dropnexo_existe(cur, id_tenant, id_drop):
            raise ValueError(f"Categoria DropNexo #{id_drop} inválida para vínculo.")
        correcoes_map[bid] = {"acao": "vincular", "id_dropnexo": id_drop}

    todos: dict[str, dict] = {m["id_bling"]: m for m in pre["mapeadas"]}
    for p in pre["pendentes"]:
        todos[p["id_bling"]] = p

    ids_ordenados = _ordenar_ids_categoria_bling(set(todos.keys()), cache_api, id_tenant)
    resolvido: dict[str, int] = {}
    criadas = 0
    vinculadas = 0
    confirmadas = 0

    for id_bling in ids_ordenados:
        item = todos[id_bling]
        cat = _fetch_categoria_bling(id_tenant, id_bling, cache_api)
        nome_bling = _nome_categoria_bling(cat, id_bling)
        parent_bling = _id_pai_bling(cat)
        parent_drop = resolvido.get(parent_bling) if parent_bling else None
        if parent_drop is None and parent_bling:
            parent_drop = _resolver_mapa_categoria_valido(cur, id_tenant, contexto, parent_bling)

        if id_bling in correcoes_map:
            id_drop = correcoes_map[id_bling]["id_dropnexo"]
            _vincular_categoria_bling(
                cur,
                id_tenant,
                contexto,
                id_bling,
                id_drop,
                meta={"nome": nome_bling, "id_bling_pai": parent_bling, "origem": "correcao_usuario"},
            )
            resolvido[id_bling] = id_drop
            vinculadas += 1
            continue

        origem = item.get("origem")
        if origem == "mapa" and item.get("id_dropnexo"):
            resolvido[id_bling] = int(item["id_dropnexo"])
            continue

        if origem == "match_automatico" and item.get("id_dropnexo"):
            id_drop = int(item["id_dropnexo"])
            _vincular_categoria_bling(
                cur,
                id_tenant,
                contexto,
                id_bling,
                id_drop,
                meta={"nome": nome_bling, "id_bling_pai": parent_bling, "origem": "match_automatico"},
            )
            resolvido[id_bling] = id_drop
            confirmadas += 1
            continue

        dec = _decisao_pendente(decisoes_map, id_bling)
        if dec["acao"] == "vincular" and dec["id_dropnexo"]:
            id_drop = dec["id_dropnexo"]
            if not _categoria_dropnexo_existe(cur, id_tenant, id_drop):
                raise ValueError(f"Categoria DropNexo #{id_drop} não encontrada.")
            _vincular_categoria_bling(
                cur,
                id_tenant,
                contexto,
                id_bling,
                id_drop,
                meta={"nome": nome_bling, "id_bling_pai": parent_bling, "origem": "vinculo_usuario"},
            )
            resolvido[id_bling] = id_drop
            vinculadas += 1
            continue

        id_drop = _criar_categoria_do_bling(
            cur,
            id_tenant,
            contexto,
            id_bling,
            id_segmento=id_segmento_resolvido,
            parent_dropnexo=parent_drop,
            cache_api=cache_api,
        )
        if not id_drop:
            raise ValueError(f"Não foi possível criar categoria para Bling #{id_bling}.")
        resolvido[id_bling] = id_drop
        criadas += 1

    return {
        "mapeamentos": len(resolvido),
        "criadas": criadas,
        "vinculadas": vinculadas,
        "confirmadas_match": confirmadas,
    }


def _validar_segmento_tenant(cur, id_tenant: int, id_segmento: int) -> None:
    cur.execute(
        """
        SELECT 1 FROM tbl_fornecedor_segmento fs
        JOIN tbl_segmento s ON s.id = fs.id_segmento AND s.ativo = TRUE
        WHERE fs.id_tenant = %s AND fs.id_segmento = %s
        """,
        (id_tenant, int(id_segmento)),
    )
    if not cur.fetchone():
        raise ValueError("Segmento inválido para esta conta.")


def listar_painel_categorias_bling(cur, id_tenant: int, contexto: str) -> dict[str, Any]:
    from api.bling.sync_categorias import (
        carregar_mapa_categorias_bling_listagem,
        listar_categorias_bling_flat,
        obter_estado_mapeamento_categoria,
        _caminho_categoria_bling_local,
        _id_pai_bling,
        _nome_categoria_bling,
    )
    from fornecedor.segmentos.servico_segmentos import ids_segmentos_fornecedor

    cache_api = carregar_mapa_categorias_bling_listagem(id_tenant)
    bling_flat = listar_categorias_bling_flat(id_tenant, by_id=cache_api)
    drop = listar_categorias_dropnexo_tenant(cur, id_tenant)
    cur.execute(
        "SELECT id, id_segmento FROM tbl_categoria WHERE id_tenant = %s AND ativo = TRUE",
        (id_tenant,),
    )
    seg_por_cat = {int(r[0]): int(r[1]) if r[1] else None for r in cur.fetchall()}
    for op in drop.get("opcoes") or []:
        op["id_segmento"] = seg_por_cat.get(int(op.get("id") or 0))
    seg_ids = ids_segmentos_fornecedor(cur, id_tenant)
    segmentos: list[dict[str, Any]] = []
    if seg_ids:
        cur.execute(
            "SELECT id, nome FROM tbl_segmento WHERE id = ANY(%s) ORDER BY nome",
            (seg_ids,),
        )
        segmentos = [{"id": int(r[0]), "nome": r[1]} for r in cur.fetchall()]

    linhas: list[dict[str, Any]] = []
    n_mapeadas = n_ignoradas = n_pendentes = 0

    for b in bling_flat:
        id_b = str(b.get("id") or "")
        estado = obter_estado_mapeamento_categoria(cur, id_tenant, contexto, id_b)
        st = estado.get("status") or "pendente"
        if st == "mapeada":
            n_mapeadas += 1
        elif st == "ignorada":
            n_ignoradas += 1
        else:
            n_pendentes += 1

        cat = cache_api.get(id_b) or {}
        parent_bling = b.get("id_bling_pai") or _id_pai_bling(cat)
        caminho = _caminho_categoria_bling_local(id_b, cache_api)
        linhas.append(
            {
                "id_bling": id_b,
                "nome_bling": b.get("nome") or _nome_categoria_bling(cat, id_b),
                "label_bling": b.get("label") or b.get("nome") or id_b,
                "caminho_bling": caminho,
                "nivel": int(b.get("nivel") or 1),
                "id_bling_pai": parent_bling,
                "status": st,
                "acao": estado.get("acao"),
                "id_dropnexo": estado.get("id_dropnexo"),
                "id_segmento": estado.get("id_segmento"),
                "nome_dropnexo": estado.get("nome_dropnexo"),
            }
        )

    total = len(linhas)
    return {
        "categorias": linhas,
        "segmentos": segmentos,
        "opcoes_dropnexo": drop["opcoes"],
        "multi_segmento": drop["multi_segmento"],
        "resumo": {
            "total": total,
            "mapeadas": n_mapeadas,
            "ignoradas": n_ignoradas,
            "pendentes": n_pendentes,
            "pronto": n_pendentes == 0 and total > 0,
        },
    }


def salvar_mapeamento_categoria_ui(
    cur,
    id_tenant: int,
    contexto: str,
    *,
    id_bling: str,
    acao: str,
    id_segmento: int | None = None,
    id_dropnexo: int | None = None,
    id_parent_dropnexo: int | None = None,
    cache_api: dict[str, dict] | None = None,
) -> dict[str, Any]:
    from api.bling.sync_categorias import (
        _fetch_categoria_bling,
        _id_pai_bling,
        _nome_categoria_bling,
        _vincular_categoria_bling,
        criar_categoria_bling_com_arvore,
        obter_estado_mapeamento_categoria,
    )

    id_bling = str(id_bling or "").strip()
    acao = (acao or "").strip().lower()
    if not id_bling:
        raise ValueError("Categoria Bling inválida.")
    if acao not in ("vincular", "criar", "ignorar"):
        raise ValueError("Ação inválida. Use vincular, criar ou ignorar.")

    cache: dict[str, dict] = cache_api if cache_api is not None else {}
    cat = cache.get(id_bling) or _fetch_categoria_bling(id_tenant, id_bling, cache)
    nome_bling = _nome_categoria_bling(cat, id_bling)
    parent_bling = _id_pai_bling(cat)

    if acao == "ignorar":
        _upsert_mapa_categoria(
            cur,
            id_tenant,
            contexto,
            id_bling,
            None,
            {
                "nome": nome_bling,
                "id_bling_pai": parent_bling,
                "acao": "ignorar",
                "origem": "integracao_ui",
            },
        )
        return {"status": "ignorada", "id_bling": id_bling}

    if acao == "vincular":
        if not id_dropnexo:
            raise ValueError("Selecione a categoria DropNexo para vincular.")
        if not _categoria_dropnexo_existe(cur, id_tenant, int(id_dropnexo)):
            raise ValueError("Categoria DropNexo não encontrada.")
        if id_segmento:
            _validar_segmento_tenant(cur, id_tenant, int(id_segmento))
            cur.execute(
                "UPDATE tbl_categoria SET id_segmento = COALESCE(id_segmento, %s) WHERE id = %s AND id_tenant = %s",
                (int(id_segmento), int(id_dropnexo), id_tenant),
            )
        _vincular_categoria_bling(
            cur,
            id_tenant,
            contexto,
            id_bling,
            int(id_dropnexo),
            meta={
                "nome": nome_bling,
                "id_bling_pai": parent_bling,
                "acao": "vincular",
                "origem": "integracao_ui",
            },
        )
        estado = obter_estado_mapeamento_categoria(cur, id_tenant, contexto, id_bling)
        return {"status": estado.get("status"), "id_bling": id_bling, **estado}

    if not id_segmento:
        raise ValueError("Selecione o segmento para criar a categoria.")
    _validar_segmento_tenant(cur, id_tenant, int(id_segmento))

    from api.bling.sync_categorias import criar_categoria_bling_com_arvore

    cat_id = criar_categoria_bling_com_arvore(
        cur,
        id_tenant,
        contexto,
        id_bling,
        id_segmento=int(id_segmento),
        cache_api=cache,
    )

    estado = obter_estado_mapeamento_categoria(cur, id_tenant, contexto, id_bling)
    return {"status": estado.get("status"), "id_bling": id_bling, "id_dropnexo": cat_id, **estado}


def processar_lote_mapeamento_categorias_ui(
    cur,
    id_tenant: int,
    contexto: str,
    acoes: list[dict[str, Any]],
    *,
    on_progresso=None,
    cache_api: dict[str, dict] | None = None,
) -> dict[str, Any]:
    """Aplica várias ações de mapeamento com throttle entre itens."""
    import time

    from api.bling.sync_categorias import (
        _ordenar_ids_categoria_bling,
        carregar_mapa_categorias_bling_listagem,
    )
    from api.bling.sync_estoque import BLING_INTERVALO_SYNC_SEG, BLING_SYNC_MAX_TENTATIVAS

    cache = dict(cache_api) if cache_api is not None else carregar_mapa_categorias_bling_listagem(id_tenant)

    normalizadas: list[dict[str, Any]] = []
    for raw in acoes or []:
        id_bling = str(raw.get("id_bling") or "").strip()
        acao = (raw.get("acao") or "").strip().lower()
        if not id_bling or acao not in ("vincular", "criar", "ignorar"):
            continue
        try:
            id_seg = int(raw["id_segmento"]) if raw.get("id_segmento") not in (None, "") else None
        except (TypeError, ValueError):
            id_seg = None
        try:
            id_drop = int(raw["id_dropnexo"]) if raw.get("id_dropnexo") not in (None, "") else None
        except (TypeError, ValueError):
            id_drop = None
        normalizadas.append(
            {
                "id_bling": id_bling,
                "acao": acao,
                "id_segmento": id_seg,
                "id_dropnexo": id_drop,
            }
        )

    ids_set = {a["id_bling"] for a in normalizadas}
    ordenadas = _ordenar_ids_categoria_bling(ids_set, cache, id_tenant)
    por_id = {a["id_bling"]: a for a in normalizadas}
    fila = [por_id[i] for i in ordenadas if i in por_id]

    total = len(fila)
    processados = ok = falhas = 0
    erros: list[str] = []

    def _emit(**kwargs) -> None:
        if on_progresso:
            on_progresso(kwargs)

    _emit(total=total, processados=0, sincronizados=0, falhas=0, mensagem="Iniciando…")

    for item in fila:
        id_bling = item["id_bling"]
        acao = item["acao"]
        id_seg = item.get("id_segmento")
        id_drop = item.get("id_dropnexo")
        nome = (cache.get(id_bling) or {}).get("descricao") or id_bling

        if acao != "ignorar" and not id_seg:
            falhas += 1
            processados += 1
            erros.append(f"{nome}: selecione o segmento.")
            _emit(
                processados=processados,
                sincronizados=ok,
                falhas=falhas,
                mensagem=f"Processados {processados}/{total}",
            )
            time.sleep(BLING_INTERVALO_SYNC_SEG)
            continue

        if acao == "vincular" and not id_drop:
            falhas += 1
            processados += 1
            erros.append(f"{nome}: selecione a categoria DropNexo.")
            _emit(
                processados=processados,
                sincronizados=ok,
                falhas=falhas,
                mensagem=f"Processados {processados}/{total}",
            )
            time.sleep(BLING_INTERVALO_SYNC_SEG)
            continue

        ultimo_erro: Exception | None = None
        for tentativa in range(BLING_SYNC_MAX_TENTATIVAS):
            try:
                salvar_mapeamento_categoria_ui(
                    cur,
                    id_tenant,
                    contexto,
                    id_bling=id_bling,
                    acao=acao,
                    id_segmento=id_seg,
                    id_dropnexo=id_drop,
                    cache_api=cache,
                )
                ok += 1
                ultimo_erro = None
                break
            except Exception as exc:
                ultimo_erro = exc
                msg = str(exc).lower()
                if "limite" in msg or "too_many" in msg or "429" in msg:
                    time.sleep(min(8.0, 1.5 * (tentativa + 1)))
                    continue
                break

        processados += 1
        if ultimo_erro:
            falhas += 1
            erros.append(f"{nome}: {ultimo_erro}")
        _emit(
            processados=processados,
            sincronizados=ok,
            falhas=falhas,
            mensagem=f"Processados {processados}/{total}",
        )
        time.sleep(BLING_INTERVALO_SYNC_SEG)

    return {
        "total": total,
        "processados": processados,
        "sincronizados": ok,
        "falhas": falhas,
        "erros": erros[:20],
    }


def validar_mapeamento_para_importacao(
    cur,
    id_tenant: int,
    contexto: str,
    *,
    ids_categorias_bling: list[str] | None = None,
    incluir_subcategorias: bool = True,
) -> dict[str, Any]:
    from api.bling.sync_categorias import obter_estado_mapeamento_categoria

    ids_escopo = coletar_ids_categoria_bling_do_escopo(
        id_tenant,
        ids_categorias_bling=ids_categorias_bling,
        incluir_subcategorias=incluir_subcategorias,
    )
    cache_api: dict[str, dict] = {}
    pendentes: list[dict[str, Any]] = []

    if not ids_escopo:
        return {
            "importacao_liberada": True,
            "pendentes": [],
            "total_categorias_escopo": 0,
            "mensagem": "Nenhuma categoria Bling nos produtos do escopo.",
        }

    for id_bling in _ordenar_ids_categoria_bling(ids_escopo, cache_api, id_tenant):
        estado = obter_estado_mapeamento_categoria(cur, id_tenant, contexto, id_bling)
        st = estado.get("status")
        if st not in ("mapeada", "ignorada"):
            cat = _fetch_categoria_bling(id_tenant, id_bling, cache_api)
            pendentes.append(
                {
                    "id_bling": id_bling,
                    "nome_bling": _nome_categoria_bling(cat, id_bling),
                    "caminho_bling": _caminho_categoria_bling(id_bling, cache_api, id_tenant),
                    "motivo": estado.get("motivo") or "nao_mapeada",
                }
            )

    ok = len(pendentes) == 0
    msg = (
        "Importação liberada."
        if ok
        else f"Importação bloqueada: {len(pendentes)} categoria(s) do Bling ainda não mapeada(s). "
        "Configure em Integrações › Bling › Categorias."
    )
    return {
        "importacao_liberada": ok,
        "pendentes": pendentes,
        "total_categorias_escopo": len(ids_escopo),
        "mensagem": msg,
    }
