# api/bling/imagens_fila.py — fila + worker de download de imagens (import Bling)
from __future__ import annotations

import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from global_utils import Var_ConectarBanco, agora_utc

_log = logging.getLogger(__name__)

WORKERS_PADRAO = 5
MAX_TENTATIVAS = 3
BATCH_CLAIM = 10

_workers_tenant: dict[int, threading.Thread] = {}
_lock_workers = threading.Lock()
_tabela_ok = False
_tabela_lock = threading.Lock()


def garantir_tabela_download_fila(cur) -> bool:
    """Cria a fila se a migration ainda não rodou. Retorna False se indisponível.

    Usa SAVEPOINT para não envenenar a transação do import se o DDL falhar.
    """
    global _tabela_ok
    if _tabela_ok:
        return True
    with _tabela_lock:
        if _tabela_ok:
            return True
        sp = "sp_img_download_fila"
        try:
            cur.execute(f"SAVEPOINT {sp}")
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS tbl_produto_imagem_download_fila (
                    id              BIGSERIAL PRIMARY KEY,
                    id_tenant       INTEGER NOT NULL,
                    id_produto      INTEGER NOT NULL,
                    id_imagem       INTEGER NOT NULL REFERENCES tbl_produto_imagem(id) ON DELETE CASCADE,
                    url_download    TEXT NOT NULL,
                    status          TEXT NOT NULL DEFAULT 'pendente',
                    tentativas      INTEGER NOT NULL DEFAULT 0,
                    max_tentativas  INTEGER NOT NULL DEFAULT 3,
                    ultimo_erro     TEXT NULL,
                    id_importacao_lote INTEGER NULL,
                    criado_em       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    atualizado_em   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    processado_em   TIMESTAMPTZ NULL,
                    CONSTRAINT uq_produto_imagem_download_fila_img UNIQUE (id_imagem)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_img_download_fila_pendente
                    ON tbl_produto_imagem_download_fila (id_tenant, status, id)
                    WHERE status IN ('pendente', 'processando')
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_img_download_fila_lote
                    ON tbl_produto_imagem_download_fila (id_importacao_lote, status)
                    WHERE id_importacao_lote IS NOT NULL
                """
            )
            cur.execute(f"RELEASE SAVEPOINT {sp}")
            _tabela_ok = True
            return True
        except Exception:
            _log.exception("Não foi possível garantir tbl_produto_imagem_download_fila")
            try:
                cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            except Exception:
                conn = getattr(cur, "connection", None)
                if conn is not None:
                    try:
                        conn.rollback()
                    except Exception:
                        pass
            return False


def enfileirar_download_imagem(
    cur,
    *,
    id_tenant: int,
    id_produto: int,
    id_imagem: int,
    url: str,
    id_importacao_lote: int | None = None,
) -> bool:
    """Registra (ou reabre) job de download. Retorna False se fila indisponível."""
    url = (url or "").strip()
    if not url.startswith(("http://", "https://")):
        return False
    if not garantir_tabela_download_fila(cur):
        return False
    agora = agora_utc()
    cur.execute(
        """
        INSERT INTO tbl_produto_imagem_download_fila (
            id_tenant, id_produto, id_imagem, url_download, status,
            tentativas, max_tentativas, id_importacao_lote, criado_em, atualizado_em
        ) VALUES (%s, %s, %s, %s, 'pendente', 0, %s, %s, %s, %s)
        ON CONFLICT (id_imagem) DO UPDATE SET
            url_download = EXCLUDED.url_download,
            id_importacao_lote = COALESCE(EXCLUDED.id_importacao_lote, tbl_produto_imagem_download_fila.id_importacao_lote),
            status = CASE
                WHEN tbl_produto_imagem_download_fila.status = 'ok' THEN 'ok'
                ELSE 'pendente'
            END,
            tentativas = CASE
                WHEN tbl_produto_imagem_download_fila.status = 'ok' THEN tbl_produto_imagem_download_fila.tentativas
                ELSE 0
            END,
            ultimo_erro = CASE
                WHEN tbl_produto_imagem_download_fila.status = 'ok' THEN tbl_produto_imagem_download_fila.ultimo_erro
                ELSE NULL
            END,
            atualizado_em = EXCLUDED.atualizado_em
        """,
        (
            int(id_tenant),
            int(id_produto),
            int(id_imagem),
            url,
            MAX_TENTATIVAS,
            int(id_importacao_lote) if id_importacao_lote else None,
            agora,
            agora,
        ),
    )
    return True


def contar_fila(
    cur,
    *,
    id_tenant: int | None = None,
    id_importacao_lote: int | None = None,
) -> dict[str, int]:
    if not garantir_tabela_download_fila(cur):
        return {"pendente": 0, "processando": 0, "ok": 0, "erro": 0, "total": 0}
    where = ["1=1"]
    params: list[Any] = []
    if id_tenant is not None:
        where.append("id_tenant = %s")
        params.append(int(id_tenant))
    if id_importacao_lote is not None:
        where.append("id_importacao_lote = %s")
        params.append(int(id_importacao_lote))
    cur.execute(
        f"""
        SELECT status, COUNT(*)
        FROM tbl_produto_imagem_download_fila
        WHERE {' AND '.join(where)}
        GROUP BY status
        """,
        params,
    )
    out = {"pendente": 0, "processando": 0, "ok": 0, "erro": 0, "total": 0}
    for status, n in cur.fetchall():
        st = (status or "").strip().lower()
        if st in out:
            out[st] = int(n)
        out["total"] += int(n)
    return out


def _claim_jobs(
    cur,
    *,
    id_tenant: int,
    id_importacao_lote: int | None,
    limite: int,
) -> list[dict[str, Any]]:
    if not garantir_tabela_download_fila(cur):
        return []
    where = ["id_tenant = %s", "status = 'pendente'", "tentativas < max_tentativas"]
    params: list[Any] = [int(id_tenant)]
    if id_importacao_lote is not None:
        where.append("id_importacao_lote = %s")
        params.append(int(id_importacao_lote))
    params.append(int(limite))
    cur.execute(
        f"""
        SELECT id, id_tenant, id_produto, id_imagem, url_download, tentativas, max_tentativas
        FROM tbl_produto_imagem_download_fila
        WHERE {' AND '.join(where)}
        ORDER BY id ASC
        FOR UPDATE SKIP LOCKED
        LIMIT %s
        """,
        params,
    )
    rows = cur.fetchall()
    if not rows:
        return []
    ids = [int(r[0]) for r in rows]
    cur.execute(
        """
        UPDATE tbl_produto_imagem_download_fila
        SET status = 'processando', atualizado_em = %s
        WHERE id = ANY(%s)
        """,
        (agora_utc(), ids),
    )
    return [
        {
            "id": int(r[0]),
            "id_tenant": int(r[1]),
            "id_produto": int(r[2]),
            "id_imagem": int(r[3]),
            "url_download": r[4],
            "tentativas": int(r[5] or 0),
            "max_tentativas": int(r[6] or MAX_TENTATIVAS),
        }
        for r in rows
    ]


def _processar_job(job: dict[str, Any]) -> dict[str, Any]:
    """Baixa uma imagem em conexão própria. Retorna {id, ok, erro?}."""
    from fornecedor.catalogo.catalogo import (
        baixar_e_gravar_imagem_tenant,
        caminho_eh_url,
        sincronizar_imagem_principal_produto,
    )

    fila_id = int(job["id"])
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        cur.execute(
            "SELECT caminho FROM tbl_produto_imagem WHERE id = %s",
            (int(job["id_imagem"]),),
        )
        row = cur.fetchone()
        if not row:
            cur.execute(
                """
                UPDATE tbl_produto_imagem_download_fila
                SET status = 'erro', ultimo_erro = %s, atualizado_em = %s, processado_em = %s
                WHERE id = %s
                """,
                ("Imagem removida.", agora_utc(), agora_utc(), fila_id),
            )
            conn.commit()
            return {"id": fila_id, "ok": False, "erro": "Imagem removida."}

        caminho_atual = row[0] or ""
        if caminho_atual and not caminho_eh_url(caminho_atual):
            cur.execute(
                """
                UPDATE tbl_produto_imagem_download_fila
                SET status = 'ok', ultimo_erro = NULL, atualizado_em = %s, processado_em = %s
                WHERE id = %s
                """,
                (agora_utc(), agora_utc(), fila_id),
            )
            conn.commit()
            return {"id": fila_id, "ok": True}

        caminho_db, tam = baixar_e_gravar_imagem_tenant(
            id_tenant=int(job["id_tenant"]),
            id_produto=int(job["id_produto"]),
            id_imagem=int(job["id_imagem"]),
            url=str(job["url_download"]),
            leve=True,
        )
        cur.execute(
            """
            UPDATE tbl_produto_imagem
            SET caminho = %s, tamanho_bytes = %s, link_expira_em = NULL
            WHERE id = %s
            """,
            (caminho_db, tam, int(job["id_imagem"])),
        )
        sincronizar_imagem_principal_produto(cur, int(job["id_produto"]))
        cur.execute(
            """
            UPDATE tbl_produto_imagem_download_fila
            SET status = 'ok', tentativas = tentativas + 1,
                ultimo_erro = NULL, atualizado_em = %s, processado_em = %s
            WHERE id = %s
            """,
            (agora_utc(), agora_utc(), fila_id),
        )
        conn.commit()
        return {"id": fila_id, "ok": True}
    except Exception as e:
        conn.rollback()
        try:
            cur = conn.cursor()
            tent = int(job.get("tentativas") or 0) + 1
            max_t = int(job.get("max_tentativas") or MAX_TENTATIVAS)
            status = "erro" if tent >= max_t else "pendente"
            cur.execute(
                """
                UPDATE tbl_produto_imagem_download_fila
                SET status = %s, tentativas = %s, ultimo_erro = %s, atualizado_em = %s,
                    processado_em = CASE WHEN %s = 'erro' THEN %s ELSE processado_em END
                WHERE id = %s
                """,
                (
                    status,
                    tent,
                    str(e)[:500],
                    agora_utc(),
                    status,
                    agora_utc(),
                    fila_id,
                ),
            )
            conn.commit()
        except Exception:
            _log.exception("Falha ao registrar erro da fila imagem id=%s", fila_id)
        return {"id": fila_id, "ok": False, "erro": str(e)[:300]}
    finally:
        conn.close()


def drenar_fila_imagens(
    *,
    id_tenant: int,
    id_importacao_lote: int | None = None,
    workers: int = WORKERS_PADRAO,
    on_progresso: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, int]:
    """Processa pendências em lotes paralelos até esvaziar (ou esgotar tentativas)."""
    workers = max(1, min(int(workers or WORKERS_PADRAO), 8))
    id_tenant = int(id_tenant)

    while True:
        conn = Var_ConectarBanco()
        try:
            cur = conn.cursor()
            jobs = _claim_jobs(
                cur,
                id_tenant=id_tenant,
                id_importacao_lote=id_importacao_lote,
                limite=max(workers, BATCH_CLAIM),
            )
            conn.commit()
        finally:
            conn.close()

        if not jobs:
            break

        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [pool.submit(_processar_job, job) for job in jobs]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception:
                    _log.exception("Erro inesperado no worker de imagem")

        if on_progresso:
            conn = Var_ConectarBanco()
            try:
                cur = conn.cursor()
                on_progresso(contar_fila(cur, id_tenant=id_tenant, id_importacao_lote=id_importacao_lote))
            finally:
                conn.close()

    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        try:
            from fornecedor.catalogo.catalogo import recalcular_bytes_imagens_tenant

            recalcular_bytes_imagens_tenant(cur, id_tenant)
            conn.commit()
        except Exception:
            conn.rollback()
            _log.exception("Falha ao recalcular bytes após fila de imagens tenant=%s", id_tenant)
        resumo = contar_fila(cur, id_tenant=id_tenant, id_importacao_lote=id_importacao_lote)
    finally:
        conn.close()
    return resumo


def _loop_worker_tenant(id_tenant: int) -> None:
    try:
        drenar_fila_imagens(id_tenant=id_tenant, id_importacao_lote=None, workers=WORKERS_PADRAO)
    except Exception:
        _log.exception("Worker de imagens tenant=%s falhou", id_tenant)
    finally:
        with _lock_workers:
            atual = _workers_tenant.get(id_tenant)
            if atual is threading.current_thread():
                _workers_tenant.pop(id_tenant, None)


def disparar_worker_imagens_tenant(id_tenant: int) -> None:
    """Garante um worker daemon por tenant para drenar a fila (fire-and-forget)."""
    id_tenant = int(id_tenant)
    with _lock_workers:
        t = _workers_tenant.get(id_tenant)
        if t and t.is_alive():
            return
        thread = threading.Thread(
            target=_loop_worker_tenant,
            args=(id_tenant,),
            daemon=True,
            name=f"img-download-{id_tenant}",
        )
        _workers_tenant[id_tenant] = thread
        thread.start()
