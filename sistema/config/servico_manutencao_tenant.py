# sistema/config/servico_manutencao_tenant.py — manutenção DEV de tenants
from __future__ import annotations

import logging
import re

from psycopg2 import sql

_log = logging.getLogger(__name__)

_COLS_TENANT = ("id_tenant", "id_tenant_vendedor", "id_tenant_fornecedor")
_SLUGS_PROTEGIDOS = frozenset({"sistema", "admin", "dropnexo", "h74"})


def slug_protegido(slug: str) -> bool:
    return (slug or "").strip().lower() in _SLUGS_PROTEGIDOS


def migrar_fornecedor_para_armazem(cur, id_tenant: int) -> dict:
    """Ao trocar tipo fornecedor/híbrido → armazém: espelha rede/aprovação.

    Cria/atualiza ``tbl_armazem_parametros`` a partir de
    ``tbl_fornecedor_requisitos_vendedor`` para o tenant não sumir da rede.
    """
    id_tenant = int(id_tenant)
    from armazem.parametros.srotas_parametros import garantir_tabela_parametros

    garantir_tabela_parametros(cur)

    visivel = False
    auto = False
    texto = None
    tinha_req = False
    try:
        cur.execute(
            """
            SELECT COALESCE(visivel_rede_vendedor, FALSE),
                   COALESCE(aprovacao_automatica, FALSE),
                   texto_adicional
            FROM tbl_fornecedor_requisitos_vendedor
            WHERE id_tenant = %s
            """,
            (id_tenant,),
        )
        row = cur.fetchone()
        if row:
            tinha_req = True
            visivel = bool(row[0])
            auto = bool(row[1])
            texto = (row[2] or "").strip() or None
    except Exception:
        # Tabela de requisitos pode não existir em bases antigas.
        pass

    cur.execute(
        """
        INSERT INTO tbl_armazem_parametros (
            id_tenant, modo_vitrine, visivel_rede_vendedor,
            aprovacao_automatica, texto_adicional, atualizado_em
        )
        VALUES (%s, 'armazem', %s, %s, %s, NOW())
        ON CONFLICT (id_tenant) DO UPDATE SET
            visivel_rede_vendedor = EXCLUDED.visivel_rede_vendedor,
            aprovacao_automatica = EXCLUDED.aprovacao_automatica,
            texto_adicional = COALESCE(EXCLUDED.texto_adicional, tbl_armazem_parametros.texto_adicional),
            atualizado_em = NOW()
        """,
        (id_tenant, visivel, auto, texto),
    )

    # Mantém espelho nos requisitos (usado em telas compartilhadas).
    if tinha_req:
        cur.execute(
            """
            UPDATE tbl_fornecedor_requisitos_vendedor
               SET visivel_rede_vendedor = %s,
                   aprovacao_automatica = %s,
                   texto_adicional = COALESCE(%s, texto_adicional)
             WHERE id_tenant = %s
            """,
            (visivel, auto, texto, id_tenant),
        )

    return {
        "visivel_rede_vendedor": visivel,
        "aprovacao_automatica": auto,
        "copiou_requisitos": tinha_req,
    }


def listar_tabelas_com_coluna_tenant(cur) -> list[tuple[str, str]]:
    """Tabelas públicas com coluna de tenant (exceto tbl_tenant)."""
    cur.execute(
        """
        SELECT c.table_name, c.column_name
        FROM information_schema.columns c
        JOIN information_schema.tables t
          ON t.table_schema = c.table_schema
         AND t.table_name = c.table_name
        WHERE c.table_schema = 'public'
          AND t.table_type = 'BASE TABLE'
          AND c.column_name = ANY(%s)
          AND c.table_name <> 'tbl_tenant'
        ORDER BY c.table_name, c.column_name
        """,
        (list(_COLS_TENANT),),
    )
    return [(str(r[0]), str(r[1])) for r in cur.fetchall()]


