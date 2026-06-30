# api/bling/estoque_sync_progresso.py — sync inicial de estoque após vincular depósito
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from flask import Flask

from api.bling.sync_estoque import sincronizar_estoque_inicial_tenant
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
    id_bling_deposito: str | None = None,
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
    if id_bling_deposito is not None:
        out["id_bling_deposito"] = str(id_bling_deposito)
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
                dados.get("id_bling_deposito"),
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
        _log.exception("Falha ao persistir progresso sync job=%s", job_id[:8])


def iniciar_sync_inicial_deposito(
    app: Flask,
    *,
    id_tenant: int,
    id_bling_deposito: str,
    contexto: str = "fornecedor",
) -> str:
    job_id = str(uuid.uuid4())
    _atualizar_job(
        job_id,
        status="processando",
        id_tenant=id_tenant,
        id_bling_deposito=id_bling_deposito,
        total=0,
        processados=0,
        sincronizados=0,
        falhas=0,
        mensagem="Iniciando…",
    )

    def _worker() -> None:
        with app.app_context():
            conn = Var_ConectarBanco()
            try:
                cur = conn.cursor()

                def _progresso(p: dict[str, int]) -> None:
                    _atualizar_job(job_id, **p)

                resultado = sincronizar_estoque_inicial_tenant(
                    cur,
                    id_tenant,
                    id_bling_deposito=id_bling_deposito,
                    contexto=contexto,
                    on_progresso=_progresso,
                )
                conn.commit()
                from api.bling.depositos import marcar_sync_estoque_deposito_concluido

                marcar_sync_estoque_deposito_concluido(cur, id_tenant, id_bling_deposito)
                conn.commit()
                fim = dict(resultado)
                fim["status"] = "concluido"
                fim["mensagem"] = "Sincronização do depósito efetuada com sucesso"
                _atualizar_job(job_id, **fim)
            except Exception as e:
                conn.rollback()
                _log.exception("Sync estoque inicial tenant=%s", id_tenant)
                _atualizar_job(job_id, status="erro", mensagem=str(e)[:300])
            finally:
                conn.close()

    threading.Thread(target=_worker, daemon=True, name=f"bling-est-{job_id[:8]}").start()
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


def obter_progresso_sync(job_id: str, id_tenant: int) -> dict[str, Any] | None:
    job = _ler_job_db(job_id, int(id_tenant))
    if job:
        return job
    with _lock:
        mem = _jobs_memoria.get(job_id)
    if not mem or int(mem.get("id_tenant") or 0) != int(id_tenant):
        return None
    return dict(mem)


def deposito_tem_sync_ativa(cur, id_tenant: int, id_bling_deposito: str) -> bool:
    from api.bling.depositos import obter_job_sync_ativo_deposito

    return obter_job_sync_ativo_deposito(cur, id_tenant, id_bling_deposito) is not None
