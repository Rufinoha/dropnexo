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


_MESES_CURTOS = (
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
)

# Competência do mês = vencimento (fallback: emissão)
_SQL_MES_COMPETENCIA = "date_trunc('month', COALESCE(f.vencimento_em, f.criado_em))::date"


def painel_assinaturas(
    conn,
    *,
    ano: int | None = None,
    mes: int | None = None,
) -> dict[str, Any]:
    cur = conn.cursor()
    hoje = date.today()
    ano_sel = int(ano or hoje.year)
    if ano_sel < 2000 or ano_sel > 2100:
        ano_sel = hoje.year
    mes_sel = int(mes or hoje.month)
    if mes_sel < 1 or mes_sel > 12:
        mes_sel = hoje.month
    mes_ref = date(ano_sel, mes_sel, 1)

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

    # ── Faturamento: competência = mês do vencimento ────────────────────
    # Faturado = emitidas no mês (pendente/vencido/pago)
    # Pago     = dessas, as que estão pagas (mesmo mês de competência)
    # Aberto   = pendente/vencido (todas, e também filtro do mês)
    cur.execute(
        f"""
        SELECT
          COALESCE(SUM(f.valor_centavos), 0)::bigint,
          COUNT(*)::int,
          COALESCE(SUM(CASE WHEN f.status = 'pago' THEN f.valor_centavos ELSE 0 END), 0)::bigint,
          COUNT(*) FILTER (WHERE f.status = 'pago')::int,
          COALESCE(SUM(CASE WHEN f.status IN ('pendente', 'vencido') THEN f.valor_centavos ELSE 0 END), 0)::bigint,
          COUNT(*) FILTER (WHERE f.status IN ('pendente', 'vencido'))::int
        FROM tbl_fatura f
        WHERE f.status IN ('pendente', 'vencido', 'pago')
          AND {_SQL_MES_COMPETENCIA} = %s
        """,
        (mes_ref,),
    )
    row_comp = cur.fetchone() or (0, 0, 0, 0, 0, 0)
    faturado_mes_centavos = int(row_comp[0] or 0)
    faturado_mes_qtd = int(row_comp[1] or 0)
    pago_mes_centavos = int(row_comp[2] or 0)
    pago_mes_qtd = int(row_comp[3] or 0)
    aberto_mes_centavos = int(row_comp[4] or 0)
    aberto_mes_qtd = int(row_comp[5] or 0)

    cur.execute(
        """
        SELECT
          COALESCE(SUM(f.valor_centavos), 0)::bigint,
          COUNT(*)::int
        FROM tbl_fatura f
        WHERE f.status IN ('pendente', 'vencido')
        """
    )
    row_ab_tot = cur.fetchone() or (0, 0)
    aberto_total_centavos = int(row_ab_tot[0] or 0)
    aberto_total_qtd = int(row_ab_tot[1] or 0)

    cur.execute(
        """
        SELECT
          f.id, f.id_tenant, t.nome, f.referencia, f.plano_slug, f.valor_centavos,
          f.status, f.forma_pagamento, f.vencimento_em, f.criado_em,
          COALESCE(NULLIF(f.periodicidade, ''), 'mensal')
        FROM tbl_fatura f
        JOIN tbl_tenant t ON t.id = f.id_tenant
        WHERE f.status IN ('pendente', 'vencido')
        ORDER BY f.vencimento_em ASC NULLS LAST, f.id ASC
        LIMIT 200
        """
    )
    em_aberto = []
    for row in cur.fetchall():
        forma = (row[7] or "").strip().lower()
        periodo = _periodo_ok(row[10])
        plano = str(row[4] or "")
        st = (row[6] or "").strip().lower()
        venc = row[8]
        no_mes = False
        if isinstance(venc, datetime):
            no_mes = venc.year == ano_sel and venc.month == mes_sel
        elif isinstance(venc, date):
            no_mes = venc.year == ano_sel and venc.month == mes_sel
        em_aberto.append(
            {
                "id_fatura": int(row[0]),
                "id_tenant": int(row[1]),
                "nome": (row[2] or "").strip() or f"Tenant #{row[1]}",
                "referencia": row[3] or "",
                "plano": plano,
                "plano_label": PLANO_LABEL.get(plano, plano or "—"),
                "valor_centavos": int(row[5] or 0),
                "valor": _fmt_reais(row[5]),
                "status": st,
                "status_label": {"pendente": "Emitida", "vencido": "Vencida"}.get(st, st),
                "forma_pagamento": forma,
                "forma_label": FORMA_LABEL.get(forma, forma or "—"),
                "vencimento_em": _fmt_data(venc),
                "vencimento_br": _fmt_data_br(venc),
                "criado_em": _fmt_data(row[9]),
                "criado_br": _fmt_data_br(row[9]),
                "periodicidade_label": PERIODO_LABEL.get(periodo, periodo),
                "no_mes_selecionado": no_mes,
            }
        )

    # Série anual (12 meses): faturado × pago por competência
    cur.execute(
        f"""
        SELECT
          {_SQL_MES_COMPETENCIA} AS mes,
          COALESCE(SUM(f.valor_centavos), 0)::bigint AS faturado,
          COALESCE(SUM(CASE WHEN f.status = 'pago' THEN f.valor_centavos ELSE 0 END), 0)::bigint AS pago,
          COUNT(*)::int AS qtd_faturado,
          COUNT(*) FILTER (WHERE f.status = 'pago')::int AS qtd_pago
        FROM tbl_fatura f
        WHERE f.status IN ('pendente', 'vencido', 'pago')
          AND EXTRACT(YEAR FROM COALESCE(f.vencimento_em, f.criado_em)) = %s
        GROUP BY 1
        ORDER BY 1
        """,
        (ano_sel,),
    )
    mapa_ano: dict[int, dict] = {}
    for row in cur.fetchall():
        mdate = row[0]
        if not isinstance(mdate, date):
            continue
        mapa_ano[mdate.month] = {
            "faturado_centavos": int(row[1] or 0),
            "pago_centavos": int(row[2] or 0),
            "qtd_faturado": int(row[3] or 0),
            "qtd_pago": int(row[4] or 0),
        }

    serie_ano = []
    for m in range(1, 13):
        d = mapa_ano.get(m) or {
            "faturado_centavos": 0,
            "pago_centavos": 0,
            "qtd_faturado": 0,
            "qtd_pago": 0,
        }
        serie_ano.append(
            {
                "mes": m,
                "mes_label": _MESES_CURTOS[m - 1],
                "mes_ref": f"{ano_sel}-{m:02d}-01",
                "faturado_centavos": d["faturado_centavos"],
                "faturado": _fmt_reais(d["faturado_centavos"]),
                "pago_centavos": d["pago_centavos"],
                "pago": _fmt_reais(d["pago_centavos"]),
                "qtd_faturado": d["qtd_faturado"],
                "qtd_pago": d["qtd_pago"],
            }
        )

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
            "filtros": {
                "ano": ano_sel,
                "mes": mes_sel,
                "mes_label": f"{mes_sel:02d}/{ano_sel}",
            },
            "resumo": {
                "faturado_mes_centavos": faturado_mes_centavos,
                "faturado_mes": _fmt_reais(faturado_mes_centavos),
                "faturado_mes_qtd": faturado_mes_qtd,
                "pago_mes_centavos": pago_mes_centavos,
                "pago_mes": _fmt_reais(pago_mes_centavos),
                "pago_mes_qtd": pago_mes_qtd,
                "aberto_mes_centavos": aberto_mes_centavos,
                "aberto_mes": _fmt_reais(aberto_mes_centavos),
                "aberto_mes_qtd": aberto_mes_qtd,
                "aberto_total_centavos": aberto_total_centavos,
                "aberto_total": _fmt_reais(aberto_total_centavos),
                "aberto_total_qtd": aberto_total_qtd,
            },
            "em_aberto": em_aberto,
            "serie_ano": {
                "ano": ano_sel,
                "meses": serie_ano,
                "faturado_ano_centavos": sum(x["faturado_centavos"] for x in serie_ano),
                "faturado_ano": _fmt_reais(sum(x["faturado_centavos"] for x in serie_ano)),
                "pago_ano_centavos": sum(x["pago_centavos"] for x in serie_ano),
                "pago_ano": _fmt_reais(sum(x["pago_centavos"] for x in serie_ano)),
            },
            "pagos_recentes": pagos_recentes,
        },
    }
