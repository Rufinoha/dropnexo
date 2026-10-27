# sistema/financeiro/assinaturas_painel.py — painel SaaS (ativas / inadimplência / faturamento)
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sistema.financeiro.cobranca import PLANOS_PAGOS
from sistema.financeiro.cupom import PERIODOS, calcular_preco

# Fallback genérico (sem tipo). Preferir nome_plano_comercial().
PLANO_LABEL = {
    "starter": "Explorar",
    "professional": "Crescer / Conectar",
    "scale": "Escalar / Expandir",
    "enterprise": "Pro / Hub",
}


def nome_plano_comercial(slug: str | None, tipo_negocio: str | None = None) -> str:
    from sistema.planos.limites import limites_plano

    s = (slug or "").strip().lower()
    tipo = (tipo_negocio or "").strip().lower()
    if tipo in ("vendedor", "fornecedor"):
        return limites_plano(plano=s, tipo_negocio=tipo).get("nome") or PLANO_LABEL.get(s, s or "—")
    return PLANO_LABEL.get(s, s or "—")
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


def _anexar_lembretes(cur, linhas: list[dict]) -> None:
    ids = [int(x["id_fatura"]) for x in linhas if x.get("id_fatura")]
    mapa: dict[int, dict] = {}
    if ids:
        try:
            cur.execute("SAVEPOINT sp_asf_lemb")
            from sistema.financeiro.cobranca import resumo_lembretes

            mapa = resumo_lembretes(cur, ids)
            cur.execute("RELEASE SAVEPOINT sp_asf_lemb")
        except Exception:
            _rollback_sp(cur, "sp_asf_lemb")
            mapa = {}
    for linha in linhas:
        info = mapa.get(int(linha["id_fatura"])) or {}
        linha["lembrete_qtd"] = int(info.get("qtd") or 0)
        linha["lembrete_rotulo"] = info.get("rotulo") or ""


def _rollback_sp(cur, nome: str) -> None:
    try:
        cur.execute(f"ROLLBACK TO SAVEPOINT {nome}")
    except Exception:
        pass


def _rotulo_desconto_cupom(cupom: dict) -> str:
    tipo = (cupom.get("tipo_desconto") or "").lower()
    valor = float(cupom.get("valor_desconto") or 0)
    if tipo == "percentual":
        txt = f"{valor:g}".replace(".", ",")
        return f"{txt}%"
    if tipo == "fixo":
        return _fmt_reais(int(round(valor * 100)))
    return ""


def _prazo_beneficio(cupom: dict | None, restantes, periodo: str) -> str:
    if not cupom:
        return "—"
    meta = PERIODOS.get((cupom.get("periodo") or periodo or "mensal"), PERIODOS["mensal"])
    if cupom.get("beneficio_vitalicio") or restantes is None:
        return "Vitalício"
    n = max(0, int(restantes or 0))
    if n <= 0:
        return "Esgotado"
    und = meta["unidade"] if n == 1 else meta["unidade_plural"]
    return f"{n} {und} restante" if n == 1 else f"{n} {und} restantes"


