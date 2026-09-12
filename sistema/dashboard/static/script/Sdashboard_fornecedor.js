(function () {
  const root = document.getElementById("dash_fn");
  if (!root) return;

  const loading = document.getElementById("dash_fn_loading");
  const erro = document.getElementById("dash_fn_erro");
  const chartEl = document.getElementById("dash_fn_chart");
  const topVdEl = document.getElementById("dash_fn_top_vendedores");
  const topPrEl = document.getElementById("dash_fn_top_produtos");
  const fatTotEl = document.getElementById("dash_fn_fat_12m");

  const ICO = {
    bag:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 2L3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z"/><line x1="3" y1="6" x2="21" y2="6"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>',
    clock:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>',
    users:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M23 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></svg>',
    userPlus:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><line x1="20" y1="8" x2="20" y2="14"/><line x1="23" y1="11" x2="17" y2="11"/></svg>',
    box:
      '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M21 16V8a2 2 0 0 0-1-1.73l-7-4a2 2 0 0 0-2 0l-7 4A2 2 0 0 0 3 8v8a2 2 0 0 0 1 1.73l7 4a2 2 0 0 0 2 0l7-4A2 2 0 0 0 21 16z"/><polyline points="3.27 6.96 12 12.01 20.73 6.96"/><line x1="12" y1="22.08" x2="12" y2="12"/></svg>',
  };

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function setKpis(k) {
    const map = {
      pedidos_hoje: k.pedidos_hoje ?? 0,
      pedidos_aguardando: k.pedidos_aguardando ?? 0,
      vendedores_ativos: k.vendedores_ativos ?? 0,
      vendedores_aguardando: k.vendedores_aguardando ?? 0,
      produtos_total: k.produtos_total ?? 0,
      produtos_publicados: k.produtos_publicados ?? 0,
      produtos_pct: k.produtos_pct ?? 0,
    };
    Object.entries(map).forEach(([key, val]) => {
      const el = root.querySelector('[data-k="' + key + '"]');
      if (el) el.textContent = String(val);
    });
    const bar = root.querySelector("[data-bar-produtos]");
    if (bar) {
      requestAnimationFrame(() => {
        bar.style.width = Math.max(0, Math.min(100, Number(map.produtos_pct) || 0)) + "%";
      });
    }
    const kpiPedAg = root.querySelector('[data-kpi="pedidos_aguardando"]');
    if (kpiPedAg) kpiPedAg.classList.toggle("is-warn", Number(map.pedidos_aguardando) > 0);
    const kpiVdAg = root.querySelector('[data-kpi="vendedores_aguardando"]');
    if (kpiVdAg) kpiVdAg.classList.toggle("is-warn", Number(map.vendedores_aguardando) > 0);
    if (fatTotEl) fatTotEl.textContent = k.faturamento_12m_fmt || "R$ 0,00";
  }

  function renderChart(rows) {
    if (!chartEl) return;
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) {
      chartEl.innerHTML = '<p class="DashFn_Vazio">Sem faturamento no período.</p>';
      return;
    }
    chartEl.innerHTML = list
      .map((m) => {
        const pct = Math.max(0, Math.min(100, Number(m.pct) || 0));
        const empty = !m.valor;
        return (
          '<div class="DashFn_Col">' +
          '<div class="DashFn_ColBarWrap">' +
          '<div class="DashFn_ColBar' +
          (empty ? " is-empty" : "") +
          '" data-tip="' +
          esc(m.valor_fmt || "R$ 0,00") +
          '" style="height:0" data-h="' +
          (empty ? 4 : Math.max(8, pct)) +
          '%"></div>' +
          "</div>" +
          '<div class="DashFn_ColLbl">' +
          esc(m.rotulo || m.mes || "") +
          "</div>" +
          "</div>"
        );
      })
      .join("");

    requestAnimationFrame(() => {
      chartEl.querySelectorAll(".DashFn_ColBar").forEach((bar) => {
        const h = bar.getAttribute("data-h") || "4%";
        bar.style.height = h;
      });
    });
  }

  function renderRank(el, rows, mode) {
    if (!el) return;
    const list = Array.isArray(rows) ? rows : [];
    if (!list.length) {
      el.innerHTML =
        '<p class="DashFn_Vazio">' +
        (mode === "vd" ? "Nenhum vendedor com pedidos ainda." : "Nenhum produto vendido ainda.") +
        "</p>";
      return;
    }
    el.innerHTML = list
      .map((r, idx) => {
        const meta =
          mode === "vd"
            ? (r.pedidos || 0) + " pedido" + (r.pedidos === 1 ? "" : "s")
            : (r.quantidade || 0) + " un.";
        const val = mode === "vd" ? r.valor_fmt || "R$ 0,00" : r.valor_fmt || "R$ 0,00";
        const pct = Math.max(0, Math.min(100, Number(r.pct) || 0));
        return (
          '<article class="DashFn_Row' +
          (idx === 0 ? " is-top" : "") +
          '">' +
          '<div class="DashFn_Rank">' +
          esc(r.rank || idx + 1) +
          "</div>" +
          "<div>" +
          '<div class="DashFn_RowName" title="' +
          esc(r.nome || "") +
          '">' +
          esc(r.nome || "—") +
          '</div><div class="DashFn_RowMeta">' +
          esc(meta) +
          "</div></div>" +
          '<div class="DashFn_RowRight"><div class="DashFn_RowVal">' +
          esc(val) +
          "</div></div>" +
          '<div class="DashFn_RowTrack"><i data-w="' +
          pct +
          '"></i></div>' +
          "</article>"
        );
      })
      .join("");

    requestAnimationFrame(() => {
      el.querySelectorAll(".DashFn_RowTrack > i").forEach((bar) => {
        bar.style.width = (bar.getAttribute("data-w") || "0") + "%";
      });
    });
  }

  // ícones estáticos no HTML via data-ico
  root.querySelectorAll("[data-ico]").forEach((node) => {
    const key = node.getAttribute("data-ico");
    if (ICO[key]) node.innerHTML = ICO[key];
  });

  async function carregar() {
    try {
      const r = await fetch("/index/dados-fornecedor", { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao carregar.");
      const d = j.dados || {};
      setKpis(d.kpis || {});
      renderChart(d.faturamento_mensal || []);
      renderRank(topVdEl, d.top_vendedores || [], "vd");
      renderRank(topPrEl, d.top_produtos || [], "pr");
      if (loading) loading.hidden = true;
      root.removeAttribute("data-loading");
    } catch (e) {
      if (loading) loading.hidden = true;
      if (erro) {
        erro.hidden = false;
        erro.textContent = e.message || "Erro ao carregar o dashboard.";
      }
    }
  }

  carregar();
})();
