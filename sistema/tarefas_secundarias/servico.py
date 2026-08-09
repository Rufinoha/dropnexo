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
CODIGO_TIKTOK_CATEGORIAS = "tiktok_categorias_cache"
CODIGO_AMAZON_PRODUCT_TYPES = "amazon_product_types_cache"
CODIGO_BLING_CATEGORIAS = "bling_categorias_cache"

CODIGOS_CACHE_CATEGORIAS = (
    CODIGO_ML_CATEGORIAS,
    CODIGO_TIKTOK_CATEGORIAS,
    CODIGO_AMAZON_PRODUCT_TYPES,
    CODIGO_BLING_CATEGORIAS,
)

# Defaults: (agendamento, hora_local HH:MM America/Sao_Paulo)
_DEFAULTS_AGENDA: dict[str, tuple[str, str]] = {
    CODIGO_ML_CATEGORIAS: ("domingo", "02:00"),
    CODIGO_TIKTOK_CATEGORIAS: ("domingo", "03:00"),
    CODIGO_AMAZON_PRODUCT_TYPES: ("domingo", "04:00"),
    CODIGO_BLING_CATEGORIAS: ("domingo", "05:00"),
}


class TarefaSecundariaErro(RuntimeError):
    """Erro de tarefa com log detalhado para a UI."""

    def __init__(self, mensagem: str, log_texto: str = ""):
        super().__init__(mensagem)
        self.log_texto = log_texto or mensagem


def _coluna_existe(cur, tabela: str, coluna: str) -> bool:
    cur.execute(
        """
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = 'public'
          AND table_name = %s
          AND column_name = %s
        LIMIT 1
        """,
        (tabela, coluna),
    )
    return bool(cur.fetchone())


def _ddl_seguro(cur, sql: str, *, sp: str) -> bool:
    """Executa DDL em savepoint. Falha de permissão/owner não aborta a transação."""
    cur.execute(f"SAVEPOINT {sp}")
    try:
        cur.execute(sql)
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return True
    except Exception as e:
        cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
        msg = str(e).lower()
        if "must be owner" in msg or "permission denied" in msg or "insufficient_privilege" in msg:
            _log.warning("DDL ignorado (%s): %s", sp, e)
            return False
        _log.warning("DDL falhou (%s): %s", sp, e)
        return False


