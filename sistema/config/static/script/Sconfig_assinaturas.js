(function () {
  "use strict";

  const cfg = JSON.parse(document.getElementById("asf_cfg")?.textContent || "{}");
  let cache = null;
  let tabAtual = "ativas";
  const hoje = new Date();
  let filtroMes = hoje.getMonth() + 1;
  let filtroAno = hoje.getFullYear();
  let filtroAtivasBusca = "";
  let filtroFatBusca = "";
  let filtroFatStatus = "";

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

  function btnMenuFatura(a) {
    const pista = a.lembrete_rotulo
      ? `<div class="Asf_Muted">${esc(a.lembrete_rotulo)}</div>`
      : "";
    const grupo = String(a.status_grupo || a.status || "").toLowerCase();
    return `<div class="Asf_Acoes"><button type="button" class="Asf_MenuBtn" data-asf-menu="1" aria-label="Ações da cobrança" aria-haspopup="menu" title="Ações" data-id="${esc(a.id_fatura)}" data-tenant="${esc(a.id_tenant)}" data-nome="${esc(a.nome)}" data-ref="${esc(a.referencia || a.id_fatura)}" data-valor="${esc(a.valor)}" data-status-grupo="${esc(grupo)}">⋮</button>${pista}</div>`;
  }

  function btnMenuAtiva(a) {
    const efi = a.recorrencia_efi ? "1" : "0";
    const criar = a.pode_criar_efi ? "1" : "0";
    const cancelar = a.pode_cancelar !== false ? "1" : "0";
    return `<div class="Asf_Acoes"><button type="button" class="Asf_MenuBtn" data-asf-menu-ativa="1" aria-label="Ações da assinatura" aria-haspopup="menu" title="Ações" data-tenant="${esc(a.id_tenant)}" data-nome="${esc(a.nome)}" data-slug="${esc(a.slug || "")}" data-efi="${efi}" data-criar-efi="${criar}" data-cancelar="${cancelar}">⋮</button></div>`;
  }

  function badgeStatus(a) {
    const grupo = String(a.status_grupo || "").toLowerCase();
    const st = String(a.status || "").toLowerCase();
    let cls = "is-pendente";
    if (grupo === "pago" || st === "pago") cls = "is-pago";
    else if (grupo === "bloqueado" || st === "bloqueado") cls = "is-bloqueado";
    else if (grupo === "cancelado" || st === "cancelado") cls = "is-cancelado";
    else if (st === "vencido") cls = "is-vencido";
    return `<span class="Asf_Badge ${cls}">${esc(a.status_label || a.status || "—")}</span>`;
  }

  function preencherAnos() {
    const y0 = hoje.getFullYear();
    ["asf_ano", "asf_ano_cx"].forEach((id) => {
      const sel = el(id);
      if (!sel || sel.options.length) return;
      for (let y = y0 + 1; y >= y0 - 5; y--) {
        const opt = document.createElement("option");
        opt.value = String(y);
        opt.textContent = String(y);
        sel.appendChild(opt);
      }
      sel.value = String(filtroAno);
    });
    ["asf_mes", "asf_mes_cx"].forEach((id) => {
      const mes = el(id);
      if (mes) mes.value = String(filtroMes);
    });
  }

  function syncFiltroSelects() {
    ["asf_mes", "asf_mes_cx"].forEach((id) => {
      const n = el(id);
      if (n) n.value = String(filtroMes);
    });
    ["asf_ano", "asf_ano_cx"].forEach((id) => {
      const n = el(id);
      if (n) n.value = String(filtroAno);
    });
  }

  function lerFiltros() {
    const mesSrc =
      tabAtual === "conciliacao"
        ? el("asf_mes_cx")?.value || el("asf_mes")?.value
        : el("asf_mes")?.value || el("asf_mes_cx")?.value;
    const anoSrc =
      tabAtual === "conciliacao"
        ? el("asf_ano_cx")?.value || el("asf_ano")?.value
        : el("asf_ano")?.value || el("asf_ano_cx")?.value;
    filtroMes = parseInt(mesSrc || filtroMes, 10) || filtroMes;
    filtroAno = parseInt(anoSrc || filtroAno, 10) || filtroAno;
    syncFiltroSelects();
    filtroAtivasBusca = (el("asf_ativas_busca")?.value || "").trim().toLowerCase();
    filtroFatBusca = (el("asf_fat_busca")?.value || "").trim().toLowerCase();
    filtroFatStatus = (el("asf_fat_status")?.value || "").trim().toLowerCase();
  }

  function matchBusca(item, q) {
    if (!q) return true;
    const nome = String(item.nome || "").toLowerCase();
    const slug = String(item.slug || "").toLowerCase();
    const id = String(item.id_tenant || "");
    return nome.includes(q) || slug.includes(q) || id === q;
  }

  function renderAtivas(data) {
    const r = data?.resumo || {};
    el("asf_ativas_kpis").innerHTML = kpisHtml([
      { label: "Assinantes", value: String(r.qtd ?? 0) },
      { label: "MRR (provisão)", value: r.mrr || "R$ 0,00", cls: "is-ok" },
      { label: "ARR", value: r.arr || "R$ 0,00" },
      { label: "Provisão / mês", value: r.provisao_mensal || "R$ 0,00" },
    ]);
    const itens = (data?.itens || []).filter((a) => matchBusca(a, filtroAtivasBusca));
    const total = (data?.itens || []).length;
    el("asf_ativas_hint").textContent = total
      ? filtroAtivasBusca
        ? `${itens.length} de ${total} tenant(s)`
        : `${total} tenant(s) em plano pago`
      : "Nenhum assinante pago ativo";
    const tb = el("asf_ativas_tbody");
    if (!itens.length) {
      tb.innerHTML = emptyRow(
        9,
        filtroAtivasBusca ? "Nenhum tenant encontrado com essa busca." : "Nenhum tenant com plano pago ativo."
      );
    } else {
      tb.innerHTML = itens
        .map((a) => {
          const benef = a.beneficio && a.beneficio !== "—"
            ? `<div>${esc(a.beneficio)}</div>${a.beneficio_prazo && a.beneficio_prazo !== "—" ? `<div class="Asf_Muted">${esc(a.beneficio_prazo)}</div>` : ""}`
            : "—";
          const valor = a.cobrado_beneficio || a.ciclo || "—";
          const efiTag = a.recorrencia_efi
            ? `<div class="Asf_Muted">Efí · recorrente</div>`
            : `<div class="Asf_Muted">Sem Efí (legado)</div>`;
          return `<tr>
        <td><strong>${esc(a.nome)}</strong><div class="Asf_Muted">#${esc(a.id_tenant)} · ${esc(a.slug || "—")}</div>${efiTag}</td>
        <td>${esc(a.plano_label)}</td>
        <td>${esc(a.periodicidade_label)}</td>
        <td>${esc(a.forma_label)}</td>
        <td><strong>${esc(valor)}</strong></td>
        <td>${benef}</td>
        <td>${esc(a.inicio_cobranca_br || "—")}</td>
        <td>${esc(a.proxima_cobranca_br || "—")}</td>
        <td class="Asf_ColAcoes">${btnMenuAtiva(a)}</td>
      </tr>`;
        })
        .join("");
    }
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
          <td>${btnMenuFatura(a)}</td>
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

  function renderBloq(data) {
    const r = data?.resumo || {};
    const sync = data?.sync || {};
    const boxKpi = el("asf_bloq_kpis");
    if (boxKpi) {
      boxKpi.innerHTML = kpisHtml([
        { label: "Itens", value: String(r.qtd ?? 0), cls: "is-warn" },
        { label: "Bloqueado (lista)", value: r.valor || "R$ 0,00", cls: "is-danger" },
        { label: "MED na Efí", value: r.bloqueio_med_efi || "R$ 0,00", cls: "is-danger" },
        { label: "Saldo Efí", value: r.saldo_efi || "R$ 0,00" },
      ]);
    }
    const hint = el("asf_bloq_hint");
    const itens = data?.itens || [];
    if (hint) {
      hint.textContent = itens.length
        ? `${itens.length} bloqueio(s) — MED / saldo contestado`
        : "Nenhum bloqueio listado. Confira o sync abaixo.";
    }
    const syncEl = el("asf_bloq_sync");
    if (syncEl) {
      if (sync.ok) {
        syncEl.textContent = `Sync Efí: ${sync.total_med ?? 0} MED · ${sync.abertos ?? 0} aberto(s) · ${sync.atualizados ?? 0} fatura(s) · ${sync.sem_fatura ?? 0} sem vínculo. Bloqueio MED conta: ${r.bloqueio_med_efi || "R$ 0,00"}.`;
        syncEl.classList.remove("is-err");
      } else {
        syncEl.textContent = sync.message
          ? `Sync Efí falhou: ${sync.message}`
          : "Sync Efí falhou. Ative gn.infractions.read e gn.balance.read na aplicação Efí (API Pix) e atualize.";
        syncEl.classList.add("is-err");
      }
    }
    const tb = el("asf_bloq_tbody");
    if (!tb) return;
    if (!itens.length) {
      const extra =
        Number(sync.bloqueio_med_centavos || 0) > 0
          ? ` Há ${r.bloqueio_med_efi || "valor"} bloqueado na conta Efí, mas a API de infrações não trouxe itens (escopo ou período).`
          : "";
      tb.innerHTML = emptyRow(8, `Nenhum item. Ao atualizar consultamos a Efí.${extra}`);
      return;
    }
    tb.innerHTML = itens
      .map((a) => {
        const med = `<span class="Asf_Badge is-bloqueado">${esc(a.med_status_label || a.med_status || "Bloqueio")}</span>`;
        const proto = a.protocolo ? `<div class="Asf_Muted">Prot. ${esc(a.protocolo)}</div>` : "";
        const tenantId = a.id_tenant ? `#${esc(a.id_tenant)}` : "—";
        const vinculo = a.vinculado
          ? ""
          : `<div class="Asf_Muted">Só na Efí (sem fatura local)</div>`;
        const acoes = a.id_fatura
          ? btnMenuFatura({ ...a, status_grupo: "bloqueado", lembrete_rotulo: "" })
          : "—";
        return `<tr>
          <td><strong>${esc(a.nome)}</strong><div class="Asf_Muted">${tenantId}</div>${vinculo}</td>
          <td>${esc(a.plano_label || "—")}</td>
          <td>${esc(a.referencia || a.id_fatura || "—")}${proto}</td>
          <td><strong>${esc(a.valor)}</strong></td>
          <td>${esc(a.pago_br || "—")}</td>
          <td>${med}<div class="Asf_Muted">${esc(a.med_atualizado_br || "")}</div></td>
          <td>${esc(a.med_razao || "—")}</td>
          <td class="Asf_ColAcoes">${acoes}</td>
        </tr>`;
      })
      .join("");
  }

  function renderConciliacao(data) {
    const r = data?.resumo || {};
    const f = data?.filtros || {};
    if (f.mes) filtroMes = Number(f.mes);
    if (f.ano) filtroAno = Number(f.ano);
    syncFiltroSelects();

    const mesLbl = f.mes_label || `${String(filtroMes).padStart(2, "0")}/${filtroAno}`;
    const box = el("asf_cx_kpis");
    if (box) {
      box.innerHTML = kpisHtml([
        { label: `Recebido ${mesLbl}`, value: r.recebido_mes || "R$ 0,00", cls: "is-ok" },
        { label: `Pagos (qtd)`, value: String(r.pago_mes_qtd ?? 0), cls: "is-ok" },
        { label: `Bloqueado ${mesLbl}`, value: r.bloqueado_mes || "R$ 0,00", cls: "is-danger" },
        {
          label: "Pendentes c/ charge",
          value: `${r.divergencias_qtd ?? 0} · ${r.divergencias || "R$ 0,00"}`,
          cls: Number(r.divergencias_qtd || 0) > 0 ? "is-warn" : "",
        },
      ]);
    }

    const recebidos = data?.recebidos_mes || [];
    const hintR = el("asf_cx_recebidos_hint");
    if (hintR) {
      hintR.textContent = recebidos.length
        ? `${recebidos.length} charge(s) · ${r.recebido_mes || "R$ 0,00"} (só Efí, por data de pagamento)`
        : `Nenhum recebimento Efí em ${mesLbl}`;
    }
    const tbr = el("asf_cx_recebidos_tbody");
    if (tbr) {
      if (!recebidos.length) {
        tbr.innerHTML = emptyRow(7, "Nenhuma cobrança Efí paga neste mês de caixa.");
      } else {
        tbr.innerHTML = recebidos
          .map((a) => {
            return `<tr>
              <td><strong>${esc(a.pago_br)}</strong><div class="Asf_Muted">venc. ${esc(a.vencimento_br || "—")}</div></td>
              <td><strong>${esc(a.nome)}</strong><div class="Asf_Muted">#${esc(a.id_tenant)} · ${esc(a.referencia || a.id_fatura)}</div></td>
              <td><code>${esc(a.efi_charge_id)}</code></td>
              <td>${esc(a.forma_label)}</td>
              <td>${badgeStatus(a)}</td>
              <td><strong>${esc(a.valor)}</strong></td>
              <td class="Asf_ColAcoes">${btnMenuFatura({ ...a, lembrete_rotulo: "" })}</td>
            </tr>`;
          })
          .join("");
      }
    }

    const divs = data?.divergencias || [];
    const hintD = el("asf_cx_div_hint");
    if (hintD) {
      hintD.textContent = divs.length
        ? `${divs.length} charge(s) ainda pendente(s) no Drop — rode “Sincronizar com Efí”`
        : "Nenhuma pendência com charge Efí";
    }
    const tbd = el("asf_cx_div_tbody");
    if (tbd) {
      if (!divs.length) {
        tbd.innerHTML = emptyRow(7, "Nenhuma divergência potencial.");
      } else {
        tbd.innerHTML = divs
          .map((a) => {
            return `<tr>
              <td><strong>${esc(a.vencimento_br)}</strong></td>
              <td><strong>${esc(a.nome)}</strong><div class="Asf_Muted">#${esc(a.id_tenant)} · ${esc(a.referencia || a.id_fatura)}</div></td>
              <td><code>${esc(a.efi_charge_id)}</code></td>
              <td>${esc(a.forma_label)}</td>
              <td><span class="Asf_Badge is-pendente">${esc(a.status_label)}</span></td>
              <td><strong>${esc(a.valor)}</strong></td>
              <td class="Asf_ColAcoes">${btnMenuFatura({ ...a, status_grupo: "aberto", lembrete_rotulo: "" })}</td>
            </tr>`;
          })
          .join("");
      }
    }
  }

  function renderFat(data) {
    const r = data?.resumo || {};
    const f = data?.filtros || {};
    if (f.mes) filtroMes = Number(f.mes);
    if (f.ano) filtroAno = Number(f.ano);
    syncFiltroSelects();

    const mesLbl = f.mes_label || `${String(filtroMes).padStart(2, "0")}/${filtroAno}`;
    el("asf_fat_kpis").innerHTML = kpisHtml([
      { label: `Faturado ${mesLbl}`, value: r.faturado_mes || "R$ 0,00" },
      { label: `Pago ${mesLbl}`, value: r.pago_mes || "R$ 0,00", cls: "is-ok" },
      { label: `Em aberto ${mesLbl}`, value: r.aberto_mes || "R$ 0,00", cls: "is-warn" },
      { label: "Em aberto (total)", value: r.aberto_total || "R$ 0,00", cls: "is-danger" },
    ]);

    renderChart(data?.serie_ano);

    const todas = data?.emitidas_mes || [];
    const filtradas = todas.filter((a) => {
      if (!matchBusca(a, filtroFatBusca)) return false;
      if (!filtroFatStatus) return true;
      return String(a.status_grupo || "").toLowerCase() === filtroFatStatus;
    });
    const hint = el("asf_emitidas_hint");
    if (hint) {
      hint.textContent = todas.length
        ? filtroFatBusca || filtroFatStatus
          ? `${filtradas.length} de ${todas.length} emitida(s) em ${mesLbl}`
          : `${todas.length} emitida(s) em ${mesLbl}`
        : `Nenhuma cobrança emitida em ${mesLbl}`;
    }
    const tba = el("asf_emitidas_tbody");
    if (!tba) return;
    if (!filtradas.length) {
      tba.innerHTML = emptyRow(
        8,
        todas.length ? "Nenhuma cobrança com esses filtros." : "Nenhuma cobrança emitida neste mês."
      );
      return;
    }
    tba.innerHTML = filtradas
      .map((a) => {
        const grupo = String(a.status_grupo || "").toLowerCase();
        const menu = grupo === "aberto" ? btnMenuFatura(a) : btnMenuFatura({ ...a, lembrete_rotulo: "" });
        return `<tr>
          <td><strong>${esc(a.vencimento_br)}</strong><div class="Asf_Muted">emitida ${esc(a.criado_br || "—")}</div></td>
          <td><strong>${esc(a.nome)}</strong><div class="Asf_Muted">#${esc(a.id_tenant)}</div></td>
          <td>${esc(a.plano_label)}</td>
          <td>${esc(a.referencia || a.id_fatura)}</td>
          <td>${badgeStatus(a)}</td>
          <td>${esc(a.forma_label)}</td>
          <td><strong>${esc(a.valor)}</strong></td>
          <td class="Asf_ColAcoes">${menu}</td>
        </tr>`;
      })
      .join("");
  }

  function renderAll(j) {
    cache = j;
    lerFiltros();
    renderAtivas(j.ativas);
    renderInad(j.inadimplencia);
    renderBloq(j.bloqueados);
    renderConciliacao(j.conciliacao);
    renderFat(j.faturamento);
    setStatus(`Atualizado agora · mês ${filtroMes.toString().padStart(2, "0")}/${filtroAno}.`);
  }

  function rerenderLocal() {
    if (!cache) return;
    lerFiltros();
    renderAtivas(cache.ativas);
    renderConciliacao(cache.conciliacao);
    renderFat(cache.faturamento);
  }

  async function sincronizarEfi() {
    const btn = el("asf_btnSyncEfi");
    const syncEl = el("asf_cx_sync");
    if (btn) btn.disabled = true;
    if (syncEl) {
      syncEl.hidden = false;
      syncEl.textContent = "Consultando charges abertas na Efí…";
      syncEl.classList.remove("is-err");
    }
    setStatus("Sincronizando com Efí…");
    try {
      const resp = await fetch(cfg.apiSyncEfi, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "same-origin",
        body: "{}",
      });
      const j = await resp.json().catch(() => ({}));
      if (!resp.ok || !j.success) {
        throw new Error(j.message || "Falha no sync Efí");
      }
      const msg = `Sync: ${j.consultadas ?? 0} consultada(s) · ${j.alterados ?? 0} alterada(s) · ${j.pagos ?? 0} paga(s).`;
      if (syncEl) syncEl.textContent = msg;
      setStatus(msg);
      await carregar();
    } catch (e) {
      if (syncEl) {
        syncEl.textContent = e.message || String(e);
        syncEl.classList.add("is-err");
      }
      setStatus(e.message || String(e), true);
    } finally {
      if (btn) btn.disabled = false;
    }
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
  let menuTipo = null;
  let menuAbertoEm = 0;

  function fecharMenus() {
    ["asf_menu", "asf_menu_ativa"].forEach((id) => {
      const menu = el(id);
      if (menu) menu.hidden = true;
    });
    menuAlvo = null;
    menuTipo = null;
  }

  function posicionarMenu(menu, btn) {
    menu.hidden = false;
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

  function abrirMenuFatura(btn) {
    const menu = el("asf_menu");
    if (!menu) return;
    el("asf_menu_ativa") && (el("asf_menu_ativa").hidden = true);
    const grupo = String(btn.getAttribute("data-status-grupo") || "aberto").toLowerCase();
    const btnLembrete = menu.querySelector('[data-acao="lembrete"]');
    const btnCancelar = menu.querySelector('[data-acao="cancelar"]');
    if (btnLembrete) btnLembrete.hidden = grupo !== "aberto";
    if (btnCancelar) btnCancelar.hidden = grupo !== "aberto";
    // bloqueado / pago / cancelado: só detalhe
    menuAlvo = btn;
    menuTipo = "fatura";
    posicionarMenu(menu, btn);
  }

  function abrirMenuAtiva(btn) {
    const menu = el("asf_menu_ativa");
    if (!menu) return;
    el("asf_menu") && (el("asf_menu").hidden = true);
    const btnCriar = menu.querySelector('[data-acao-ativa="criar_efi"]');
    const btnCancelar = menu.querySelector('[data-acao-ativa="cancelar_assinatura"]');
    if (btnCriar) btnCriar.hidden = btn.getAttribute("data-criar-efi") !== "1";
    if (btnCancelar) btnCancelar.hidden = btn.getAttribute("data-cancelar") !== "1";
    menuAlvo = btn;
    menuTipo = "ativa";
    posicionarMenu(menu, btn);
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
    } finally {
      cancelando = false;
    }
  }

  function htmlDetalheTenant(t) {
    const fat = t.ultima_fatura || null;
    const fatHtml = fat
      ? `${esc(fat.referencia)} · ${esc(fat.status_label)} · ${esc(fat.valor)}`
      : "—";
    return `
      <dl class="Asf_Detalhe">
        ${linhaDetalhe("Tenant", `${t.nome || ""} #${t.id_tenant || ""}`)}
        ${linhaDetalhe("Slug", t.slug)}
        ${linhaDetalhe("Plano", t.plano_label)}
        ${linhaDetalhe("Ciclo", t.periodicidade_label)}
        ${linhaDetalhe("Forma", t.forma_label)}
        ${linhaDetalhe("E-mail cobrança", t.email_cobranca)}
        ${linhaDetalhe("Adesão", t.inicio_cobranca_br)}
        ${linhaDetalhe("Próx. cobrança", t.proxima_cobranca_br)}
        ${linhaDetalhe("Recorrência Efí", t.assinatura_status_label)}
        ${linhaDetalhe("Subscription Efí", t.efi_subscription_id || "—")}
        ${linhaDetalhe("Última fatura", fatHtml)}
      </dl>`;
  }

  async function verDetalheTenant(btn) {
    const idTenant = parseInt(btn.getAttribute("data-tenant") || "0", 10);
    if (!idTenant) return;
    const modal = el("asf_modal");
    const body = el("asf_modal_body");
    const titulo = el("asf_modal_titulo");
    if (!modal || !body) return;
    if (titulo) titulo.textContent = "Assinatura";
    body.innerHTML = `<p class="Asf_Hint">Carregando…</p>`;
    if (typeof modal.showModal === "function") modal.showModal();
    else modal.hidden = false;
    const url = new URL(`${cfg.apiTenant || ""}${idTenant}`, window.location.origin);
    const r = await fetch(url.toString(), { credentials: "include", headers: { Accept: "application/json" } });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Não foi possível abrir o detalhe.");
    const t = j.tenant || {};
    if (titulo) titulo.textContent = t.nome || `Tenant #${idTenant}`;
    body.innerHTML = htmlDetalheTenant(t);
  }

  async function criarAssinaturaEfi(btn) {
    const idTenant = parseInt(btn.getAttribute("data-tenant") || "0", 10);
    const nome = btn.getAttribute("data-nome") || "este tenant";
    if (!idTenant || !window.Swal) return;
    const c = await Swal.fire({
      title: "Criar assinatura na Efí?",
      html: `<p style="margin:0 0 8px"><strong>${esc(nome)}</strong></p><p style="margin:0">Gera a recorrência na Efí. A 1ª cobrança fica para o <strong>próximo ciclo</strong> (boleto) — o período já pago não é re-cobrado.</p><p style="margin:8px 0 0;color:#64748b;font-size:0.9rem">Se a forma for cartão, não dá para criar aqui (falta o token).</p>`,
      icon: "question",
      showCancelButton: true,
      confirmButtonText: "Criar na Efí",
      cancelButtonText: "Voltar",
      confirmButtonColor: "#021F81",
    });
    if (!c.isConfirmed) return;
    Swal.fire({ title: "Criando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    const r = await fetch(cfg.apiCriarEfi, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ id_tenant: idTenant }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Não foi possível criar a assinatura.");
    await Swal.fire({
      icon: "success",
      title: "Assinatura na Efí",
      text: j.message || j.mensagem || "Criada.",
      confirmButtonColor: "#021F81",
    });
    await carregar();
  }

  async function cancelarAssinaturaTenant(btn) {
    const idTenant = parseInt(btn.getAttribute("data-tenant") || "0", 10);
    const nome = btn.getAttribute("data-nome") || "este tenant";
    if (!idTenant || !window.Swal) return;
    const c = await Swal.fire({
      title: "Cancelar assinatura?",
      html: `<p style="margin:0 0 8px"><strong>${esc(nome)}</strong></p><p style="margin:0">Encerra a recorrência (Efí e local). O período já pago continua até o fim; depois a conta volta ao Explorar.</p>`,
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, cancelar",
      cancelButtonText: "Voltar",
      confirmButtonColor: "#E53935",
    });
    if (!c.isConfirmed) return;
    Swal.fire({ title: "Cancelando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    const r = await fetch(cfg.apiCancelarAssinatura, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ id_tenant: idTenant }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Não foi possível cancelar.");
    await Swal.fire({
      icon: "success",
      title: "Assinatura cancelada",
      text: j.message || "Cancelada.",
      confirmButtonColor: "#021F81",
    });
    await carregar();
  }

  function acaoAtiva(acao, btn) {
    const falha = (e) => {
      if (window.Swal) Swal.fire("Erro", e.message || "Não foi possível concluir.", "error");
    };
    if (acao === "detalhe") verDetalheTenant(btn).catch(falha);
    else if (acao === "criar_efi") criarAssinaturaEfi(btn).catch(falha);
    else if (acao === "cancelar_assinatura") cancelarAssinaturaTenant(btn).catch(falha);
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
      const menuBtnFat = ev.target.closest("[data-asf-menu]");
      if (menuBtnFat) {
        ev.stopPropagation();
        if (menuAlvo === menuBtnFat && menuTipo === "fatura" && el("asf_menu") && !el("asf_menu").hidden) {
          fecharMenus();
        } else {
          abrirMenuFatura(menuBtnFat);
        }
        return;
      }
      const menuBtnAtiva = ev.target.closest("[data-asf-menu-ativa]");
      if (menuBtnAtiva) {
        ev.stopPropagation();
        if (menuAlvo === menuBtnAtiva && menuTipo === "ativa" && el("asf_menu_ativa") && !el("asf_menu_ativa").hidden) {
          fecharMenus();
        } else {
          abrirMenuAtiva(menuBtnAtiva);
        }
        return;
      }
      const acaoFat = ev.target.closest("#asf_menu [data-acao]");
      if (acaoFat && menuAlvo && menuTipo === "fatura") {
        const alvo = menuAlvo;
        const acao = acaoFat.getAttribute("data-acao");
        fecharMenus();
        const falha = (e) => {
          if (window.Swal) Swal.fire("Erro", e.message || "Não foi possível concluir.", "error");
        };
        if (acao === "lembrete") enviarLembrete(alvo).catch(falha);
        else if (acao === "detalhe") verDetalhe(alvo).catch(falha);
        else if (acao === "cancelar") cancelarCobranca(alvo).catch(falha);
        return;
      }
      const acaoAt = ev.target.closest("#asf_menu_ativa [data-acao-ativa]");
      if (acaoAt && menuAlvo && menuTipo === "ativa") {
        const alvo = menuAlvo;
        const acao = acaoAt.getAttribute("data-acao-ativa");
        fecharMenus();
        acaoAtiva(acao, alvo);
        return;
      }
      if (!ev.target.closest("#asf_menu") && !ev.target.closest("#asf_menu_ativa")) fecharMenus();
    });
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") fecharMenus();
    });
    window.addEventListener(
      "scroll",
      () => {
        if (Date.now() - menuAbertoEm < 250) return;
        fecharMenus();
      },
      true
    );
    el("asf_mes")?.addEventListener("change", carregar);
    el("asf_ano")?.addEventListener("change", carregar);
    el("asf_mes_cx")?.addEventListener("change", carregar);
    el("asf_ano_cx")?.addEventListener("change", carregar);
    el("asf_btnSyncEfi")?.addEventListener("click", sincronizarEfi);
    el("asf_ativas_busca")?.addEventListener("input", () => {
      filtroAtivasBusca = (el("asf_ativas_busca")?.value || "").trim().toLowerCase();
      if (cache) renderAtivas(cache.ativas);
    });
    el("asf_fat_busca")?.addEventListener("input", () => {
      filtroFatBusca = (el("asf_fat_busca")?.value || "").trim().toLowerCase();
      if (cache) renderFat(cache.faturamento);
    });
    el("asf_fat_status")?.addEventListener("change", () => {
      filtroFatStatus = (el("asf_fat_status")?.value || "").trim().toLowerCase();
      if (cache) renderFat(cache.faturamento);
    });
    setTab("ativas");
    carregar();
  });
})();
