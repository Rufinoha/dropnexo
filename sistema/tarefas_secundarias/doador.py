# sistema/tarefas_secundarias/doador.py — tenant doador de credenciais para cache de categorias
from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)

# codigo tarefa → (provedor, tabela integração)
_MAPA_TAREFA: dict[str, tuple[str, str]] = {
    "ml_categorias_cache": ("mercado_livre", "tbl_integracao_mercado_livre"),
    "tiktok_categorias_cache": ("tiktok", "tbl_integracao_tiktok"),
    "amazon_product_types_cache": ("amazon", "tbl_integracao_amazon"),
    "bling_categorias_cache": ("bling", "tbl_integracao_bling"),
}

_PROVEDOR_PARA_CODIGO = {v[0]: k for k, v in _MAPA_TAREFA.items()}


def codigo_por_provedor(provedor: str) -> str | None:
    return _PROVEDOR_PARA_CODIGO.get((provedor or "").strip().lower())


def _tabela_ok(cur, tabela: str) -> bool:
    cur.execute("SELECT to_regclass(%s)", (tabela,))
    row = cur.fetchone()
    return bool(row and row[0])


def _tenant_conectado(cur, tabela: str, id_tenant: int) -> bool:
    if not _tabela_ok(cur, tabela):
        return False
    cur.execute(
        f"SELECT 1 FROM {tabela} WHERE id_tenant = %s AND status = 'conectado' LIMIT 1",
        (int(id_tenant),),
    )
    return bool(cur.fetchone())


def listar_tenants_conectados(cur, codigo: str) -> list[int]:
    info = _MAPA_TAREFA.get(codigo)
    if not info:
        return []
    _, tabela = info
    if not _tabela_ok(cur, tabela):
        return []
    cur.execute(
        f"""
        SELECT id_tenant FROM {tabela}
        WHERE status = 'conectado'
        ORDER BY conectado_em ASC NULLS LAST, atualizado_em ASC NULLS LAST, id_tenant
        """
    )
    return [int(r[0]) for r in cur.fetchall() if r and r[0]]


def obter_id_doador(cur, codigo: str) -> int | None:
    cur.execute(
        """
        SELECT id_tenant_doador FROM tbl_tarefa_secundaria
        WHERE codigo = %s
        LIMIT 1
        """,
        (codigo,),
    )
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    return int(row[0])


def definir_doador(cur, codigo: str, id_tenant: int | None) -> None:
    cur.execute(
        """
        UPDATE tbl_tarefa_secundaria
        SET id_tenant_doador = %s, atualizado_em = NOW()
        WHERE codigo = %s
        """,
        (int(id_tenant) if id_tenant else None, codigo),
    )


def info_doador(cur, codigo: str) -> dict[str, Any] | None:
    tid = obter_id_doador(cur, codigo)
    if not tid:
        return None
    info = _MAPA_TAREFA.get(codigo)
    tabela = info[1] if info else None
    conectado = _tenant_conectado(cur, tabela, tid) if tabela else False
    cur.execute(
        """
        SELECT id, nome, slug,
               COALESCE(NULLIF(TRIM(tipo_negocio), ''), 'vendedor')
        FROM tbl_tenant WHERE id = %s
        """,
        (tid,),
    )
    row = cur.fetchone()
    if not row:
        return {
            "id_tenant": tid,
            "nome": f"Tenant #{tid}",
            "slug": "",
            "tipo_negocio": "",
            "conectado": False,
            "valido": False,
        }
    return {
        "id_tenant": int(row[0]),
        "nome": (row[1] or "").strip() or f"Tenant #{tid}",
        "slug": (row[2] or "").strip(),
        "tipo_negocio": (row[3] or "").strip(),
        "conectado": conectado,
        "valido": conectado,
    }


