# sistema/dashboard/servico_dashboard_vendedor.py — resumo operacional do vendedor
from __future__ import annotations

from core.pedidos.notificacoes import STATUS_LABEL
from core.pedidos.servico import col_status_vendedor

CANAIS_INTEGRACAO = (
    ("tbl_integracao_mercado_livre", "Mercado Livre", "/integracoes/mercado-livre"),
    ("tbl_integracao_tiktok", "TikTok Shop", "/integracoes/tiktok"),
    ("tbl_integracao_amazon", "Amazon", "/integracoes/amazon"),
    ("tbl_integracao_melhor_envio", "Melhor Envio", "/integracoes/melhor-envio"),
)


def _fmt_brl(v) -> str:
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        n = 0.0
    return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def montar_dashboard_vendedor(cur, id_vendedor: int) -> dict:
    cv = col_status_vendedor(cur)

    cur.execute(
        f"""
        SELECT COUNT(*)::int, COALESCE(SUM(valor_total), 0)
        FROM tbl_pedido
        WHERE id_tenant_vendedor = %s
          AND criado_em >= NOW() - INTERVAL '7 days'
          AND COALESCE({cv}, '') <> 'cancelado'
        """,
        (id_vendedor,),
    )
    ped_7d, gmv_7d = cur.fetchone()

    cur.execute(
        f"""
        SELECT COUNT(*)::int
        FROM tbl_pedido
        WHERE id_tenant_vendedor = %s
          AND COALESCE({cv}, '') IN ('rascunho', 'importado', 'aguardando_pagamento', 'pago')
        """,
        (id_vendedor,),
    )
    pedidos_acao = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT status, COUNT(*)::int
        FROM tbl_vinculo_vendedor_fornecedor
        WHERE id_tenant_vendedor = %s
          AND status IN ('ativo', 'aguardando', 'pausado')
        GROUP BY status
        """,
        (id_vendedor,),
    )
    vinculos = {"ativo": 0, "aguardando": 0, "pausado": 0}
    for st, qtd in cur.fetchall():
        vinculos[(st or "").strip()] = int(qtd or 0)

    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s AND ativo = TRUE
        """,
        (id_vendedor,),
    )
    produtos_ativos = int(cur.fetchone()[0] or 0)

    cur.execute(
        """
        SELECT COUNT(*)::int FROM tbl_produto_vendedor
        WHERE id_tenant_vendedor = %s
          AND ativo = TRUE
          AND COALESCE(estoque_vitrine, 0) = 0
        """,
        (id_vendedor,),
    )
    estoque_zerado = int(cur.fetchone()[0] or 0)

    cur.execute(
        f"""
        SELECT p.id, p.numero, COALESCE(p.{cv}, '') AS status_v,
               p.valor_total, p.criado_em, p.origem,
               COALESCE(NULLIF(TRIM(tf.nome_fantasia), ''), NULLIF(TRIM(tf.nome), ''), 'Fornecedor')
        FROM tbl_pedido p
        LEFT JOIN tbl_tenant tf ON tf.id = p.id_tenant_fornecedor
        WHERE p.id_tenant_vendedor = %s
        ORDER BY p.criado_em DESC NULLS LAST, p.id DESC
        LIMIT 8
        """,
        (id_vendedor,),
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
                "parceiro": row[6] or "Fornecedor",
                "fornecedor": row[6] or "Fornecedor",
                "url": "/vendedor/pedidos",
            }
        )

    alertas = []
    if pedidos_acao:
        alertas.append(
            {
                "tipo": "pedido_acao",
                "nivel": "alta",
                "titulo": f"{pedidos_acao} pedido(s) precisam da sua ação",
                "texto": "Rascunho, importado, aguardando pagamento ou pago aguardando expedição.",
                "url": "/vendedor/pedidos",
                "cta": "Ver pedidos",
            }
        )
    if vinculos["pausado"]:
        alertas.append(
            {
                "tipo": "vinculo_pausado",
                "nivel": "media",
                "titulo": f"{vinculos['pausado']} vínculo(s) pausado(s)",
                "texto": "Estoques zerados e novos produtos bloqueados nesse vínculo.",
                "url": "/fornecedores",
                "cta": "Ver fornecedores",
            }
        )
    if vinculos["aguardando"]:
        alertas.append(
            {
                "tipo": "vinculo_aguardando",
                "nivel": "baixa",
                "titulo": f"{vinculos['aguardando']} solicitação(ões) aguardando aprovação",
                "texto": "O fornecedor ainda não respondeu ao pedido de vínculo.",
                "url": "/fornecedores",
                "cta": "Ver fornecedores",
            }
        )
    if estoque_zerado:
        alertas.append(
            {
                "tipo": "estoque_zerado",
                "nivel": "media",
                "titulo": f"{estoque_zerado} produto(s) ativo(s) com estoque 0",
                "texto": "Continuam visíveis na vitrine, mas sem estoque para venda.",
                "url": "/meus-produtos",
                "cta": "Meus produtos",
            }
        )

    for tabela, nome, url in CANAIS_INTEGRACAO:
        try:
            cur.execute(
                f"SELECT status FROM {tabela} WHERE id_tenant = %s LIMIT 1",
                (id_vendedor,),
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
                    "texto": "Reconecte para voltar a sincronizar pedidos e anúncios.",
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
            "produtos_ativos": produtos_ativos,
            "fornecedores_ativos": vinculos["ativo"],
        },
        "alertas": alertas,
        "pedidos_recentes": recentes,
    }
