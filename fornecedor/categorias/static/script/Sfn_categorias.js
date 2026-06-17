(function () {
  const segLista = document.getElementById("fn_cat_seg_lista");
  const segVazio = document.getElementById("fn_cat_seg_vazio");
  const segTitulo = document.getElementById("fn_cat_seg_titulo");
  const segCount = document.getElementById("fn_cat_seg_count");
  const arvoreEl = document.getElementById("fn_cat_arvore");
  const arvoreVazio = document.getElementById("fn_cat_arvore_vazio");
  const btnRaiz = document.getElementById("fn_cat_btn_raiz");
  const btnRaizEmpty = document.getElementById("fn_cat_btn_raiz_empty");
  const menuPop = document.getElementById("fn_cat_menu_pop");
  const modal = document.getElementById("fn_cat_modal");
  const form = document.getElementById("fn_cat_form");
  const inpId = document.getElementById("fn_cat_id");
  const inpParent = document.getElementById("fn_cat_parent_id");
  const inpNome = document.getElementById("fn_cat_nome");
  const inpOrdem = document.getElementById("fn_cat_ordem");
  const inpCtx = document.getElementById("fn_cat_ctx");
  const modalTitulo = document.getElementById("fn_cat_modal_titulo");
  const btnExcluir = document.getElementById("fn_cat_btn_excluir");
  const blingBanner = document.getElementById("fn_cat_bling_banner");
  const blingTitulo = document.getElementById("fn_cat_bling_titulo");
  const btnAssociarBling = document.getElementById("fn_cat_btn_associar_bling");

  const BASE = "/fornecedor/categorias";
  const MAX_NIVEL = 3;

  const ICON_BAG =
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>';
  const ICON_DOTS =
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>';
  const ICON_CHEV =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="m9 18 6-6-6-6"/></svg>';

  let segmentos = [];
  let idSegmentoAtual = null;
  let arvoreCache = [];
  let blingPendentes = { total: 0, segmentos: [], auto_segmento: null };
  let menuCtx = null;
  const fechadosPorSeg = new Map();

  function fechados() {
    if (!idSegmentoAtual) return new Set();
    if (!fechadosPorSeg.has(idSegmentoAtual)) fechadosPorSeg.set(idSegmentoAtual, new Set());
    return fechadosPorSeg.get(idSegmentoAtual);
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function alertar(msg, tipo) {
    const U = window.Util;
    return U?.alertar ? U.alertar(msg, tipo || "info") : Swal.fire("Atenção", msg, "warning");
  }

  async function confirmarAcao(titulo, texto) {
    const U = window.Util;
    if (U?.confirmar) return U.confirmar(titulo, texto);
    const r = await Swal.fire({
      title: titulo || "Confirmar?",
      text: texto || "",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim",
      cancelButtonText: "Cancelar",
    });
    return !!r.isConfirmed;
  }

  function fecharModal() {
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
  }

  function abrirModal() {
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    inpNome.focus();
  }

  function fecharMenu() {
    if (!menuPop) return;
    menuPop.hidden = true;
    menuCtx = null;
  }

  function findNode(nodes, id) {
    for (const n of nodes || []) {
      if (n.id === id) return n;
      const f = findNode(n.filhos, id);
      if (f) return f;
    }
    return null;
  }

  function gripEl() {
    const g = document.createElement("span");
    g.className = "FnCatTree-grip";
    g.setAttribute("aria-hidden", "true");
    g.title = "Arrastar";
    const col1 = document.createElement("span");
    col1.className = "FnCatTree-gripCols";
    const col2 = document.createElement("span");
    col2.className = "FnCatTree-gripCols";
    for (let i = 0; i < 3; i++) {
      col1.appendChild(document.createElement("span"));
      col2.appendChild(document.createElement("span"));
    }
    g.appendChild(col1);
    g.appendChild(col2);
    return g;
  }

  function renderNo(n, nivel) {
    const temFilhos = !!(n.filhos && n.filhos.length);
    const aberto = temFilhos && !fechados().has(n.id);
    const qtd = Number(n.qtd_produtos || 0);

    const li = document.createElement("li");
    li.className = "FnCatTree-item";
    li.dataset.level = String(nivel);
    li.dataset.id = String(n.id);

    const row = document.createElement("div");
    row.className = "FnCatTree-row";

    row.appendChild(gripEl());

    if (temFilhos) {
      const chev = document.createElement("button");
      chev.type = "button";
      chev.className = "FnCatTree-chevron" + (aberto ? " is-open" : "");
      chev.innerHTML = ICON_CHEV;
      chev.dataset.toggleId = String(n.id);
      chev.setAttribute("aria-label", (aberto ? "Recolher " : "Expandir ") + (n.nome || "categoria"));
      chev.setAttribute("aria-expanded", aberto ? "true" : "false");
      row.appendChild(chev);
    } else {
      const sp = document.createElement("span");
      sp.className = "FnCatTree-chevronSpacer";
      sp.setAttribute("aria-hidden", "true");
      row.appendChild(sp);
    }

    const icon = document.createElement("span");
    icon.className = "FnCatTree-icon";
    icon.innerHTML = ICON_BAG;
    row.appendChild(icon);

    const body = document.createElement("div");
    body.className = "FnCatTree-body";

    const nome = document.createElement("span");
    nome.className = "FnCatTree-nome";
    nome.textContent = n.nome || "";
    body.appendChild(nome);

    const qtdEl = document.createElement("span");
    qtdEl.className = "FnCatTree-qtd";
    qtdEl.textContent = qtd + (qtd === 1 ? " produto" : " produtos");
    body.appendChild(qtdEl);

    row.appendChild(body);

    const menuBtn = document.createElement("button");
    menuBtn.type = "button";
    menuBtn.className = "FnCatTree-menu";
    menuBtn.innerHTML = ICON_DOTS;
    menuBtn.setAttribute("aria-label", "Ações de " + (n.nome || "categoria"));
    menuBtn.dataset.menuId = String(n.id);
    menuBtn.dataset.menuNivel = String(nivel);
    row.appendChild(menuBtn);

    li.appendChild(row);

    if (temFilhos) {
      const sub = document.createElement("ul");
      sub.className = "FnCatTree-children";
      sub.dataset.depth = String(nivel);
      if (!aberto) sub.hidden = true;
      n.filhos.forEach((f) => sub.appendChild(renderNo(f, nivel + 1)));
      li.appendChild(sub);
    }

    return li;
  }

  function renderArvore() {
    arvoreEl.innerHTML = "";
    if (!idSegmentoAtual) {
      arvoreVazio.hidden = true;
      return;
    }
    if (!arvoreCache.length) {
      arvoreVazio.hidden = false;
      return;
    }
    arvoreVazio.hidden = true;
    const ul = document.createElement("ul");
    ul.className = "FnCatTree-raiz";
    arvoreCache.forEach((n) => ul.appendChild(renderNo(n, 1)));
    arvoreEl.appendChild(ul);
  }

  function segCountLabel(n) {
    return n + (n === 1 ? " segmento" : " segmentos");
  }

  function renderSegmentos() {
    if (!segmentos.length) {
      segLista.innerHTML = "";
      segVazio.hidden = false;
      if (segCount) segCount.textContent = segCountLabel(0);
      return;
    }
    segVazio.hidden = true;
    segLista.innerHTML = segmentos
      .map(
        (s) =>
          `<button type="button" class="FnCat_SegBtn${s.id === idSegmentoAtual ? " is-active" : ""}" data-id="${s.id}">
            <span class="FnCat_SegBtnIco">${ICON_BAG}</span>
            <span class="FnCat_SegBtnNome">${escapeHtml(s.nome)}</span>
            <span class="FnCat_SegBtnChev" aria-hidden="true">›</span>
          </button>`
      )
      .join("");
    if (segCount) segCount.textContent = segCountLabel(segmentos.length);
  }

  function syncToolbar() {
    const temSeg = !!idSegmentoAtual;
    btnRaiz.disabled = !temSeg;
    if (btnRaizEmpty) btnRaizEmpty.disabled = !temSeg;
  }

  function abrirMenu(btn, node, nivel) {
    if (!menuPop) return;
    menuCtx = { node, nivel };
    const rect = btn.getBoundingClientRect();
    const items = [
      { acao: "editar", label: "Editar categoria", danger: false },
      ...(nivel < MAX_NIVEL
        ? [{ acao: "filho", label: "Nova subcategoria", danger: false }]
        : []),
      { acao: "excluir", label: "Excluir", danger: true },
    ];
    menuPop.innerHTML = items
      .map(
        (it) =>
          `<button type="button" data-acao="${it.acao}" class="${it.danger ? "danger" : ""}">${escapeHtml(it.label)}</button>`
      )
      .join("");
    menuPop.hidden = false;
    menuPop.style.top = rect.bottom + 6 + "px";
    menuPop.style.left = Math.max(8, rect.right - 168) + "px";
  }

  async function excluirNo(id) {
    const ok = await confirmarAcao("Excluir categoria?", "Esta ação não pode ser desfeita.");
    if (!ok) return;
    const r = await fetch(BASE + "/excluir", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    await alertar(j.message, j.success ? "success" : "error");
    if (j.success) await carregarArvore();
  }

  async function carregarBlingPendentes() {
    if (!blingBanner) return;
    try {
      const r = await fetch(BASE + "/bling/pendentes", { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success) return;
      blingPendentes = j;
      if (j.total > 0) {
        blingBanner.hidden = false;
        if (blingTitulo) {
          blingTitulo.textContent = "Categorias do Bling aguardando segmento";
        }
      } else {
        blingBanner.hidden = true;
      }
    } catch {
      /* ignore */
    }
  }

  async function associarCategoriasBling() {
    const segs = blingPendentes.segmentos || segmentos;
    if (!segs.length) {
      return alertar("Ative ao menos um segmento em Minha empresa.", "warning");
    }
    let idSeg = blingPendentes.auto_segmento || idSegmentoAtual;
    if (segs.length > 1) {
      const opcoes = segs.reduce((acc, s) => {
        acc[s.id] = s.nome;
        return acc;
      }, {});
      const escolha = await Swal.fire({
        title: "Associar categorias do Bling",
        text: "Escolha o segmento (nicho) destas categorias:",
        input: "select",
        inputOptions: opcoes,
        inputValue: String(idSeg || segs[0].id),
        showCancelButton: true,
        confirmButtonText: "Associar",
        cancelButtonText: "Cancelar",
      });
      if (!escolha.isConfirmed) return;
      idSeg = +escolha.value;
    } else {
      idSeg = segs[0].id;
      const ok = await Swal.fire({
        icon: "question",
        title: "Associar categorias do Bling?",
        text: `Todas as categorias importadas serão vinculadas ao segmento "${segs[0].nome}".`,
        showCancelButton: true,
        confirmButtonText: "Associar",
      });
      if (!ok.isConfirmed) return;
    }
    const r = await fetch(BASE + "/bling/associar-segmento", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_segmento: idSeg }),
    });
    const j = await r.json();
    await alertar(j.message, j.success ? "success" : "error");
    if (j.success) {
      await carregarBlingPendentes();
      if (idSegmentoAtual === idSeg) await carregarArvore();
      else await selecionarSegmento(idSeg);
    }
  }

  async function carregarSegmentos() {
    const r = await fetch(BASE + "/segmentos", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    segmentos = j.segmentos || [];
    renderSegmentos();
    const ini = window.FN_CAT_SEG_INICIAL;
    if (ini && segmentos.some((s) => String(s.id) === String(ini))) {
      await selecionarSegmento(+ini);
    } else if (segmentos.length === 1) {
      await selecionarSegmento(segmentos[0].id);
    } else {
      syncToolbar();
    }
  }

  async function selecionarSegmento(id) {
    idSegmentoAtual = id;
    const seg = segmentos.find((s) => s.id === id);
    segTitulo.textContent = seg ? seg.nome : "Segmento";
    renderSegmentos();
    const url = new URL(window.location.href);
    url.searchParams.set("segmento", id);
    window.history.replaceState({}, "", url);
    await carregarArvore();
  }

  async function carregarArvore() {
    if (!idSegmentoAtual) {
      arvoreCache = [];
      renderArvore();
      syncToolbar();
      return;
    }
    const r = await fetch(BASE + "/arvore?id_segmento=" + encodeURIComponent(idSegmentoAtual), {
      credentials: "same-origin",
    });
    const j = await r.json();
    if (!j.success) {
      alertar(j.message || "Erro ao carregar.", "error");
      return;
    }
    arvoreCache = j.arvore || [];
    renderArvore();
    syncToolbar();
  }

  function abrirForm(opts) {
    inpId.value = opts.id || "";
    inpParent.value = opts.parentId || "";
    inpNome.value = opts.nome || "";
    inpOrdem.value = opts.ordem != null ? opts.ordem : 0;
    modalTitulo.textContent = opts.titulo || "Categoria";
    inpCtx.textContent = opts.ctx || "";
    btnExcluir.hidden = !opts.excluir;
    abrirModal();
  }

  function abrirNovaRaiz() {
    abrirForm({
      titulo: "Nova categoria (nível 1)",
      ctx: "Categoria principal do segmento.",
      parentId: "",
      excluir: false,
    });
  }

  function toggleNo(id) {
    const f = fechados();
    if (f.has(id)) f.delete(id);
    else f.add(id);
    renderArvore();
  }

  segLista.addEventListener("click", (e) => {
    const btn = e.target.closest(".FnCat_SegBtn");
    if (!btn) return;
    selecionarSegmento(+btn.getAttribute("data-id"));
  });

  btnRaiz.addEventListener("click", abrirNovaRaiz);
  btnRaizEmpty?.addEventListener("click", abrirNovaRaiz);

  arvoreEl.addEventListener("click", (e) => {
    const chev = e.target.closest(".FnCatTree-chevron[data-toggle-id]");
    if (chev) {
      e.preventDefault();
      e.stopPropagation();
      toggleNo(+chev.dataset.toggleId);
      return;
    }

    const menuBtn = e.target.closest(".FnCatTree-menu[data-menu-id]");
    if (!menuBtn) return;
    e.stopPropagation();
    const node = findNode(arvoreCache, +menuBtn.dataset.menuId);
    if (!node) return;
    abrirMenu(menuBtn, node, +menuBtn.dataset.menuNivel);
  });

  menuPop?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-acao]");
    if (!btn || !menuCtx) return;
    const { node, nivel } = menuCtx;
    fecharMenu();
    const acao = btn.getAttribute("data-acao");
    if (acao === "editar") {
      abrirForm({
        id: node.id,
        parentId: node.parent_id || "",
        nome: node.nome,
        ordem: node.ordem,
        titulo: "Editar categoria",
        ctx: "Nível " + (node.nivel || nivel),
        excluir: true,
      });
    } else if (acao === "filho") {
      abrirForm({
        titulo: "Nova subcategoria",
        ctx: "Filha de: " + node.nome,
        parentId: node.id,
        excluir: false,
      });
    } else if (acao === "excluir") {
      excluirNo(node.id).catch((err) => alertar(err.message, "error"));
    }
  });

  document.addEventListener("click", (e) => {
    if (!menuPop || menuPop.hidden) return;
    if (e.target.closest(".FnCatTree-menu") || e.target.closest("#fn_cat_menu_pop")) return;
    fecharMenu();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") fecharMenu();
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nome = inpNome.value.trim();
    if (!nome || !idSegmentoAtual) return;
    const r = await fetch(BASE + "/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id: inpId.value ? +inpId.value : null,
        id_segmento: idSegmentoAtual,
        parent_id: inpParent.value ? +inpParent.value : null,
        nome,
        ordem: +inpOrdem.value || 0,
      }),
    });
    const j = await r.json();
    alertar(j.message, j.success ? "success" : "error");
    if (j.success) {
      fecharModal();
      await carregarArvore();
    }
  });

  btnExcluir.addEventListener("click", async () => {
    if (!inpId.value) return;
    await excluirNo(+inpId.value);
    fecharModal();
  });

  document.getElementById("fn_cat_modal_fechar").onclick = fecharModal;
  document.getElementById("fn_cat_btn_cancelar").onclick = fecharModal;
  modal.addEventListener("click", (e) => {
    if (e.target === modal) fecharModal();
  });

  btnAssociarBling?.addEventListener("click", () =>
    associarCategoriasBling().catch((e) => alertar(e.message, "error"))
  );

  carregarBlingPendentes();
  carregarSegmentos();
})();
