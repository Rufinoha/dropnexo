(function () {
  const pills = document.getElementById("fn_seg_pills");
  const grid = document.getElementById("fn_seg_grid");
  const vazio = document.getElementById("fn_seg_vazio");
  const URL_CATEGORIAS = window.FN_SEG_URL_CATEGORIAS || "/fornecedor/categorias";

  const BASE = "/fornecedor/segmentos";

  function renderChart(categorias) {
    if (!categorias || !categorias.length) {
      return '<p class="FnSeg_ChartEmpty">Sem categorias nível 1 — abra Categorias para montar a árvore.</p>';
    }
    const max = Math.max(...categorias.map((c) => c.qtd_produtos), 1);
    return categorias
      .slice(0, 8)
      .map((c) => {
        const pct = Math.round((c.qtd_produtos / max) * 100);
        return `
        <div class="FnSeg_BarRow">
          <span class="FnSeg_BarLabel" title="${escapeAttr(c.nome)}">${escapeHtml(c.nome)}</span>
          <div class="FnSeg_BarTrack"><div class="FnSeg_BarFill" style="width:${pct}%"></div></div>
          <span class="FnSeg_BarQtd">${c.qtd_produtos}</span>
        </div>`;
      })
      .join("");
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replace(/"/g, "&quot;");
  }

  function renderPills(disponiveis) {
    pills.innerHTML = disponiveis
      .map(
        (s) => `
      <button type="button" class="FnSeg_Pill${s.selecionado ? " is-on" : ""}" data-id="${s.id}" data-on="${s.selecionado ? "1" : "0"}">
        ${escapeHtml(s.nome)}
      </button>`
      )
      .join("");
  }

  function renderGrid(ativos) {
    if (!ativos || !ativos.length) {
      grid.innerHTML = "";
      vazio.hidden = false;
      return;
    }
    vazio.hidden = true;
    grid.innerHTML = ativos
      .map(
        (s) => `
      <article class="FnSeg_Card" data-id="${s.id}" tabindex="0" role="link">
        <h4 class="FnSeg_CardNome">${escapeHtml(s.nome)}</h4>
        <div class="FnSeg_CardStats">
          <span><strong>${s.qtd_categorias}</strong>categorias</span>
          <span><strong>${s.qtd_produtos}</strong>produtos</span>
        </div>
        <div class="FnSeg_Chart">${renderChart(s.categorias)}</div>
        <p class="FnSeg_CardHint">Clique para abrir a árvore de categorias</p>
      </article>`
      )
      .join("");
  }

  async function carregar() {
    const r = await fetch(BASE + "/dados", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    renderPills(j.disponiveis || []);
    renderGrid(j.ativos || []);
  }

  async function toggleSegmento(id, ativar) {
    const r = await fetch(BASE + "/toggle", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_segmento: id, ativo: ativar }),
    });
    const j = await r.json();
    if (!j.success) {
      if (window.Util && Util.alertar) await Util.alertar(j.message, "error");
      else await Swal.fire("Erro", j.message, "error");
    }
    carregar();
  }

  function irCategorias(idSegmento) {
    const u = new URL(URL_CATEGORIAS, window.location.origin);
    u.searchParams.set("segmento", idSegmento);
    window.location.href = u.pathname + u.search;
  }

  pills.addEventListener("click", (e) => {
    const btn = e.target.closest(".FnSeg_Pill");
    if (!btn) return;
    const id = +btn.getAttribute("data-id");
    const on = btn.getAttribute("data-on") === "1";
    toggleSegmento(id, !on);
  });

  grid.addEventListener("click", (e) => {
    const card = e.target.closest(".FnSeg_Card");
    if (!card) return;
    irCategorias(card.getAttribute("data-id"));
  });

  grid.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const card = e.target.closest(".FnSeg_Card");
    if (!card) return;
    e.preventDefault();
    irCategorias(card.getAttribute("data-id"));
  });

  carregar();
})();
