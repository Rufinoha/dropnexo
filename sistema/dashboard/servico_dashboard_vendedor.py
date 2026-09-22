# sistema/dashboard/servico_dashboard_vendedor.py — resumo operacional do vendedor
from __future__ import annotations

from datetime import date, timedelta

from core.pedidos.servico import col_status_vendedor

CANAIS_INTEGRACAO = (
    ("tbl_integracao_mercado_livre", "Mercado Livre", "/integracoes/mercado-livre"),
    ("tbl_integracao_tiktok", "TikTok Shop", "/integracoes/tiktok"),
    ("tbl_integracao_amazon", "Amazon", "/integracoes/amazon"),
    ("tbl_integracao_melhor_envio", "Melhor Envio", "/integracoes/melhor-envio"),
)

ORIGEM_LABEL = {
    "manual": "Manual",
    "mercado_livre": "Mercado Livre",
    "bling": "Bling",
    "tiktok": "TikTok",
    "amazon": "Amazon",
}

ORIGEM_ORDEM = ("manual", "mercado_livre", "bling", "tiktok", "amazon")


def _fmt_brl(v) -> str:
    try:
        n = float(v or 0)
    except (TypeError, ValueError):
        n = 0.0
    return f"R$ {n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _num(v) -> float:
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def _pct(parte: float, todo: float) -> float | None:
    if todo <= 0:
        return None
    return round((parte / todo) * 100, 1)


def _normalizar_dias(dias: int) -> int:
    return dias if dias in (1, 7, 30) else 7


def _janela(dias: int) -> tuple[date, date, date, date]:
    """Retorna (inicio, fim, inicio_anterior, fim_anterior) no fuso de São Paulo."""
    from datetime import datetime
    from zoneinfo import ZoneInfo

    hoje = datetime.now(ZoneInfo("America/Sao_Paulo")).date()
    inicio = hoje - timedelta(days=dias - 1)
    fim_ant = inicio - timedelta(days=1)
    inicio_ant = fim_ant - timedelta(days=dias - 1)
    return inicio, hoje, inicio_ant, fim_ant


def _totais_periodo(cur, id_vendedor: int, cv: str, inicio: date, fim: date) -> dict:
    cur.execute(
        f"""
        WITH ped AS (
            SELECT p.id,
                   COALESCE(p.valor_taxa_pedido, 0) AS taxa,
                   LOWER(COALESCE(NULLIF(TRIM(p.origem), ''), 'manual')) AS origem
            FROM tbl_pedido p
            WHERE p.id_tenant_vendedor = %s
              AND COALESCE(p.{cv}, '') <> 'cancelado'
              AND (p.criado_em AT TIME ZONE 'America/Sao_Paulo')::date BETWEEN %s AND %s
        )
        SELECT
            COALESCE((
                SELECT SUM(i.preco_venda * i.quantidade)
                FROM tbl_pedido_item i
                WHERE i.id_pedido IN (SELECT id FROM ped)
            ), 0),
            COALESCE((
                SELECT SUM(i.valor_drop * i.quantidade)
                FROM tbl_pedido_item i
                WHERE i.id_pedido IN (SELECT id FROM ped)
            ), 0),
            COALESCE((SELECT SUM(taxa) FROM ped), 0),
            COALESCE((SELECT COUNT(*) FROM ped), 0)
        """,
        (id_vendedor, inicio, fim),
    )
    vendido, custo_itens, taxa, pedidos = cur.fetchone()
    vendido_n = _num(vendido)
    custo_n = _num(custo_itens) + _num(taxa)
    margem = vendido_n - custo_n
    return {
        "vendido": vendido_n,
        "custo": custo_n,
        "margem": margem,
        "margem_pct": _pct(margem, vendido_n),
        "pedidos": int(pedidos or 0),
        "vendido_fmt": _fmt_brl(vendido_n),
        "custo_fmt": _fmt_brl(custo_n),
        "margem_fmt": _fmt_brl(margem),
    }


def _serie_diaria(cur, id_vendedor: int, cv: str, inicio: date, fim: date) -> list[dict]:
    cur.execute(
        f"""
        WITH dias AS (
            SELECT gs::date AS dia
            FROM generate_series(%s::date, %s::date, interval '1 day') gs
        ),
        ped AS (
            SELECT p.id,
                   (p.criado_em AT TIME ZONE 'America/Sao_Paulo')::date AS dia,
                   COALESCE(p.valor_taxa_pedido, 0) AS taxa
            FROM tbl_pedido p
            WHERE p.id_tenant_vendedor = %s
              AND COALESCE(p.{cv}, '') <> 'cancelado'
              AND (p.criado_em AT TIME ZONE 'America/Sao_Paulo')::date BETWEEN %s AND %s
        ),
        itens AS (
            SELECT ped.dia,
                   ped.id,
                   SUM(i.preco_venda * i.quantidade) AS vendido,
                   SUM(i.valor_drop * i.quantidade) AS custo
            FROM ped
            JOIN tbl_pedido_item i ON i.id_pedido = ped.id
            GROUP BY ped.dia, ped.id
        )
        SELECT d.dia,
               COALESCE((SELECT SUM(vendido) FROM itens it WHERE it.dia = d.dia), 0),
               COALESCE((SELECT SUM(custo) FROM itens it WHERE it.dia = d.dia), 0)
                 + COALESCE((SELECT SUM(taxa) FROM ped WHERE ped.dia = d.dia), 0),
               COALESCE((SELECT COUNT(*) FROM ped WHERE ped.dia = d.dia), 0)
        FROM dias d
        ORDER BY d.dia
        """,
        (inicio, fim, id_vendedor, inicio, fim),
    )
    hoje = fim
    out = []
    for dia, vendido, custo, pedidos in cur.fetchall():
        vendido_n = _num(vendido)
        custo_n = _num(custo)
        margem = vendido_n - custo_n
        out.append(
            {
                "dia": dia.isoformat(),
                "dia_num": dia.day,
                "mes": dia.month,
                "hoje": dia == hoje,
                "vendido": vendido_n,
                "vendido_fmt": _fmt_brl(vendido_n),
                "custo_fmt": _fmt_brl(custo_n),
                "margem": margem,
                "margem_fmt": _fmt_brl(margem),
                "pedidos": int(pedidos or 0),
            }
        )
    return out


