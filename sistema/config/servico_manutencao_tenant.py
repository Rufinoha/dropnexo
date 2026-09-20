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
        VALUES (%s, 'fornecedores', %s, %s, %s, NOW())
        ON CONFLICT (id_tenant) DO UPDATE SET
            modo_vitrine = 'fornecedores',
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


_TIPOS_METRICAS = ("vendedor", "fornecedor", "armazem")


def _classificar_pessoa(tipo_pessoa: str | None, documento: str | None) -> str:
    tp = (tipo_pessoa or "").strip().upper()
    digitos = "".join(ch for ch in (documento or "") if ch.isdigit())
    if tp == "J" or len(digitos) == 14:
        return "cnpj"
    if tp == "F" or len(digitos) == 11:
        return "pf"
    return "indefinido"


def _slot_tipo() -> dict:
    return {
        "total": 0,
        "ativos": 0,
        "inativos": 0,
        "pf": 0,
        "cnpj": 0,
        "indefinido": 0,
        "encerramentos_solicitados": 0,
        "encerramentos_concluidos": 0,
    }


def metricas_tenants(cur) -> dict:
    """Agrega panorama de tenants para o dashboard DEV."""
    from datetime import date, datetime, timedelta, timezone

    por_tipo = {t: _slot_tipo() for t in _TIPOS_METRICAS}
    pessoa = {"pf": 0, "cnpj": 0, "indefinido": 0}
    ativos = inativos = 0

    cur.execute(
        """
        SELECT
          LOWER(COALESCE(NULLIF(TRIM(tipo_negocio), ''), 'vendedor')),
          COALESCE(ativo, FALSE),
          COALESCE(tipo_pessoa, ''),
          COALESCE(documento, '')
        FROM tbl_tenant
        """
    )
    for tipo_raw, ativo, tipo_pessoa, documento in cur.fetchall():
        tipo = tipo_raw if tipo_raw in por_tipo else "vendedor"
        slot = por_tipo[tipo]
        slot["total"] += 1
        if ativo:
            slot["ativos"] += 1
            ativos += 1
        else:
            slot["inativos"] += 1
            inativos += 1
        pessoa_cls = _classificar_pessoa(tipo_pessoa, documento)
        slot[pessoa_cls] += 1
        pessoa[pessoa_cls] += 1

    total = ativos + inativos
    enc = {
        "solicitados": 0,
        "em_andamento": 0,
        "concluidos": 0,
        "por_tipo": {t: 0 for t in _TIPOS_METRICAS},
        "concluidos_por_tipo": {t: 0 for t in _TIPOS_METRICAS},
    }
    inativos_via_encerramento = 0
    encerramentos_ainda_ativos = 0
    ativacao_pendente = {
        "total": 0,
        "por_tipo": {t: 0 for t in _TIPOS_METRICAS},
        "itens": [],
    }
    inativos_outros = 0

    tem_cancel = False
    try:
        cur.execute("SELECT to_regclass('public.tbl_cancelamento_conta')")
        tem_cancel = bool(cur.fetchone()[0])
    except Exception:
        tem_cancel = False

    if tem_cancel:
        cur.execute(
            """
            SELECT
              LOWER(COALESCE(NULLIF(TRIM(t.tipo_negocio), ''), 'vendedor')),
              COALESCE(c.etapa, 1),
              (c.concluido_em IS NOT NULL OR COALESCE(c.etapa, 1) >= 3) AS concluido,
              COALESCE(t.ativo, FALSE) AS tenant_ativo
            FROM tbl_cancelamento_conta c
            JOIN tbl_tenant t ON t.id = c.id_tenant
            """
        )
        for tipo_raw, etapa, concluido, tenant_ativo in cur.fetchall():
            tipo = tipo_raw if tipo_raw in por_tipo else "vendedor"
            enc["solicitados"] += 1
            enc["por_tipo"][tipo] = enc["por_tipo"].get(tipo, 0) + 1
            por_tipo[tipo]["encerramentos_solicitados"] += 1
            if concluido:
                enc["concluidos"] += 1
                enc["concluidos_por_tipo"][tipo] = enc["concluidos_por_tipo"].get(tipo, 0) + 1
                por_tipo[tipo]["encerramentos_concluidos"] += 1
                if not tenant_ativo:
                    inativos_via_encerramento += 1
            else:
                enc["em_andamento"] += 1
                if tenant_ativo:
                    encerramentos_ainda_ativos += 1

    # Cadastros que preencheram o formulário, receberam e-mail, mas não criaram senha.
    try:
        filtro_cancel = ""
        if tem_cancel:
            filtro_cancel = """
              AND NOT EXISTS (
                SELECT 1
                FROM tbl_cancelamento_conta c
                WHERE c.id_tenant = t.id
                  AND (c.concluido_em IS NOT NULL OR COALESCE(c.etapa, 1) >= 3)
              )
            """
        cur.execute(
            f"""
            SELECT DISTINCT ON (t.id)
              t.id,
              COALESCE(NULLIF(TRIM(t.nome), ''), t.slug, 'Tenant') AS tenant_nome,
              LOWER(COALESCE(NULLIF(TRIM(t.tipo_negocio), ''), 'vendedor')) AS tipo,
              COALESCE(u.nome, '') AS usuario_nome,
              COALESCE(u.email, '') AS email,
              COALESCE(NULLIF(TRIM(u.whatsapp), ''), NULLIF(TRIM(t.telefone_comercial), ''), '') AS whatsapp,
              t.criado_em
            FROM tbl_tenant t
            JOIN tbl_usuario_tenant ut ON ut.id_tenant = t.id AND COALESCE(ut.ativo, TRUE) = TRUE
            JOIN tbl_perfil pf ON pf.id = ut.id_perfil AND LOWER(COALESCE(pf.codigo, '')) = 'dono'
            JOIN tbl_usuario u ON u.id = ut.id_usuario
            WHERE COALESCE(t.ativo, FALSE) = FALSE
              AND (
                u.senha_hash IS NULL
                OR NULLIF(TRIM(COALESCE(u.token_ativacao, '')), '') IS NOT NULL
              )
              {filtro_cancel}
            ORDER BY t.id, ut.id
            """
        )
        for row in cur.fetchall():
            tipo = row[2] if row[2] in ativacao_pendente["por_tipo"] else "vendedor"
            ativacao_pendente["por_tipo"][tipo] = ativacao_pendente["por_tipo"].get(tipo, 0) + 1
            ativacao_pendente["total"] += 1
            criado = row[6]
            ativacao_pendente["itens"].append(
                {
                    "id_tenant": int(row[0]),
                    "tenant_nome": row[1] or "",
                    "tipo_negocio": tipo,
                    "usuario_nome": row[3] or "",
                    "email": row[4] or "",
                    "whatsapp": row[5] or "",
                    "criado_em": criado.isoformat() if criado else None,
                }
            )
        ativacao_pendente["itens"].sort(
            key=lambda x: x.get("criado_em") or "",
            reverse=True,
        )
    except Exception:
        _log.exception("metricas_tenants: falha ao contar ativação pendente")

    inativos_outros = max(
        0,
        inativos - inativos_via_encerramento - int(ativacao_pendente["total"] or 0),
    )

    hoje = datetime.now(timezone.utc).date()
    inicio = hoje - timedelta(days=6)
    dias = [(inicio + timedelta(days=i)).isoformat() for i in range(7)]
    idx = {d: i for i, d in enumerate(dias)}

    cadastros = [0] * 7
    descadastros = [0] * 7
    cad_tipo = {t: [0] * 7 for t in _TIPOS_METRICAS}
    des_tipo = {t: [0] * 7 for t in _TIPOS_METRICAS}

    cur.execute(
        """
        SELECT
          criado_em::date AS dia,
          LOWER(COALESCE(NULLIF(TRIM(tipo_negocio), ''), 'vendedor')) AS tipo,
          COUNT(*)::int
        FROM tbl_tenant
        WHERE criado_em IS NOT NULL
          AND criado_em::date >= %s
          AND criado_em::date <= %s
        GROUP BY 1, 2
        """,
        (inicio, hoje),
    )
    for dia, tipo_raw, qtd in cur.fetchall():
        key = dia.isoformat() if isinstance(dia, date) else str(dia)
        i = idx.get(key)
        if i is None:
            continue
        tipo = tipo_raw if tipo_raw in por_tipo else "vendedor"
        n = int(qtd or 0)
        cadastros[i] += n
        cad_tipo[tipo][i] += n

    if tem_cancel:
        cur.execute(
            """
            SELECT
              c.concluido_em::date AS dia,
              LOWER(COALESCE(NULLIF(TRIM(t.tipo_negocio), ''), 'vendedor')) AS tipo,
              COUNT(*)::int
            FROM tbl_cancelamento_conta c
            JOIN tbl_tenant t ON t.id = c.id_tenant
            WHERE c.concluido_em IS NOT NULL
              AND c.concluido_em::date >= %s
              AND c.concluido_em::date <= %s
            GROUP BY 1, 2
            """,
            (inicio, hoje),
        )
        for dia, tipo_raw, qtd in cur.fetchall():
            key = dia.isoformat() if isinstance(dia, date) else str(dia)
            i = idx.get(key)
            if i is None:
                continue
            tipo = tipo_raw if tipo_raw in por_tipo else "vendedor"
            n = int(qtd or 0)
            descadastros[i] += n
            des_tipo[tipo][i] += n

    def _soma(mapa: dict[str, list[int]]) -> dict[str, int]:
        return {k: int(sum(v)) for k, v in mapa.items()}

    # "Online" aproximado: último acesso recente (não há heartbeat contínuo).
    janela_min = 30
    online = {
        "janela_minutos": janela_min,
        "total": 0,
        "por_tipo": {t: 0 for t in _TIPOS_METRICAS},
        "itens": [],
    }
    try:
        cur.execute(
            """
            SELECT DISTINCT ON (t.id)
              t.id,
              COALESCE(NULLIF(TRIM(t.nome), ''), t.slug, 'Tenant') AS tenant_nome,
              LOWER(COALESCE(NULLIF(TRIM(t.tipo_negocio), ''), 'vendedor')) AS tipo,
              COALESCE(u.nome, '') AS usuario_nome,
              COALESCE(u.email, '') AS email,
              COALESCE(NULLIF(TRIM(u.whatsapp), ''), NULLIF(TRIM(t.telefone_comercial), ''), '') AS whatsapp,
              ut.ultimo_acesso_em
            FROM tbl_usuario_tenant ut
            JOIN tbl_tenant t ON t.id = ut.id_tenant
            JOIN tbl_usuario u ON u.id = ut.id_usuario
            WHERE COALESCE(t.ativo, FALSE) = TRUE
              AND COALESCE(ut.ativo, TRUE) = TRUE
              AND ut.ultimo_acesso_em IS NOT NULL
              AND ut.ultimo_acesso_em >= (NOW() - (%s * INTERVAL '1 minute'))
            ORDER BY t.id, ut.ultimo_acesso_em DESC NULLS LAST
            """,
            (int(janela_min),),
        )
        for row in cur.fetchall():
            tipo = row[2] if row[2] in online["por_tipo"] else "vendedor"
            online["por_tipo"][tipo] = online["por_tipo"].get(tipo, 0) + 1
            online["total"] += 1
            acesso = row[6]
            online["itens"].append(
                {
                    "id_tenant": int(row[0]),
                    "tenant_nome": row[1] or "",
                    "tipo_negocio": tipo,
                    "usuario_nome": row[3] or "",
                    "email": row[4] or "",
                    "whatsapp": row[5] or "",
                    "ultimo_acesso_em": acesso.isoformat() if acesso else None,
                }
            )
        online["itens"].sort(
            key=lambda x: x.get("ultimo_acesso_em") or "",
            reverse=True,
        )
    except Exception:
        _log.exception("metricas_tenants: falha ao listar online")

    return {
        "total": total,
        "ativos": ativos,
        "inativos": inativos,
        "inativos_via_encerramento": inativos_via_encerramento,
        "inativos_outros": inativos_outros,
        "ativacao_pendente": ativacao_pendente,
        "encerramentos_ainda_ativos": encerramentos_ainda_ativos,
        "pessoa": pessoa,
        "encerramentos": enc,
        "por_tipo": por_tipo,
        "online": online,
        "ultimos_7_dias": {
            "dias": dias,
            "cadastros": cadastros,
            "descadastros": descadastros,
            "cadastros_por_tipo": cad_tipo,
            "descadastros_por_tipo": des_tipo,
            "resumo": {
                "cadastros": int(sum(cadastros)),
                "descadastros": int(sum(descadastros)),
                "cadastros_por_tipo": _soma(cad_tipo),
                "descadastros_por_tipo": _soma(des_tipo),
            },
        },
        "gerado_em": datetime.now(timezone.utc).isoformat(),
    }


