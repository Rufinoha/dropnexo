(function () {
  "use strict";

  const cfg = JSON.parse(document.getElementById("asf_cfg")?.textContent || "{}");
  let cache = null;
  let tabAtual = "ativas";
  const hoje = new Date();
  let filtroMes = hoje.getMonth() + 1;
  let filtroAno = hoje.getFullYear();

  function el(id) {
    return document.getElementById(id);
  }

  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function setStatus(msg, err) {
    const n = el("asf_status");
    if (!n) return;
    n.textContent = msg || "";
    n.classList.toggle("is-err", !!err);
  }

  function setTab(tab) {
    tabAtual = tab || "ativas";
    document.querySelectorAll(".Asf_Tab").forEach((btn) => {
      const on = btn.getAttribute("data-tab") === tabAtual;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".Asf_Panel").forEach((pane) => {
      const on = pane.getAttribute("data-tab-panel") === tabAtual;
      pane.classList.toggle("is-active", on);
      pane.hidden = !on;
    });
  }

  function kpisHtml(items) {
    return (items || [])
      .map((k) => {
        const cls = k.cls ? ` Asf_Kpi ${k.cls}` : " Asf_Kpi";
        return `<div class="${cls.trim()}"><span>${esc(k.label)}</span><strong>${esc(k.value)}</strong></div>`;
      })
      .join("");
  }

  function emptyRow(cols, msg) {
    return `<tr><td colspan="${cols}" class="Asf_Empty">${esc(msg)}</td></tr>`;
  }

  function preencherAnos() {
    const sel = el("asf_ano");
    if (!sel || sel.options.length) return;
    const y0 = hoje.getFullYear();
    for (let y = y0 + 1; y >= y0 - 5; y--) {
      const opt = document.createElement("option");
      opt.value = String(y);
      opt.textContent = String(y);
      sel.appendChild(opt);
    }
    sel.value = String(filtroAno);
    const mes = el("asf_mes");
    if (mes) mes.value = String(filtroMes);
  }

  function lerFiltros() {
    filtroMes = parseInt(el("asf_mes")?.value || filtroMes, 10) || filtroMes;
    filtroAno = parseInt(el("asf_ano")?.value || filtroAno, 10) || filtroAno;
  }

  function renderAtivas(data) {
    const r = data?.resumo || {};
    el("asf_ativas_kpis").innerHTML = kpisHtml([
      { label: "Assinantes", value: String(r.qtd ?? 0) },
      { label: "MRR (provisão)", value: r.mrr || "R$ 0,00", cls: "is-ok" },
      { label: "ARR", value: r.arr || "R$ 0,00" },
      { label: "Provisão / mês", value: r.provisao_mensal || "R$ 0,00" },
    ]);
    const itens = data?.itens || [];
    el("asf_ativas_hint").textContent = itens.length
      ? `${itens.length} tenant(s) em plano pago`
      : "Nenhum assinante pago ativo";
    const tb = el("asf_ativas_tbody");
    if (!itens.length) {
      tb.innerHTML = emptyRow(7, "Nenhum tenant com plano pago ativo.");
      return;
    }
    tb.innerHTML = itens
      .map(
        (a) => `<tr>
        <td><strong>${esc(a.nome)}</strong><div class="Asf_Muted">#${esc(a.id_tenant)} · ${esc(a.slug || "—")}</div></td>
        <td>${esc(a.plano_label)}</td>
        <td>${esc(a.periodicidade_label)}</td>
        <td>${esc(a.forma_label)}</td>
        <td><strong>${esc(a.mrr)}</strong></td>
        <td>${esc(a.ciclo)}</td>
        <td>${esc(a.proxima_cobranca_br || "—")}</td>
      </tr>`
      )
      .join("");
  }

  function renderInad(data) {
    const r = data?.resumo || {};
    el("asf_inad_kpis").innerHTML = kpisHtml([
      { label: "Em atraso", value: String(r.qtd_atraso ?? 0), cls: "is-danger" },
      { label: "Valor em atraso", value: r.valor_atraso || "R$ 0,00", cls: "is-warn" },
      { label: "Rebaixamentos", value: String(r.qtd_rebaixados ?? 0) },
      { label: "Ainda no Starter", value: String(r.qtd_ainda_starter ?? 0) },
    ]);

    const atraso = data?.em_atraso || [];
    el("asf_atraso_hint").textContent = atraso.length
      ? `${atraso.length} com fatura vencida/pendente`
      : "Nenhum em atraso";
    const tba = el("asf_atraso_tbody");
    if (!atraso.length) {
      tba.innerHTML = emptyRow(7, "Nenhuma assinatura paga em atraso.");
    } else {
      tba.innerHTML = atraso
        .map((a) => {
          const st = String(a.status || "").toLowerCase();
          const badge = st === "vencido" ? "is-vencido" : "is-pendente";
          return `<tr>
          <td><strong>${esc(a.nome)}</strong><div class="Asf_Muted">#${esc(a.id_tenant)}</div></td>
          <td>${esc(a.plano_label)}</td>
          <td>${esc(a.referencia || a.id_fatura)}</td>
          <td><span class="Asf_Badge ${badge}">${esc(a.status)}</span></td>
          <td>${esc(a.vencimento_br)}</td>
          <td><strong>${esc(a.valor)}</strong></td>
          <td>${esc(a.forma_label)}</td>
        </tr>`;
        })
        .join("");
    }

    const rebaix = data?.rebaixados || [];
    el("asf_rebaix_hint").textContent = rebaix.length
      ? `${rebaix.length} registro(s) · ${r.qtd_ainda_starter || 0} ainda no Starter`
      : "Nenhum rebaixamento registrado";
    const tbr = el("asf_rebaix_tbody");
    if (!rebaix.length) {
      tbr.innerHTML = emptyRow(6, "Nenhum rebaixamento por inadimplência.");
      return;
    }
    tbr.innerHTML = rebaix
      .map((a) => {
        const atual = a.ainda_starter
          ? `<span class="Asf_Badge is-starter">${esc(a.plano_atual_label)}</span>`
          : esc(a.plano_atual_label);
        return `<tr>
        <td><strong>${esc(a.nome)}</strong><div class="Asf_Muted">#${esc(a.id_tenant)}</div></td>
        <td>${atual}</td>
        <td>${esc(a.plano_origem_label)}</td>
        <td>${esc(a.rebaixado_br)}</td>
        <td>${esc(a.referencia || a.id_fatura)}</td>
        <td>${esc(a.valor)}</td>
      </tr>`;
      })
      .join("");
  }

  function renderChart(serie) {
    const box = el("asf_chart");
    if (!box) return;
    const meses = serie?.meses || [];
    const ano = serie?.ano || filtroAno;
    el("asf_graf_ano").textContent = String(ano);
    el("asf_graf_hint").textContent = `Ano ${ano} · ${serie?.faturado_ano || "R$ 0,00"} faturado · ${serie?.pago_ano || "R$ 0,00"} pago`;

    let max = 0;
    meses.forEach((m) => {
      max = Math.max(max, Number(m.faturado_centavos || 0), Number(m.pago_centavos || 0));
    });
    if (max <= 0) max = 1;

    box.innerHTML = meses
      .map((m) => {
        const fat = Number(m.faturado_centavos || 0);
        const pago = Number(m.pago_centavos || 0);
        const hFat = Math.round((fat / max) * 100);
        const hPago = Math.round((pago / max) * 100);
        const on = Number(m.mes) === filtroMes ? " is-sel" : "";
        return `<button type="button" class="Asf_BarGroup${on}" data-mes="${esc(m.mes)}" title="${esc(m.mes_label)}: faturado ${esc(m.faturado)} · pago ${esc(m.pago)}">
          <div class="Asf_Bars">
            <div class="Asf_Bar Asf_Bar--fat" style="height:${hFat}%"></div>
            <div class="Asf_Bar Asf_Bar--pago" style="height:${hPago}%"></div>
          </div>
          <span class="Asf_BarLabel">${esc(m.mes_label)}</span>
        </button>`;
      })
      .join("");

    box.querySelectorAll(".Asf_BarGroup").forEach((btn) => {
      btn.addEventListener("click", () => {
        const m = parseInt(btn.getAttribute("data-mes") || "0", 10);
        if (!m) return;
        const mesSel = el("asf_mes");
        if (mesSel) mesSel.value = String(m);
        carregar();
      });
    });
  }

  function renderFat(data) {
    const r = data?.resumo || {};
    const f = data?.filtros || {};
    if (f.mes) {
      filtroMes = Number(f.mes);
      const mesSel = el("asf_mes");
      if (mesSel) mesSel.value = String(filtroMes);
    }
    if (f.ano) {
      filtroAno = Number(f.ano);
      const anoSel = el("asf_ano");
      if (anoSel) anoSel.value = String(filtroAno);
    }

    const mesLbl = f.mes_label || `${String(filtroMes).padStart(2, "0")}/${filtroAno}`;
    el("asf_fat_kpis").innerHTML = kpisHtml([
      { label: `Faturado ${mesLbl}`, value: r.faturado_mes || "R$ 0,00" },
      { label: `Pago ${mesLbl}`, value: r.pago_mes || "R$ 0,00", cls: "is-ok" },
      { label: `Em aberto ${mesLbl}`, value: r.aberto_mes || "R$ 0,00", cls: "is-warn" },
      { label: "Em aberto (total)", value: r.aberto_total || "R$ 0,00", cls: "is-danger" },
    ]);

    renderChart(data?.serie_ano);

    const abertos = data?.em_aberto || [];
    const noMes = abertos.filter((a) => a.no_mes_selecionado).length;
    el("asf_aberto_hint").textContent = abertos.length
      ? `${abertos.length} em aberto · ${noMes} com vencimento em ${mesLbl}`
      : "Nenhuma cobrança em aberto";
    const tba = el("asf_aberto_tbody");
    if (!abertos.length) {
      tba.innerHTML = emptyRow(7, "Nenhuma fatura emitida/vencida em aberto.");
    } else {
      tba.innerHTML = abertos
        .map((a) => {
          const st = String(a.status || "").toLowerCase();
          const badge = st === "vencido" ? "is-vencido" : "is-pendente";
          const rowCls = a.no_mes_selecionado ? ' class="is-mes"' : "";
          return `<tr${rowCls}>
          <td><strong>${esc(a.vencimento_br)}</strong><div class="Asf_Muted">emitida ${esc(a.criado_br || "—")}</div></td>
          <td><strong>${esc(a.nome)}</strong><div class="Asf_Muted">#${esc(a.id_tenant)}</div></td>
          <td>${esc(a.plano_label)}</td>
          <td>${esc(a.referencia || a.id_fatura)}</td>
          <td><span class="Asf_Badge ${badge}">${esc(a.status_label || a.status)}</span></td>
          <td>${esc(a.forma_label)}</td>
          <td><strong>${esc(a.valor)}</strong></td>
        </tr>`;
        })
        .join("");
    }

    const pagos = data?.pagos_recentes || [];
    const tbp = el("asf_pagos_tbody");
    if (!pagos.length) {
      tbp.innerHTML = emptyRow(5, "Nenhum pagamento recente.");
      return;
    }
    tbp.innerHTML = pagos
      .map(
        (p) => `<tr>
        <td>${esc(p.pago_br)}</td>
        <td><strong>${esc(p.nome)}</strong><div class="Asf_Muted">#${esc(p.id_tenant)}</div></td>
        <td>${esc(p.plano_label)}</td>
        <td>${esc(p.periodicidade_label)}</td>
        <td><strong>${esc(p.valor)}</strong></td>
      </tr>`
      )
      .join("");
  }

  function renderAll(j) {
    cache = j;
    renderAtivas(j.ativas);
    renderInad(j.inadimplencia);
    renderFat(j.faturamento);
    setStatus(`Atualizado agora · competência ${filtroMes.toString().padStart(2, "0")}/${filtroAno}.`);
  }

  async function carregar() {
    setStatus("Carregando…");
    lerFiltros();
    try {
      const url = new URL(cfg.apiDados || "/configuracoes/assinaturas-faturamento/dados", window.location.origin);
      url.searchParams.set("ano", String(filtroAno));
      url.searchParams.set("mes", String(filtroMes));
      const r = await fetch(url.toString(), {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) {
        throw new Error(j.message || `Falha ao carregar (${r.status}).`);
      }
      renderAll(j);
    } catch (e) {
      setStatus(e.message || "Erro ao carregar.", true);
      if (window.Swal) Swal.fire("Erro", e.message || "Falha ao carregar painel.", "error");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    preencherAnos();
    document.querySelectorAll(".Asf_Tab").forEach((btn) => {
      btn.addEventListener("click", () => setTab(btn.getAttribute("data-tab")));
    });
    el("asf_btnAtualizar")?.addEventListener("click", carregar);
    el("asf_mes")?.addEventListener("change", carregar);
    el("asf_ano")?.addEventListener("change", carregar);
    setTab("ativas");
    carregar();
  });
})();
