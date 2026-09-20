(function () {
  const BASE = "/configuracoes/manutencao-tenant";
  const TIPOS = ["vendedor", "fornecedor", "armazem"];
  const TIPO_LABEL = {
    vendedor: "Vendedor",
    fornecedor: "Fornecedor",
    armazem: "Armazém",
  };
  const CORES = {
    brand: "#021F81",
    on: "#059669",
    off: "#94a3b8",
    cancel: "#dc2626",
    pf: "#0ea5e9",
    cnpj: "#7c3aed",
    vendedor: "#2563eb",
    fornecedor: "#ea580c",
    armazem: "#16a34a",
    up: "#10b981",
    down: "#ef4444",
  };

  const el = {
    busca: document.getElementById("ob_filtroBusca"),
    tipo: document.getElementById("ob_filtroTipo"),
    ativo: document.getElementById("ob_filtroAtivo"),
    btnFiltrar: document.getElementById("ob_btnFiltrar"),
    btnLimpar: document.getElementById("ob_btnLimpar"),
    lista: document.getElementById("ob_listaTenants"),
    dash: document.getElementById("cfgmt_dash"),
    lead: document.getElementById("cfgmt_dash_lead"),
    btnRefresh: document.getElementById("cfgmt_btnRefresh"),
    weekPills: document.getElementById("cfgmt_week_pills"),
    weekBreakdown: document.getElementById("cfgmt_week_breakdown"),
    matrix: document.getElementById("cfgmt_matrix"),
  };
  if (!el.lista) return;

  const charts = {
    ativo: null,
    tipo: null,
    pessoa: null,
    semana: null,
  };

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function badgeTipo(t) {
    const x = (t || "vendedor").toLowerCase();
    return `<span class="CfgMt_Badge CfgMt_Badge--${esc(x)}">${esc(x)}</span>`;
  }

  function formatarDataHora(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) {
      const s = String(iso).replace("T", " ");
      return esc(s.length >= 16 ? s.slice(0, 16) : s);
    }
    const pad = (n) => String(n).padStart(2, "0");
    return (
      `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ` +
      `${pad(d.getHours())}:${pad(d.getMinutes())}`
    );
  }

  function pct(parte, total) {
    if (!total) return "0%";
    return `${Math.round((parte / total) * 1000) / 10}%`;
  }

  function animarNumero(node, alvo) {
    if (!node) return;
    const fim = Number(alvo) || 0;
    const inicio = Number(String(node.textContent).replace(/\D+/g, "")) || 0;
    if (inicio === fim) {
      node.textContent = String(fim);
      return;
    }
    const t0 = performance.now();
    const dur = 520;
    function tick(now) {
      const p = Math.min(1, (now - t0) / dur);
      const ease = 1 - Math.pow(1 - p, 3);
      node.textContent = String(Math.round(inicio + (fim - inicio) * ease));
      if (p < 1) requestAnimationFrame(tick);
    }
    requestAnimationFrame(tick);
  }

  function destruirChart(key) {
    if (charts[key]) {
      charts[key].destroy();
      charts[key] = null;
    }
  }

  function chartDefaults() {
    if (!window.Chart) return;
    Chart.defaults.font.family = "inherit";
    Chart.defaults.color = "#64748b";
    Chart.defaults.plugins.legend.labels.boxWidth = 12;
    Chart.defaults.plugins.legend.labels.usePointStyle = true;
  }

  function renderKpis(m) {
    const set = (key, val) => {
      const node = document.querySelector(`[data-kpi="${key}"]`);
      animarNumero(node, val);
    };
    set("total", m.total);
    set("ativos", m.ativos);
    set("inativos", m.inativos);
    set("encerramentos", m.encerramentos?.solicitados || 0);
    set("pf", m.pessoa?.pf || 0);
    set("cnpj", m.pessoa?.cnpj || 0);

    const hint = (k, txt) => {
      const n = document.querySelector(`[data-kpi-hint="${k}"]`);
      if (n) n.textContent = txt;
    };
    hint("ativos_pct", pct(m.ativos, m.total) + " da base");
    hint("inativos_pct", pct(m.inativos, m.total) + " da base");
    const enc = m.encerramentos || {};
    hint(
      "encerramentos",
      `${enc.em_andamento || 0} em andamento · ${enc.concluidos || 0} concluídos`
    );

    if (el.lead) {
      const semana = m.ultimos_7_dias?.resumo || {};
      el.lead.textContent =
        `${m.total} tenants · ${m.ativos} ativos · ${m.inativos} inativos · ` +
        `${enc.solicitados || 0} pediram encerramento · ` +
        `7 dias: +${semana.cadastros || 0} / −${semana.descadastros || 0}`;
    }
  }

  function renderMatrix(m) {
    if (!el.matrix) return;
    const por = m.por_tipo || {};
    const rows = [
      ["Total", (s) => s.total, "tenants"],
      ["Ativos", (s) => s.ativos, "ativos"],
      ["Inativos", (s) => s.inativos, "inativos"],
      ["PF", (s) => s.pf, "CPF"],
      ["CNPJ", (s) => s.cnpj, "CNPJ"],
      ["Encerr. solicitados", (s) => s.encerramentos_solicitados, "pedidos"],
      ["Encerr. concluídos", (s) => s.encerramentos_concluidos, "ok"],
    ];
    let html = `<div class="CfgMt_MatrixHead"></div>`;
    TIPOS.forEach((t) => {
      html += `<div class="CfgMt_MatrixHead">${esc(TIPO_LABEL[t])}</div>`;
    });
    rows.forEach(([label, getter, hint]) => {
      html += `<div class="CfgMt_MatrixLabel">${esc(label)}</div>`;
      TIPOS.forEach((t) => {
        const slot = por[t] || {};
        html += `<div class="CfgMt_MatrixCell CfgMt_MatrixCell--${t}">
          <strong>${getter(slot) || 0}</strong>
          <span>${esc(hint)}</span>
        </div>`;
      });
    });
    el.matrix.innerHTML = html;
  }

  function renderWeekMeta(m) {
    const resumo = m.ultimos_7_dias?.resumo || {};
    if (el.weekPills) {
      el.weekPills.innerHTML = `
        <span class="CfgMt_WeekPill CfgMt_WeekPill--up">Cadastros <strong>+${resumo.cadastros || 0}</strong></span>
        <span class="CfgMt_WeekPill CfgMt_WeekPill--down">Descadastros <strong>−${resumo.descadastros || 0}</strong></span>
        <span class="CfgMt_WeekPill">Saldo <strong>${(resumo.cadastros || 0) - (resumo.descadastros || 0)}</strong></span>
      `;
    }
    if (el.weekBreakdown) {
      const box = (titulo, mapa) => {
        const tags = TIPOS.map((t) => {
          const n = (mapa && mapa[t]) || 0;
          return `<span class="CfgMt_WeekTag">${esc(TIPO_LABEL[t])} <em>${n}</em></span>`;
        }).join("");
        return `<div class="CfgMt_WeekBox"><h5>${esc(titulo)}</h5><div class="CfgMt_WeekTags">${tags}</div></div>`;
      };
      el.weekBreakdown.innerHTML =
        box("Cadastros por tipo (7 dias)", resumo.cadastros_por_tipo) +
        box("Descadastros por tipo (7 dias)", resumo.descadastros_por_tipo);
    }
  }

  function renderCharts(m) {
    if (!window.Chart) return;
    chartDefaults();
    const por = m.por_tipo || {};

    destruirChart("ativo");
    charts.ativo = new Chart(document.getElementById("cfgmt_chart_ativo"), {
      type: "doughnut",
      data: {
        labels: ["Ativos", "Inativos"],
        datasets: [
          {
            data: [m.ativos || 0, m.inativos || 0],
            backgroundColor: [CORES.on, CORES.off],
            borderWidth: 0,
            hoverOffset: 6,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        cutout: "68%",
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const v = ctx.raw || 0;
                return ` ${ctx.label}: ${v} (${pct(v, m.total)})`;
              },
            },
          },
        },
      },
    });

    destruirChart("tipo");
    charts.tipo = new Chart(document.getElementById("cfgmt_chart_tipo"), {
      type: "bar",
      data: {
        labels: TIPOS.map((t) => TIPO_LABEL[t]),
        datasets: [
          {
            label: "Ativos",
            data: TIPOS.map((t) => por[t]?.ativos || 0),
            backgroundColor: CORES.on,
            borderRadius: 8,
            maxBarThickness: 34,
          },
          {
            label: "Inativos",
            data: TIPOS.map((t) => por[t]?.inativos || 0),
            backgroundColor: CORES.off,
            borderRadius: 8,
            maxBarThickness: 34,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { stacked: true, grid: { display: false } },
          y: { stacked: true, beginAtZero: true, ticks: { precision: 0 } },
        },
        plugins: { legend: { position: "bottom" } },
      },
    });

    destruirChart("pessoa");
    charts.pessoa = new Chart(document.getElementById("cfgmt_chart_pessoa"), {
      type: "bar",
      data: {
        labels: TIPOS.map((t) => TIPO_LABEL[t]),
        datasets: [
          {
            label: "PF",
            data: TIPOS.map((t) => por[t]?.pf || 0),
            backgroundColor: CORES.pf,
            borderRadius: 8,
            maxBarThickness: 28,
          },
          {
            label: "CNPJ",
            data: TIPOS.map((t) => por[t]?.cnpj || 0),
            backgroundColor: CORES.cnpj,
            borderRadius: 8,
            maxBarThickness: 28,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { grid: { display: false } },
          y: { beginAtZero: true, ticks: { precision: 0 } },
        },
        plugins: { legend: { position: "bottom" } },
      },
    });

    const semana = m.ultimos_7_dias || {};
    const labels = (semana.dias || []).map((d) => {
      const [y, mo, da] = String(d).split("-");
      return `${da}/${mo}`;
    });

    destruirChart("semana");
    charts.semana = new Chart(document.getElementById("cfgmt_chart_semana"), {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            label: "Cadastros",
            data: semana.cadastros || [],
            borderColor: CORES.up,
            backgroundColor: "rgba(16,185,129,0.12)",
            fill: true,
            tension: 0.35,
            pointRadius: 4,
            pointHoverRadius: 6,
          },
          {
            label: "Descadastros",
            data: semana.descadastros || [],
            borderColor: CORES.down,
            backgroundColor: "rgba(239,68,68,0.08)",
            fill: true,
            tension: 0.35,
            pointRadius: 4,
            pointHoverRadius: 6,
          },
          ...TIPOS.map((t) => ({
            label: `Cad. ${TIPO_LABEL[t]}`,
            data: (semana.cadastros_por_tipo && semana.cadastros_por_tipo[t]) || [],
            borderColor: CORES[t],
            borderDash: [5, 4],
            tension: 0.3,
            pointRadius: 0,
            borderWidth: 1.5,
            hidden: true,
          })),
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          x: { grid: { display: false } },
          y: { beginAtZero: true, ticks: { precision: 0 } },
        },
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              afterBody: (items) => {
                if (!items.length) return "";
                const i = items[0].dataIndex;
                const linhas = TIPOS.map((t) => {
                  const c = semana.cadastros_por_tipo?.[t]?.[i] || 0;
                  const d = semana.descadastros_por_tipo?.[t]?.[i] || 0;
                  return `${TIPO_LABEL[t]}: +${c} / −${d}`;
                });
                return ["", ...linhas];
              },
            },
          },
        },
      },
    });
  }

  async function carregarMetricas() {
    if (!el.dash) return;
    el.btnRefresh?.classList.add("is-loading");
    el.dash.classList.remove("is-error");
    try {
      const r = await fetch(`${BASE}/metricas`, { credentials: "same-origin" });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar métricas.");
      const m = j.metricas || {};
      renderKpis(m);
      renderMatrix(m);
      renderWeekMeta(m);
      renderCharts(m);
    } catch (e) {
      el.dash.classList.add("is-error");
      if (el.lead) el.lead.textContent = e.message || "Não foi possível carregar o panorama.";
    } finally {
      el.btnRefresh?.classList.remove("is-loading");
    }
  }

  function abrirApoio(id) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: `${BASE}/editar`,
      id: id || null,
      titulo: id ? `Editar tenant #${id}` : "Tenant",
      largura: 920,
      altura: 680,
      nivel: 1,
    });
  }

  async function carregar() {
    const qs = new URLSearchParams();
    const q = (el.busca?.value || "").trim();
    const tipo = (el.tipo?.value || "").trim();
    const ativo = (el.ativo?.value || "").trim();
    if (q) qs.set("q", q);
    if (tipo) qs.set("tipo", tipo);
    if (ativo !== "") qs.set("ativo", ativo);
    el.lista.innerHTML = `<tr><td colspan="9">Carregando…</td></tr>`;
    try {
      const r = await fetch(`${BASE}/dados?${qs}`, { credentials: "same-origin" });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao listar.");
      const itens = j.itens || [];
      if (!itens.length) {
        el.lista.innerHTML = `<tr><td colspan="9">Nenhum tenant encontrado.</td></tr>`;
        return;
      }
      const util = window.Util || { gerarIconeTech: () => "…" };
      el.lista.innerHTML = itens
        .map((t) => {
          const sessao = t.eh_tenant_sessao
            ? ' <span class="CfgMt_Badge CfgMt_Badge--sessao">sessão</span>'
            : "";
          const bloqueado = !!(t.eh_tenant_sessao || t.protegido);
          const titleExcluir = t.protegido
            ? "Tenant protegido"
            : t.eh_tenant_sessao
              ? "Não exclua o tenant da sessão atual"
              : "Excluir";
          const ehCnpj =
            String(t.tipo_pessoa || "").toUpperCase() === "J" ||
            String(t.documento || "").replace(/\D+/g, "").length === 14;
          const razao = ehCnpj ? esc(t.razao_social || "") || "—" : "—";
          return `
        <tr data-id="${t.id}">
          <td class="CfgMt_ColId">${t.id}</td>
          <td class="CfgMt_ColNome"><strong>${esc(t.nome)}</strong>${sessao}</td>
          <td class="CfgMt_ColRazao">${razao}</td>
          <td class="CfgMt_ColTipo">${badgeTipo(t.tipo_negocio)}</td>
          <td class="CfgMt_ColPlano">${esc(t.plano)}</td>
          <td class="CfgMt_ColAtivo">${t.ativo ? "Sim" : "Não"}</td>
          <td class="CfgMt_ColData">${formatarDataHora(t.criado_em)}</td>
          <td class="CfgMt_ColData">${formatarDataHora(t.dono_ultimo_acesso)}</td>
          <td class="Cl_TableActions CfgMt_ColAcoes">
            <button type="button" class="Cl_BtnAcao btnEditar" data-id="${t.id}" title="Editar">${util.gerarIconeTech("editar")}</button>
            <button type="button" class="Cl_BtnAcao btnExcluir" data-id="${t.id}" data-slug="${esc(t.slug)}" data-nome="${esc(t.nome)}" title="${titleExcluir}" ${bloqueado ? "disabled" : ""}>${util.gerarIconeTech("excluir")}</button>
          </td>
        </tr>`;
        })
        .join("");
      window.lucide?.createIcons?.();
      window.Util?.gerarIconeTech?.refresh?.();
    } catch (e) {
      el.lista.innerHTML = `<tr><td colspan="9">${esc(e.message)}</td></tr>`;
    }
  }

  async function excluir(id, slug, nome) {
    if (!id || !slug) return;
    const c1 = await Swal.fire({
      icon: "warning",
      title: "Excluir tenant permanentemente?",
      html:
        `Isso remove <strong>${esc(nome || slug)}</strong> (#${id}) e todos os dados ligados ` +
        `(produtos, pedidos, usuários, integrações, etc.).<br><br>` +
        `<small>Ação irreversível — use só para tenants de teste.</small>`,
      showCancelButton: true,
      confirmButtonText: "Continuar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
    });
    if (!c1.isConfirmed) return;

    const c2 = await Swal.fire({
      icon: "warning",
      title: "Confirme digitando o slug",
      html: `Digite <strong>${esc(slug)}</strong> para confirmar a exclusão.`,
      input: "text",
      inputPlaceholder: slug,
      showCancelButton: true,
      confirmButtonText: "Excluir de vez",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
      preConfirm: (v) => {
        if ((v || "").trim().toLowerCase() !== String(slug).toLowerCase()) {
          Swal.showValidationMessage("Slug não confere.");
          return false;
        }
        return (v || "").trim();
      },
    });
    if (!c2.isConfirmed) return;

    Swal.fire({
      title: "Excluindo…",
      text: "Removendo dados em cascata. Pode demorar alguns segundos.",
      allowOutsideClick: false,
      didOpen: () => Swal.showLoading(),
    });
    const r = await fetch(`${BASE}/excluir`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, confirm_slug: c2.value }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) {
      throw new Error(j.message || "Falha ao excluir.");
    }
    await Swal.fire({
      icon: "success",
      title: "Tenant excluído",
      text: j.message || "Concluído.",
      confirmButtonColor: "#021F81",
    });
    await Promise.all([carregar(), carregarMetricas()]);
  }

  el.btnFiltrar?.addEventListener("click", () => carregar());
  el.btnLimpar?.addEventListener("click", () => {
    if (el.busca) el.busca.value = "";
    if (el.tipo) el.tipo.value = "";
    if (el.ativo) el.ativo.value = "";
    carregar();
  });
  el.busca?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      carregar();
    }
  });
  el.btnRefresh?.addEventListener("click", () => carregarMetricas());
  el.lista.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button");
    if (!btn) return;
    const id = Number(btn.dataset.id || 0);
    if (!id) return;
    try {
      if (btn.classList.contains("btnEditar")) return abrirApoio(id);
      if (btn.classList.contains("btnExcluir")) {
        return await excluir(id, btn.dataset.slug || "", btn.dataset.nome || "");
      }
    } catch (e) {
      await Swal.fire("Erro", e.message, "error");
    }
  });

  window.addEventListener("message", (event) => {
    if (event.data?.grupo === "atualizarTabela") {
      Promise.all([carregar(), carregarMetricas()]).catch((e) =>
        Swal.fire("Erro", e.message, "error")
      );
    }
  });

  carregarMetricas();
  carregar();
})();
