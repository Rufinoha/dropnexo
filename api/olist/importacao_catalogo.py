# api/olist/importacao_catalogo.py — importação do catálogo no mesmo fluxo da aba Bling
from __future__ import annotations

import logging
import threading
from typing import Any

from flask import Flask

from api.olist.cliente import api_request
from api.olist.painel import listar_categorias, listar_depositos, salvar_categoria
from api.olist.produtos import _id_categoria_olist, importar_lote
from fornecedor.importacao.servico_importacao import (
    MODULO_CATALOGO,
    ORIGEM_INTEGRACAO,
    STATUS_CONCLUIDO,
    STATUS_ERRO,
    STATUS_PROCESSANDO,
    atualizar_progresso_lote,
    criar_lote,
    finalizar_lote,
    marcar_lote_erro_fatal,
)
from global_utils import Var_ConectarBanco

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_threads: dict[int, threading.Thread] = {}


def _expandir_filhas(nos: list[dict], ids: set[str]) -> set[str]:
    filhos: dict[str, list[str]] = {}
    for no in nos:
        filhos.setdefault(str(no.get("id_pai") or ""), []).append(str(no.get("id") or ""))
    saida = {i for i in ids if i}
    pilha = list(saida)
    while pilha:
        atual = pilha.pop()
        for filho in filhos.get(atual, []):
            if filho and filho not in saida:
                saida.add(filho)
                pilha.append(filho)
    return saida


def _ids_categoria_nos_produtos(id_tenant: int) -> set[str]:
    offset = 0
    ids: set[str] = set()
    while True:
        dados = api_request(
            id_tenant,
            "GET",
            "/produtos",
            params={"situacao": "A", "limit": 100, "offset": offset},
        )
        if isinstance(dados, list):
            itens = dados
            pag = {}
        elif isinstance(dados, dict):
            itens = dados.get("itens") if isinstance(dados.get("itens"), list) else []
            pag = dados.get("paginacao") if isinstance(dados.get("paginacao"), dict) else {}
        else:
            break
        for item in itens:
            if isinstance(item, dict):
                cid = _id_categoria_olist(item)
                if cid:
                    ids.add(cid)
        if not itens or len(itens) < 100:
            break
        total = pag.get("total")
        offset += len(itens)
        try:
            if total is not None and offset >= int(total):
                break
        except (TypeError, ValueError):
            pass
    return ids


def _segmento_padrao(cur, id_tenant: int) -> int | None:
    cur.execute(
        """
        SELECT id_segmento FROM tbl_fornecedor_segmento
        WHERE id_tenant = %s
        ORDER BY id_segmento
        LIMIT 1
        """,
        (int(id_tenant),),
    )
    row = cur.fetchone()
    return int(row[0]) if row and row[0] else None


def _contar_locais(cur, id_tenant: int) -> tuple[int, int]:
    cur.execute(
        "SELECT COUNT(*)::int FROM tbl_categoria WHERE id_tenant = %s AND ativo = TRUE",
        (int(id_tenant),),
    )
    n_cat = int(cur.fetchone()[0] or 0)
    cur.execute(
        "SELECT COUNT(*)::int FROM tbl_deposito_expedicao WHERE id_tenant = %s AND ativo = TRUE",
        (int(id_tenant),),
    )
    n_dep = int(cur.fetchone()[0] or 0)
    return n_cat, n_dep


def _modulo_olist_desligado(erro: BaseException) -> bool:
    return "não tem o módulo" in str(erro)


def escopo_categorias(
    cur,
    id_tenant: int,
    *,
    ids_categorias: list[str] | None,
    incluir_subcategorias: bool,
) -> tuple[list[dict], set[str] | None]:
    """Retorna (categorias do escopo, ids para filtrar produtos). None = todos."""
    dados = listar_categorias(cur, id_tenant)
    nos = dados.get("olist") or []
    if ids_categorias:
        escolhidos = {str(i).strip() for i in ids_categorias if str(i or "").strip()}
        if incluir_subcategorias:
            escolhidos = _expandir_filhas(nos, escolhidos)
        return [n for n in nos if str(n.get("id")) in escolhidos], escolhidos
    presentes = _ids_categoria_nos_produtos(id_tenant)
    if not presentes:
        return [], None
    return [n for n in nos if str(n.get("id")) in presentes], None