def _enriquecer_beneficios(cur, ativas: list[dict]) -> None:
    """Cupom, Fornecedor Fundador, valor a cobrar e se a Efí já gerou cobrança."""
    if not ativas:
        return
    ids = [int(a["id_tenant"]) for a in ativas]
    fundador: dict[int, bool] = {}
    cupom_vinc: dict[int, tuple] = {}
    cupons: dict[int, dict] = {}
    efi: dict[int, dict] = {}

    try:
        cur.execute("SAVEPOINT sp_asf_benef")
        cur.execute(
            """
            SELECT t.id,
                   COALESCE(t.eh_fornecedor_fundador, FALSE),
                   COALESCE(t.fornecedor_fundador_ativo, FALSE),
                   tc.id_cupom_beneficio,
                   tc.cupom_ciclos_restantes
            FROM tbl_tenant t
            LEFT JOIN tbl_tenant_cobranca tc ON tc.id_tenant = t.id
            WHERE t.id = ANY(%s)
            """,
            (ids,),
        )
        for row in cur.fetchall():
            fundador[int(row[0])] = bool(row[1]) and bool(row[2])
            cupom_vinc[int(row[0])] = (row[3], row[4])
        cur.execute("RELEASE SAVEPOINT sp_asf_benef")
    except Exception:
        _rollback_sp(cur, "sp_asf_benef")

    cupom_ids = [int(v[0]) for v in cupom_vinc.values() if v and v[0]]
    if cupom_ids:
        try:
            cur.execute("SAVEPOINT sp_asf_cupom")
            cur.execute(
                """
                SELECT id, codigo, tipo_desconto, valor_desconto, periodo,
                       COALESCE(beneficio_vitalicio, FALSE),
                       COALESCE(ciclos_beneficio, 1)
                FROM tbl_cupom_desconto
                WHERE id = ANY(%s)
                """,
                (cupom_ids,),
            )
            for row in cur.fetchall():
                cupons[int(row[0])] = {
                    "id": int(row[0]),
                    "codigo": row[1] or "",
                    "tipo_desconto": row[2],
                    "valor_desconto": float(row[3] or 0),
                    "periodo": row[4],
                    "beneficio_vitalicio": bool(row[5]),
                    "ciclos_beneficio": int(row[6] or 1),
                }
            cur.execute("RELEASE SAVEPOINT sp_asf_cupom")
        except Exception:
            _rollback_sp(cur, "sp_asf_cupom")

    try:
        cur.execute("SAVEPOINT sp_asf_efi")
        cur.execute(
            """
            SELECT DISTINCT ON (f.id_tenant)
                   f.id_tenant, f.referencia, f.status
            FROM tbl_fatura f
            WHERE f.id_tenant = ANY(%s)
              AND (
                NULLIF(TRIM(COALESCE(f.efi_charge_id, '')), '') IS NOT NULL
                OR NULLIF(TRIM(COALESCE(f.efi_txid, '')), '') IS NOT NULL
              )
            ORDER BY f.id_tenant, f.id DESC
            """,
            (ids,),
        )
        for row in cur.fetchall():
            efi[int(row[0])] = {
                "referencia": row[1] or "",
                "status": row[2] or "",
            }
        cur.execute("RELEASE SAVEPOINT sp_asf_efi")
    except Exception:
        _rollback_sp(cur, "sp_asf_efi")

    for item in ativas:
        tid = int(item["id_tenant"])
        eh_fund = fundador.get(tid, False)
        vinc = cupom_vinc.get(tid) or (None, None)
        cupom = cupons.get(int(vinc[0])) if vinc[0] else None
        partes = []
        item["eh_fundador"] = eh_fund
        if eh_fund:
            partes.append("Fornecedor Fundador")
        if cupom:
            desc = _rotulo_desconto_cupom(cupom)
            partes.append(f"Cupom {cupom['codigo']}" + (f" · {desc}" if desc else ""))
        item["beneficio"] = " · ".join(partes) if partes else "—"
        if eh_fund:
            item["beneficio_prazo"] = "Vitalício"
            cobrado = 0
        elif cupom:
            item["beneficio_prazo"] = _prazo_beneficio(cupom, vinc[1], item.get("periodicidade") or "mensal")
            preco = calcular_preco(
                int(item.get("catalogo_mensal_centavos") or 0),
                item.get("periodicidade") or "mensal",
                cupom=cupom,
            )
            cobrado = int(preco["valor_final_centavos"])
        else:
            item["beneficio_prazo"] = "—"
            cobrado = int(item.get("ciclo_centavos") or 0)
        item["cobrado_beneficio_centavos"] = cobrado
        item["cobrado_beneficio"] = _fmt_reais(cobrado)
        info = efi.get(tid)
        item["efi_gerada"] = bool(info)
        item["efi_rotulo"] = "Sim" if info else "Não"
        if info:
            ref = info["referencia"] or "fatura"
            st = info["status"] or ""
            item["efi_detalhe"] = f"{ref} · {st}" if st else ref
        else:
            item["efi_detalhe"] = ""


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
# Caixa / conciliação Efí = mês em que o dinheiro entrou (pago_em)
_SQL_MES_CAIXA = "date_trunc('month', f.pago_em)::date"
_SQL_CHARGE_REAL = (
    "NULLIF(TRIM(COALESCE(f.efi_charge_id, '')), '') IS NOT NULL "
    "AND COALESCE(f.valor_centavos, 0) > 0"
)


