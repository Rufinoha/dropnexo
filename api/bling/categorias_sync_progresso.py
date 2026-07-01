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
_PAYLOAD_COL: bool | None = None


def _payload_col_disponivel(cur) -> bool:
    global _PAYLOAD_COL
    if _PAYLOAD_COL is not None:
        return _PAYLOAD_COL
    try:
        cur.execute(
            """
            SELECT 1 FROM information_schema.columns
            WHERE table_name = 'tbl_integracao_bling_sync_job' AND column_name = 'payload'
            """
        )
        _PAYLOAD_COL = bool(cur.fetchone())
    except Exception:
        _PAYLOAD_COL = False
    return _PAYLOAD_COL


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
        payload = dados.get("payload")
        if payload is None and dados.get("dados") is not None:
            payload = dados.get("dados")
        payload_json: str | None = None
        if payload is not None:
            try:
                payload_json = json.dumps(payload, ensure_ascii=False, default=str)
            except Exception:
                _log.exception("Serializar payload job=%s", job_id[:8])
                payload_json = None
        params = (
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
        )
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
            params,
        )
        if payload_json and _payload_col_disponivel(cur):
            try:
                cur.execute(
                    """
                    UPDATE tbl_integracao_bling_sync_job
                    SET payload = %s::jsonb, atualizado_em = %s
                    WHERE job_id = %s
                    """,
                    (payload_json, agora_utc(), job_id),
                )
            except Exception:
                _log.exception("Falha ao gravar payload job=%s", job_id[:8])
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
                from api.bling.sync_categorias import (
                    carregar_mapa_categorias_bling_listagem,
                    obter_cache_categorias_bling_enriquecido,
                )

                def _progresso_prep(**p) -> None:
                    _atualizar_job(job_id, **p)

                cache = obter_cache_categorias_bling_enriquecido(
                    id_tenant,
                    cache_api=carregar_mapa_categorias_bling_listagem(id_tenant),
                    on_progresso=_progresso_prep,
                )
                _atualizar_job(job_id, mensagem="Iniciando…", total=len(acoes or []))

                cur = conn.cursor()

                def _progresso(**p) -> None:
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


def iniciar_reparar_hierarquia_categorias(
    app: Flask,
    *,
    id_tenant: int,
    contexto: str,
) -> str:
    job_id = str(uuid.uuid4())
    _atualizar_job(
        job_id,
        status="processando",
        id_tenant=id_tenant,
        total=0,
        processados=0,
        sincronizados=0,
        falhas=0,
        mensagem="Iniciando reparo…",
        resumo=json.dumps({"tipo": "categorias_reparo_hierarquia"}, ensure_ascii=False),
    )

    def _worker() -> None:
        with app.app_context():
            conn = Var_ConectarBanco()
            try:
                from api.bling.sync_categorias import reparar_hierarquia_categorias_mapeadas

                cur = conn.cursor()

                def _progresso(**p) -> None:
                    _atualizar_job(job_id, **p)

                resultado = reparar_hierarquia_categorias_mapeadas(
                    cur,
                    id_tenant,
                    contexto,
                    on_progresso=_progresso,
                )
                conn.commit()

                falhas = int(resultado.get("falhas") or 0)
                ok = int(resultado.get("sincronizados") or 0)
                erros = resultado.get("erros") or []
                msg = resultado.get("mensagem") or f"{ok} categoria(s) reorganizada(s)."
                if falhas and ok:
                    msg = f"{msg} {falhas} categoria(s) ignorada(s) (não existem mais no Bling)."
                elif falhas and not ok:
                    msg = (
                        erros[0]
                        if erros
                        else "Nenhuma categoria pôde ser reorganizada. Verifique os mapeamentos no Bling."
                    )
                _atualizar_job(
                    job_id,
                    status="concluido" if ok or not falhas else "erro",
                    total=int(resultado.get("total") or 0),
                    processados=int(resultado.get("processados") or 0),
                    sincronizados=ok,
                    falhas=falhas,
                    mensagem=msg,
                    resumo=json.dumps(
                        {"tipo": "categorias_reparo_hierarquia", "erros": (resultado.get("erros") or [])[:10]},
                        ensure_ascii=False,
                    )[:500],
                )
            except Exception as e:
                conn.rollback()
                _log.exception("Reparo hierarquia categorias tenant=%s", id_tenant)
                _atualizar_job(job_id, status="erro", mensagem=str(e)[:300])
            finally:
                conn.close()

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"bling-cat-fix-{job_id[:8]}",
    ).start()
    return job_id


