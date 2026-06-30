# api/bling/categorias_sync_progresso.py — salvar mapeamento de categorias em lote (background)
from __future__ import annotations

import json
import logging
import threading
import uuid
from typing import Any

from flask import Flask

from api.bling.mapeamento_categorias import processar_lote_mapeamento_categorias_ui
from api.bling.sync_categorias import carregar_mapa_categorias_bling_listagem
from global_utils import Var_ConectarBanco, agora_utc

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_jobs_memoria: dict[str, dict[str, Any]] = {}
_USE_DB: bool | None = None


def _tabela_disponivel(cur) -> bool:
    global _USE_DB
    if _USE_DB is not None:
        return _USE_DB
    try:
        cur.execute("SELECT 1 FROM tbl_integracao_bling_sync_job LIMIT 1")
        _USE_DB = True
    except Exception:
        _USE_DB = False
    return _USE_DB


def _job_dict(
    *,
    status: str = "processando",
    id_tenant: int | None = None,
    total: int = 0,
    processados: int = 0,
    sincronizados: int = 0,
    falhas: int = 0,
    mensagem: str = "",
    resumo: str | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "status": status,
        "total": int(total or 0),
        "processados": int(processados or 0),
        "sincronizados": int(sincronizados or 0),
        "falhas": int(falhas or 0),
        "mensagem": mensagem or "",
    }
    if id_tenant is not None:
        out["id_tenant"] = int(id_tenant)
    if resumo:
        out["resumo"] = resumo
    return out


def _salvar_job_db(job_id: str, dados: dict[str, Any]) -> None:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not _tabela_disponivel(cur):
            return
        cur.execute(
            """
            INSERT INTO tbl_integracao_bling_sync_job (
                job_id, id_tenant, id_bling_deposito, status,
                total, processados, sincronizados, falhas, mensagem, resumo, atualizado_em
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (job_id) DO UPDATE SET
                status = EXCLUDED.status,
                total = EXCLUDED.total,
                processados = EXCLUDED.processados,
                sincronizados = EXCLUDED.sincronizados,
                falhas = EXCLUDED.falhas,
                mensagem = EXCLUDED.mensagem,
                resumo = COALESCE(EXCLUDED.resumo, tbl_integracao_bling_sync_job.resumo),
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (
                job_id,
                int(dados.get("id_tenant") or 0),
                None,
                dados.get("status") or "processando",
                int(dados.get("total") or 0),
                int(dados.get("processados") or 0),
                int(dados.get("sincronizados") or 0),
                int(dados.get("falhas") or 0),
                (dados.get("mensagem") or "")[:500] or None,
                (dados.get("resumo") or "")[:500] or None,
                agora_utc(),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _atualizar_job(job_id: str, **kwargs) -> None:
    with _lock:
        job = dict(_jobs_memoria.get(job_id) or {})
        job.update(kwargs)
        _jobs_memoria[job_id] = job
    try:
        _salvar_job_db(job_id, job)
    except Exception:
        _log.exception("Falha ao persistir progresso categorias job=%s", job_id[:8])


def iniciar_salvar_categorias_lote(
    app: Flask,
    *,
    id_tenant: int,
    contexto: str,
    acoes: list[dict[str, Any]],
) -> str:
    job_id = str(uuid.uuid4())
    total = len(acoes or [])
    _atualizar_job(
        job_id,
        status="processando",
        id_tenant=id_tenant,
        total=total,
        processados=0,
        sincronizados=0,
        falhas=0,
        mensagem="Carregando categorias do Bling…",
        resumo=json.dumps({"tipo": "categorias_mapeamento"}, ensure_ascii=False),
    )

    def _worker() -> None:
        with app.app_context():
            conn = Var_ConectarBanco()
            try:
                cache = carregar_mapa_categorias_bling_listagem(id_tenant)
                _atualizar_job(job_id, mensagem="Iniciando…", total=len(acoes or []))

                cur = conn.cursor()

                def _progresso(p: dict[str, int | str]) -> None:
                    _atualizar_job(job_id, **p)

                resultado = processar_lote_mapeamento_categorias_ui(
                    cur,
                    id_tenant,
                    contexto,
                    acoes,
                    on_progresso=_progresso,
                    cache_api=cache,
                )
                conn.commit()

                erros = resultado.get("erros") or []
                resumo = json.dumps(
                    {"tipo": "categorias_mapeamento", "erros": erros[:10]},
                    ensure_ascii=False,
                )[:500]
                falhas = int(resultado.get("falhas") or 0)
                ok = int(resultado.get("sincronizados") or 0)

                if falhas and ok:
                    msg = f"{ok} salva(s), {falhas} falha(s)."
                    status = "concluido"
                elif falhas:
                    msg = erros[0][:200] if erros else "Nenhuma categoria salva."
                    status = "erro"
                else:
                    msg = f"{ok} categoria(s) salva(s)."
                    status = "concluido"

                _atualizar_job(
                    job_id,
                    status=status,
                    total=int(resultado.get("total") or 0),
                    processados=int(resultado.get("processados") or 0),
                    sincronizados=ok,
                    falhas=falhas,
                    mensagem=msg,
                    resumo=resumo,
                )
            except Exception as e:
                conn.rollback()
                _log.exception("Salvar categorias lote tenant=%s", id_tenant)
                _atualizar_job(job_id, status="erro", mensagem=str(e)[:300])
            finally:
                conn.close()

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"bling-cat-{job_id[:8]}",
    ).start()
    return job_id


def _ler_job_db(job_id: str, id_tenant: int) -> dict[str, Any] | None:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not _tabela_disponivel(cur):
            return None
        cur.execute(
            """
            SELECT status, total, processados, sincronizados, falhas, mensagem, resumo
            FROM tbl_integracao_bling_sync_job
            WHERE job_id = %s AND id_tenant = %s
            """,
            (job_id, int(id_tenant)),
        )
        row = cur.fetchone()
        if not row:
            return None
        return _job_dict(
            status=row[0],
            total=row[1],
            processados=row[2],
            sincronizados=row[3],
            falhas=row[4],
            mensagem=row[5] or "",
            resumo=row[6],
        )
    finally:
        conn.close()


def obter_progresso_categorias(job_id: str, id_tenant: int) -> dict[str, Any] | None:
    job = _ler_job_db(job_id, int(id_tenant))
    if job:
        return job
    with _lock:
        mem = _jobs_memoria.get(job_id)
    if not mem or int(mem.get("id_tenant") or 0) != int(id_tenant):
        return None
    return dict(mem)
