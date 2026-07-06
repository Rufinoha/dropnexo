(function () {
  const arvoreEl = document.getElementById("vd_cat_arvore");
  const arvoreVazio = document.getElementById("vd_cat_arvore_vazio");
  const btnRaiz = document.getElementById("vd_cat_btn_raiz");
  const btnRaizEmpty = document.getElementById("vd_cat_btn_raiz_empty");
  const menuPop = document.getElementById("vd_cat_menu_pop");
  const modal = document.getElementById("vd_cat_modal");
  const form = document.getElementById("vd_cat_form");
  const inpId = document.getElementById("vd_cat_id");
  const inpParent = document.getElementById("vd_cat_parent_id");
  const inpNome = document.getElementById("vd_cat_nome");
  const inpOrdem = document.getElementById("vd_cat_ordem");
  const inpCtx = document.getElementById("vd_cat_ctx");
  const modalTitulo = document.getElementById("vd_cat_modal_titulo");
  const btnExcluir = document.getElementById("vd_cat_btn_excluir");

  if (!arvoreEl) return;

  const BASE = "/vendedor/categorias";
  const MAX_NIVEL = 3;
  const fechadosIds = new Set();
  let arvoreCache = [];
  let menuCtx = null;

  const ICON_BAG =
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4Z"/><path d="M3 6h18"/><path d="M16 10a4 4 0 0 1-8 0"/></svg>';
  const ICON_DOTS =
    '<svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor"><circle cx="12" cy="5" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="12" cy="19" r="1.5"/></svg>';
  const ICON_CHEV =
    '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="m9 18 6-6-6-6"/></svg>';

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

  function gripEl() {
    const g = document.createElement("span");
    g.className = "FnCatTree-grip";
    g.setAttribute("aria-hidden", "true");
    g.textContent = "⋮⋮";
    return g;
  }

  function renderNo(n, nivel) {
    const temFilhos = !!(n.filhos && n.filhos.length);
    const aberto = temFilhos && !fechadosIds.has(n.id);
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
      row.appendChild(chev);
    } else {
      const sp = document.createElement("span");
      sp.className = "FnCatTree-chevronSpacer";
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
    menuBtn.dataset.menuId = String(n.id);
    menuBtn.dataset.menuNivel = String(nivel);
    row.appendChild(menuBtn);
    li.appendChild(row);
    if (temFilhos) {
      const sub = document.createElement("ul");
      sub.className = "FnCatTree-children";
      if (!aberto) sub.hidden = true;
      n.filhos.forEach((f) => sub.appendChild(renderNo(f, nivel + 1)));
      li.appendChild(sub);
    }
    return li;
  }

  function renderArvore() {
    arvoreEl.innerHTML = "";
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

  async function carregarArvore() {
    const r = await fetch(BASE + "/arvore", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      alertar(j.message || "Erro ao carregar.", "error");
      return;
    }
    arvoreCache = j.arvore || [];
    renderArvore();
  }

  function abrirModal() {
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    inpNome.focus();
  }

  function fecharModal() {
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
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

  function abrirMenu(btn, node, nivel) {
    menuCtx = { node, nivel };
    const rect = btn.getBoundingClientRect();
    const items = [
      { acao: "editar", label: "Editar categoria" },
      ...(nivel < MAX_NIVEL ? [{ acao: "filho", label: "Nova subcategoria" }] : []),
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

  function acharNo(id, lista) {
    for (const n of lista || []) {
      if (n.id === id) return n;
      const f = acharNo(id, n.filhos);
      if (f) return f;
    }
    return null;
  }

  async function salvar(e) {
    e.preventDefault();
    const body = {
      id: inpId.value ? parseInt(inpId.value, 10) : null,
      parent_id: inpParent.value ? parseInt(inpParent.value, 10) : null,
      nome: (inpNome.value || "").trim(),
      ordem: parseInt(inpOrdem.value, 10) || 0,
    };
    const r = await fetch(BASE + "/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    await alertar(j.message, j.success ? "success" : "error");
    if (j.success) {
      fecharModal();
      await carregarArvore();
    }
  }

  async function excluirNo(id) {
    const ok = await Swal.fire({
      title: "Excluir categoria?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Excluir",
    });
    if (!ok.isConfirmed) return;
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

  function novaRaiz() {
    abrirForm({ titulo: "Nova categoria nível 1", ctx: "Categoria principal" });
  }

  arvoreEl.addEventListener("click", (e) => {
    const chev = e.target.closest("[data-toggle-id]");
    if (chev) {
      const id = +chev.dataset.toggleId;
      if (fechadosIds.has(id)) fechadosIds.delete(id);
      else fechadosIds.add(id);
      renderArvore();
      return;
    }
    const menuBtn = e.target.closest("[data-menu-id]");
    if (menuBtn) {
      const id = +menuBtn.dataset.menuId;
      const nivel = +menuBtn.dataset.menuNivel;
      const node = acharNo(id, arvoreCache);
      if (node) abrirMenu(menuBtn, node, nivel);
    }
  });

  menuPop.addEventListener("click", async (e) => {
    const btn = e.target.closest("[data-acao]");
    if (!btn || !menuCtx) return;
    menuPop.hidden = true;
    const { node, nivel } = menuCtx;
    const acao = btn.dataset.acao;
    if (acao === "editar") {
      abrirForm({
        id: node.id,
        nome: node.nome,
        ordem: node.ordem,
        titulo: "Editar categoria",
        excluir: true,
      });
    } else if (acao === "filho") {
      abrirForm({
        parentId: node.id,
        titulo: "Nova subcategoria",
        ctx: "Dentro de: " + node.nome,
      });
    } else if (acao === "excluir") {
      await excluirNo(node.id);
    }
    menuCtx = null;
  });

  document.addEventListener("click", (e) => {
    if (!menuPop.hidden && !e.target.closest("#vd_cat_menu_pop") && !e.target.closest(".FnCatTree-menu")) {
      menuPop.hidden = true;
    }
  });

  if (btnRaiz) btnRaiz.addEventListener("click", novaRaiz);
  if (btnRaizEmpty) btnRaizEmpty.addEventListener("click", novaRaiz);
  if (form) form.addEventListener("submit", salvar);
  if (btnExcluir) {
    btnExcluir.addEventListener("click", () => {
      const id = parseInt(inpId.value, 10);
      if (id) excluirNo(id);
    });
  }
  document.getElementById("vd_cat_modal_fechar")?.addEventListener("click", fecharModal);
  document.getElementById("vd_cat_btn_cancelar")?.addEventListener("click", fecharModal);

  carregarArvore();
})();
