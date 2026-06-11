(function () {
  const segLista = document.getElementById("fn_cat_seg_lista");
  const segVazio = document.getElementById("fn_cat_seg_vazio");
  const segTitulo = document.getElementById("fn_cat_seg_titulo");
  const arvoreEl = document.getElementById("fn_cat_arvore");
  const arvoreVazio = document.getElementById("fn_cat_arvore_vazio");
  const btnRaiz = document.getElementById("fn_cat_btn_raiz");
  const modal = document.getElementById("fn_cat_modal");
  const form = document.getElementById("fn_cat_form");
  const inpId = document.getElementById("fn_cat_id");
  const inpParent = document.getElementById("fn_cat_parent_id");
  const inpNome = document.getElementById("fn_cat_nome");
  const inpOrdem = document.getElementById("fn_cat_ordem");
  const inpCtx = document.getElementById("fn_cat_ctx");
  const modalTitulo = document.getElementById("fn_cat_modal_titulo");
  const btnExcluir = document.getElementById("fn_cat_btn_excluir");

  const BASE = "/fornecedor/categorias";
  const MAX_NIVEL = 3;
  let segmentos = [];
  let idSegmentoAtual = null;
  let arvoreCache = [];
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

  const U = window.Util || {};

  function alertar(msg, tipo) {
    return U.alertar ? U.alertar(msg, tipo || "info") : Swal.fire("Atenção", msg, "warning");
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

  function findNode(nodes, id) {
    for (const n of nodes || []) {
      if (n.id === id) return n;
      const f = findNode(n.filhos, id);
      if (f) return f;
    }
    return null;
  }

  function renderNo(n, nivel) {
    const temFilhos = !!(n.filhos && n.filhos.length);
    const aberto = temFilhos && !fechados().has(n.id);

    const li = document.createElement("li");
    li.className = "FnCatTree-item";
    li.dataset.level = String(nivel);
    li.dataset.id = String(n.id);

    const row = document.createElement("div");
    row.className = "FnCatTree-row";
    if (temFilhos) {
      row.classList.add("FnCatTree-row--pai");
      row.dataset.toggleId = String(n.id);
      row.setAttribute("role", "button");
      row.setAttribute("tabindex", "0");
      row.setAttribute("aria-expanded", aberto ? "true" : "false");
      row.setAttribute("aria-label", (aberto ? "Recolher " : "Expandir ") + (n.nome || "categoria"));
    }

    const guide = document.createElement("span");
    guide.className = "FnCatTree-guide";
    guide.setAttribute("aria-hidden", "true");
    row.appendChild(guide);

    const nome = document.createElement("span");
    nome.className = "FnCatTree-nome";
    nome.textContent = n.nome || "";
    row.appendChild(nome);

    const qtd = document.createElement("span");
    qtd.className = "FnCatTree-qtd";
    qtd.textContent = (n.qtd_produtos || 0) + " prod.";
    row.appendChild(qtd);

    const acoes = document.createElement("span");
    acoes.className = "FnCatTree-acoes";
    acoes.innerHTML =
      '<button type="button" data-acao="editar">Editar</button>' +
      (nivel < MAX_NIVEL ? '<button type="button" data-acao="filho">+ Sub</button>' : "");
    row.appendChild(acoes);

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

  function renderSegmentos() {
    if (!segmentos.length) {
      segLista.innerHTML = "";
      segVazio.hidden = false;
      return;
    }
    segVazio.hidden = true;
    segLista.innerHTML = segmentos
      .map(
        (s) =>
          `<button type="button" class="FnCat_SegBtn${s.id === idSegmentoAtual ? " is-active" : ""}" data-id="${s.id}">${escapeHtml(s.nome)}</button>`
      )
      .join("");
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
    }
  }

  async function selecionarSegmento(id) {
    idSegmentoAtual = id;
    const seg = segmentos.find((s) => s.id === id);
    segTitulo.textContent = seg ? seg.nome : "Segmento";
    btnRaiz.disabled = !id;
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
      return;
    }
    const r = await fetch(
      BASE + "/arvore?id_segmento=" + encodeURIComponent(idSegmentoAtual),
      { credentials: "same-origin" }
    );
    const j = await r.json();
    if (!j.success) {
      alertar(j.message || "Erro ao carregar.", "error");
      return;
    }
    arvoreCache = j.arvore || [];
    renderArvore();
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

  segLista.addEventListener("click", (e) => {
    const btn = e.target.closest(".FnCat_SegBtn");
    if (!btn) return;
    selecionarSegmento(+btn.getAttribute("data-id"));
  });

  btnRaiz.addEventListener("click", () =>
    abrirForm({
      titulo: "Nova categoria (nível 1)",
      ctx: "Categoria principal do segmento.",
      parentId: "",
      excluir: false,
    })
  );

  arvoreEl.addEventListener("click", (e) => {
    const tog = e.target.closest(".FnCatTree-row--pai[data-toggle-id]");
    if (tog) {
      if (e.target.closest("[data-acao]")) return;
      e.preventDefault();
      const id = +tog.dataset.toggleId;
      const f = fechados();
      if (f.has(id)) f.delete(id);
      else f.add(id);
      renderArvore();
      return;
    }

    const acao = e.target.closest("[data-acao]");
    if (!acao) return;
    const li = e.target.closest(".FnCatTree-item[data-id]");
    if (!li) return;
    const node = findNode(arvoreCache, +li.dataset.id);
    if (!node) return;
    if (acao.getAttribute("data-acao") === "editar") {
      abrirForm({
        id: node.id,
        parentId: node.parent_id || "",
        nome: node.nome,
        ordem: node.ordem,
        titulo: "Editar categoria",
        ctx: "Nível " + (node.nivel || 1),
        excluir: true,
      });
    } else {
      abrirForm({
        titulo: "Nova subcategoria",
        ctx: "Filha de: " + node.nome,
        parentId: node.id,
        excluir: false,
      });
    }
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
    const ok = U.confirmar
      ? await U.confirmar("Excluir categoria?", "Esta ação não pode ser desfeita.")
      : confirm("Excluir esta categoria?");
    if (!ok) return;
    const r = await fetch(BASE + "/excluir", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: +inpId.value }),
    });
    const j = await r.json();
    alertar(j.message, j.success ? "success" : "error");
    if (j.success) {
      fecharModal();
      await carregarArvore();
    }
  });

  document.getElementById("fn_cat_modal_fechar").onclick = fecharModal;
  document.getElementById("fn_cat_btn_cancelar").onclick = fecharModal;
  modal.addEventListener("click", (e) => {
    if (e.target === modal) fecharModal();
  });

  carregarSegmentos();
})();