def obter_ou_promover_doador(cur, codigo: str) -> int | None:
    """Retorna doador válido; se inválido/ausente, promove o próximo conectado."""
    info = _MAPA_TAREFA.get(codigo)
    if not info:
        return None
    _, tabela = info
    atual = obter_id_doador(cur, codigo)
    if atual and _tenant_conectado(cur, tabela, atual):
        return atual

    candidatos = listar_tenants_conectados(cur, codigo)
    if not candidatos:
        if atual:
            definir_doador(cur, codigo, None)
        return None

    # Prefere manter ordem estável; se atual ainda está na lista (raro), usa o próximo
    novo = candidatos[0]
    if atual and atual in candidatos:
        idx = candidatos.index(atual)
        novo = candidatos[(idx + 1) % len(candidatos)] if len(candidatos) > 1 else candidatos[0]
        if not _tenant_conectado(cur, tabela, atual):
            novo = candidatos[0]

    definir_doador(cur, codigo, novo)
    return novo


def ao_conectar_integracao(
    provedor: str,
    id_tenant: int,
    *,
    disparar_sync: bool = True,
) -> dict[str, Any]:
    """Chamado após OAuth. Se não houver doador válido, promove este tenant e dispara sync."""
    from sistema.tarefas_secundarias.servico import (
        disparar_tarefa_async,
        garantir_tabelas_tarefas,
    )

    codigo = codigo_por_provedor(provedor)
    if not codigo:
        return {"ok": False, "motivo": "provedor_desconhecido"}

    conn = None
    from global_utils import Var_ConectarBanco

    conn = Var_ConectarBanco()
    tornou_doador = False
    try:
        cur = conn.cursor()
        garantir_tabelas_tarefas(cur)
        info = _MAPA_TAREFA[codigo]
        atual = obter_id_doador(cur, codigo)
        valido = bool(atual and _tenant_conectado(cur, info[1], atual))
        if not valido:
            definir_doador(cur, codigo, int(id_tenant))
            tornou_doador = True
        conn.commit()
    except Exception:
        if conn is not None:
            conn.rollback()
        _log.exception("ao_conectar_integracao %s tenant=%s", provedor, id_tenant)
        raise
    finally:
        if conn is not None:
            conn.close()

    sync_iniciado = False
    if tornou_doador and disparar_sync:
        try:
            disparar_tarefa_async(codigo, disparado_por="oauth")
            sync_iniciado = True
        except Exception as e:
            _log.warning(
                "Sync cache após OAuth %s (tenant %s): %s", provedor, id_tenant, e
            )

    return {
        "ok": True,
        "codigo": codigo,
        "tornou_doador": tornou_doador,
        "sync_iniciado": sync_iniciado,
        "id_tenant": int(id_tenant),
    }


def ao_desconectar_integracao(provedor: str, id_tenant: int) -> dict[str, Any]:
    """Se o doador desconectou, limpa e promove o próximo (sem apagar o cache)."""
    from sistema.tarefas_secundarias.servico import (
        disparar_tarefa_async,
        garantir_tabelas_tarefas,
    )
    from global_utils import Var_ConectarBanco

    codigo = codigo_por_provedor(provedor)
    if not codigo:
        return {"ok": False, "motivo": "provedor_desconhecido"}

    conn = Var_ConectarBanco()
    novo_doador: int | None = None
    era_doador = False
    try:
        cur = conn.cursor()
        garantir_tabelas_tarefas(cur)
        atual = obter_id_doador(cur, codigo)
        if not atual or int(atual) != int(id_tenant):
            conn.commit()
            return {
                "ok": True,
                "codigo": codigo,
                "era_doador": False,
                "novo_doador": None,
            }
        era_doador = True
        definir_doador(cur, codigo, None)
        novo_doador = obter_ou_promover_doador(cur, codigo)
        conn.commit()
    except Exception:
        conn.rollback()
        _log.exception("ao_desconectar_integracao %s tenant=%s", provedor, id_tenant)
        raise
    finally:
        conn.close()

    sync_iniciado = False
    if era_doador and novo_doador:
        try:
            disparar_tarefa_async(codigo, disparado_por="doador_fallback")
            sync_iniciado = True
        except Exception as e:
            _log.warning("Sync após fallback doador %s: %s", codigo, e)

    return {
        "ok": True,
        "codigo": codigo,
        "era_doador": era_doador,
        "novo_doador": novo_doador,
        "sync_iniciado": sync_iniciado,
    }
