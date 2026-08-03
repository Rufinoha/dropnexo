# sistema/dashboard/servico_dashboard_fornecedor.py — resumo operacional do fornecedor
from __future__ import annotations

from core.pedidos.notificacoes import STATUS_LABEL
from core.pedidos.servico import col_status_vendedor

CANAIS_STATUS = (
    ("tbl_integracao_bling", "Bling", "/integracoes/bling"),
    ("tbl_integracao_mercadopago", "Mercado Pago", "/integracoes/mercado-pago"),
)


def _fmt_brl(v) -> str:
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        n = 0.0
    return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _tabela_existe(cur, nome: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema IN (current_schema(), 'public')
          AND table_name = %s
        LIMIT 1
        """,
        (nome,),
    )
    return bool(cur.fetchone())


def montar_dashboard_fornecedor(cur, id_fornecedor: int) -> dict:
    cv = col_status_vendedor(cur)

    cur.execute(
        f"""
        SELECT COUNT(*)::int, COALESCE(SUM(valor_total), 0)
        FROM tbl_pedido
        WHERE id_tenant_fornecedor = %s
          AND criado_em >= NOW() - INTERVAL '7 days'
          AND COALESCE({cv}, '') NOT IN ('rascunho', 'importado', 'cancelado')
        """,
        (id_fornecedor,),
    )
    ped_7d, gmv_7d = cur.fetchone()

    cur.execute(
        """
        SELECT status, COUNT(*)::int
        FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_fornecedor = %s
          AND status IN ('ativo', 'aguardando', 'pausado')
        GROUP BY status
        """,
        (id_fornecedor,),
    )
    vinculos = {"ativo": 0, "aguardando": 0, "pausado": 0}
    for st, qtd in cur.fetchall():
        vinculos[(st or "").strip()] = int(qtd or 0)

    cur.execute(
        f"""
        SELECT COUNT(*)::int
        FROM tbl_pedido
        WHERE id_tenant_fornecedor = %s
          AND COALESCE(status_pagamento, '') = 'comprovante_enviado'
          AND COALESCE({cv}, '') = 'aguardando_pagamento'
        """,
        (id_fornecedor,),
    )
    pix_validar = int(cur.fetchone()[0] or 0)

    cur.execute(
        f"""
        SELECT COUNT(*)::int
        FROM tbl_pedido
        WHERE id_tenant_fornecedor = %s
          AND COALESCE({cv}, '') = 'pago'
        """,
        (id_fornecedor,),
    )
    pedidos_expedir = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_produto
        WHERE id_tenant = %s AND publicado = TRUE
        """,
        (id_fornecedor,),
    )
    produtos_ativos = int(cur.fetchone()[0] or 0)

    cur.execute(
        f"""
        SELECT p.id, p.numero, COALESCE(p.{cv}, '') AS status_v,
               p.valor_total, p.criado_em, p.origem,
               COALESCE(NULLIF(TRIM(tv.nome_fantasia), ''), NULLIF(TRIM(tv.nome), ''), 'Vendedor')
        FROM tbl_pedido p
        LEFT JOIN tbl_tenant tv ON tv.id = p.id_tenant_vendedor
        WHERE p.id_tenant_fornecedor = %s
          AND COALESCE(p.{cv}, '') NOT IN ('rascunho', 'importado')
        ORDER BY p.criado_em DESC NULLS LAST, p.id DESC
        LIMIT 8
        """,
        (id_fornecedor,),
    )
    recentes = []
    for row in cur.fetchall():
        st = (row[2] or "").strip()
        recentes.append(
            {
                "id": int(row[0]),
                "numero": (row[1] or str(row[0])).strip(),
                "status": st,
                "status_label": STATUS_LABEL.get(st, st or "—"),
                "valor_total": float(row[3] or 0),
                "valor_fmt": _fmt_brl(row[3]),
                "criado_em": row[4].isoformat() if row[4] else "",
                "origem": (row[5] or "manual").strip(),
                "parceiro": row[6] or "Vendedor",
                "url": "/fornecedor/pedidos",
            }
        )

    alertas = []
    if vinculos["aguardando"]:
        alertas.append(
            {
                "tipo": "vinculo_aguardando",
                "nivel": "alta",
                "titulo": f"{vinculos['aguardando']} solicitação(ões) de vínculo aguardando",
                "texto": "Vendedores esperando sua aprovação para operar com o catálogo.",
                "url": "/fornecedor/vendedores",
                "cta": "Ver vendedores",
            }
        )
    if pix_validar:
        alertas.append(
            {
                "tipo": "pix_comprovante",
                "nivel": "alta",
                "titulo": f"{pix_validar} comprovante(s) PIX para validar",
                "texto": "Confirme ou rejeite o pagamento manual enviado pelo vendedor.",
                "url": "/fornecedor/pedidos",
                "cta": "Ver pedidos",
            }
        )
    if pedidos_expedir:
        alertas.append(
            {
                "tipo": "pedido_expedir",
                "nivel": "alta",
                "titulo": f"{pedidos_expedir} pedido(s) pagos aguardando expedição",
                "texto": "Pedidos pagos prontos para separar, emitir NF ou enviar.",
                "url": "/fornecedor/pedidos",
                "cta": "Ver pedidos",
            }
        )
    if vinculos["pausado"]:
        alertas.append(
            {
                "tipo": "vinculo_pausado",
                "nivel": "media",
                "titulo": f"{vinculos['pausado']} vínculo(s) pausado(s)",
                "texto": "Operação parcial com esses vendedores até despausar ou encerrar.",
                "url": "/fornecedor/vendedores",
                "cta": "Ver vendedores",
            }
        )

    for tabela, nome, url in CANAIS_STATUS:
        try:
            if not _tabela_existe(cur, tabela):
                continue
            cur.execute(
                f"SELECT status FROM {tabela} WHERE id_tenant = %s LIMIT 1",
                (id_fornecedor,),
            )
            row = cur.fetchone()
        except Exception:
            try:
                cur.connection.rollback()
            except Exception:
                pass
            continue
        if not row:
            continue
        st = (row[0] or "").strip().lower()
        if st and st != "conectado":
            alertas.append(
                {
                    "tipo": "integracao_desconectada",
                    "nivel": "alta",
                    "titulo": f"{nome} desconectado",
                    "texto": "Reconecte para receber pagamentos ou sincronizar o catálogo.",
                    "url": url,
                    "cta": "Abrir integração",
                }
            )

    nivel_rank = {"alta": 0, "media": 1, "baixa": 2}
    alertas.sort(key=lambda a: nivel_rank.get(a.get("nivel"), 9))

    return {
        "periodo_dias": 7,
        "kpis": {
            "pedidos_7d": int(ped_7d or 0),
            "faturamento_7d": float(gmv_7d or 0),
            "faturamento_7d_fmt": _fmt_brl(gmv_7d),
            "vendedores_ativos": vinculos["ativo"],
            "aguardando": vinculos["aguardando"],
            "produtos_ativos": produtos_ativos,
        },
        "alertas": alertas,
        "pedidos_recentes": recentes,
    }