def pre_analisar_importacao(
    cur,
    id_tenant: int,
    *,
    ids_categorias: list[str] | None,
    incluir_subcategorias: bool,
) -> dict[str, Any]:
    n_cat, n_dep = _contar_locais(cur, id_tenant)
    bootstrap = n_cat == 0 and n_dep == 0
    sem_categorias_olist = False
    sem_depositos_olist = False
    try:
        escopo, ids_filtro = escopo_categorias(
            cur,
            id_tenant,
            ids_categorias=ids_categorias,
            incluir_subcategorias=incluir_subcategorias,
        )
    except RuntimeError as e:
        if _modulo_olist_desligado(e) and not ids_categorias:
            escopo, ids_filtro = [], None
            sem_categorias_olist = True
        elif _modulo_olist_desligado(e):
            raise ValueError(
                "A conta no Olist não tem o módulo Categorias ativado. "
                "Importe todos os produtos. O vínculo fica para depois."
            ) from e
        else:
            raise ValueError(str(e)) from e

    cur.execute(
        """
        SELECT id_olist, acao, id_categoria
        FROM tbl_integracao_olist_categoria
        WHERE id_tenant = %s
        """,
        (int(id_tenant),),
    )
    mapa = {str(r[0]): (str(r[1] or ""), r[2]) for r in cur.fetchall()}
    pendentes = []
    for cat in escopo:
        cid = str(cat.get("id") or "")
        acao, id_drop = mapa.get(cid, ("", None))
        if acao == "ignorar" or (acao == "vincular" and id_drop):
            continue
        pendentes.append(
            {
                "id_bling": cid,
                "nome_bling": cat.get("nome") or cid,
                "caminho_bling": cat.get("caminho") or cat.get("nome") or cid,
            }
        )

    try:
        deps = listar_depositos(cur, id_tenant)
    except RuntimeError as e:
        deps = {"olist": [], "dropnexo": []}
        sem_depositos_olist = _modulo_olist_desligado(e)
    except Exception:
        deps = {"olist": [], "dropnexo": []}
    pend_dep = [d for d in (deps.get("olist") or []) if not d.get("id_deposito")]
    bloqueio_dep = bool(deps.get("dropnexo")) and bool(pend_dep) and not bootstrap
    bloqueio_cat = bool(pendentes) and not bootstrap

    if bloqueio_cat:
        msg = (
            f"Importação bloqueada: {len(pendentes)} categoria(s) do Olist sem vínculo. "
            "Configure em Integrações › Olist › Categorias."
        )
    elif bloqueio_dep:
        msg = (
            f"Importação bloqueada: {len(pend_dep)} depósito(s) do Olist sem vínculo. "
            "Configure em Integrações › Olist › Depósitos."
        )
    elif sem_categorias_olist or sem_depositos_olist:
        faltam = []
        if sem_categorias_olist:
            faltam.append("categorias")
        if sem_depositos_olist:
            faltam.append("depósitos")
        msg = (
            "Importação liberada sem "
            + " e sem ".join(faltam)
            + " do Olist. O vínculo fica para depois."
        )
    elif bootstrap:
        msg = "Importação liberada com bootstrap (estrutura local vazia)."
    else:
        msg = "Importação liberada."

    return {
        "exibir_modal": False,
        "mapeadas": [],
        "pendentes": pendentes,
        "total_produtos_escopo": 0,
        "ids_filtro": sorted(ids_filtro) if ids_filtro is not None else None,
        "validacao": {
            "importacao_liberada": not bloqueio_cat and not bloqueio_dep,
            "bootstrap": bootstrap,
            "mensagem": msg,
            "categorias": {
                "importacao_liberada": not bloqueio_cat,
                "pendentes": pendentes,
            },
            "depositos": {
                "importacao_liberada": not bloqueio_dep,
                "pendentes": [
                    {"id_bling": d.get("id"), "nome_bling": d.get("nome")} for d in pend_dep
                ],
            },
        },
        "importacao_liberada": not bloqueio_cat and not bloqueio_dep,
        "bootstrap": bootstrap,
        "sem_categorias_olist": sem_categorias_olist,
        "sem_depositos_olist": sem_depositos_olist,
    }


def _criar_categorias_bootstrap(cur, id_tenant: int, escopo: list[dict]) -> None:
    segmento = _segmento_padrao(cur, id_tenant)
    if not segmento:
        return
    for cat in escopo:
        salvar_categoria(
            cur,
            id_tenant,
            {
                "id_olist": cat.get("id"),
                "nome": cat.get("nome") or cat.get("caminho") or "Categoria",
                "acao": "criar",
                "id_segmento": segmento,
            },
        )