def contagens_resumo_tenant(cur, id_tenant: int) -> dict:
    cur.execute(
        """
        SELECT
          (SELECT COUNT(*)::int FROM tbl_produto WHERE id_tenant = %s),
          (SELECT COUNT(*)::int FROM tbl_vinculo_vendedor_fornecedor
             WHERE id_tenant_fornecedor = %s OR id_tenant_vendedor = %s),
          (SELECT COUNT(*)::int FROM tbl_pedido
             WHERE id_tenant_fornecedor = %s OR id_tenant_vendedor = %s),
          (SELECT COUNT(*)::int FROM tbl_usuario_tenant WHERE id_tenant = %s)
        """,
        (id_tenant, id_tenant, id_tenant, id_tenant, id_tenant, id_tenant),
    )
    row = cur.fetchone() or (0, 0, 0, 0)
    return {
        "produtos": int(row[0] or 0),
        "vinculos": int(row[1] or 0),
        "pedidos": int(row[2] or 0),
        "usuarios": int(row[3] or 0),
    }


def excluir_tenant_completo(cur, id_tenant: int) -> dict:
    """Remove dados do tenant em cascata (várias passadas) e a linha em tbl_tenant.

    Usa SAVEPOINT por tabela para contornar ordem de FKs. Retorna log resumido.
    """
    id_tenant = int(id_tenant)
    if id_tenant <= 0:
        raise RuntimeError("Tenant inválido.")

    cur.execute(
        "SELECT id, nome, slug FROM tbl_tenant WHERE id = %s FOR UPDATE",
        (id_tenant,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError("Tenant não encontrado.")
    nome = row[1] or ""
    slug = (row[2] or "").strip().lower()
    if slug_protegido(slug):
        raise RuntimeError(f"Tenant «{slug}» é protegido e não pode ser excluído.")

    resumo_antes = contagens_resumo_tenant(cur, id_tenant)
    targets = listar_tabelas_com_coluna_tenant(cur)
    log: list[str] = []
    total_linhas = 0

    for _pass in range(40):
        mudou = False
        for table, col in targets:
            # Identifiers seguros (somente nomes vindos do information_schema).
            if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", table):
                continue
            if col not in _COLS_TENANT:
                continue
            cur.execute("SAVEPOINT sp_del_tenant_row")
            try:
                cur.execute(
                    sql.SQL("DELETE FROM {} WHERE {} = %s").format(
                        sql.Identifier(table), sql.Identifier(col)
                    ),
                    (id_tenant,),
                )
                n = int(cur.rowcount or 0)
                cur.execute("RELEASE SAVEPOINT sp_del_tenant_row")
                if n > 0:
                    mudou = True
                    total_linhas += n
                    log.append(f"{table}.{col}: {n}")
            except Exception as e:
                cur.execute("ROLLBACK TO SAVEPOINT sp_del_tenant_row")
                _log.debug(
                    "Pass delete %s.%s tenant=%s: %s", table, col, id_tenant, e
                )
        if not mudou:
            break
    else:
        raise RuntimeError(
            "Não foi possível limpar todas as dependências do tenant "
            "(limite de passadas). Verifique FKs manuais."
        )

    # Garante que não restou linha óbvia nas colunas scanneadas
    restos: list[str] = []
    for table, col in targets:
        if not re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]*", table):
            continue
        cur.execute("SAVEPOINT sp_chk_tenant_row")
        try:
            cur.execute(
                sql.SQL("SELECT 1 FROM {} WHERE {} = %s LIMIT 1").format(
                    sql.Identifier(table), sql.Identifier(col)
                ),
                (id_tenant,),
            )
            if cur.fetchone():
                restos.append(f"{table}.{col}")
            cur.execute("RELEASE SAVEPOINT sp_chk_tenant_row")
        except Exception:
            cur.execute("ROLLBACK TO SAVEPOINT sp_chk_tenant_row")

    if restos:
        raise RuntimeError(
            "Ainda há resíduos ligados ao tenant em: "
            + ", ".join(restos[:12])
            + ("…" if len(restos) > 12 else "")
        )

    cur.execute("DELETE FROM tbl_tenant WHERE id = %s", (id_tenant,))
    if cur.rowcount != 1:
        raise RuntimeError("Falha ao remover o registro do tenant.")

    log.append("tbl_tenant: 1")
    return {
        "id": id_tenant,
        "nome": nome,
        "slug": slug,
        "linhas_removidas": total_linhas + 1,
        "resumo_antes": resumo_antes,
        "log": log[-80:],  # últimas entradas
        "tabelas_alvo": len(targets),
    }
