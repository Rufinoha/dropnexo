(function () {
  "use strict";

  const cfg = JSON.parse(document.getElementById("asf_cfg")?.textContent || "{}");
  let cache = null;
  let tabAtual = "ativas";

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
      tb.innerHTML = `<tr><td colspan="7" class="Asf_Hint">Nenhum tenant com plano pago ativo.</td></tr>`;
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
      tba.innerHTML = `<tr><td colspan="7" class="Asf_Hint">Nenhuma assinatura paga em atraso.</td></tr>`;
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
      tbr.innerHTML = `<tr><td colspan="6" class="Asf_Hint">Nenhum rebaixamento por inadimplência.</td></tr>`;
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

  function renderFat(data) {
    const r = data?.resumo || {};
    el("asf_fat_kpis").innerHTML = kpisHtml([
      { label: "Pago neste mês", value: r.pago_mes || "R$ 0,00", cls: "is-ok" },
      { label: "Faturas no mês", value: String(r.pago_mes_qtd ?? 0) },
      { label: "Meses com dados", value: String(r.meses_com_dados ?? 0) },
    ]);

    const meses = data?.meses || [];
    const tbm = el("asf_meses_tbody");
    if (!meses.length) {
      tbm.innerHTML = `<tr><td colspan="3" class="Asf_Hint">Nenhum pagamento registrado.</td></tr>`;
    } else {
      tbm.innerHTML = meses
        .map(
          (m) => `<tr>
          <td><strong>${esc(m.mes_label)}</strong></td>
          <td>${esc(m.qtd)}</td>
          <td><strong>${esc(m.total)}</strong></td>
        </tr>`
        )
        .join("");
    }

    const pagos = data?.pagos_recentes || [];
    const tbp = el("asf_pagos_tbody");
    if (!pagos.length) {
      tbp.innerHTML = `<tr><td colspan="5" class="Asf_Hint">Nenhum pagamento recente.</td></tr>`;
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
    setStatus("Atualizado agora.");
  }

  async function carregar() {
    setStatus("Carregando…");
    try {
      const r = await fetch(cfg.apiDados || "/configuracoes/assinaturas-faturamento/dados", {
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
    document.querySelectorAll(".Asf_Tab").forEach((btn) => {
      btn.addEventListener("click", () => setTab(btn.getAttribute("data-tab")));
    });
    el("asf_btnAtualizar")?.addEventListener("click", carregar);
    setTab("ativas");
    carregar();
  });
})();