def iniciar_carregar_painel_categorias(
    app: Flask,
    *,
    id_tenant: int,
    contexto: str,
) -> str:
    job_id = str(uuid.uuid4())
    _atualizar_job(
        job_id,
        status="processando",
        id_tenant=id_tenant,
        total=0,
        processados=0,
        sincronizados=0,
        falhas=0,
        mensagem="Carregando categorias do Bling…",
        resumo=json.dumps({"tipo": "categorias_painel", "contexto": contexto}, ensure_ascii=False),
    )

    def _atualizar_painel(**kwargs) -> None:
        if "dados" in kwargs:
            kwargs["payload"] = kwargs.pop("dados")
        kwargs.setdefault("id_tenant", id_tenant)
        _atualizar_job(job_id, **kwargs)

    def _worker() -> None:
        with app.app_context():
            conn = Var_ConectarBanco()
            try:
                from api.bling.mapeamento_categorias import listar_painel_categorias_bling
                from api.bling.sync_categorias import (
                    carregar_mapa_categorias_bling_listagem,
                    cache_categorias_precisa_enriquecer,
                    obter_cache_categorias_bling_enriquecido,
                )

                cache = carregar_mapa_categorias_bling_listagem(id_tenant)
                total = len(cache)
                _atualizar_painel(total=total, mensagem="Consultando hierarquia no Bling…")

                if cache_categorias_precisa_enriquecer(cache):

                    def _prog(**p) -> None:
                        _atualizar_painel(
                            total=int(p.get("total") or total),
                            processados=int(p.get("processados") or 0),
                            mensagem=str(p.get("mensagem") or ""),
                        )

                    cache = obter_cache_categorias_bling_enriquecido(
                        id_tenant,
                        cache_api=cache,
                        on_progresso=_prog,
                    )

                _atualizar_painel(
                    processados=total,
                    total=total,
                    mensagem="Montando árvore de categorias…",
                )

                cur = conn.cursor()
                dados = listar_painel_categorias_bling(
                    cur,
                    id_tenant,
                    contexto,
                    cache_api=cache,
                    cache_enriquecido=True,
                )
                _atualizar_painel(
                    status="concluido",
                    processados=total,
                    total=total,
                    mensagem=f"{len(dados.get('categorias') or [])} categorias carregadas.",
                    dados=dados,
                )
            except Exception as e:
                _log.exception("Carregar painel categorias tenant=%s", id_tenant)
                _atualizar_painel(status="erro", mensagem=str(e)[:300])
            finally:
                conn.close()

    threading.Thread(
        target=_worker,
        daemon=True,
        name=f"bling-cat-panel-{job_id[:8]}",
    ).start()
    return job_id


def _ler_job_painel_db(job_id: str, id_tenant: int) -> dict[str, Any] | None:
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        if not _tabela_disponivel(cur):
            return None
        if _payload_col_disponivel(cur):
            cur.execute(
                """
                SELECT status, total, processados, mensagem, resumo, payload
                FROM tbl_integracao_bling_sync_job
                WHERE job_id = %s AND id_tenant = %s
                """,
                (job_id, int(id_tenant)),
            )
        else:
            cur.execute(
                """
                SELECT status, total, processados, mensagem, resumo, NULL
                FROM tbl_integracao_bling_sync_job
                WHERE job_id = %s AND id_tenant = %s
                """,
                (job_id, int(id_tenant)),
            )
        row = cur.fetchone()
        if not row:
            return None
        resumo_raw = row[4]
        tipo = ""
        if resumo_raw:
            try:
                meta = json.loads(resumo_raw) if isinstance(resumo_raw, str) else resumo_raw
                tipo = (meta.get("tipo") or "") if isinstance(meta, dict) else ""
            except Exception:
                tipo = ""
        if tipo != "categorias_painel":
            return None
        out: dict[str, Any] = {
            "status": row[0],
            "total": int(row[1] or 0),
            "processados": int(row[2] or 0),
            "mensagem": row[3] or "",
        }
        payload = row[5]
        if isinstance(payload, str):
            try:
                payload = json.loads(payload)
            except Exception:
                payload = None
        if row[0] == "concluido" and isinstance(payload, dict):
            out["dados"] = payload
        elif row[0] == "concluido":
            out["recarregar_sync"] = True
        return out
    finally:
        conn.close()


def obter_job_painel_categorias(job_id: str, id_tenant: int) -> dict[str, Any] | None:
    db_job = _ler_job_painel_db(job_id, int(id_tenant))
    with _lock:
        mem = dict(_jobs_memoria.get(job_id) or {})
    if int(mem.get("id_tenant") or 0) not in (0, int(id_tenant)) and not db_job:
        return None
    if mem and "categorias_painel" not in str(mem.get("resumo") or ""):
        mem = {}

    job: dict[str, Any] = dict(db_job or {})
    if mem and int(mem.get("id_tenant") or 0) == int(id_tenant):
        mem_status = mem.get("status") or "processando"
        db_status = job.get("status") or "processando"
        if not job or mem_status in ("concluido", "erro") and db_status == "processando":
            job = {
                "status": mem_status,
                "total": int(mem.get("total") or job.get("total") or 0),
                "processados": int(mem.get("processados") or job.get("processados") or 0),
                "mensagem": mem.get("mensagem") or job.get("mensagem") or "",
            }
            payload = mem.get("payload") or mem.get("dados")
            if mem_status == "concluido" and isinstance(payload, dict):
                job["dados"] = payload
            elif mem_status == "concluido":
                job["recarregar_sync"] = True

    if not job:
        return None
    return job


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