def garantir_tabelas_tarefas(cur) -> None:
    _ddl_seguro(
        cur,
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
        """,
        sp="sp_ts_tarefa",
    )
    _ddl_seguro(
        cur,
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
        """,
        sp="sp_ts_exec",
    )
    for sp, sql in (
        (
            "sp_ts_ml_cache",
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
            """,
        ),
        (
            "sp_ts_tt_cache",
            """
            CREATE TABLE IF NOT EXISTS tbl_tiktok_categoria_cache (
                id SERIAL PRIMARY KEY,
                region VARCHAR(16) NOT NULL DEFAULT 'BR',
                category_id VARCHAR(64) NOT NULL,
                nome VARCHAR(255) NOT NULL,
                path_nomes TEXT NOT NULL DEFAULT '',
                path_ids TEXT NOT NULL DEFAULT '',
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (region, category_id)
            )
            """,
        ),
        (
            "sp_ts_amz_cache",
            """
            CREATE TABLE IF NOT EXISTS tbl_amazon_product_type_cache (
                id SERIAL PRIMARY KEY,
                marketplace_id VARCHAR(32) NOT NULL,
                product_type VARCHAR(128) NOT NULL,
                display_name VARCHAR(255) NOT NULL DEFAULT '',
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (marketplace_id, product_type)
            )
            """,
        ),
        (
            "sp_ts_bling_cache",
            """
            CREATE TABLE IF NOT EXISTS tbl_bling_categoria_cache (
                id SERIAL PRIMARY KEY,
                category_id VARCHAR(64) NOT NULL,
                nome VARCHAR(255) NOT NULL,
                path_nomes TEXT NOT NULL DEFAULT '',
                parent_id VARCHAR(64) NOT NULL DEFAULT '',
                is_leaf BOOLEAN NOT NULL DEFAULT TRUE,
                atualizado_em TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                UNIQUE (category_id)
            )
            """,
        ),
    ):
        _ddl_seguro(cur, sql, sp=sp)

    # Colunas do plano 3 — só ALTER se faltar (evita "must be owner" no request)
    tem_hora = _coluna_existe(cur, "tbl_tarefa_secundaria", "hora_local")
    tem_doador = _coluna_existe(cur, "tbl_tarefa_secundaria", "id_tenant_doador")
    if not tem_hora:
        tem_hora = _ddl_seguro(
            cur,
            """
            ALTER TABLE tbl_tarefa_secundaria
                ADD COLUMN hora_local VARCHAR(5) NOT NULL DEFAULT '02:00'
            """,
            sp="sp_ts_hora",
        )
    if not tem_doador:
        tem_doador = _ddl_seguro(
            cur,
            """
            ALTER TABLE tbl_tarefa_secundaria
                ADD COLUMN id_tenant_doador INTEGER
                    REFERENCES tbl_tenant(id) ON DELETE SET NULL
            """,
            sp="sp_ts_doador",
        )
        if tem_doador:
            _ddl_seguro(
                cur,
                """
                CREATE INDEX IF NOT EXISTS idx_tarefa_sec_doador
                    ON tbl_tarefa_secundaria (id_tenant_doador)
                    WHERE id_tenant_doador IS NOT NULL
                """,
                sp="sp_ts_idx_doador",
            )

    seeds = [
        (
            CODIGO_ML_CATEGORIAS,
            "Cache de categorias Mercado Livre",
            "Baixa categorias publicáveis (folha) usando a conta doadora e atualiza o cache do mapeamento.",
        ),
        (
            CODIGO_TIKTOK_CATEGORIAS,
            "Cache de categorias TikTok Shop",
            "Baixa categorias folha usando a conta doadora e atualiza o cache do mapeamento.",
        ),
        (
            CODIGO_AMAZON_PRODUCT_TYPES,
            "Cache de Product Types Amazon",
            "Baixa Product Types usando a conta doadora e atualiza o cache do mapeamento.",
        ),
        (
            CODIGO_BLING_CATEGORIAS,
            "Cache de categorias Bling",
            "Baixa a árvore de categorias usando a conta doadora e atualiza o cache do mapeamento.",
        ),
    ]
    for codigo, nome, desc in seeds:
        agenda, hora = _DEFAULTS_AGENDA.get(codigo, ("domingo", "02:00"))
        if tem_hora:
            cur.execute(
                """
                INSERT INTO tbl_tarefa_secundaria (
                    codigo, nome, descricao, agendamento, hora_local, ativo
                ) VALUES (%s, %s, %s, %s, %s, TRUE)
                ON CONFLICT (codigo) DO UPDATE SET
                    nome = EXCLUDED.nome,
                    descricao = EXCLUDED.descricao,
                    ativo = TRUE,
                    atualizado_em = NOW()
                """,
                (codigo, nome, desc, agenda, hora),
            )
        else:
            cur.execute(
                """
                INSERT INTO tbl_tarefa_secundaria (
                    codigo, nome, descricao, agendamento, ativo
                ) VALUES (%s, %s, %s, %s, TRUE)
                ON CONFLICT (codigo) DO UPDATE SET
                    nome = EXCLUDED.nome,
                    descricao = EXCLUDED.descricao,
                    ativo = TRUE,
                    atualizado_em = NOW()
                """,
                (codigo, nome, desc, agenda),
            )

    if tem_hora:
        cur.execute(
            """
            UPDATE tbl_tarefa_secundaria
            SET agendamento = 'domingo',
                hora_local = '02:00',
                atualizado_em = NOW()
            WHERE codigo = %s AND agendamento = 'segunda'
            """,
            (CODIGO_ML_CATEGORIAS,),
        )
        for codigo, (_ag, hora) in _DEFAULTS_AGENDA.items():
            cur.execute(
                """
                UPDATE tbl_tarefa_secundaria
                SET hora_local = %s, atualizado_em = NOW()
                WHERE codigo = %s
                  AND (hora_local IS NULL OR TRIM(hora_local) = '')
                """,
                (hora, codigo),
            )
        cur.execute(
            """
            UPDATE tbl_tarefa_secundaria
            SET hora_local = '03:00', atualizado_em = NOW()
            WHERE codigo = %s
              AND agendamento = 'domingo'
              AND TRIM(hora_local) = '02:00'
            """,
            (CODIGO_TIKTOK_CATEGORIAS,),
        )
        cur.execute(
            """
            UPDATE tbl_tarefa_secundaria
            SET hora_local = '04:00', atualizado_em = NOW()
            WHERE codigo = %s
              AND agendamento = 'domingo'
              AND TRIM(hora_local) = '02:00'
            """,
            (CODIGO_AMAZON_PRODUCT_TYPES,),
        )

    if tem_doador:
        _bootstrap_doadores_existentes(cur)
    if not tem_hora or not tem_doador:
        _log.warning(
            "Colunas hora_local/id_tenant_doador ausentes em tbl_tarefa_secundaria. "
            "Aplique __doc/sql/107_tarefas_doador_agenda.sql como dono da tabela."
        )


def _garantir_tabelas_integracao_cache(cur) -> None:
    """Garante tabelas de integração usadas pelo doador (TikTok/Amazon podem não existir ainda)."""
    try:
        from api.tiktok.tiktok import _garantir_tabela_tiktok

        _garantir_tabela_tiktok(cur)
    except Exception:
        _log.debug("garantir tabela tiktok ignorado", exc_info=True)
    try:
        from api.amazon.amazon import _garantir_tabela_amazon

        _garantir_tabela_amazon(cur)
    except Exception:
        _log.debug("garantir tabela amazon ignorado", exc_info=True)


def _bootstrap_doadores_existentes(cur) -> None:
    """Se a tarefa não tem doador, promove o 1º tenant já conectado (ex.: sua conta ML)."""
    from sistema.tarefas_secundarias.doador import obter_id_doador, obter_ou_promover_doador

    _garantir_tabelas_integracao_cache(cur)
    for codigo in CODIGOS_CACHE_CATEGORIAS:
        try:
            if obter_id_doador(cur, codigo):
                continue
            obter_ou_promover_doador(cur, codigo)
        except Exception:
            _log.debug("Bootstrap doador %s ignorado", codigo, exc_info=True)


def _parse_meta(meta) -> dict:
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            return {}
    return meta if isinstance(meta, dict) else {}


def _idade_segundos(dt_val) -> float | None:
    if dt_val is None:
        return None
    agora = agora_utc()
    try:
        if isinstance(dt_val, str):
            dt_val = datetime.fromisoformat(dt_val.replace("Z", "+00:00"))
        if getattr(dt_val, "tzinfo", None) is None:
            dt_val = dt_val.replace(tzinfo=agora.tzinfo)
        return max(0.0, (agora - dt_val).total_seconds())
    except Exception:
        return None


def execucao_esta_orfaa(iniciado_em, meta) -> bool:
    """Sem heartbeat recente = processo morreu (ex.: restart do app)."""
    meta = _parse_meta(meta)
    hb_age = _idade_segundos(meta.get("heartbeat_em"))
    if hb_age is not None:
        return hb_age > 180  # 3 min sem sinal
    ini_age = _idade_segundos(iniciado_em)
    # Sem nenhum heartbeat: 90s já basta (primeiro sinal sai em poucos segundos)
    return ini_age is None or ini_age > 90


def encerrar_execucoes_orfaas(cur) -> int:
    """Marca execuções 'rodando' órfãs como erro. Retorna quantas encerrou."""
    cur.execute(
        """
        SELECT id, iniciado_em, meta
        FROM tbl_tarefa_secundaria_execucao
        WHERE status = 'rodando'
        """
    )
    rows = cur.fetchall() or []
    n = 0
    agora = agora_utc()
    for id_exec, iniciado_em, meta in rows:
        if not execucao_esta_orfaa(iniciado_em, meta):
            continue
        cur.execute(
            """
            UPDATE tbl_tarefa_secundaria_execucao
            SET status = 'erro',
                finalizado_em = %s,
                mensagem = %s,
                log_texto = COALESCE(log_texto, '') || %s
            WHERE id = %s AND status = 'rodando'
            """,
            (
                agora,
                "Execução interrompida (sem sinal de progresso).",
                "\n[sistema] Encerrada automaticamente por falta de heartbeat.",
                int(id_exec),
            ),
        )
        n += 1
    return n


def listar_tarefas_secundarias(cur) -> list[dict]:
    from sistema.tarefas_secundarias.doador import info_doador

    garantir_tabelas_tarefas(cur)
    encerrar_execucoes_orfaas(cur)
    tem_hora = _coluna_existe(cur, "tbl_tarefa_secundaria", "hora_local")
    tem_doador = _coluna_existe(cur, "tbl_tarefa_secundaria", "id_tenant_doador")
    hora_sql = (
        "COALESCE(NULLIF(TRIM(t.hora_local), ''), '02:00')"
        if tem_hora
        else "'02:00'"
    )
    order_sql = "t.hora_local NULLS LAST, t.nome" if tem_hora else "t.nome"
    cur.execute(
        f"""
        SELECT t.id, t.codigo, t.nome, t.descricao, t.agendamento, t.ativo,
               {hora_sql},
               e.id, e.status, e.disparado_por, e.iniciado_em, e.finalizado_em,
               e.mensagem, e.meta
        FROM tbl_tarefa_secundaria t
        LEFT JOIN LATERAL (
            SELECT id, status, disparado_por, iniciado_em, finalizado_em, mensagem, meta
            FROM tbl_tarefa_secundaria_execucao
            WHERE id_tarefa = t.id
            ORDER BY iniciado_em DESC
            LIMIT 1
        ) e ON TRUE
        WHERE t.ativo = TRUE
        ORDER BY {order_sql}
        """
    )
    out = []
    for r in cur.fetchall():
        meta = _parse_meta(r[13] if len(r) > 13 else None)
        codigo = r[1]
        doador = None
        if tem_doador:
            try:
                doador = info_doador(cur, codigo)
            except Exception:
                doador = None
        out.append(
            {
                "id": int(r[0]),
                "codigo": codigo,
                "nome": r[2],
                "descricao": r[3] or "",
                "agendamento": r[4] or "manual",
                "hora_local": r[6] or "02:00",
                "ativo": bool(r[5]),
                "doador": doador,
                "ultima_execucao": (
                    None
                    if not r[7]
                    else {
                        "id": int(r[7]),
                        "status": r[8],
                        "disparado_por": r[9],
                        "iniciado_em": r[10].isoformat() if r[10] else None,
                        "finalizado_em": r[11].isoformat() if r[11] else None,
                        "mensagem": r[12] or "",
                        "meta": meta,
                    }
                ),
            }
        )
    return out


def salvar_agenda_tarefa(
    cur, codigo: str, *, agendamento: str, hora_local: str
) -> dict:
    garantir_tabelas_tarefas(cur)
    if not _coluna_existe(cur, "tbl_tarefa_secundaria", "hora_local"):
        raise RuntimeError(
            "Coluna hora_local ausente. Aplique o SQL 107 como dono da tabela "
            "(postgres / role que criou tbl_tarefa_secundaria)."
        )
    a = (agendamento or "").strip().lower()
    if a not in ("domingo", "segunda", "terca", "quarta", "quinta", "sexta", "sabado", "diario", "manual"):
        raise ValueError("Agendamento inválido.")
    h = (hora_local or "").strip()
    if len(h) == 4 and h[1] == ":":
        h = "0" + h
    try:
        hh, mm = h.split(":")
        hi, mi = int(hh), int(mm)
        if not (0 <= hi <= 23 and 0 <= mi <= 59):
            raise ValueError
        h = f"{hi:02d}:{mi:02d}"
    except Exception as e:
        raise ValueError("Horário inválido. Use HH:MM.") from e
    cur.execute(
        """
        UPDATE tbl_tarefa_secundaria
        SET agendamento = %s, hora_local = %s, atualizado_em = NOW()
        WHERE codigo = %s
        RETURNING id, codigo, agendamento, hora_local
        """,
        (a, h, codigo),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Tarefa «{codigo}» não encontrada.")
    return {
        "id": int(row[0]),
        "codigo": row[1],
        "agendamento": row[2],
        "hora_local": row[3],
    }


def _atualizar_progresso_exec(
    cur,
    conn,
    id_exec: int | None,
    mensagem: str,
    meta: dict | None = None,
) -> None:
    """Heartbeat da execução em andamento (visível no card / polling)."""
    if not id_exec:
        return
    payload = dict(meta or {})
    payload["heartbeat_em"] = agora_utc().isoformat()
    cur.execute(
        """
        UPDATE tbl_tarefa_secundaria_execucao
        SET mensagem = %s,
            meta = COALESCE(meta, '{}'::jsonb) || %s::jsonb
        WHERE id = %s AND status = 'rodando'
        """,
        (mensagem[:500], json.dumps(payload, ensure_ascii=False), int(id_exec)),
    )
    if conn is not None:
        conn.commit()


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


_WEEKDAY_NOME = {
    0: "segunda",
    1: "terca",
    2: "quarta",
    3: "quinta",
    4: "sexta",
    5: "sabado",
    6: "domingo",
}


def _agendamento_permite_agora(
    agendamento: str,
    hora_local: str | None,
    *,
    forcar: bool = False,
) -> bool:
    """Dia + hora (America/Sao_Paulo). Cron deve rodar ao menos 1x/hora."""
    if forcar:
        return True
    a = (agendamento or "manual").strip().lower()
    if a in ("", "manual"):
        return False
    agora = datetime.now(TZ_BR)
    if a != "diario":
        if _WEEKDAY_NOME.get(agora.weekday()) != a:
            return False
    h = (hora_local or "02:00").strip()
    try:
        hh, mm = h.split(":")
        alvo_min = int(hh) * 60 + int(mm)
    except Exception:
        alvo_min = 2 * 60
    agora_min = agora.hour * 60 + agora.minute
    # Janela de 60 min a partir do horário configurado
    return alvo_min <= agora_min < alvo_min + 60


def _rodar_sync_por_codigo(cur, codigo: str, *, conn=None, id_exec: int | None = None) -> dict:
    from sistema.tarefas_secundarias.doador import obter_ou_promover_doador

    id_doador = obter_ou_promover_doador(cur, codigo)
    if not id_doador and codigo in CODIGOS_CACHE_CATEGORIAS:
        raise RuntimeError(
            "Nenhuma conta conectada para doar credenciais. "
            "O cache será preenchido quando o 1º vendedor conectar a integração."
        )
    if codigo == CODIGO_ML_CATEGORIAS:
        return sincronizar_cache_categorias_ml(
            cur, conn=conn, id_exec=id_exec, id_tenant_doador=id_doador
        )
    if codigo == CODIGO_TIKTOK_CATEGORIAS:
        from sistema.tarefas_secundarias.cache_tiktok import sincronizar_cache_categorias_tiktok

        return sincronizar_cache_categorias_tiktok(
            cur,
            id_tenant=id_doador,
            conn=conn,
            id_exec=id_exec,
            atualizar_progresso=_atualizar_progresso_exec,
        )
    if codigo == CODIGO_AMAZON_PRODUCT_TYPES:
        from sistema.tarefas_secundarias.cache_amazon import sincronizar_cache_product_types_amazon

        return sincronizar_cache_product_types_amazon(
            cur,
            id_tenant=id_doador,
            conn=conn,
            id_exec=id_exec,
            atualizar_progresso=_atualizar_progresso_exec,
        )
    if codigo == CODIGO_BLING_CATEGORIAS:
        from sistema.tarefas_secundarias.cache_bling import sincronizar_cache_categorias_bling

        return sincronizar_cache_categorias_bling(
            cur,
            id_tenant=id_doador,
            conn=conn,
            id_exec=id_exec,
            atualizar_progresso=_atualizar_progresso_exec,
        )
    raise RuntimeError(f"Executor não implementado para «{codigo}».")


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
    cur,
    id_tenant: int,
    site_id: str,
    log: list[str],
    *,
    on_progress=None,
) -> tuple[list[tuple[str, str, str, str]], int]:
    """Percorre a árvore ML por raiz (para progresso) e retorna folhas publicáveis."""
    site_id = (site_id or "MLB").upper()
    ignoradas_sem_nome = 0
    roots = _ml_get_autenticado(cur, id_tenant, f"/sites/{site_id}/categories")
    if not isinstance(roots, list):
        raise RuntimeError("Resposta de categorias raiz inválida.")

    raizes: list[tuple[str, str]] = []
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
        raizes.append((rid, rnome))

    folhas: list[tuple[str, str, str, str]] = []
    visitados: set[str] = set()
    nos_visitados = 0
    ultimo_hb = 0.0
    raizes_total = max(len(raizes), 1)

    def _emit(raiz_idx: int, raiz_nome: str, forcar: bool = False) -> None:
        nonlocal ultimo_hb
        agora = time.monotonic()
        if not forcar and (agora - ultimo_hb) < 2.5:
            return
        ultimo_hb = agora
        if not on_progress:
            return
        pct = min(99.0, ((raiz_idx - 1) / raizes_total) * 100)
        on_progress(
            {
                "fase": "baixando",
                "site_id": site_id,
                "raiz_idx": raiz_idx,
                "raizes_total": raizes_total,
                "raiz_nome": raiz_nome,
                "nos_visitados": nos_visitados,
                "folhas": len(folhas),
                "pct": round(pct, 1),
            },
            (
                f"{site_id}: raiz {raiz_idx}/{raizes_total} «{raiz_nome}» · "
                f"{nos_visitados} nós · {len(folhas)} folhas"
            ),
        )

    for raiz_idx, (rid, rnome) in enumerate(raizes, start=1):
        log.append(f"Raiz {raiz_idx}/{raizes_total}: {rnome} ({rid})")
        _emit(raiz_idx, rnome, forcar=True)
        fila: list[tuple[str, list[str], list[str]]] = [(rid, [rnome], [rid])]
        while fila:
            cat_id, path_nomes, path_ids = fila.pop()
            if cat_id in visitados:
                continue
            visitados.add(cat_id)
            nos_visitados += 1
            try:
                det = _ml_get_autenticado(cur, id_tenant, f"/categories/{cat_id}")
            except Exception as e:
                log.append(f"ERRO categoria {cat_id}: {e}")
                time.sleep(0.05)
                _emit(raiz_idx, rnome)
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
            if nos_visitados % 15 == 0:
                _emit(raiz_idx, rnome)
        _emit(raiz_idx, rnome, forcar=True)

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
    cur,
    *,
    sites: list[str] | None = None,
    conn=None,
    id_exec: int | None = None,
    id_tenant_doador: int | None = None,
) -> dict:
    """Baixa categorias folha (publicáveis) e grava no cache. Retorna resumo + log.

    Usa o tenant doador quando informado; senão qualquer conta conectada.
    """
    from sistema.tarefas_secundarias.doador import obter_ou_promover_doador

    garantir_tabelas_tarefas(cur)
    id_doador = id_tenant_doador or obter_ou_promover_doador(cur, CODIGO_ML_CATEGORIAS)
    if not id_doador:
        raise RuntimeError(
            "Nenhuma conta Mercado Livre conectada. O cache será preenchido quando o 1º vendedor conectar."
        )
    if sites is None:
        cur.execute(
            """
            SELECT UPPER(NULLIF(TRIM(ml_site_id), ''))
            FROM tbl_integracao_mercado_livre
            WHERE id_tenant = %s AND status = 'conectado'
            LIMIT 1
            """,
            (int(id_doador),),
        )
        row = cur.fetchone()
        site = (row[0] if row and row[0] else "MLB") or "MLB"
        sites = [str(site).upper()]
    if conn is not None:
        conn.commit()

    log: list[str] = [f"Doador tenant #{id_doador}"]
    total_folhas = 0
    ignoradas_sem_nome = 0
    erros_site = 0
    sites_total = max(len(sites), 1)

    def progresso(meta_local: dict, mensagem: str, site_idx: int = 1) -> None:
        meta = {
            **meta_local,
            "site_idx": site_idx,
            "sites_total": sites_total,
        }
        # Combina progresso entre sites + raízes
        raiz_idx = int(meta.get("raiz_idx") or 0)
        raizes_total = max(int(meta.get("raizes_total") or 1), 1)
        base = (site_idx - 1) / sites_total
        fatia = (max(raiz_idx - 1, 0) / raizes_total) / sites_total
        if meta.get("fase") == "gravando":
            pct = min(99.5, (site_idx / sites_total) * 100 - 0.5)
        else:
            pct = min(99.0, (base + fatia) * 100)
        meta["pct"] = round(pct, 1)
        _atualizar_progresso_exec(cur, conn, id_exec, mensagem, meta)

    _atualizar_progresso_exec(
        cur,
        conn,
        id_exec,
        "Iniciando sincronização do cache…",
        {"fase": "inicio", "pct": 0, "sites_total": sites_total},
    )

    for site_i, site_id in enumerate(sites, start=1):
        site_id = (site_id or "MLB").upper()
        log.append(f"=== Site {site_id} ===")
        try:
            id_tenant = int(id_doador)
            log.append(f"Usando conta doadora tenant #{id_tenant} (Bearer).")

            def _on_prog(meta_local, mensagem, _site_i=site_i):
                progresso(meta_local, mensagem, site_idx=_site_i)

            folhas, ign = _coletar_folhas_site(
                cur, id_tenant, site_id, log, on_progress=_on_prog
            )
            ignoradas_sem_nome += ign
        except Exception as e:
            erros_site += 1
            log.append(f"ERRO ao listar raízes {site_id}: {e}")
            continue

        progresso(
            {
                "fase": "gravando",
                "site_id": site_id,
                "folhas": len(folhas),
                "raizes_total": 1,
                "raiz_idx": 1,
            },
            f"{site_id}: gravando {len(folhas)} categorias no banco…",
            site_idx=site_i,
        )
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
    _atualizar_progresso_exec(
        cur,
        conn,
        id_exec,
        msg,
        {"fase": "ok", "pct": 100, "folhas": total_folhas},
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
    tem_hora = _coluna_existe(cur, "tbl_tarefa_secundaria", "hora_local")
    hora_sel = (
        "COALESCE(NULLIF(TRIM(hora_local), ''), '02:00')"
        if tem_hora
        else "'02:00'"
    )
    cur.execute(
        f"""
        SELECT id, codigo, agendamento, ativo, {hora_sel}
        FROM tbl_tarefa_secundaria
        WHERE codigo = %s
        """,
        (codigo,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"Tarefa «{codigo}» não cadastrada.")
    id_tarefa = int(row[0])
    codigo_db = row[1]
    agendamento = row[2] or "manual"
    ativo = bool(row[3])
    hora_local = row[4] or "02:00"
    if not ativo:
        raise RuntimeError("Tarefa inativa.")

    if not _agendamento_permite_agora(agendamento, hora_local, forcar=forcar):
        label = {
            "segunda": "segunda-feira",
            "terca": "terça-feira",
            "quarta": "quarta-feira",
            "quinta": "quinta-feira",
            "sexta": "sexta-feira",
            "sabado": "sábado",
            "domingo": "domingo",
            "diario": "diariamente",
        }.get((agendamento or "").lower(), agendamento or "manual")
        return {
            "skipped": True,
            "codigo": codigo_db,
            "mensagem": f"Agendada para {label} às {hora_local} — execução ignorada agora.",
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
        res = _rodar_sync_por_codigo(cur, codigo_db, conn=conn, id_exec=id_exec)
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


def executar_tarefas_agendadas(
    cur, *, disparado_por: str = "cron", forcar: bool = False, conn=None
) -> dict:
    """Roda todas as tarefas ativas cujo agendamento permite hoje (ou todas se forcar)."""
    garantir_tabelas_tarefas(cur)
    cur.execute(
        """
        SELECT codigo FROM tbl_tarefa_secundaria
        WHERE ativo = TRUE
        ORDER BY codigo
        """
    )
    codigos = [str(r[0]) for r in cur.fetchall() if r and r[0]]
    resultados: list[dict] = []
    for codigo in codigos:
        try:
            res = executar_tarefa(
                cur,
                codigo,
                disparado_por=disparado_por,
                forcar=forcar,
                conn=conn,
            )
            resultados.append(res)
            if conn is not None:
                conn.commit()
        except Exception as e:
            if conn is not None:
                conn.rollback()
            resultados.append(
                {"skipped": False, "codigo": codigo, "erro": str(e)[:300]}
            )
            _log.exception("Tarefa %s falhou no job", codigo)
    ok = sum(1 for r in resultados if not r.get("skipped") and not r.get("erro"))
    skip = sum(1 for r in resultados if r.get("skipped"))
    err = sum(1 for r in resultados if r.get("erro"))
    return {
        "message": f"{ok} executada(s) · {skip} ignorada(s) · {err} erro(s).",
        "resultados": resultados,
    }


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
            SELECT id, iniciado_em, meta
            FROM tbl_tarefa_secundaria_execucao
            WHERE id_tarefa = %s AND status = 'rodando'
            ORDER BY iniciado_em DESC
            LIMIT 1
            """,
            (id_tarefa,),
        )
        rodando = cur.fetchone()
        if rodando:
            id_old, ini_old, meta_old = int(rodando[0]), rodando[1], rodando[2]
            if not execucao_esta_orfaa(ini_old, meta_old):
                raise RuntimeError("Esta tarefa já está em execução.")
            cur.execute(
                """
                UPDATE tbl_tarefa_secundaria_execucao
                SET status = 'erro',
                    finalizado_em = %s,
                    mensagem = %s,
                    log_texto = COALESCE(log_texto, '') || %s
                WHERE id = %s AND status = 'rodando'
                """,
                (
                    agora_utc(),
                    "Execução interrompida (sem sinal de progresso).",
                    "\n[sistema] Marcada como órfã ao reiniciar a tarefa.",
                    id_old,
                ),
            )
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
            res = _rodar_sync_por_codigo(cur2, codigo, conn=c2, id_exec=id_exec)
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
