# sistema/financeiro/assinaturas_painel.py — painel SaaS (ativas / inadimplência / faturamento)
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sistema.financeiro.cobranca import PLANOS_PAGOS
from sistema.financeiro.cupom import PERIODOS, calcular_preco

PLANO_LABEL = {
    "starter": "Starter",
    "professional": "Professional",
    "scale": "Scale",
    "enterprise": "Enterprise",
}
PERIODO_LABEL = {k: v["rotulo"] for k, v in PERIODOS.items()}
FORMA_LABEL = {
    "boleto": "Boleto",
    "pix": "Pix",
    "cartao": "Cartão",
    "credit_card": "Cartão",
}


def _fmt_reais(centavos: int | None) -> str:
    v = int(centavos or 0) / 100.0
    return f"R$ {v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _fmt_data(v) -> str | None:
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.date().isoformat()
    if isinstance(v, date):
        return v.isoformat()
    return str(v)[:10]


def _fmt_data_br(v) -> str:
    iso = _fmt_data(v)
    if not iso or len(iso) < 10:
        return "—"
    y, m, d = iso[:10].split("-")
    return f"{d}/{m}/{y}"


def _periodo_ok(raw: str | None) -> str:
    p = (raw or "mensal").strip().lower()
    return p if p in PERIODOS else "mensal"


def _mrr_de_catalogo(valor_mensal_centavos: int, periodo: str) -> dict[str, int]:
    """Provisão sem cupom: valor do ciclo com desconto de período, normalizado /mês."""
    preco = calcular_preco(int(valor_mensal_centavos or 0), periodo, cupom=None)
    meses = max(1, int(preco["meses_cobertos"]))
    ciclo = int(preco["valor_final_centavos"])
    return {
        "ciclo_centavos": ciclo,
        "mrr_centavos": int(round(ciclo / meses)),
        "meses_cobertos": meses,
    }


def _proxima_cobranca_estimada(dia_vencimento: int | None, hoje: date | None = None) -> date | None:
    if not dia_vencimento:
        return None
    hoje = hoje or date.today()
    dia = max(1, min(28, int(dia_vencimento)))
    try:
        cand = date(hoje.year, hoje.month, dia)
    except ValueError:
        return None
    if cand < hoje:
        if hoje.month == 12:
            return date(hoje.year + 1, 1, dia)
        return date(hoje.year, hoje.month + 1, dia)
    return cand