def _worker_importacao(
    app: Flask,
    *,
    id_tenant: int,
    id_lote: int,
    ids_filtro: list[str] | None,
    bootstrap: bool,
    ids_categorias: list[str] | None,
    incluir_subcategorias: bool,
    sem_categorias_olist: bool = False,
) -> None:
    with app.app_context():
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            if bootstrap and not sem_categorias_olist:
                escopo, _ = escopo_categorias(
                    cur,
                    id_tenant,
                    ids_categorias=ids_categorias,
                    incluir_subcategorias=incluir_subcategorias,
                )
                _criar_categorias_bootstrap(cur, id_tenant, escopo)
                conn.commit()

            offset = 0
            importados = atualizados = rejeitadas = ignorados = 0
            total = 0
            processados = 0
            filtro = set(ids_filtro) if ids_filtro is not None else None
            while True:
                res = importar_lote(
                    cur,
                    id_tenant,
                    offset,
                    ids_categorias=filtro,
                    id_importacao_lote=id_lote,
                    respeitar_ignorar=True,
                )
                importados += int(res.get("importados") or 0)
                atualizados += int(res.get("atualizados") or 0)
                rejeitadas += len(res.get("erros") or [])
                ignorados += int(res.get("ignorados") or 0)
                total = int(res.get("total") or total)
                processados = int(res.get("proximo_offset") or 0)
                atualizar_progresso_lote(
                    cur,
                    id_lote,
                    total=total,
                    processados=processados,
                    importados=importados,
                    atualizados=atualizados,
                    rejeitadas=rejeitadas,
                    ignorados=ignorados,
                )
                conn.commit()
                if res.get("fim"):
                    break
                offset = int(res.get("proximo_offset") or 0)

            status = STATUS_ERRO if importados + atualizados == 0 and rejeitadas else STATUS_CONCLUIDO
            msg = f"{importados} novo(s), {atualizados} atualizado(s), {rejeitadas} erro(s)."
            finalizar_lote(
                cur,
                id_lote,
                status=status,
                total_linhas=total or processados,
                total_importadas=importados,
                total_atualizadas=atualizados,
                total_rejeitadas=rejeitadas,
                meta={
                    "fase": "concluido",
                    "mensagem": msg,
                    "status_importacao": "aviso" if rejeitadas else "ok",
                    "processados": total or processados,
                },
            )
            conn.commit()
        except Exception as exc:
            _log.exception("Importação Olist lote %s falhou", id_lote)
            try:
                conn.rollback()
                cur = conn.cursor()
                marcar_lote_erro_fatal(cur, id_lote, str(exc))
                conn.commit()
            except Exception:
                _log.exception("Falha ao marcar lote Olist %s como erro", id_lote)
        finally:
            conn.close()
            with _lock:
                _threads.pop(id_lote, None)


def iniciar_importacao_olist_async(
    app: Flask,
    *,
    id_tenant: int,
    id_usuario: int | None,
    ids_categorias: list[str] | None,
    incluir_subcategorias: bool,
    ids_filtro: list[str] | None,
    bootstrap: bool,
    sem_categorias_olist: bool = False,
) -> dict[str, Any]:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        id_lote, numero = criar_lote(
            cur,
            id_tenant=id_tenant,
            modulo=MODULO_CATALOGO,
            origem=ORIGEM_INTEGRACAO,
            id_usuario=id_usuario,
            provedor="olist",
            nome_lote="Olist — fornecedor",
            meta={
                "fase": "iniciando",
                "ids_categorias_olist": ids_categorias,
                "incluir_subcategorias": incluir_subcategorias,
                "bootstrap": bool(bootstrap),
            },
        )
        conn.commit()
    finally:
        conn.close()

    thread = threading.Thread(
        target=_worker_importacao,
        kwargs={
            "app": app,
            "id_tenant": id_tenant,
            "id_lote": id_lote,
            "ids_filtro": ids_filtro,
            "bootstrap": bool(bootstrap),
            "ids_categorias": ids_categorias,
            "incluir_subcategorias": incluir_subcategorias,
            "sem_categorias_olist": bool(sem_categorias_olist),
        },
        daemon=True,
        name=f"olist-import-{id_lote}",
    )
    with _lock:
        _threads[id_lote] = thread
    thread.start()
    return {"id_lote": id_lote, "numero": numero, "status": STATUS_PROCESSANDO}