_FILTROS_LISTA = frozenset(
    {
        "total",
        "ativos",
        "inativos",
        "pf",
        "cnpj",
        "encerr_solicitados",
        "encerr_concluidos",
        "ativacao_pendente",
    }
)


def listar_tenants_metricas(cur, *, tipo: str | None = None, filtro: str = "total") -> dict:
    """Lista tenants para drill-down do dashboard (matriz / KPIs)."""
    tipo_n = (tipo or "").strip().lower()
    if tipo_n and tipo_n not in _TIPOS_METRICAS:
        raise ValueError("Tipo inválido.")
    filtro_n = (filtro or "total").strip().lower()
    if filtro_n not in _FILTROS_LISTA:
        raise ValueError("Filtro inválido.")

    tem_cancel = False
    try:
        cur.execute("SELECT to_regclass('public.tbl_cancelamento_conta')")
        tem_cancel = bool(cur.fetchone()[0])
    except Exception:
        tem_cancel = False

    where = ["TRUE"]
    params: list = []
    if tipo_n:
        where.append("LOWER(COALESCE(NULLIF(TRIM(t.tipo_negocio), ''), 'vendedor')) = %s")
        params.append(tipo_n)

    joins = """
      FROM tbl_tenant t
      LEFT JOIN LATERAL (
        SELECT u.nome, u.email, u.whatsapp, u.senha_hash, u.token_ativacao
        FROM tbl_usuario_tenant ut
        JOIN tbl_perfil pf ON pf.id = ut.id_perfil AND LOWER(COALESCE(pf.codigo, '')) = 'dono'
        JOIN tbl_usuario u ON u.id = ut.id_usuario
        WHERE ut.id_tenant = t.id
        ORDER BY ut.ativo DESC NULLS LAST, ut.id
        LIMIT 1
      ) dono ON TRUE
    """

    if filtro_n == "ativos":
        where.append("COALESCE(t.ativo, FALSE) = TRUE")
    elif filtro_n == "inativos":
        where.append("COALESCE(t.ativo, FALSE) = FALSE")
    elif filtro_n == "pf":
        where.append(
            """(
              UPPER(COALESCE(t.tipo_pessoa, '')) = 'F'
              OR length(regexp_replace(COALESCE(t.documento, ''), '\\D', '', 'g')) = 11
            )"""
        )
    elif filtro_n == "cnpj":
        where.append(
            """(
              UPPER(COALESCE(t.tipo_pessoa, '')) = 'J'
              OR length(regexp_replace(COALESCE(t.documento, ''), '\\D', '', 'g')) = 14
            )"""
        )
    elif filtro_n == "ativacao_pendente":
        where.append("COALESCE(t.ativo, FALSE) = FALSE")
        where.append(
            """(
              dono.senha_hash IS NULL
              OR NULLIF(TRIM(COALESCE(dono.token_ativacao, '')), '') IS NOT NULL
            )"""
        )
        if tem_cancel:
            where.append(
                """NOT EXISTS (
                  SELECT 1 FROM tbl_cancelamento_conta c
                  WHERE c.id_tenant = t.id
                    AND (c.concluido_em IS NOT NULL OR COALESCE(c.etapa, 1) >= 3)
                )"""
            )
    elif filtro_n in ("encerr_solicitados", "encerr_concluidos"):
        if not tem_cancel:
            return {"tipo": tipo_n or "", "filtro": filtro_n, "itens": [], "total": 0}
        joins += """
          JOIN tbl_cancelamento_conta c ON c.id_tenant = t.id
        """
        if filtro_n == "encerr_concluidos":
            where.append("(c.concluido_em IS NOT NULL OR COALESCE(c.etapa, 1) >= 3)")

    cur.execute(
        f"""
        SELECT
          t.id,
          COALESCE(NULLIF(TRIM(t.nome), ''), t.slug, 'Tenant'),
          LOWER(COALESCE(NULLIF(TRIM(t.tipo_negocio), ''), 'vendedor')),
          COALESCE(t.ativo, FALSE),
          COALESCE(dono.nome, ''),
          COALESCE(dono.email, ''),
          COALESCE(NULLIF(TRIM(dono.whatsapp), ''), NULLIF(TRIM(t.telefone_comercial), ''), ''),
          t.criado_em
        {joins}
        WHERE {" AND ".join(where)}
        ORDER BY t.criado_em DESC NULLS LAST, t.id DESC
        LIMIT 400
        """,
        params,
    )
    itens = []
    for row in cur.fetchall():
        itens.append(
            {
                "id_tenant": int(row[0]),
                "tenant_nome": row[1] or "",
                "tipo_negocio": row[2] or "vendedor",
                "ativo": bool(row[3]),
                "usuario_nome": row[4] or "",
                "email": row[5] or "",
                "whatsapp": row[6] or "",
                "criado_em": row[7].isoformat() if row[7] else None,
            }
        )
    return {
        "tipo": tipo_n or "",
        "filtro": filtro_n,
        "itens": itens,
        "total": len(itens),
    }