def painel_assinaturas(conn) -> dict[str, Any]:
    cur = conn.cursor()

    # ── Ativas ──────────────────────────────────────────────────────────
    cur.execute(
        """
        SELECT
          t.id, t.nome, t.slug, t.plano, t.tipo_negocio, t.ativo,
          COALESCE(NULLIF(tc.periodicidade, ''), 'mensal'),
          tc.dia_vencimento, tc.forma_pagamento, tc.inicio_cobranca,
          COALESCE(p.valor_centavos, 0), COALESCE(p.nome, t.plano)
        FROM tbl_tenant t
        LEFT JOIN tbl_tenant_cobranca tc ON tc.id_tenant = t.id
        LEFT JOIN tbl_plano p ON p.slug = t.plano
        WHERE COALESCE(t.ativo, TRUE) = TRUE
          AND t.plano = ANY(%s)
        ORDER BY t.nome ASC NULLS LAST, t.id ASC
        """,
        (list(PLANOS_PAGOS),),
    )
    ativas = []
    mrr_total = 0
    ciclo_mes_estimado = 0
    por_plano: dict[str, dict] = {}
    por_periodo: dict[str, dict] = {}

    for row in cur.fetchall():
        periodo = _periodo_ok(row[6])
        catalogo = int(row[10] or 0)
        meta = _mrr_de_catalogo(catalogo, periodo)
        mrr_total += meta["mrr_centavos"]
        # estimativa de caixa no próximo ciclo “médio” mensal ≈ MRR
        ciclo_mes_estimado += meta["mrr_centavos"]
        plano = str(row[3] or "")
        forma = (row[8] or "").strip().lower()
        prox = _proxima_cobranca_estimada(row[7])
        item = {
            "id_tenant": int(row[0]),
            "nome": (row[1] or "").strip() or f"Tenant #{row[0]}",
            "slug": row[2] or "",
            "plano": plano,
            "plano_label": PLANO_LABEL.get(plano, (row[11] or plano)),
            "tipo_negocio": row[4] or "",
            "periodicidade": periodo,
            "periodicidade_label": PERIODO_LABEL.get(periodo, periodo),
            "dia_vencimento": int(row[7]) if row[7] else None,
            "forma_pagamento": forma,
            "forma_label": FORMA_LABEL.get(forma, forma or "—"),
            "inicio_cobranca": _fmt_data(row[9]),
            "inicio_cobranca_br": _fmt_data_br(row[9]),
            "catalogo_mensal_centavos": catalogo,
            "catalogo_mensal": _fmt_reais(catalogo),
            "ciclo_centavos": meta["ciclo_centavos"],
            "ciclo": _fmt_reais(meta["ciclo_centavos"]),
            "mrr_centavos": meta["mrr_centavos"],
            "mrr": _fmt_reais(meta["mrr_centavos"]),
            "proxima_cobranca": _fmt_data(prox),
            "proxima_cobranca_br": _fmt_data_br(prox),
        }
        ativas.append(item)

        bp = por_plano.setdefault(
            plano,
            {"plano": plano, "plano_label": item["plano_label"], "qtd": 0, "mrr_centavos": 0},
        )
        bp["qtd"] += 1
        bp["mrr_centavos"] += meta["mrr_centavos"]

        pp = por_periodo.setdefault(
            periodo,
            {
                "periodicidade": periodo,
                "periodicidade_label": item["periodicidade_label"],
                "qtd": 0,
                "mrr_centavos": 0,
            },
        )
        pp["qtd"] += 1
        pp["mrr_centavos"] += meta["mrr_centavos"]

    for d in (por_plano, por_periodo):
        for v in d.values():
            v["mrr"] = _fmt_reais(v["mrr_centavos"])

    # ── Inadimplência: atraso (ainda em plano pago) ─────────────────────
    cur.execute(
        """
        SELECT DISTINCT ON (t.id)
          t.id, t.nome, t.slug, t.plano,
          f.id, f.referencia, f.status, f.forma_pagamento, f.valor_centavos,
          f.vencimento_em, f.avisado_em, f.criado_em,
          COALESCE(NULLIF(f.periodicidade, ''), NULLIF(tc.periodicidade, ''), 'mensal')
        FROM tbl_tenant t
        JOIN tbl_fatura f ON f.id_tenant = t.id
        LEFT JOIN tbl_tenant_cobranca tc ON tc.id_tenant = t.id
        WHERE t.plano = ANY(%s)
          AND f.status IN ('pendente', 'vencido')
          AND f.rebaixado_em IS NULL
          AND (
            f.status = 'vencido'
            OR f.vencimento_em < CURRENT_DATE
          )
        ORDER BY t.id, f.vencimento_em ASC NULLS LAST, f.id ASC
        """,
        (list(PLANOS_PAGOS),),
    )
    em_atraso = []
    atraso_total = 0
    for row in cur.fetchall():
        valor = int(row[8] or 0)
        atraso_total += valor
        forma = (row[7] or "").strip().lower()
        periodo = _periodo_ok(row[12])
        em_atraso.append(
            {
                "id_tenant": int(row[0]),
                "nome": (row[1] or "").strip() or f"Tenant #{row[0]}",
                "slug": row[2] or "",
                "plano": row[3] or "",
                "plano_label": PLANO_LABEL.get(str(row[3] or ""), str(row[3] or "")),
                "id_fatura": int(row[4]),
                "referencia": row[5] or "",
                "status": row[6] or "",
                "forma_pagamento": forma,
                "forma_label": FORMA_LABEL.get(forma, forma or "—"),
                "valor_centavos": valor,
                "valor": _fmt_reais(valor),
                "vencimento_em": _fmt_data(row[9]),
                "vencimento_br": _fmt_data_br(row[9]),
                "avisado_em": _fmt_data(row[10]),
                "periodicidade": periodo,
                "periodicidade_label": PERIODO_LABEL.get(periodo, periodo),
            }
        )

    # ── Rebaixados ao gratuito (histórico recente) ──────────────────────
    cur.execute(
        """
        SELECT
          t.id, t.nome, t.slug, t.plano,
          f.id, f.referencia, f.valor_centavos, f.rebaixado_em,
          f.plano_slug, f.status, f.forma_pagamento
        FROM tbl_fatura f
        JOIN tbl_tenant t ON t.id = f.id_tenant
        WHERE f.rebaixado_em IS NOT NULL
        ORDER BY f.rebaixado_em DESC
        LIMIT 200
        """
    )
    rebaixados = []
    for row in cur.fetchall():
        forma = (row[10] or "").strip().lower()
        plano_orig = str(row[8] or "")
        rebaixados.append(
            {
                "id_tenant": int(row[0]),
                "nome": (row[1] or "").strip() or f"Tenant #{row[0]}",
                "slug": row[2] or "",
                "plano_atual": row[3] or "",
                "plano_atual_label": PLANO_LABEL.get(str(row[3] or ""), str(row[3] or "")),
                "id_fatura": int(row[4]),
                "referencia": row[5] or "",
                "valor_centavos": int(row[6] or 0),
                "valor": _fmt_reais(row[6]),
                "rebaixado_em": _fmt_data(row[7]),
                "rebaixado_br": _fmt_data_br(row[7]),
                "plano_origem": plano_orig,
                "plano_origem_label": PLANO_LABEL.get(plano_orig, plano_orig or "—"),
                "status_fatura": row[9] or "",
                "forma_label": FORMA_LABEL.get(forma, forma or "—"),
                "ainda_starter": str(row[3] or "").lower() == "starter",
            }
        )

    # ── Faturamento mês a mês (pago) ────────────────────────────────────
    cur.execute(
        """
        SELECT
          date_trunc('month', f.pago_em)::date AS mes,
          COUNT(*)::int,
          COALESCE(SUM(f.valor_centavos), 0)::bigint
        FROM tbl_fatura f
        WHERE f.status = 'pago'
          AND f.pago_em IS NOT NULL
        GROUP BY 1
        ORDER BY 1 DESC
        LIMIT 36
        """
    )
    meses = []
    for row in cur.fetchall():
        mes = row[0]
        total = int(row[2] or 0)
        label = "—"
        if isinstance(mes, date):
            label = f"{mes.month:02d}/{mes.year}"
        meses.append(
            {
                "mes": _fmt_data(mes),
                "mes_label": label,
                "qtd": int(row[1] or 0),
                "total_centavos": total,
                "total": _fmt_reais(total),
            }
        )

    cur.execute(
        """
        SELECT
          COALESCE(SUM(f.valor_centavos), 0)::bigint,
          COUNT(*)::int
        FROM tbl_fatura f
        WHERE f.status = 'pago'
          AND f.pago_em IS NOT NULL
          AND date_trunc('month', f.pago_em) = date_trunc('month', CURRENT_TIMESTAMP)
        """
    )
    row_mes = cur.fetchone() or (0, 0)
    pago_mes_centavos = int(row_mes[0] or 0)
    pago_mes_qtd = int(row_mes[1] or 0)

    cur.execute(
        """
        SELECT
          f.id, f.id_tenant, t.nome, f.referencia, f.plano_slug, f.valor_centavos,
          f.pago_em, f.forma_pagamento,
          COALESCE(NULLIF(f.periodicidade, ''), 'mensal')
        FROM tbl_fatura f
        JOIN tbl_tenant t ON t.id = f.id_tenant
        WHERE f.status = 'pago'
          AND f.pago_em IS NOT NULL
        ORDER BY f.pago_em DESC, f.id DESC
        LIMIT 80
        """
    )
    pagos_recentes = []
    for row in cur.fetchall():
        forma = (row[7] or "").strip().lower()
        periodo = _periodo_ok(row[8])
        plano = str(row[4] or "")
        pagos_recentes.append(
            {
                "id_fatura": int(row[0]),
                "id_tenant": int(row[1]),
                "nome": (row[2] or "").strip() or f"Tenant #{row[1]}",
                "referencia": row[3] or "",
                "plano": plano,
                "plano_label": PLANO_LABEL.get(plano, plano or "—"),
                "valor_centavos": int(row[5] or 0),
                "valor": _fmt_reais(row[5]),
                "pago_em": _fmt_data(row[6]),
                "pago_br": _fmt_data_br(row[6]),
                "forma_label": FORMA_LABEL.get(forma, forma or "—"),
                "periodicidade_label": PERIODO_LABEL.get(periodo, periodo),
            }
        )

    return {
        "ativas": {
            "resumo": {
                "qtd": len(ativas),
                "mrr_centavos": mrr_total,
                "mrr": _fmt_reais(mrr_total),
                "arr_centavos": mrr_total * 12,
                "arr": _fmt_reais(mrr_total * 12),
                "provisao_mensal_centavos": ciclo_mes_estimado,
                "provisao_mensal": _fmt_reais(ciclo_mes_estimado),
                "por_plano": list(por_plano.values()),
                "por_periodo": list(por_periodo.values()),
            },
            "itens": ativas,
        },
        "inadimplencia": {
            "resumo": {
                "qtd_atraso": len(em_atraso),
                "valor_atraso_centavos": atraso_total,
                "valor_atraso": _fmt_reais(atraso_total),
                "qtd_rebaixados": len(rebaixados),
                "qtd_ainda_starter": sum(1 for r in rebaixados if r["ainda_starter"]),
            },
            "em_atraso": em_atraso,
            "rebaixados": rebaixados,
        },
        "faturamento": {
            "resumo": {
                "pago_mes_centavos": pago_mes_centavos,
                "pago_mes": _fmt_reais(pago_mes_centavos),
                "pago_mes_qtd": pago_mes_qtd,
                "meses_com_dados": len(meses),
            },
            "meses": meses,
            "pagos_recentes": pagos_recentes,
        },
    }