def _montar_conciliacao(cur, ano_sel: int, mes_sel: int) -> dict[str, Any]:
    """Espelho de cobranças Efí por data de pagamento (caixa), sem cortesia R$ 0."""
    mes_ref = date(ano_sel, mes_sel, 1)

    cur.execute(
        f"""
        SELECT
          COALESCE(SUM(f.valor_centavos), 0)::bigint,
          COUNT(*)::int,
          COALESCE(SUM(CASE WHEN f.status = 'pago' THEN f.valor_centavos ELSE 0 END), 0)::bigint,
          COUNT(*) FILTER (WHERE f.status = 'pago')::int,
          COALESCE(SUM(CASE WHEN f.status = 'bloqueado' THEN f.valor_centavos ELSE 0 END), 0)::bigint,
          COUNT(*) FILTER (WHERE f.status = 'bloqueado')::int
        FROM tbl_fatura f
        WHERE f.status IN ('pago', 'bloqueado')
          AND f.pago_em IS NOT NULL
          AND {_SQL_MES_CAIXA} = %s
          AND {_SQL_CHARGE_REAL}
        """,
        (mes_ref,),
    )
    row = cur.fetchone() or (0, 0, 0, 0, 0, 0)
    recebido_centavos = int(row[0] or 0)
    recebido_qtd = int(row[1] or 0)
    pago_centavos = int(row[2] or 0)
    pago_qtd = int(row[3] or 0)
    bloq_centavos = int(row[4] or 0)
    bloq_qtd = int(row[5] or 0)

    cur.execute(
        f"""
        SELECT
          f.id, f.id_tenant, t.nome, f.referencia, f.plano_slug, f.valor_centavos,
          f.status, f.forma_pagamento, f.pago_em, f.vencimento_em, f.efi_charge_id,
          t.tipo_negocio
        FROM tbl_fatura f
        JOIN tbl_tenant t ON t.id = f.id_tenant
        WHERE f.status IN ('pago', 'bloqueado')
          AND f.pago_em IS NOT NULL
          AND {_SQL_MES_CAIXA} = %s
          AND {_SQL_CHARGE_REAL}
        ORDER BY f.pago_em DESC, f.id DESC
        LIMIT 500
        """,
        (mes_ref,),
    )
    recebidos = []
    for r in cur.fetchall():
        st = (r[6] or "").strip().lower()
        forma = (r[7] or "").strip().lower()
        recebidos.append(
            {
                "id_fatura": int(r[0]),
                "id_tenant": int(r[1]),
                "nome": (r[2] or "").strip() or f"Tenant #{r[1]}",
                "referencia": r[3] or "",
                "plano": str(r[4] or ""),
                "plano_label": nome_plano_comercial(r[4], r[11]),
                "valor_centavos": int(r[5] or 0),
                "valor": _fmt_reais(r[5]),
                "status": st,
                "status_grupo": "bloqueado" if st == "bloqueado" else "pago",
                "status_label": "Bloqueado" if st == "bloqueado" else "Pago",
                "forma_pagamento": forma,
                "forma_label": FORMA_LABEL.get(forma, forma or "—"),
                "pago_em": _fmt_data(r[8]),
                "pago_br": _fmt_data_br(r[8]),
                "vencimento_br": _fmt_data_br(r[9]),
                "efi_charge_id": str(r[10] or ""),
            }
        )

    # Pendentes com charge real = possíveis buracos (paid na Efí ainda não baixado)
    cur.execute(
        f"""
        SELECT
          f.id, f.id_tenant, t.nome, f.referencia, f.plano_slug, f.valor_centavos,
          f.status, f.forma_pagamento, f.vencimento_em, f.efi_charge_id, t.tipo_negocio
        FROM tbl_fatura f
        JOIN tbl_tenant t ON t.id = f.id_tenant
        WHERE f.status IN ('pendente', 'vencido')
          AND {_SQL_CHARGE_REAL}
        ORDER BY f.vencimento_em ASC NULLS LAST, f.id ASC
        LIMIT 200
        """
    )
    divergencias = []
    for r in cur.fetchall():
        st = (r[6] or "").strip().lower()
        forma = (r[7] or "").strip().lower()
        divergencias.append(
            {
                "id_fatura": int(r[0]),
                "id_tenant": int(r[1]),
                "nome": (r[2] or "").strip() or f"Tenant #{r[1]}",
                "referencia": r[3] or "",
                "plano_label": nome_plano_comercial(r[4], r[10]),
                "valor_centavos": int(r[5] or 0),
                "valor": _fmt_reais(r[5]),
                "status": st,
                "status_label": "Vencida" if st == "vencido" else "Pendente",
                "forma_label": FORMA_LABEL.get(forma, forma or "—"),
                "vencimento_br": _fmt_data_br(r[8]),
                "efi_charge_id": str(r[9] or ""),
            }
        )

    # Série anual por caixa (pago_em)
    cur.execute(
        f"""
        SELECT
          {_SQL_MES_CAIXA} AS mes,
          COALESCE(SUM(f.valor_centavos), 0)::bigint AS total,
          COUNT(*)::int AS qtd
        FROM tbl_fatura f
        WHERE f.status IN ('pago', 'bloqueado')
          AND f.pago_em IS NOT NULL
          AND EXTRACT(YEAR FROM f.pago_em) = %s
          AND {_SQL_CHARGE_REAL}
        GROUP BY 1
        ORDER BY 1
        """,
        (ano_sel,),
    )
    mapa: dict[int, dict] = {}
    for r in cur.fetchall():
        mdate = r[0]
        if isinstance(mdate, date):
            mapa[mdate.month] = {
                "recebido_centavos": int(r[1] or 0),
                "qtd": int(r[2] or 0),
            }

    _MESES = (
        "Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
        "Jul", "Ago", "Set", "Out", "Nov", "Dez",
    )
    serie = []
    for m in range(1, 13):
        d = mapa.get(m) or {"recebido_centavos": 0, "qtd": 0}
        serie.append(
            {
                "mes": m,
                "mes_label": _MESES[m - 1],
                "recebido_centavos": d["recebido_centavos"],
                "recebido": _fmt_reais(d["recebido_centavos"]),
                "qtd": d["qtd"],
            }
        )

    return {
        "filtros": {
            "ano": ano_sel,
            "mes": mes_sel,
            "mes_label": f"{mes_sel:02d}/{ano_sel}",
            "criterio": "pago_em",
            "criterio_label": "Data de pagamento (caixa / Efí paid_at)",
        },
        "resumo": {
            "recebido_mes_centavos": recebido_centavos,
            "recebido_mes": _fmt_reais(recebido_centavos),
            "recebido_mes_qtd": recebido_qtd,
            "pago_mes_centavos": pago_centavos,
            "pago_mes": _fmt_reais(pago_centavos),
            "pago_mes_qtd": pago_qtd,
            "bloqueado_mes_centavos": bloq_centavos,
            "bloqueado_mes": _fmt_reais(bloq_centavos),
            "bloqueado_mes_qtd": bloq_qtd,
            "divergencias_qtd": len(divergencias),
            "divergencias_centavos": sum(int(x["valor_centavos"]) for x in divergencias),
            "divergencias": _fmt_reais(sum(int(x["valor_centavos"]) for x in divergencias)),
        },
        "recebidos_mes": recebidos,
        "divergencias": divergencias,
        "serie_ano": {
            "ano": ano_sel,
            "meses": serie,
            "recebido_ano_centavos": sum(x["recebido_centavos"] for x in serie),
            "recebido_ano": _fmt_reais(sum(x["recebido_centavos"] for x in serie)),
        },
    }


