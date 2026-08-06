# sistema/tarefas_secundarias/servico.py — catálogo de tarefas agendadas + cache ML
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from global_utils import Var_ConectarBanco, agora_utc

_log = logging.getLogger(__name__)

ML_API_BASE = "https://api.mercadolibre.com"
ML_CAT_TIMEOUT = (5, 25)
TZ_BR = ZoneInfo("America/Sao_Paulo")

CODIGO_ML_CATEGORIAS = "ml_categorias_cache"


class TarefaSecundariaErro(RuntimeError):
    """Erro de tarefa com log detalhado para a UI."""

    def __init__(self, mensagem: str, log_texto: str = ""):
        super().__init__(mensagem)
        self.log_texto = log_texto or mensagem


def garantir_tabelas_tarefas(cur) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_tarefa_secundaria (
            id SERIAL PRIMARY KEY,
            codigo VARCHAR(64) NOT NULL UNIQUE,
            nome VARCHAR(160) NOT NULL,
            descricao TEXT,
            agendamento VARCHAR(80) NOT NULL DEFAULT 'manual',
            ativo BOOLEAN NOT NULL DEFAULT TRUE,
            meta JSONB NOT NULL DEFAULT '{}',
            criado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_tarefa_secundaria_execucao (
            id SERIAL PRIMARY KEY,
            id_tarefa INTEGER NOT NULL REFERENCES tbl_tarefa_secundaria(id) ON DELETE CASCADE,
            status VARCHAR(32) NOT NULL DEFAULT 'pendente',
            disparado_por VARCHAR(32) NOT NULL DEFAULT 'cron',
            iniciado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            finalizado_em TIMESTAMPTZ,
            mensagem TEXT,
            log_texto TEXT,
            meta JSONB NOT NULL DEFAULT '{}'
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS tbl_ml_categoria_cache (
            id SERIAL PRIMARY KEY,
            site_id VARCHAR(8) NOT NULL,
            category_id VARCHAR(32) NOT NULL,
            nome VARCHAR(255) NOT NULL,
            path_nomes TEXT NOT NULL DEFAULT '',
            path_ids TEXT NOT NULL DEFAULT '',
            atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            UNIQUE (site_id, category_id)
        )
        """
    )
    cur.execute(
        """
        INSERT INTO tbl_tarefa_secundaria (codigo, nome, descricao, agendamento, ativo)
        VALUES (
            %s,
            'Cache de categorias Mercado Livre',
            'Baixa categorias publicáveis (folha) por site das contas conectadas e atualiza o cache usado no mapeamento.',
            'segunda',
            TRUE
        )
        ON CONFLICT (codigo) DO NOTHING
        """,
        (CODIGO_ML_CATEGORIAS,),
    )


def listar_tarefas_secundarias(cur) -> list[dict]:
    garantir_tabelas_tarefas(cur)
    cur.execute(
        """
        SELECT t.id, t.codigo, t.nome, t.descricao, t.agendamento, t.ativo,
               e.id, e.status, e.disparado_por, e.iniciado_em, e.finalizado_em,
               e.mensagem
        FROM tbl_tarefa_secundaria t
        LEFT JOIN LATERAL (
            SELECT id, status, disparado_por, iniciado_em, finalizado_em, mensagem
            FROM tbl_tarefa_secundaria_execucao
            WHERE id_tarefa = t.id
            ORDER BY iniciado_em DESC
            LIMIT 1
        ) e ON TRUE
        WHERE t.ativo = TRUE
        ORDER BY t.nome
        """
    )
    out = []
    for r in cur.fetchall():
        out.append(
            {
                "id": int(r[0]),
                "codigo": r[1],
                "nome": r[2],
                "descricao": r[3] or "",
                "agendamento": r[4] or "manual",
                "ativo": bool(r[5]),
                "ultima_execucao": (
                    None
                    if not r[6]
                    else {
                        "id": int(r[6]),
                        "status": r[7],
                        "disparado_por": r[8],
                        "iniciado_em": r[9].isoformat() if r[9] else None,
                        "finalizado_em": r[10].isoformat() if r[10] else None,
                        "mensagem": r[11] or "",
                    }
                ),
            }
        )
    return out


def listar_execucoes_tarefa(cur, id_tarefa: int, limit: int = 20) -> list[dict]:
    garantir_tabelas_tarefas(cur)
    cur.execute(
        """
        SELECT id, status, disparado_por, iniciado_em, finalizado_em, mensagem, log_texto
        FROM tbl_tarefa_secundaria_execucao
        WHERE id_tarefa = %s
        ORDER BY iniciado_em DESC
        LIMIT %s
        """,
        (int(id_tarefa), max(1, min(int(limit), 50))),
    )
    return [
        {
            "id": int(r[0]),
            "status": r[1],
            "disparado_por": r[2],
            "iniciado_em": r[3].isoformat() if r[3] else None,
            "finalizado_em": r[4].isoformat() if r[4] else None,
            "mensagem": r[5] or "",
            "log_texto": r[6] or "",
        }
        for r in cur.fetchall()
    ]


def _hoje_e_segunda() -> bool:
    return datetime.now(TZ_BR).weekday() == 0


def _ml_get_autenticado(cur, id_tenant: int, path: str) -> Any:
    """GET na API ML com token de uma conta conectada (categorias exigem Bearer)."""
    from api.mercado_livre.mercado_livre import api_request

    return api_request(cur, id_tenant, "GET", path, timeout=ML_CAT_TIMEOUT)


def sites_ml_para_cache(cur) -> list[str]:
    """Sites das contas conectadas. Sem conta, não inventa MLB anônimo (API retorna 403)."""
    sites: set[str] = set()
    cur.execute("SAVEPOINT sp_sites_ml_cache")
    try:
        cur.execute(
            """
            SELECT DISTINCT UPPER(NULLIF(TRIM(ml_site_id), ''))
            FROM tbl_integracao_mercado_livre
            WHERE status = 'conectado'
              AND NULLIF(TRIM(ml_site_id), '') IS NOT NULL
            """
        )
        for (sid,) in cur.fetchall():
            if sid:
                sites.add(str(sid).upper())
        # Contas conectadas sem site_id ainda: assume MLB
        if not sites:
            cur.execute(
                """
                SELECT 1 FROM tbl_integracao_mercado_livre
                WHERE status = 'conectado'
                LIMIT 1
                """
            )
            if cur.fetchone():
                sites.add("MLB")
        cur.execute("RELEASE SAVEPOINT sp_sites_ml_cache")
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT sp_sites_ml_cache")
        _log.warning("Falha ao listar sites ML conectados", exc_info=True)
        raise RuntimeError(
            "Não foi possível listar contas Mercado Livre conectadas para o cache."
        ) from None
    if not sites:
        raise RuntimeError(
            "Nenhuma conta Mercado Livre conectada. Conecte uma conta e tente de novo."
        )
    return sorted(sites)


def tenant_ml_para_site(cur, site_id: str) -> int:
    """Tenant com ML conectado no site (ou qualquer conectado como fallback)."""
    site_id = (site_id or "MLB").upper()
    cur.execute(
        """
        SELECT id_tenant
        FROM tbl_integracao_mercado_livre
        WHERE status = 'conectado'
          AND UPPER(NULLIF(TRIM(ml_site_id), '')) = %s
        ORDER BY atualizado_em DESC NULLS LAST
        LIMIT 1
        """,
        (site_id,),
    )
    row = cur.fetchone()
    if row:
        return int(row[0])
    cur.execute(
        """
        SELECT id_tenant
        FROM tbl_integracao_mercado_livre
        WHERE status = 'conectado'
        ORDER BY atualizado_em DESC NULLS LAST
        LIMIT 1
        """
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(
            f"Nenhuma conta Mercado Livre conectada para o site {site_id}."
        )
    return int(row[0])


def _coletar_folhas_site(
    cur, id_tenant: int, site_id: str, log: list[str]
) -> tuple[list[tuple[str, str, str, str]], int]:
    """Percorre a árvore ML e retorna folhas (category_id, nome, path_nomes, path_ids)."""
    site_id = (site_id or "MLB").upper()
    ignoradas_sem_nome = 0
    roots = _ml_get_autenticado(cur, id_tenant, f"/sites/{site_id}/categories")
    if not isinstance(roots, list):
        raise RuntimeError("Resposta de categorias raiz inválida.")

    folhas: list[tuple[str, str, str, str]] = []
    fila: list[tuple[str, list[str], list[str]]] = []
    for root in roots:
        if not isinstance(root, dict):
            continue
        rid = str(root.get("id") or "").strip().upper()
        rnome = str(root.get("name") or "").strip()
        if not rid:
            continue
        if not rnome:
            ignoradas_sem_nome += 1
            log.append(f"IGNORADO sem nome (raiz): {rid}")
            continue
        fila.append((rid, [rnome], [rid]))

    visitados: set[str] = set()
    while fila:
        cat_id, path_nomes, path_ids = fila.pop()
        if cat_id in visitados:
            continue
        visitados.add(cat_id)
        try:
            det = _ml_get_autenticado(cur, id_tenant, f"/categories/{cat_id}")
        except Exception as e:
            log.append(f"ERRO categoria {cat_id}: {e}")
            time.sleep(0.05)
            continue
        if not isinstance(det, dict):
            continue
        nome = str(det.get("name") or "").strip()
        if not nome:
            ignoradas_sem_nome += 1
            log.append(f"IGNORADO sem nome: {cat_id} (path={' > '.join(path_nomes)})")
            continue
        children = det.get("children_categories") or []
        if not children:
            folhas.append((cat_id, nome, " > ".join(path_nomes), " / ".join(path_ids)))
        else:
            for ch in children:
                if not isinstance(ch, dict):
                    continue
                cid = str(ch.get("id") or "").strip().upper()
                cnome = str(ch.get("name") or "").strip()
                if not cid:
                    continue
                if not cnome:
                    ignoradas_sem_nome += 1
                    log.append(f"IGNORADO sem nome (filho): {cid}")
                    continue
                fila.append((cid, path_nomes + [cnome], path_ids + [cid]))
        time.sleep(0.03)
    return folhas, ignoradas_sem_nome


def _gravar_folhas_cache(
    cur, site_id: str, folhas: list[tuple[str, str, str, str]]
) -> None:
    site_id = (site_id or "MLB").upper()
    cur.execute("DELETE FROM tbl_ml_categoria_cache WHERE site_id = %s", (site_id,))
    agora = agora_utc()
    for cat_id, nome, path_n, path_i in folhas:
        cur.execute(
            """
            INSERT INTO tbl_ml_categoria_cache (
                site_id, category_id, nome, path_nomes, path_ids, atualizado_em
            ) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (site_id, category_id) DO UPDATE SET
                nome = EXCLUDED.nome,
                path_nomes = EXCLUDED.path_nomes,
                path_ids = EXCLUDED.path_ids,
                atualizado_em = EXCLUDED.atualizado_em
            """,
            (site_id, cat_id, nome[:255], path_n, path_i, agora),
        )


def sincronizar_cache_categorias_ml(
    cur, *, sites: list[str] | None = None, conn=None
) -> dict:
    """Baixa categorias folha (publicáveis) e grava no cache. Retorna resumo + log.

    Se `conn` for passado, faz commit após preparar tabelas (libera a transação
    durante o download HTTP) e após gravar cada site.
    """
    garantir_tabelas_tarefas(cur)
    sites = sites or sites_ml_para_cache(cur)
    if conn is not None:
        conn.commit()

    log: list[str] = []
    total_folhas = 0
    ignoradas_sem_nome = 0
    erros_site = 0

    for site_id in sites:
        site_id = (site_id or "MLB").upper()
        log.append(f"=== Site {site_id} ===")
        try:
            id_tenant = tenant_ml_para_site(cur, site_id)
            log.append(f"Usando conta tenant #{id_tenant} (Bearer).")
            folhas, ign = _coletar_folhas_site(cur, id_tenant, site_id, log)
            ignoradas_sem_nome += ign
        except Exception as e:
            erros_site += 1
            log.append(f"ERRO ao listar raízes {site_id}: {e}")
            continue

        _gravar_folhas_cache(cur, site_id, folhas)
        if conn is not None:
            conn.commit()
        total_folhas += len(folhas)
        log.append(f"OK {site_id}: {len(folhas)} categorias publicáveis em cache.")

    msg = (
        f"{total_folhas} categorias em cache · "
        f"{ignoradas_sem_nome} ignoradas sem nome · "
        f"{erros_site} site(s) com erro"
    )
    log.append(msg)
    log_texto = "\n".join(log)
    if total_folhas <= 0:
        raise TarefaSecundariaErro(
            "Cache de categorias ML ficou vazio. "
            "Confira se há conta conectada e se o app ML tem permissão de leitura. "
            f"Detalhe: {msg}",
            log_texto=log_texto,
        )
    return {
        "folhas": total_folhas,
        "ignoradas_sem_nome": ignoradas_sem_nome,
        "erros_site": erros_site,
        "sites": sites,
        "mensagem": msg,
        "log_texto": log_texto,
    }


def _marcar_execucao_erro(cur, id_exec: int, erro: BaseException, log_extra: str = "") -> None:
    msg = str(erro)[:500]
    log = (
        log_extra
        or getattr(erro, "log_texto", None)
        or str(erro)
    ).strip()
    cur.execute(
        """
        UPDATE tbl_tarefa_secundaria_execucao
        SET status = %s, finalizado_em = %s, mensagem = %s, log_texto = %s
        WHERE id = %s
        """,
        ("erro", agora_utc(), msg, log[:20000], id_exec),
    )


def executar_tarefa(
    cur,
    codigo: str,
    *,
    disparado_por: str = "cron",
    forcar: bool = False,
    conn=None,
) -> dict:
    garantir_tabelas_tarefas(cur)
    cur.execute(
        """
        SELECT id, codigo, agendamento, ativo
        FROM tbl_tarefa_secundaria
        WHERE codigo = %s
        """,
        (codigo,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Tarefa «{codigo}» não cadastrada.")
    id_tarefa, codigo_db, agendamento, ativo = int(row[0]), row[1], row[2] or "manual", bool(row[3])
    if not ativo:
        raise RuntimeError("Tarefa inativa.")

    if not forcar and agendamento == "segunda" and not _hoje_e_segunda():
        return {
            "skipped": True,
            "codigo": codigo_db,
            "mensagem": "Agendada para segunda-feira — execução ignorada hoje.",
        }

    cur.execute(
        """
        INSERT INTO tbl_tarefa_secundaria_execucao (
            id_tarefa, status, disparado_por, iniciado_em
        ) VALUES (%s, 'rodando', %s, %s)
        RETURNING id
        """,
        (id_tarefa, disparado_por, agora_utc()),
    )
    id_exec = int(cur.fetchone()[0])
    if conn is not None:
        conn.commit()

    try:
        if codigo_db == CODIGO_ML_CATEGORIAS:
            res = sincronizar_cache_categorias_ml(cur, conn=conn)
        else:
            raise RuntimeError(f"Executor não implementado para «{codigo_db}».")
        cur.execute(
            """
            UPDATE tbl_tarefa_secundaria_execucao
            SET status = %s, finalizado_em = %s, mensagem = %s, log_texto = %s,
                meta = %s::jsonb
            WHERE id = %s
            """,
            (
                "sucesso",
                agora_utc(),
                res.get("mensagem") or "OK",
                res.get("log_texto") or "",
                json.dumps(
                    {
                        "folhas": res.get("folhas"),
                        "ignoradas_sem_nome": res.get("ignoradas_sem_nome"),
                        "erros_site": res.get("erros_site"),
                        "sites": res.get("sites"),
                    },
                    ensure_ascii=False,
                ),
                id_exec,
            ),
        )
        cur.execute(
            "UPDATE tbl_tarefa_secundaria SET atualizado_em = %s WHERE id = %s",
            (agora_utc(), id_tarefa),
        )
        return {"skipped": False, "codigo": codigo_db, "id_execucao": id_exec, **res}
    except Exception as e:
        if conn is not None:
            conn.rollback()
        try:
            _marcar_execucao_erro(cur, id_exec, e)
            if conn is not None:
                conn.commit()
        except Exception:
            if conn is not None:
                conn.rollback()
        raise


def buscar_categorias_cache(
    cur, site_id: str, termo: str, limit: int = 40
) -> list[dict]:
    garantir_tabelas_tarefas(cur)
    site_id = (site_id or "MLB").upper()
    termo = (termo or "").strip()
    lim = max(1, min(int(limit or 40), 80))
    if len(termo) < 2:
        cur.execute(
            """
            SELECT category_id, nome, path_nomes
            FROM tbl_ml_categoria_cache
            WHERE site_id = %s
            ORDER BY nome
            LIMIT %s
            """,
            (site_id, lim),
        )
    else:
        like = f"%{termo}%"
        cur.execute(
            """
            SELECT category_id, nome, path_nomes
            FROM tbl_ml_categoria_cache
            WHERE site_id = %s
              AND (nome ILIKE %s OR path_nomes ILIKE %s OR category_id ILIKE %s)
            ORDER BY
              CASE WHEN lower(nome) = lower(%s) THEN 0
                   WHEN lower(nome) LIKE lower(%s) THEN 1
                   ELSE 2 END,
              nome
            LIMIT %s
            """,
            (site_id, like, like, like, termo, f"{termo}%", lim),
        )
    return [
        {
            "category_id": str(r[0]),
            "nome": r[1],
            "path_nomes": r[2] or "",
        }
        for r in cur.fetchall()
        if r[1]
    ]


def nome_categoria_cache(cur, site_id: str, category_id: str) -> str:
    garantir_tabelas_tarefas(cur)
    cur.execute(
        """
        SELECT nome FROM tbl_ml_categoria_cache
        WHERE site_id = %s AND category_id = %s
        LIMIT 1
        """,
        ((site_id or "MLB").upper(), (category_id or "").strip().upper()),
    )
    row = cur.fetchone()
    return (row[0] or "").strip() if row else ""


def disparar_tarefa_async(codigo: str, *, disparado_por: str = "manual") -> dict:
    """Abre execução 'rodando' e processa em thread (evita timeout HTTP)."""
    conn = Var_ConectarBanco()
    try:
        cur = conn.cursor()
        garantir_tabelas_tarefas(cur)
        cur.execute(
            "SELECT id, ativo FROM tbl_tarefa_secundaria WHERE codigo = %s",
            (codigo,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"Tarefa «{codigo}» não cadastrada.")
        if not row[1]:
            raise RuntimeError("Tarefa inativa.")
        id_tarefa = int(row[0])
        cur.execute(
            """
            SELECT 1 FROM tbl_tarefa_secundaria_execucao
            WHERE id_tarefa = %s AND status = 'rodando'
            LIMIT 1
            """,
            (id_tarefa,),
        )
        if cur.fetchone():
            raise RuntimeError("Esta tarefa já está em execução.")
        cur.execute(
            """
            INSERT INTO tbl_tarefa_secundaria_execucao (
                id_tarefa, status, disparado_por, iniciado_em
            ) VALUES (%s, 'rodando', %s, %s)
            RETURNING id
            """,
            (id_tarefa, disparado_por, agora_utc()),
        )
        id_exec = int(cur.fetchone()[0])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    def _worker() -> None:
        import traceback

        c2 = Var_ConectarBanco()
        try:
            cur2 = c2.cursor()
            if codigo == CODIGO_ML_CATEGORIAS:
                res = sincronizar_cache_categorias_ml(cur2, conn=c2)
            else:
                raise RuntimeError(f"Executor não implementado para «{codigo}».")
            cur2.execute(
                """
                UPDATE tbl_tarefa_secundaria_execucao
                SET status = %s, finalizado_em = %s, mensagem = %s, log_texto = %s,
                    meta = %s::jsonb
                WHERE id = %s
                """,
                (
                    "sucesso",
                    agora_utc(),
                    res.get("mensagem") or "OK",
                    res.get("log_texto") or "",
                    json.dumps(
                        {
                            "folhas": res.get("folhas"),
                            "ignoradas_sem_nome": res.get("ignoradas_sem_nome"),
                            "erros_site": res.get("erros_site"),
                            "sites": res.get("sites"),
                        },
                        ensure_ascii=False,
                    ),
                    id_exec,
                ),
            )
            cur2.execute(
                "UPDATE tbl_tarefa_secundaria SET atualizado_em = %s WHERE id = %s",
                (agora_utc(), id_tarefa),
            )
            c2.commit()
        except Exception as e:
            tb = traceback.format_exc()
            detalhe = (getattr(e, "log_texto", None) or "").strip()
            log_extra = f"{detalhe}\n\n---\n{tb}".strip() if detalhe else tb
            c2.rollback()
            try:
                cur2 = c2.cursor()
                _marcar_execucao_erro(cur2, id_exec, e, log_extra=log_extra)
                c2.commit()
            except Exception:
                c2.rollback()
            _log.exception("Tarefa secundária %s falhou", codigo)
        finally:
            c2.close()

    threading.Thread(target=_worker, daemon=True, name=f"tarefa-{codigo}").start()
    return {
        "codigo": codigo,
        "id_execucao": id_exec,
        "status": "rodando",
        "mensagem": "Tarefa iniciada em segundo plano.",
    }