def _por_origem(cur, id_vendedor: int, cv: str, inicio: date, fim: date) -> list[dict]:
    cur.execute(
        f"""
        SELECT LOWER(COALESCE(NULLIF(TRIM(p.origem), ''), 'manual')) AS origem,
               COUNT(DISTINCT p.id)::int,
               COALESCE(SUM(i.preco_venda * i.quantidade), 0)
        FROM tbl_pedido p
        LEFT JOIN tbl_pedido_item i ON i.id_pedido = p.id
        WHERE p.id_tenant_vendedor = %s
          AND COALESCE(p.{cv}, '') <> 'cancelado'
          AND (p.criado_em AT TIME ZONE 'America/Sao_Paulo')::date BETWEEN %s AND %s
        GROUP BY 1
        """,
        (id_vendedor, inicio, fim),
    )
    bruto = { (r[0] or "manual"): (int(r[1] or 0), _num(r[2])) for r in cur.fetchall() }
    total = sum(v[1] for v in bruto.values()) or 0
    chaves = [k for k in ORIGEM_ORDEM if k in bruto]
    extras = [k for k in bruto if k not in ORIGEM_ORDEM]
    linhas = []
    for chave in chaves + extras:
        qtd, vendido = bruto[chave]
        if qtd <= 0 and vendido <= 0:
            continue
        linhas.append(
            {
                "origem": chave,
                "label": ORIGEM_LABEL.get(chave, chave.replace("_", " ").title()),
                "pedidos": qtd,
                "vendido": vendido,
                "vendido_fmt": _fmt_brl(vendido),
                "pct": _pct(vendido, total) or 0,
            }
        )
    linhas.sort(key=lambda x: x["vendido"], reverse=True)
    return linhas


def _top_produtos(cur, id_vendedor: int, cv: str, inicio: date, fim: date) -> list[dict]:
    cur.execute(
        f"""
        SELECT COALESCE(NULLIF(TRIM(i.nome_produto), ''), 'Produto'),
               COALESCE(NULLIF(TRIM(i.sku), ''), ''),
               COALESCE(SUM(i.quantidade), 0)::int,
               COALESCE(SUM(i.preco_venda * i.quantidade), 0),
               COALESCE(SUM(i.valor_drop * i.quantidade), 0)
        FROM tbl_pedido p
        JOIN tbl_pedido_item i ON i.id_pedido = p.id
        WHERE p.id_tenant_vendedor = %s
          AND COALESCE(p.{cv}, '') <> 'cancelado'
          AND (p.criado_em AT TIME ZONE 'America/Sao_Paulo')::date BETWEEN %s AND %s
        GROUP BY 1, 2
        ORDER BY SUM(i.quantidade) DESC, SUM(i.preco_venda * i.quantidade) DESC
        LIMIT 5
        """,
        (id_vendedor, inicio, fim),
    )
    out = []
    for nome, sku, qtd, vendido, custo in cur.fetchall():
        vendido_n = _num(vendido)
        margem = vendido_n - _num(custo)
        out.append(
            {
                "nome": nome,
                "sku": sku,
                "quantidade": int(qtd or 0),
                "vendido_fmt": _fmt_brl(vendido_n),
                "margem": margem,
                "margem_fmt": _fmt_brl(margem),
                "margem_pct": _pct(margem, vendido_n),
            }
        )
    return out


def montar_dashboard_vendedor(cur, id_vendedor: int, dias: int = 7) -> dict:
    cv = col_status_vendedor(cur)
    dias = _normalizar_dias(int(dias or 7))
    inicio, fim, inicio_ant, fim_ant = _janela(dias)

    atual = _totais_periodo(cur, id_vendedor, cv, inicio, fim)
    anterior = _totais_periodo(cur, id_vendedor, cv, inicio_ant, fim_ant)
    delta_pct = _pct(atual["vendido"] - anterior["vendido"], anterior["vendido"])

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

    rotulo = {1: "Hoje", 7: "Últimos 7 dias", 30: "Últimos 30 dias"}[dias]
    return {
        "dias": dias,
        "rotulo": rotulo,
        "kpis": {
            **atual,
            "delta_pct": delta_pct,
            "anterior_fmt": _fmt_brl(anterior["vendido"]),
            "produtos_ativos": produtos_ativos,
            "fornecedores_ativos": vinculos["ativo"],
        },
        "serie": _serie_diaria(cur, id_vendedor, cv, inicio, fim),
        "origens": _por_origem(cur, id_vendedor, cv, inicio, fim),
        "top_produtos": _top_produtos(cur, id_vendedor, cv, inicio, fim),
        "alertas": alertas,
    }
