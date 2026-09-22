(function () {
  const root = document.getElementById("dash_vd");
  if (!root) return;

  const loading = document.getElementById("dash_vd_loading");
  const erro = document.getElementById("dash_vd_erro");
  const alertasWrap = document.getElementById("dash_vd_alertas_wrap");
  const alertasEl = document.getElementById("dash_vd_alertas");
  const okEl = document.getElementById("dash_vd_ok");
  const CORES = ["#021f81", "#c6a15b", "#0f766e", "#7c3aed", "#e11d48", "#64748b"];

  let dias = 7;

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function renderAlertas(list) {
    if (!alertasEl || !alertasWrap || !okEl) return;
    if (!list.length) {
      alertasWrap.hidden = true;
      alertasEl.innerHTML = "";
      okEl.hidden = false;
      return;
    }
    okEl.hidden = true;
    alertasWrap.hidden = false;
    alertasEl.innerHTML = list
      .map((a) => {
        const nivel = a.nivel || "baixa";
        return (
          '<article class="DashVd_Alerta is-' + esc(nivel) + '">' +
          "<div><p class=\"DashVd_AlertaTitulo\">" + esc(a.titulo) +
          "</p><p class=\"DashVd_AlertaTexto\">" + esc(a.texto) + "</p></div>" +
          (a.url ? '<a href="' + esc(a.url) + '">' + esc(a.cta || "Abrir") + "</a>" : "") +
          "</article>"
        );
      })
      .join("");
  }

  function textoDelta(k) {
    const el = document.getElementById("dash_vd_delta");
    if (!el) return;
    el.className = "";
    const base = dias === 1 ? "ontem" : "os " + dias + " dias anteriores";
    if (k.delta_pct == null) {
      el.textContent = (k.vendido || 0) > 0 ? "Primeira venda neste recorte" : "Nada vendido neste recorte";
      return;
    }
    const n = Number(k.delta_pct);
    const sinal = n > 0 ? "+" : "";
    el.textContent = sinal + String(n).replace(".", ",") + "% em relação a " + base;
    el.classList.add(n > 0 ? "is-up" : n < 0 ? "is-down" : "");
  }

  function renderKpis(k, rotulo) {
    const vendido = document.getElementById("dash_vd_vendido");
    const custo = document.getElementById("dash_vd_custo");
    const margem = document.getElementById("dash_vd_margem");
    const pct = document.getElementById("dash_vd_margem_pct");
    const pedidos = document.getElementById("dash_vd_pedidos");
    const titulo = document.getElementById("dash_vd_rotulo");
    if (titulo) titulo.textContent = rotulo || "Últimos 7 dias";
    if (vendido) vendido.textContent = k.vendido_fmt || "R$ 0,00";
    if (custo) custo.textContent = k.custo_fmt || "R$ 0,00";
    if (margem) {
      margem.textContent = k.margem_fmt || "R$ 0,00";
      margem.classList.toggle("is-down", (k.margem || 0) < 0);
      margem.classList.toggle("is-up", (k.margem || 0) > 0);
    }
    if (pct) {
      pct.textContent = k.margem_pct == null
        ? "Sem venda no recorte"
        : String(k.margem_pct).replace(".", ",") + "% sobre o vendido";
    }
    if (pedidos) pedidos.textContent = String(k.pedidos ?? 0);
    textoDelta(k);
    const rodape = document.getElementById("dash_vd_rodape");
    if (rodape) {
      const prod = k.produtos_ativos ?? 0;
      const forn = k.fornecedores_ativos ?? 0;
      rodape.textContent =
        prod + (prod === 1 ? " produto ativo" : " produtos ativos") +
        " · " +
        forn + (forn === 1 ? " fornecedor na rede" : " fornecedores na rede");
    }
  }

  function renderChart(serie) {
    const box = document.getElementById("dash_vd_chart");
    if (!box) return;
    const rows = serie || [];
    if (!rows.length) {
      box.innerHTML = '<p class="DashVd_Vazio">Sem dias neste recorte.</p>';
      return;
    }
    const max = Math.max(...rows.map((d) => Number(d.vendido) || 0), 0);
    const muitos = rows.length > 10;
    box.innerHTML = rows
      .map((d, i) => {
        const valor = Number(d.vendido) || 0;
        const h = max > 0 ? Math.max(4, Math.round((valor / max) * 132)) : 4;
        const zero = valor <= 0;
        const mostrar =
          d.hoje || !muitos || i === 0 || i === rows.length - 1 || d.dia_num === 1 || d.dia_num % 5 === 0;
        const label = mostrar ? String(d.dia_num).padStart(2, "0") : "";
        const cls = "DashVd_Bar" + (d.hoje ? " is-hoje" : "") + (zero ? " is-zero" : "");
        return (
          '<button type="button" class="' + cls + '" style="--h:' + h + 'px">' +
          '<span class="DashVd_Tip"><b>' + esc(d.vendido_fmt) + "</b>" +
          "<span>" + esc(d.pedidos) + (d.pedidos === 1 ? " pedido" : " pedidos") + "</span>" +
          "<span>Margem " + esc(d.margem_fmt) + "</span></span>" +
          "<i></i><small>" + esc(label) + "</small></button>"
        );
      })
      .join("");
  }

  function renderOrigens(rows) {
    const box = document.getElementById("dash_vd_origens");
    if (!box) return;
    if (!rows.length) {
      box.innerHTML = '<p class="DashVd_Vazio">Nenhuma venda neste recorte.</p>';
      return;
    }
    const barra = rows
      .map((o, i) => {
        const cor = CORES[i % CORES.length];
        return '<i style="width:' + Math.max(o.pct || 0, 2) + "%;background:" + cor + '"></i>';
      })
      .join("");
    const lista = rows
      .map((o, i) => {
        const cor = CORES[i % CORES.length];
        return (
          '<div class="DashVd_Origem"><span class="DashVd_Dot" style="background:' + cor + '"></span>' +
          "<div><strong>" + esc(o.label) + "</strong> <small>" + esc(o.pedidos) +
          (o.pedidos === 1 ? " pedido" : " pedidos") + "</small></div>" +
          "<em>" + esc(o.vendido_fmt) + "</em></div>"
        );
      })
      .join("");
    box.innerHTML = '<div class="DashVd_Stack">' + barra + "</div>" + lista;
  }

  function renderTop(rows) {
    const box = document.getElementById("dash_vd_top");
    if (!box) return;
    if (!rows.length) {
      box.innerHTML = '<p class="DashVd_Vazio">Nenhum produto vendido neste recorte.</p>';
      return;
    }
    box.innerHTML =
      '<ol class="DashVd_Top">' +
      rows
        .map((p, i) => {
          const down = (p.margem || 0) < 0 ? " is-down" : "";
          const pct = p.margem_pct == null ? "" : String(p.margem_pct).replace(".", ",") + "%";
          const sku = p.sku ? esc(p.sku) + " · " : "";
          return (
            "<li><span class=\"DashVd_Rank\">" + (i + 1) + "</span><div>" +
            '<span class="DashVd_TopNome">' + esc(p.nome) + "</span>" +
            '<span class="DashVd_TopMeta">' + sku + esc(p.quantidade) + " un. · " + esc(p.vendido_fmt) + "</span>" +
            "</div><div class=\"DashVd_TopMargem" + down + "\">" + esc(p.margem_fmt) +
            (pct ? "<small>" + esc(pct) + "</small>" : "") + "</div></li>"
          );
        })
        .join("") +
      "</ol>";
  }

  async function carregar() {
    try {
      if (erro) erro.hidden = true;
      const r = await fetch("/index/dados-vendedor?dias=" + dias, { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao carregar.");
      const d = j.dados || {};
      renderKpis(d.kpis || {}, d.rotulo);
      renderChart(d.serie || []);
      renderOrigens(d.origens || []);
      renderTop(d.top_produtos || []);
      renderAlertas(d.alertas || []);
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

  root.querySelectorAll(".DashVd_Chips button").forEach((btn) => {
    btn.addEventListener("click", () => {
      dias = Number(btn.getAttribute("data-dias")) || 7;
      root.querySelectorAll(".DashVd_Chips button").forEach((b) => {
        const on = b === btn;
        b.classList.toggle("is-on", on);
        b.setAttribute("aria-selected", on ? "true" : "false");
      });
      carregar();
    });
  });

  carregar();
})();
