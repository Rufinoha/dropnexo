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

  function btnMenu(a) {
    const pista = a.lembrete_rotulo
      ? `<div class="Asf_Muted">${esc(a.lembrete_rotulo)}</div>`
      : "";
    return `<div class="Asf_Acoes"><button type="button" class="Asf_MenuBtn" data-asf-menu="1" aria-label="Ações da cobrança" aria-haspopup="menu" data-id="${esc(a.id_fatura)}" data-tenant="${esc(a.id_tenant)}" data-nome="${esc(a.nome)}" data-ref="${esc(a.referencia || a.id_fatura)}" data-valor="${esc(a.valor)}"><i></i><i></i><i></i></button>${pista}</div>`;
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
      tb.innerHTML = emptyRow(11, "Nenhum tenant com plano pago ativo.");
    } else tb.innerHTML = itens
      .map(
        (a) => `<tr>
        <td><strong>${esc(a.nome)}</strong><div class="Asf_Muted">#${esc(a.id_tenant)} · ${esc(a.slug || "—")}</div></td>
        <td>${esc(a.plano_label)}</td>
        <td>${esc(a.periodicidade_label)}</td>
        <td>${esc(a.forma_label)}</td>
        <td><strong>${esc(a.mrr)}</strong></td>
        <td>${esc(a.ciclo)}</td>
        <td>${esc(a.beneficio || "—")}</td>
        <td>${esc(a.beneficio_prazo || "—")}</td>
        <td><strong>${esc(a.cobrado_beneficio || a.ciclo)}</strong></td>
        <td>${esc(a.efi_rotulo || "Não")}${a.efi_detalhe ? `<div class="Asf_Muted">${esc(a.efi_detalhe)}</div>` : ""}</td>
        <td>${esc(a.proxima_cobranca_br || "—")}</td>
      </tr>`
      )
      .join("");
    const canceladas = data?.canceladas || [];
    const tbc = el("asf_cancel_tbody");
    const hint = el("asf_cancel_hint");
    if (hint) {
      hint.textContent = canceladas.length
        ? `${canceladas.length} assinatura(s) cancelada(s)`
        : "Nenhum cancelamento registrado";
    }
    if (tbc) {
      tbc.innerHTML = canceladas.length
        ? canceladas
            .map(
              (a) => `<tr>
        <td><strong>${esc(a.nome)}</strong><div class="Asf_Muted">#${esc(a.id_tenant)}</div></td>
        <td>${esc(a.plano_label)}</td>
        <td>${esc(a.cancelado_br || "—")}</td>
        <td>${esc(a.efi || "—")}</td>
      </tr>`
            )
            .join("")
        : emptyRow(4, "Nenhum cancelamento de plano.");
    }
  }

  function renderInad(data) {
    const r = data?.resumo || {};
    el("asf_inad_kpis").innerHTML = kpisHtml([
      { label: "Em atraso", value: String(r.qtd_atraso ?? 0), cls: "is-danger" },
      { label: "Valor em atraso", value: r.valor_atraso || "R$ 0,00", cls: "is-warn" },
      { label: "Rebaixamentos", value: String(r.qtd_rebaixados ?? 0) },
      { label: "Ainda no Explorar", value: String(r.qtd_ainda_starter ?? 0) },
    ]);

    const atraso = data?.em_atraso || [];
    el("asf_atraso_hint").textContent = atraso.length
      ? `${atraso.length} com fatura vencida/pendente`
      : "Nenhum em atraso";
    const tba = el("asf_atraso_tbody");
    if (!atraso.length) {
      tba.innerHTML = emptyRow(8, "Nenhuma assinatura paga em atraso.");
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
          <td>${btnMenu(a)}</td>
        </tr>`;
        })
        .join("");
    }

    const rebaix = data?.rebaixados || [];
    el("asf_rebaix_hint").textContent = rebaix.length
      ? `${rebaix.length} registro(s) · ${r.qtd_ainda_starter || 0} ainda no Explorar`
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
      tba.innerHTML = emptyRow(8, "Nenhuma fatura emitida/vencida em aberto.");
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
          <td>${btnMenu(a)}</td>
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

  let cancelando = false;
  let menuAlvo = null;
  let menuAbertoEm = 0;

  function fecharMenu() {
    const menu = el("asf_menu");
    if (!menu) return;
    menu.hidden = true;
    menuAlvo = null;
  }

  function abrirMenu(btn) {
    const menu = el("asf_menu");
    if (!menu) return;
    menu.hidden = false;
    menuAlvo = btn;
    menuAbertoEm = Date.now();
    const rect = btn.getBoundingClientRect();
    const largura = menu.offsetWidth || 196;
    const altura = menu.offsetHeight || 140;
    let left = rect.right - largura;
    let top = rect.bottom + 6;
    if (left < 8) left = 8;
    if (left + largura > window.innerWidth - 8) left = window.innerWidth - largura - 8;
    if (top + altura > window.innerHeight - 8) top = Math.max(8, rect.top - altura - 6);
    menu.style.top = `${top}px`;
    menu.style.left = `${left}px`;
  }

  function linhaDetalhe(rotulo, valor) {
    if (!valor) return "";
    return `<dt>${esc(rotulo)}</dt><dd>${esc(valor)}</dd>`;
  }

  function htmlDetalhe(f) {
    const lembretes = f.lembretes || [];
    const hist = lembretes.length
      ? lembretes
          .map((l) => {
            const evs = (l.eventos || [])
              .map((ev) => `<div class="Asf_Evento">${esc(ev.quando)} · ${esc(ev.tipo)}</div>`)
              .join("");
            return `<article class="Asf_Lembrete"><strong>${esc(l.enviado_em)} · ${esc(l.status)}</strong><div class="Asf_Muted">${esc(l.email)}</div>${evs}</article>`;
          })
          .join("")
      : `<p class="Asf_Hint">Nenhum lembrete enviado ainda.</p>`;
    const boleto = f.link_boleto
      ? `<p><a class="Cl_BtnLink" href="${esc(f.link_boleto)}" target="_blank" rel="noopener">Abrir boleto</a></p>`
      : "";
    const barras = f.codigo_barras ? `<p class="Asf_Codigo">${esc(f.codigo_barras)}</p>` : "";
    const pix = f.pix_copia_cola ? `<p class="Asf_Codigo">${esc(f.pix_copia_cola)}</p>` : "";
    const pago = f.link_pagamento && !f.link_boleto
      ? `<p><a class="Cl_BtnLink" href="${esc(f.link_pagamento)}" target="_blank" rel="noopener">Link de pagamento</a></p>`
      : "";
    return `
      <dl class="Asf_Detalhe">
        ${linhaDetalhe("Tenant", `${f.nome || ""} #${f.id_tenant || ""}`)}
        ${linhaDetalhe("Plano", f.plano_label)}
        ${linhaDetalhe("Ciclo", f.periodicidade)}
        ${linhaDetalhe("Fatura", f.referencia)}
        ${linhaDetalhe("Status", f.status_label)}
        ${linhaDetalhe("Valor", f.valor)}
        ${linhaDetalhe("Valor cheio", f.valor_cheio)}
        ${linhaDetalhe("Desconto do ciclo", f.desconto_periodo)}
        ${linhaDetalhe("Desconto do cupom", f.desconto_cupom ? `${f.desconto_cupom}${f.cupom_codigo ? ` · ${f.cupom_codigo}` : ""}` : "")}
        ${linhaDetalhe("Vencimento", f.vencimento)}
        ${linhaDetalhe("Emitida em", f.criado_em)}
        ${linhaDetalhe("Paga em", f.pago_em)}
        ${linhaDetalhe("Forma", f.forma_label)}
        ${linhaDetalhe("Cobrança na Efí", f.efi)}
      </dl>
      <div class="Asf_Bloco">
        <h4>Pagamento</h4>
        ${boleto || barras || pix || pago || `<p class="Asf_Hint">Sem link ou código de pagamento nesta fatura.</p>`}
        ${boleto && barras ? barras : ""}
        ${pix && (boleto || barras) ? pix : ""}
      </div>
      <div class="Asf_Bloco">
        <h4>Lembretes</h4>
        <p class="Asf_Hint">O status (entregue, aberto, clique) chega pelo Brevo.</p>
        ${hist}
      </div>`;
  }

  async function verDetalhe(btn) {
    const id = parseInt(btn.getAttribute("data-id") || "0", 10);
    const idTenant = parseInt(btn.getAttribute("data-tenant") || "0", 10);
    if (!id) return;
    const modal = el("asf_modal");
    const body = el("asf_modal_body");
    const titulo = el("asf_modal_titulo");
    if (!modal || !body) return;
    if (titulo) titulo.textContent = "Cobrança";
    body.innerHTML = `<p class="Asf_Hint">Carregando…</p>`;
    if (typeof modal.showModal === "function") modal.showModal();
    else modal.hidden = false;
    const url = new URL(`${cfg.apiDetalhe || ""}${id}`, window.location.origin);
    if (idTenant) url.searchParams.set("id_tenant", String(idTenant));
    const r = await fetch(url.toString(), { credentials: "include", headers: { Accept: "application/json" } });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Não foi possível abrir o detalhe.");
    const f = j.fatura || {};
    if (titulo) titulo.textContent = `Fatura ${f.referencia || id}`;
    body.innerHTML = htmlDetalhe(f);
  }

  async function enviarLembrete(btn) {
    const id = parseInt(btn.getAttribute("data-id") || "0", 10);
    const idTenant = parseInt(btn.getAttribute("data-tenant") || "0", 10);
    const nome = btn.getAttribute("data-nome") || "esta conta";
    const ref = btn.getAttribute("data-ref") || String(id);
    const valor = btn.getAttribute("data-valor") || "";
    if (!id || !window.Swal) return;
    const c = await Swal.fire({
      title: "Enviar lembrete?",
      html: `<p style="margin:0 0 8px"><strong>${esc(nome)}</strong></p><p style="margin:0">Fatura ${esc(ref)}${valor ? ` · ${esc(valor)}` : ""}</p><p style="margin:8px 0 0">O e-mail vai para o contato de cobrança e fica registrado, com abertura pelo Brevo.</p>`,
      icon: "question",
      showCancelButton: true,
      confirmButtonText: "Enviar lembrete",
      cancelButtonText: "Voltar",
      confirmButtonColor: "#021F81",
    });
    if (!c.isConfirmed) return;
    Swal.fire({ title: "Enviando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    const r = await fetch(cfg.apiLembrete, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ id_fatura: id, id_tenant: idTenant }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Não foi possível enviar o lembrete.");
    await Swal.fire({
      icon: "success",
      title: "Lembrete enviado",
      text: j.message || "Enviado.",
      confirmButtonColor: "#021F81",
    });
    await carregar();
  }

  async function cancelarCobranca(btn) {
    if (cancelando) return;
    const id = parseInt(btn.getAttribute("data-id") || "0", 10);
    const idTenant = parseInt(btn.getAttribute("data-tenant") || "0", 10);
    const nome = btn.getAttribute("data-nome") || "este tenant";
    const ref = btn.getAttribute("data-ref") || String(id);
    const valor = btn.getAttribute("data-valor") || "";
    if (!id || !window.Swal) return;
    const c = await Swal.fire({
      title: "Cancelar esta cobrança?",
      html: `<p style="margin:0 0 8px"><strong>${esc(nome)}</strong></p><p style="margin:0">Fatura ${esc(ref)}${valor ? ` · ${esc(valor)}` : ""}</p><p style="margin:8px 0 0">Sai desta lista e é cancelada na Efí. O plano do tenant permanece.</p>`,
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, cancelar cobrança",
      cancelButtonText: "Voltar",
      confirmButtonColor: "#E53935",
    });
    if (!c.isConfirmed) return;
    cancelando = true;
    document.querySelectorAll("[data-asf-cancelar]").forEach((b) => {
      b.disabled = true;
    });
    Swal.fire({ title: "Cancelando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
      const r = await fetch(cfg.apiCancelar, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ id_fatura: id, id_tenant: idTenant }),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.message || "Não foi possível cancelar a cobrança.");
      await Swal.fire({ icon: "success", title: "Cobrança cancelada", text: j.message || "Cancelada.", confirmButtonColor: "#021F81" });
      await carregar();
    } catch (e) {
      document.querySelectorAll("[data-asf-cancelar]").forEach((b) => {
        b.disabled = false;
      });
      throw e;
    } finally {
      cancelando = false;
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    preencherAnos();
    document.querySelectorAll(".Asf_Tab").forEach((btn) => {
      btn.addEventListener("click", () => setTab(btn.getAttribute("data-tab")));
    });
    el("asf_btnAtualizar")?.addEventListener("click", carregar);
    el("asf_modal_fechar")?.addEventListener("click", () => el("asf_modal")?.close());
    el("asf_modal")?.addEventListener("click", (ev) => {
      if (ev.target === el("asf_modal")) el("asf_modal").close();
    });
    document.addEventListener("click", (ev) => {
      const menuBtn = ev.target.closest("[data-asf-menu]");
      if (menuBtn) {
        ev.stopPropagation();
        if (menuAlvo === menuBtn && el("asf_menu") && !el("asf_menu").hidden) fecharMenu();
        else abrirMenu(menuBtn);
        return;
      }
      const acaoBtn = ev.target.closest("#asf_menu [data-acao]");
      if (acaoBtn && menuAlvo) {
        const alvo = menuAlvo;
        const acao = acaoBtn.getAttribute("data-acao");
        fecharMenu();
        const falha = (e) => {
          if (window.Swal) Swal.fire("Erro", e.message || "Não foi possível concluir.", "error");
        };
        if (acao === "lembrete") enviarLembrete(alvo).catch(falha);
        else if (acao === "detalhe") verDetalhe(alvo).catch(falha);
        else if (acao === "cancelar") cancelarCobranca(alvo).catch(falha);
        return;
      }
      if (!ev.target.closest("#asf_menu")) fecharMenu();
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") fecharMenu();
    });
    window.addEventListener(
      "scroll",
      () => {
        if (Date.now() - menuAbertoEm < 250) return;
        fecharMenu();
      },
      true
    );
    el("asf_mes")?.addEventListener("change", carregar);
    el("asf_ano")?.addEventListener("change", carregar);
    setTab("ativas");
    carregar();
  });
})();
