# api/bling/estoque_sync_progresso.py — sync inicial de estoque após vincular depósito
from __future__ import annotations

import logging
import threading
import uuid
from typing import Any

from flask import Flask

from api.bling.sync_estoque import sincronizar_estoque_inicial_tenant
from global_utils import Var_ConectarBanco

_log = logging.getLogger(__name__)
_lock = threading.Lock()
_jobs: dict[str, dict[str, Any]] = {}


def _atualizar_job(job_id: str, **kwargs) -> None:
    with _lock:
        job = _jobs.get(job_id) or {}
        job.update(kwargs)
        _jobs[job_id] = job


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
                _atualizar_job(
                    job_id,
                    status="concluido",
                    **resultado,
                    mensagem=resultado.get("resumo") or "Concluído",
                )
            except Exception as e:
                conn.rollback()
                _log.exception("Sync estoque inicial tenant=%s", id_tenant)
                _atualizar_job(job_id, status="erro", mensagem=str(e)[:300])
            finally:
                conn.close()

    threading.Thread(target=_worker, daemon=True, name=f"bling-est-{job_id[:8]}").start()
    return job_id


def obter_progresso_sync(job_id: str, id_tenant: int) -> dict[str, Any] | None:
    with _lock:
        job = _jobs.get(job_id)
    if not job or int(job.get("id_tenant") or 0) != int(id_tenant):
        return None
    return dict(job)
