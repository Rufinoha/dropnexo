# api/bling/importacao_progresso.py — importação Bling em background com progresso
from __future__ import annotations

import logging
import threading
from typing import Any

from flask import Flask

from api.bling.sync_produtos import importar_produtos
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
    obter_lote,
    obter_meta_lote,
    progresso_importacao_dict,
)
from global_utils import Var_ConectarBanco

_log = logging.getLogger(__name__)

_threads_ativos: dict[int, threading.Thread] = {}
_lock = threading.Lock()

PROGRESSO_COMMIT_CADA = 3


def _worker_importacao(
    app: Flask,
    *,
    id_tenant: int,
    id_lote: int,
    contexto: str,
    ids_categorias_bling: list[str] | None,
    incluir_subcategorias: bool,
    id_usuario: int | None,
) -> None:
    with app.app_context():
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE tbl_importacao_lote
                SET meta = COALESCE(meta, '{}'::jsonb) || '{"fase":"listando"}'::jsonb
                WHERE id = %s
                """,
                (id_lote,),
            )
            conn.commit()

            def _on_progresso(p: dict[str, int]) -> None:
                atualizar_progresso_lote(
                    cur,
                    id_lote,
                    total=p["total"],
                    processados=p["processados"],
                    importados=p["importados"],
                    atualizados=p["atualizados"],
                    rejeitadas=p["rejeitadas"],
                    ignorados=p.get("ignorados") or 0,
                )
                conn.commit()

            resultado = importar_produtos(
                cur,
                id_tenant,
                contexto,
                ids_categorias_bling=ids_categorias_bling,
                incluir_subcategorias=incluir_subcategorias,
                id_importacao_lote=id_lote,
                id_usuario=id_usuario,
                modo_categorias="mapeamento",
                on_progresso=_on_progresso,
                intervalo_progresso=PROGRESSO_COMMIT_CADA,
            )
            conn.commit()

            status_res = resultado.get("status") or "ok"
            importados = int(resultado.get("importados") or 0)
            atualizados = int(resultado.get("atualizados") or 0)
            total_falhas = int(resultado.get("total_falhas") or 0)
            total_linhas = int(resultado.get("total_jobs") or 0)

            if status_res == "erro":
                msg = f"Nenhum produto importado. {total_falhas} com falha."
            elif status_res == "aviso":
                msg = f"Concluída com {total_falhas} falha(s)."
            else:
                msg = "Importação concluída com sucesso."

            lote_status = STATUS_ERRO if importados + atualizados == 0 and total_falhas else STATUS_CONCLUIDO
            finalizar_lote(
                cur,
                id_lote,
                status=lote_status,
                total_linhas=total_linhas,
                total_importadas=importados,
                total_atualizadas=atualizados,
                total_rejeitadas=total_falhas,
                meta={
                    "fase": "concluido",
                    "mensagem": msg,
                    "status_importacao": status_res,
                    "processados": total_linhas,
                },
            )
            conn.commit()
        except Exception as exc:
            _log.exception("Importação Bling lote %s falhou", id_lote)
            try:
                conn.rollback()
                cur = conn.cursor()
                marcar_lote_erro_fatal(cur, id_lote, str(exc))
                conn.commit()
            except Exception:
                _log.exception("Falha ao marcar lote %s como erro", id_lote)
        finally:
            conn.close()
            with _lock:
                _threads_ativos.pop(id_lote, None)


def iniciar_importacao_bling_async(
    app: Flask,
    *,
    id_tenant: int,
    contexto: str,
    ids_categorias_bling: list[str] | None,
    incluir_subcategorias: bool,
    id_usuario: int | None,
) -> dict[str, Any]:
    """Cria lote, dispara thread de importação e retorna id imediatamente."""
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        id_lote, numero = criar_lote(
            cur,
            id_tenant=id_tenant,
            modulo=MODULO_CATALOGO,
            origem=ORIGEM_INTEGRACAO,
            id_usuario=id_usuario,
            provedor="bling",
            nome_lote=f"Bling — {contexto}",
            meta={
                "contexto": contexto,
                "fase": "iniciando",
                "ids_categorias_bling": ids_categorias_bling,
                "incluir_subcategorias": incluir_subcategorias,
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
            "contexto": contexto,
            "ids_categorias_bling": ids_categorias_bling,
            "incluir_subcategorias": incluir_subcategorias,
            "id_usuario": id_usuario,
        },
        daemon=True,
        name=f"bling-import-{id_lote}",
    )
    with _lock:
        _threads_ativos[id_lote] = thread
    thread.start()

    return {"id_lote": id_lote, "numero": numero, "status": STATUS_PROCESSANDO}


def obter_progresso_bling(id_tenant: int, id_lote: int) -> dict[str, Any] | None:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        lote = obter_lote(cur, id_tenant, id_lote, modulo=MODULO_CATALOGO)
        if not lote:
            return None
        meta = obter_meta_lote(cur, id_tenant, id_lote)
        return progresso_importacao_dict(lote, meta)
    finally:
        conn.close()