def painel_assinaturas(
    conn,
    *,
    ano: int | None = None,
    mes: int | None = None,
) -> dict[str, Any]:
    cur = conn.cursor()
    try:
        from sistema.financeiro.cobranca import garantir_colunas_assinatura

        cur.execute("SAVEPOINT sp_asf_cols")
        garantir_colunas_assinatura(cur)
        cur.execute("RELEASE SAVEPOINT sp_asf_cols")
    except Exception:
        _rollback_sp(cur, "sp_asf_cols")
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
          COALESCE(p.valor_centavos, 0), COALESCE(p.nome, t.plano),
          COALESCE(tc.efi_subscription_id, ''), COALESCE(tc.assinatura_status, '')
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
        plano = str(row[3] or "")
        forma = (row[8] or "").strip().lower()
        prox = _proxima_cobranca_estimada(row[7])
        efi_sub = str(row[12] or "").strip() if len(row) > 12 else ""
        efi_st = str(row[13] or "").strip() if len(row) > 13 else ""
        recorrencia_efi = bool(efi_sub) and efi_st != "cancelada"
        item = {
            "id_tenant": int(row[0]),
            "nome": (row[1] or "").strip() or f"Tenant #{row[0]}",
            "slug": row[2] or "",
            "plano": plano,
            "plano_label": nome_plano_comercial(plano, row[4]),
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
            "efi_subscription_id": efi_sub,
            "assinatura_status": efi_st,
            "recorrencia_efi": recorrencia_efi,
            "pode_criar_efi": not recorrencia_efi,
            "pode_cancelar": efi_st != "cancelada",
        }
        ativas.append(item)

    _enriquecer_beneficios(cur, ativas)

    mrr_total = 0
    ciclo_mes_estimado = 0
    for item in ativas:
        if item.get("eh_fundador"):
            item["mrr_centavos"] = 0
            item["mrr"] = _fmt_reais(0)
            item["ciclo_centavos"] = 0
            item["ciclo"] = _fmt_reais(0)
            item["cobrado_beneficio_centavos"] = 0
            item["cobrado_beneficio"] = _fmt_reais(0)
            item["proxima_cobranca"] = None
            item["proxima_cobranca_br"] = "—"
        mrr_total += int(item["mrr_centavos"])
        ciclo_mes_estimado += int(item["mrr_centavos"])
        plano = item["plano"]
        periodo = item["periodicidade"]
        meta_mrr = int(item["mrr_centavos"])
        bp = por_plano.setdefault(
            plano,
            {"plano": plano, "plano_label": item["plano_label"], "qtd": 0, "mrr_centavos": 0},
        )
        bp["qtd"] += 1
        bp["mrr_centavos"] += meta_mrr

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
        pp["mrr_centavos"] += meta_mrr

    for d in (por_plano, por_periodo):
        for v in d.values():
            v["mrr"] = _fmt_reais(v["mrr_centavos"])

    # ── Inadimplência: atraso (ainda em plano pago) ─────────────────────
    cur.execute(
        """
        SELECT DISTINCT ON (t.id)
          t.id, t.nome, t.slug, t.plano, t.tipo_negocio,
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
        valor = int(row[9] or 0)
        atraso_total += valor
        forma = (row[8] or "").strip().lower()
        periodo = _periodo_ok(row[13])
        em_atraso.append(
            {
                "id_tenant": int(row[0]),
                "nome": (row[1] or "").strip() or f"Tenant #{row[0]}",
                "slug": row[2] or "",
                "plano": row[3] or "",
                "plano_label": nome_plano_comercial(row[3], row[4]),
                "id_fatura": int(row[5]),
                "referencia": row[6] or "",
                "status": row[7] or "",
                "forma_pagamento": forma,
                "forma_label": FORMA_LABEL.get(forma, forma or "—"),
                "valor_centavos": valor,
                "valor": _fmt_reais(valor),
                "vencimento_em": _fmt_data(row[10]),
                "vencimento_br": _fmt_data_br(row[10]),
                "avisado_em": _fmt_data(row[11]),
                "periodicidade": periodo,
                "periodicidade_label": PERIODO_LABEL.get(periodo, periodo),
            }
        )

    # ── Rebaixados ao gratuito (histórico recente) ──────────────────────
    cur.execute(
        """
        SELECT
          t.id, t.nome, t.slug, t.plano, t.tipo_negocio,
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
        forma = (row[11] or "").strip().lower()
        tipo = row[4]
        plano_orig = str(row[9] or "")
        rebaixados.append(
            {
                "id_tenant": int(row[0]),
                "nome": (row[1] or "").strip() or f"Tenant #{row[0]}",
                "slug": row[2] or "",
                "plano_atual": row[3] or "",
                "plano_atual_label": nome_plano_comercial(row[3], tipo),
                "id_fatura": int(row[5]),
                "referencia": row[6] or "",
                "valor_centavos": int(row[7] or 0),
                "valor": _fmt_reais(row[7]),
                "rebaixado_em": _fmt_data(row[8]),
                "rebaixado_br": _fmt_data_br(row[8]),
                "plano_origem": plano_orig,
                "plano_origem_label": nome_plano_comercial(plano_orig, tipo),
                "status_fatura": row[10] or "",
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

    # Emitidas do mês de competência (todas: pagas, em aberto e canceladas)
    cur.execute(
        f"""
        SELECT
          f.id, f.id_tenant, t.nome, f.referencia, f.plano_slug, f.valor_centavos,
          f.status, f.forma_pagamento, f.vencimento_em, f.criado_em, f.pago_em,
          COALESCE(NULLIF(f.periodicidade, ''), 'mensal'), t.tipo_negocio
        FROM tbl_fatura f
        JOIN tbl_tenant t ON t.id = f.id_tenant
        WHERE f.status IN ('pendente', 'vencido', 'pago', 'cancelado', 'bloqueado')
          AND {_SQL_MES_COMPETENCIA} = %s
        ORDER BY f.vencimento_em ASC NULLS LAST, f.id ASC
        LIMIT 500
        """,
        (mes_ref,),
    )
    emitidas_mes = []
    for row in cur.fetchall():
        forma = (row[7] or "").strip().lower()
        periodo = _periodo_ok(row[11])
        plano = str(row[4] or "")
        st = (row[6] or "").strip().lower()
        if st == "pago":
            st_grupo = "pago"
            st_label = "Pago"
        elif st == "bloqueado":
            st_grupo = "bloqueado"
            st_label = "Bloqueado"
        elif st == "cancelado":
            st_grupo = "cancelado"
            st_label = "Cancelada"
        else:
            st_grupo = "aberto"
            st_label = "Em aberto" if st == "pendente" else "Vencida"
        emitidas_mes.append(
            {
                "id_fatura": int(row[0]),
                "id_tenant": int(row[1]),
                "nome": (row[2] or "").strip() or f"Tenant #{row[1]}",
                "referencia": row[3] or "",
                "plano": plano,
                "plano_label": nome_plano_comercial(plano, row[12] if len(row) > 12 else None),
                "valor_centavos": int(row[5] or 0),
                "valor": _fmt_reais(row[5]),
                "status": st,
                "status_grupo": st_grupo,
                "status_label": st_label,
                "forma_pagamento": forma,
                "forma_label": FORMA_LABEL.get(forma, forma or "—"),
                "vencimento_em": _fmt_data(row[8]),
                "vencimento_br": _fmt_data_br(row[8]),
                "criado_em": _fmt_data(row[9]),
                "criado_br": _fmt_data_br(row[9]),
                "pago_em": _fmt_data(row[10]),
                "pago_br": _fmt_data_br(row[10]),
                "periodicidade_label": PERIODO_LABEL.get(periodo, periodo),
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
          COALESCE(NULLIF(f.periodicidade, ''), 'mensal'), t.tipo_negocio
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
                "plano_label": nome_plano_comercial(plano, row[9] if len(row) > 9 else None),
                "valor_centavos": int(row[5] or 0),
                "valor": _fmt_reais(row[5]),
                "pago_em": _fmt_data(row[6]),
                "pago_br": _fmt_data_br(row[6]),
                "forma_label": FORMA_LABEL.get(forma, forma or "—"),
                "periodicidade_label": PERIODO_LABEL.get(periodo, periodo),
            }
        )

    _anexar_lembretes(cur, em_atraso)
    _anexar_lembretes(cur, emitidas_mes)

    canceladas: list[dict] = []
    try:
        cur.execute("SAVEPOINT sp_asf_cancel")
        cur.execute(
            """
            SELECT t.id,
                   COALESCE(NULLIF(t.nome_fantasia, ''), NULLIF(t.nome, ''), ''),
                   tc.plano_slug, tc.cancelado_em, tc.efi_subscription_id, t.tipo_negocio
            FROM tbl_tenant_cobranca tc
            JOIN tbl_tenant t ON t.id = tc.id_tenant
            WHERE tc.assinatura_status = 'cancelada'
            ORDER BY tc.cancelado_em DESC NULLS LAST
            LIMIT 80
            """
        )
        for row in cur.fetchall():
            canceladas.append(
                {
                    "id_tenant": int(row[0]),
                    "nome": (row[1] or "").strip() or f"Tenant #{row[0]}",
                    "plano_label": nome_plano_comercial(row[2], row[5]),
                    "cancelado_br": _fmt_data_br(row[3]),
                    "efi": "Sim" if row[4] else "Não",
                }
            )
        cur.execute("RELEASE SAVEPOINT sp_asf_cancel")
    except Exception:
        _rollback_sp(cur, "sp_asf_cancel")
        canceladas = []

    # ── Bloqueados (MED / pago contestado na Efí) ───────────────────────
    # Sync chama API externa: não usar SAVEPOINT em volta (DDL + rollback apagava colunas).
    sync_med: dict[str, Any] = {
        "ok": False,
        "message": "não sincronizado",
        "atualizados": 0,
        "abertos": 0,
        "infracoes_abertas": [],
        "bloqueio_med_centavos": 0,
        "bloqueio_total_centavos": 0,
        "saldo_centavos": 0,
    }
    try:
        from sistema.financeiro.med_bloqueios import garantir_colunas_med_fatura, sincronizar_bloqueios_med

        garantir_colunas_med_fatura(cur)
        sync_med = sincronizar_bloqueios_med(cur, dias=180) or sync_med
    except Exception as e:
        sync_med = {
            **sync_med,
            "ok": False,
            "message": str(e),
            "atualizados": 0,
            "abertos": 0,
            "infracoes_abertas": [],
        }

    bloqueados: list[dict] = []
    try:
        from sistema.financeiro.med_bloqueios import listar_faturas_bloqueadas, rotulo_med_status

        vistos_med: set[str] = set()
        vistos_fat: set[int] = set()
        for row in listar_faturas_bloqueadas(cur):
            forma = (row[7] or "").strip().lower()
            med_st = str(row[14] or "").strip().upper()
            med_id = str(row[13] or "").strip()
            if med_id:
                vistos_med.add(med_id)
            vistos_fat.add(int(row[0]))
            bloqueados.append(
                {
                    "id_fatura": int(row[0]),
                    "id_tenant": int(row[1]),
                    "nome": (row[2] or "").strip() or f"Tenant #{row[1]}",
                    "referencia": row[3] or "",
                    "plano": str(row[4] or ""),
                    "plano_label": nome_plano_comercial(row[4], row[17]),
                    "valor_centavos": int(row[5] or 0),
                    "valor": _fmt_reais(row[5]),
                    "status": (row[6] or "").strip().lower(),
                    "status_label": "Bloqueado",
                    "status_grupo": "bloqueado",
                    "forma_pagamento": forma,
                    "forma_label": FORMA_LABEL.get(forma, forma or "—"),
                    "vencimento_br": _fmt_data_br(row[8]),
                    "pago_br": _fmt_data_br(row[9]),
                    "criado_br": _fmt_data_br(row[10]),
                    "efi_txid": row[11] or "",
                    "efi_e2e": row[12] or "",
                    "med_id": med_id,
                    "protocolo": "",
                    "med_status": med_st,
                    "med_status_label": rotulo_med_status(med_st),
                    "med_razao": (row[15] or "").strip() or "—",
                    "med_atualizado_br": _fmt_data_br(row[16]),
                    "vinculado": True,
                    "origem": "fatura",
                }
            )

        # MEDs abertos na Efí sem fatura local (ou ainda não sincronizados na tbl)
        for med in sync_med.get("infracoes_abertas") or []:
            mid = str(med.get("med_id") or "").strip()
            fid = med.get("id_fatura")
            if mid and mid in vistos_med:
                continue
            if fid and int(fid) in vistos_fat:
                continue
            tid = med.get("id_tenant")
            nome = "Sem vínculo no DropNexo"
            plano_label = "—"
            if tid:
                cur.execute(
                    "SELECT nome, plano, tipo_negocio FROM tbl_tenant WHERE id = %s",
                    (int(tid),),
                )
                tr = cur.fetchone()
                if tr:
                    nome = (tr[0] or "").strip() or f"Tenant #{tid}"
                    plano_label = nome_plano_comercial(tr[1], tr[2])
            protocolo = str(med.get("protocolo") or "").strip()
            bloqueados.append(
                {
                    "id_fatura": int(fid) if fid else None,
                    "id_tenant": int(tid) if tid else None,
                    "nome": nome,
                    "referencia": f"MED {protocolo}" if protocolo else (mid[:12] or "MED"),
                    "plano": "",
                    "plano_label": plano_label,
                    "valor_centavos": int(med.get("valor_centavos") or 0),
                    "valor": _fmt_reais(med.get("valor_centavos")),
                    "status": "bloqueado",
                    "status_label": "Bloqueado",
                    "status_grupo": "bloqueado",
                    "forma_pagamento": "pix",
                    "forma_label": "Pix",
                    "vencimento_br": "—",
                    "pago_br": med.get("data_tx_br") or "—",
                    "criado_br": med.get("data_tx_br") or "—",
                    "efi_txid": med.get("efi_txid") or "",
                    "efi_e2e": med.get("efi_e2e") or "",
                    "med_id": mid,
                    "protocolo": protocolo,
                    "med_status": med.get("med_status") or "",
                    "med_status_label": med.get("med_status_label") or rotulo_med_status(med.get("med_status")),
                    "med_razao": med.get("med_razao") or "MED Pix",
                    "med_atualizado_br": med.get("data_tx_br") or "—",
                    "vinculado": bool(med.get("vinculado")),
                    "origem": "efi_med",
                }
            )
    except Exception as e:
        # Mantém o que veio da Efí mesmo se a query local falhar
        if not bloqueados:
            for med in sync_med.get("infracoes_abertas") or []:
                bloqueados.append(
                    {
                        "id_fatura": None,
                        "id_tenant": None,
                        "nome": "Sem vínculo no DropNexo",
                        "referencia": f"MED {med.get('protocolo') or med.get('med_id') or ''}".strip(),
                        "plano_label": "—",
                        "valor_centavos": int(med.get("valor_centavos") or 0),
                        "valor": _fmt_reais(med.get("valor_centavos")),
                        "status": "bloqueado",
                        "status_label": "Bloqueado",
                        "status_grupo": "bloqueado",
                        "forma_label": "Pix",
                        "pago_br": med.get("data_tx_br") or "—",
                        "med_id": med.get("med_id") or "",
                        "protocolo": str(med.get("protocolo") or ""),
                        "med_status": med.get("med_status") or "",
                        "med_status_label": med.get("med_status_label") or "Bloqueado",
                        "med_razao": med.get("med_razao") or "MED Pix",
                        "med_atualizado_br": med.get("data_tx_br") or "—",
                        "vinculado": False,
                        "origem": "efi_med",
                    }
                )
        sync_med["message"] = (
            (sync_med.get("message") or "") + f" | lista local: {e}"
        ).strip(" |")

    valor_bloq = sum(int(x["valor_centavos"]) for x in bloqueados)
    # Preferir total da Efí (saldo bloqueado) quando disponível
    valor_efi = int(sync_med.get("bloqueio_total_centavos") or 0)
    if valor_efi > valor_bloq:
        valor_bloq = valor_efi

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
            "canceladas": canceladas,
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
            "emitidas_mes": emitidas_mes,
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
        "conciliacao": _montar_conciliacao(cur, ano_sel, mes_sel),
        "bloqueados": {
            "resumo": {
                "qtd": len(bloqueados),
                "valor_centavos": valor_bloq,
                "valor": _fmt_reais(valor_bloq),
                "saldo_efi": _fmt_reais(sync_med.get("saldo_centavos")),
                "bloqueio_med_efi": _fmt_reais(sync_med.get("bloqueio_med_centavos")),
                "bloqueio_total_efi": _fmt_reais(sync_med.get("bloqueio_total_centavos")),
            },
            "itens": bloqueados,
            "sync": sync_med,
        },
    }
