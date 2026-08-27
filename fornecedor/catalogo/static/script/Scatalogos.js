(function () {
  let paginaAtual = 1;
  let totalPaginas = 1;
  let totalRegistros = 0;
  const porPagina = 100;
  let linhasCompletas = [];
  /** IDs de produtos pai com variações recolhidas */
  const recolhidos = new Set();
  /** Produtos pai selecionados para ações em lote */
  const selecionados = new Set();

  const el = {
    filtroBusca: document.getElementById("ob_filtroBusca"),
    filtroCategoria: document.getElementById("ob_filtroCategoria"),
    filtroTipo: document.getElementById("ob_filtroTipo"),
    filtroAtivos: document.getElementById("ob_filtroAtivos"),
    filtroResumo: document.getElementById("ob_filtroResumo"),
    btnFiltrar: document.getElementById("ob_btnFiltrar"),
    btnLimpar: document.getElementById("ob_btnLimpar"),
    btnIncluir: document.getElementById("ob_btnIncluir"),
    btnImportar: document.getElementById("ob_btnImportar"),
    btnExportar: document.getElementById("ob_btnExportar"),
    btnImportarBling: document.getElementById("ob_btnImportarBling"),
    btnToggleExpandTodos: document.getElementById("ob_btnToggleExpandTodos"),
    chkTodos: document.getElementById("ob_chkTodos"),
    bulkRow: document.getElementById("ob_bulkRow"),
    bulkActions: document.getElementById("ob_bulkActions"),
    tbody: document.getElementById("ob_listaProdutos"),
    paginaAtual: document.getElementById("ob_paginaAtual"),
    totalPaginas: document.getElementById("ob_totalPaginas"),
    totalRegistros: document.getElementById("ob_totalRegistros"),
    btnPrimeiro: document.getElementById("ob_btnPrimeiro"),
    btnAnterior: document.getElementById("ob_btnAnterior"),
    btnProximo: document.getElementById("ob_btnProximo"),
    btnUltimo: document.getElementById("ob_btnUltimo"),
  };
  if (!el.tbody) return;

  const BASE = window.CAT_BASE || "/catalogos";
  const isArmazem = window.CAT_CONTEXTO_ARMAZEM === true || window.CAT_CONTEXTO_ARMAZEM === "true";

  function util() {
    return window.Util || { gerarIconeTech: () => "…" };
  }

  function fmtMoeda(v) {
    return Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function thumb(url) {
    if (url) {
      return `<img class="Cat_Thumb" src="${escapeHtml(url)}" alt="" loading="lazy" />`;
    }
    return '<span class="Cat_Thumb Cat_Thumb--vazio">—</span>';
  }

  function produtoTemVariacoes(l) {
    return l.tipo === "pai" && l.formato === "E" && Number(l.qtd_variantes || 0) > 0;
  }

  function syncRecolhidosPadrao(linhas) {
    recolhidos.clear();
    linhas.forEach((l) => {
      if (produtoTemVariacoes(l)) recolhidos.add(l.id);
    });
  }

  function idsPaisComVariacoes(linhas) {
    return linhas.filter(produtoTemVariacoes).map((l) => l.id);
  }

  function linhasVisiveis() {
    if (!linhasCompletas.length) return [];
    const out = [];
    for (const l of linhasCompletas) {
      if (l.tipo === "pai") {
        out.push(l);
        continue;
      }
      if (l.tipo === "variante" && !recolhidos.has(l.id_produto)) {
        out.push(l);
      }
    }
    return out;
  }

  function renderAtributos(attrs) {
    const entries = Object.entries(attrs || {}).filter(([, v]) => String(v || "").trim());
    if (!entries.length) return "";
    return entries
      .map(
        ([k, v]) =>
          `<span class="Cat_AttrChip"><span class="Cat_AttrChip__k">${escapeHtml(k)}</span> ${escapeHtml(v)}</span>`
      )
      .join("");
  }

  function badgeInativo(ativo) {
    return ativo === false ? '<span class="Cat_BadgeInativo">Inativo</span>' : "";
  }

  function badgeNaoPublicado(publicado) {
    return publicado === false ? '<span class="Cat_BadgeInativo">Não publicado</span>' : "";
  }

  function renderNomePai(l) {
    const badge =
      l.formato === "E"
        ? `<span class="Cat_BadgeVar">${Number(l.qtd_variantes || 0)} variações</span>`
        : `<span class="Cat_BadgeSimples">Simples</span>`;
    const forn =
      l.armazem_fornecedor_nome
        ? `<span class="Cat_BadgeSimples" title="Fornecedor local">${escapeHtml(l.armazem_fornecedor_nome)}</span>`
        : "";
    return `<div class="Cat_PaiCell"><strong class="Cat_PaiNome">${escapeHtml(l.nome)}</strong>${badge}${forn}${badgeNaoPublicado(l.publicado)}</div>`;
  }

  function renderNomeVar(l) {
    const chips = renderAtributos(l.atributos);
    const inativo = badgeInativo(l.ativo);
    if (chips) {
      return `<div class="Cat_VarCell"><span class="Cat_BadgeVarItem">Variação</span>${inativo}<div class="Cat_VarAttrs">${chips}</div></div>`;
    }
    return `<div class="Cat_VarCell"><span class="Cat_BadgeVarItem">Variação</span>${inativo}<span class="Cat_VarNome">${escapeHtml(l.nome)}</span></div>`;
  }

  function idsPaisVisiveis() {
    return linhasVisiveis().filter((l) => l.tipo === "pai").map((l) => l.id);
  }

  function syncTheadStickyOffset() {
    const wrap = document.getElementById("content-area-Principal");
    const first = wrap?.querySelector("thead tr:first-child");
    if (!wrap || !first) return;
    const h = Math.ceil(first.getBoundingClientRect().height) || 42;
    wrap.style.setProperty("--cat-thead-h", `${h}px`);
  }

  function syncBulkBar() {
    const n = selecionados.size;
    if (el.bulkRow) el.bulkRow.hidden = n === 0;
    if (n > 0) window.Util?.gerarIconeTech?.refresh?.();
    syncTheadStickyOffset();
    if (!el.chkTodos) return;
    const visiveis = idsPaisVisiveis();
    const marcados = visiveis.filter((id) => selecionados.has(id)).length;
    el.chkTodos.checked = visiveis.length > 0 && marcados === visiveis.length;
    el.chkTodos.indeterminate = marcados > 0 && marcados < visiveis.length;
  }

  function renderSelCell(l) {
    if (l.tipo !== "pai") {
      return '<span class="Cat_ExpandSpacer Cat_ExpandSpacer--var" aria-hidden="true"></span>';
    }
    const on = selecionados.has(l.id);
    return `<input type="checkbox" class="Cat_ChkSel Cat_ChkRow" data-produto="${l.id}" ${on ? "checked" : ""} aria-label="Selecionar produto" />`;
  }

  function initBulkActions() {
    if (!el.bulkActions || el.bulkActions.dataset.ready) return;
    el.bulkActions.dataset.ready = "1";
    const acoes = [
      { acao: "excluir", icon: "excluir", title: "Excluir selecionados", danger: true },
      { acao: "categoria", icon: "categorias", title: "Associar categoria" },
      { acao: "exportar", icon: "download", title: "Exportar lista" },
      { acao: "estoque", icon: "estoque", title: "Sincronizar estoque agora" },
      { acao: "etiquetas", icon: "etiquetas", title: "Imprimir etiquetas" },
      { acao: "rede", icon: "rede", title: "Publicar / despublicar na rede" },
    ];
    if (isArmazem) {
      acoes.splice(2, 0, {
        acao: "fornecedor",
        icon: "vincular_clientes",
        title: "Associar ao fornecedor local",
      });
    }
    acoes.forEach((a) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = `Cl_BtnAcao Cat_BulkBtn${a.danger ? " Cat_BulkBtn--danger" : ""}`;
      btn.dataset.bulk = a.acao;
      btn.title = a.title;
      btn.setAttribute("aria-label", a.title);
      window.Util?.gerarIconeTech?.({ dest: btn, nome: a.icon });
      el.bulkActions.appendChild(btn);
    });
    el.bulkActions.addEventListener("click", async (ev) => {
      const btn = ev.target.closest("[data-bulk]");
      if (!btn) return;
      try {
        if (btn.dataset.bulk === "exportar") {
          await exportarLista();
          return;
        }
        const ids = [...selecionados];
        if (!ids.length) return;
        if (btn.dataset.bulk === "excluir") await excluirLote(ids);
        else if (btn.dataset.bulk === "categoria") await associarCategoriaLote(ids);
        else if (btn.dataset.bulk === "fornecedor") await associarFornecedorArmazemLote(ids);
        else if (btn.dataset.bulk === "estoque") await sincronizarEstoqueLote(ids);
        else if (btn.dataset.bulk === "etiquetas") await swalEmDesenvolvimento("Impressão de etiquetas");
        else if (btn.dataset.bulk === "rede") await alternarPublicacaoRedeLote(ids);
      } catch (e) {
        await Swal.fire("Erro", e.message, "error");
      }
    });
  }

  async function exportarLista() {
    const escolha = await Swal.fire({
      title: "Exportar catálogo",
      text: "Será gerado o arquivo conforme o filtro atual da tela.",
      icon: "question",
      showDenyButton: true,
      showCancelButton: true,
      confirmButtonText: "CSV",
      denyButtonText: "Excel",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
    });
    if (escolha.isDismissed) return;
    const formato = escolha.isDenied ? "xlsx" : "csv";
    const p = new URLSearchParams({
      formato,
      busca: (el.filtroBusca?.value || "").trim(),
      id_categoria: el.filtroCategoria?.value || "",
      tipo: el.filtroTipo?.value || "",
      ativos: el.filtroAtivos?.checked ? "sim" : "nao",
    });
    window.location.href = `${BASE}/exportar?${p}`;
  }

  async function swalEmDesenvolvimento(recurso) {
    await Swal.fire({
      icon: "info",
      title: "Em desenvolvimento",
      text: `${recurso} será disponibilizado em breve. Ainda estamos definindo alguns detalhes.`,
      confirmButtonColor: "#021F81",
    });
  }

  async function excluirLote(ids) {
    const c = await Swal.fire({
      title: `Excluir ${ids.length} produto(s)?`,
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, excluir",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
    });
    if (!c.isConfirmed) return;
    const r = await fetch(`${BASE}/delete/lote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    selecionados.clear();
    syncBulkBar();
    await Swal.fire("Sucesso", j.message, "success");
    await carregar();
  }

  function montarHtmlAssociarCategoria(categorias, qtdProdutos) {
    const n = Number(qtdProdutos) || 0;
    const itens = (categorias || [])
      .map(
        (c, i) => `
      <button type="button" class="CatAssoc__opt${i === 0 ? " is-selected" : ""}" data-id="${c.id}" role="option" aria-selected="${i === 0 ? "true" : "false"}">
        <span class="CatAssoc__radio" aria-hidden="true"></span>
        <span class="CatAssoc__name">${escapeHtml(c.nome)}</span>
      </button>`
      )
      .join("");
    return `
      <div class="CatAssoc">
        <div class="CatAssoc__head">
          <div class="CatAssoc__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16"/><path d="M4 12h10"/><path d="M4 17h14"/><circle cx="18" cy="12" r="2"/></svg>
          </div>
          <div>
            <h3 class="CatAssoc__title">Associar categoria</h3>
            <p class="CatAssoc__sub">Aplicar em <strong>${n}</strong> produto${n === 1 ? "" : "s"} selecionado${n === 1 ? "" : "s"}.</p>
          </div>
        </div>
        <div class="CatAssoc__searchWrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
          <input type="search" id="catAssocBusca" class="CatAssoc__search" placeholder="Buscar categoria…" autocomplete="off" />
        </div>
        <div class="CatAssoc__list${(categorias || []).length > 5 ? " is-scrollable" : ""}" id="catAssocLista" role="listbox">
          ${itens || '<p class="CatAssoc__empty">Nenhuma categoria cadastrada.</p>'}
        </div>
        <input type="hidden" id="catAssocId" value="${categorias?.[0]?.id || ""}" />
      </div>`;
  }

  function ligarPickerAssociarCategoria(popup) {
    const lista = popup.querySelector("#catAssocLista");
    const hidden = popup.querySelector("#catAssocId");
    const busca = popup.querySelector("#catAssocBusca");
    if (!lista || !hidden) return;

    const marcar = (btn) => {
      lista.querySelectorAll(".CatAssoc__opt").forEach((elOpt) => {
        const on = elOpt === btn;
        elOpt.classList.toggle("is-selected", on);
        elOpt.setAttribute("aria-selected", on ? "true" : "false");
      });
      hidden.value = btn?.dataset?.id || "";
    };

    lista.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".CatAssoc__opt");
      if (!btn || !lista.contains(btn)) return;
      marcar(btn);
    });

    busca?.addEventListener("input", () => {
      const q = (busca.value || "").trim().toLowerCase();
      let visiveis = 0;
      lista.querySelectorAll(".CatAssoc__opt").forEach((btn) => {
        const nome = (btn.querySelector(".CatAssoc__name")?.textContent || "").toLowerCase();
        const ok = !q || nome.includes(q);
        btn.hidden = !ok;
        if (ok) visiveis += 1;
      });
      let empty = lista.querySelector(".CatAssoc__empty");
      if (!visiveis) {
        if (!empty) {
          empty = document.createElement("p");
          empty.className = "CatAssoc__empty";
          empty.textContent = "Nenhuma categoria encontrada.";
          lista.appendChild(empty);
        }
        empty.hidden = false;
      } else if (empty) {
        empty.hidden = true;
      }
      const sel = lista.querySelector(".CatAssoc__opt.is-selected");
      if (sel?.hidden) {
        const primeiro = lista.querySelector(".CatAssoc__opt:not([hidden])");
        if (primeiro) marcar(primeiro);
      }
    });

    setTimeout(() => busca?.focus(), 40);
  }

  async function associarCategoriaLote(ids) {
    const r = await fetch(`${BASE}/combos`);
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar categorias.");
    const categorias = j.categorias || [];
    if (!categorias.length) {
      throw new Error("Cadastre categorias antes de associar.");
    }
    const res = await Swal.fire({
      html: montarHtmlAssociarCategoria(categorias, ids.length),
      width: 420,
      heightAuto: true,
      showCancelButton: true,
      confirmButtonText: "Associar",
      cancelButtonText: "Cancelar",
      focusConfirm: false,
      buttonsStyling: false,
      customClass: {
        popup: "CatAssocSwal",
        htmlContainer: "CatAssocSwal__html",
        actions: "CatAssocSwal__actions",
        confirmButton: "CatAssocSwal__confirm",
        cancelButton: "CatAssocSwal__cancel",
      },
      didOpen: (popup) => ligarPickerAssociarCategoria(popup),
      preConfirm: () => {
        const v = document.getElementById("catAssocId")?.value;
        if (!v) {
          Swal.showValidationMessage("Selecione uma categoria.");
          return false;
        }
        return v;
      },
    });
    if (!res.isConfirmed) return;
    const resp = await fetch(`${BASE}/categoria/associar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, id_categoria: res.value }),
    });
    const jj = await resp.json();
    if (!resp.ok || !jj.success) throw new Error(jj.message || "Erro.");
    selecionados.clear();
    syncBulkBar();
    await Swal.fire({
      icon: "success",
      title: "Categoria associada",
      text: jj.message,
      timer: 2200,
      showConfirmButton: false,
    });
    await carregar();
  }

  function montarHtmlAssociarFornecedor(fornecedores, qtdProdutos) {
    const n = Number(qtdProdutos) || 0;
    const limparOpt = `
      <button type="button" class="CatAssoc__opt" data-id="" data-limpar="1" role="option" aria-selected="false">
        <span class="CatAssoc__radio" aria-hidden="true"></span>
        <span class="CatAssoc__name">Sem fornecedor (remover vínculo)</span>
      </button>`;
    const itens = (fornecedores || [])
      .map(
        (f, i) => `
      <button type="button" class="CatAssoc__opt${i === 0 ? " is-selected" : ""}" data-id="${f.id}" role="option" aria-selected="${i === 0 ? "true" : "false"}">
        <span class="CatAssoc__radio" aria-hidden="true"></span>
        <span class="CatAssoc__name">${escapeHtml(f.nome)}</span>
      </button>`
      )
      .join("");
    return `
      <div class="CatAssoc">
        <div class="CatAssoc__head">
          <div class="CatAssoc__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>
          </div>
          <div>
            <h3 class="CatAssoc__title">Associar fornecedor</h3>
            <p class="CatAssoc__sub">Aplicar em <strong>${n}</strong> produto${n === 1 ? "" : "s"} selecionado${n === 1 ? "" : "s"}.</p>
          </div>
        </div>
        <div class="CatAssoc__searchWrap">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/></svg>
          <input type="search" id="fornAssocBusca" class="CatAssoc__search" placeholder="Buscar fornecedor…" autocomplete="off" />
        </div>
        <div class="CatAssoc__list${(fornecedores || []).length > 5 ? " is-scrollable" : ""}" id="fornAssocLista" role="listbox">
          ${itens}${limparOpt}
        </div>
        <input type="hidden" id="fornAssocId" value="${fornecedores?.[0]?.id || ""}" />
        <input type="hidden" id="fornAssocLimpar" value="0" />
      </div>`;
  }

  function ligarPickerAssociarFornecedor(popup) {
    const lista = popup.querySelector("#fornAssocLista");
    const hidden = popup.querySelector("#fornAssocId");
    const limpar = popup.querySelector("#fornAssocLimpar");
    const busca = popup.querySelector("#fornAssocBusca");
    if (!lista || !hidden) return;

    const marcar = (btn) => {
      lista.querySelectorAll(".CatAssoc__opt").forEach((elOpt) => {
        const on = elOpt === btn;
        elOpt.classList.toggle("is-selected", on);
        elOpt.setAttribute("aria-selected", on ? "true" : "false");
      });
      hidden.value = btn?.dataset?.id || "";
      if (limpar) limpar.value = btn?.dataset?.limpar === "1" ? "1" : "0";
    };

    lista.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".CatAssoc__opt");
      if (!btn || !lista.contains(btn)) return;
      marcar(btn);
    });

    busca?.addEventListener("input", () => {
      const q = (busca.value || "").trim().toLowerCase();
      let visiveis = 0;
      lista.querySelectorAll(".CatAssoc__opt").forEach((btn) => {
        const nome = (btn.querySelector(".CatAssoc__name")?.textContent || "").toLowerCase();
        const ok = !q || nome.includes(q) || btn.dataset.limpar === "1";
        btn.hidden = !ok;
        if (ok) visiveis += 1;
      });
      let empty = lista.querySelector(".CatAssoc__empty");
      if (!visiveis) {
        if (!empty) {
          empty = document.createElement("p");
          empty.className = "CatAssoc__empty";
          empty.textContent = "Nenhum fornecedor encontrado.";
          lista.appendChild(empty);
        }
        empty.hidden = false;
      } else if (empty) {
        empty.hidden = true;
      }
      const sel = lista.querySelector(".CatAssoc__opt.is-selected");
      if (sel?.hidden) {
        const primeiro = lista.querySelector(".CatAssoc__opt:not([hidden])");
        if (primeiro) marcar(primeiro);
      }
    });

    setTimeout(() => busca?.focus(), 40);
  }

  async function associarFornecedorArmazemLote(ids) {
    const r = await fetch("/armazem/fornecedores/dados", { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar fornecedores.");
    const fornecedores = (j.dados || []).map((d) => ({
      id: d.id,
      nome: d.nome_fantasia || d.nome || `#${d.id}`,
    }));
    if (!fornecedores.length) {
      throw new Error("Cadastre fornecedores locais (Armazém → Fornecedores) antes de associar.");
    }
    const res = await Swal.fire({
      html: montarHtmlAssociarFornecedor(fornecedores, ids.length),
      width: 420,
      heightAuto: true,
      showCancelButton: true,
      confirmButtonText: "Associar",
      cancelButtonText: "Cancelar",
      focusConfirm: false,
      buttonsStyling: false,
      customClass: {
        popup: "CatAssocSwal",
        htmlContainer: "CatAssocSwal__html",
        actions: "CatAssocSwal__actions",
        confirmButton: "CatAssocSwal__confirm",
        cancelButton: "CatAssocSwal__cancel",
      },
      didOpen: (popup) => ligarPickerAssociarFornecedor(popup),
      preConfirm: () => {
        const limpar = document.getElementById("fornAssocLimpar")?.value === "1";
        const v = document.getElementById("fornAssocId")?.value;
        if (!limpar && !v) {
          Swal.showValidationMessage("Selecione um fornecedor.");
          return false;
        }
        return { limpar, id: v || null };
      },
    });
    if (!res.isConfirmed) return;
    const payload = { ids };
    if (res.value.limpar) payload.limpar = true;
    else payload.id_armazem_fornecedor = res.value.id;
    const resp = await fetch(`${BASE}/armazem-fornecedor/associar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const jj = await resp.json().catch(() => ({}));
    if (!resp.ok || !jj.success) throw new Error(jj.message || "Erro.");
    selecionados.clear();
    syncBulkBar();
    await Swal.fire({
      icon: "success",
      title: "Fornecedor atualizado",
      text: jj.message,
      timer: 2200,
      showConfirmButton: false,
    });
    await carregar();
  }

  async function sincronizarEstoqueLote(ids) {
    const c = await Swal.fire({
      title: "Sincronizar estoque?",
      text: `Importar saldos do Bling para ${ids.length} produto(s) selecionado(s).`,
      icon: "question",
      showCancelButton: true,
      confirmButtonText: "Sincronizar",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;
    const r = await fetch(`${BASE}/estoque/sincronizar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await Swal.fire("Concluído", j.message, "success");
    await carregar();
  }

  async function alternarPublicacaoRedeLote(ids) {
    const selecionadosDados = linhasCompletas.filter((l) => l.tipo === "pai" && ids.includes(l.id));
    const todosPublicados =
      selecionadosDados.length > 0 && selecionadosDados.every((l) => l.publicado);
    const publicar = !todosPublicados;
    const c = await Swal.fire({
      title: publicar ? "Publicar na rede?" : "Despublicar da rede?",
      text: publicar
        ? `${ids.length} produto(s) ficarão visíveis para vendedores da rede.`
        : `${ids.length} produto(s) deixarão de aparecer na rede de vendedores.`,
      icon: "question",
      showCancelButton: true,
      confirmButtonText: publicar ? "Publicar" : "Despublicar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
    });
    if (!c.isConfirmed) return;
    const r = await fetch(`${BASE}/rede/publicar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids, publicado: publicar }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await Swal.fire("Concluído", j.message, "success");
    await carregar();
  }

  function renderExpand(l) {
    if (!produtoTemVariacoes(l)) {
      return '<span class="Cat_ExpandSpacer" aria-hidden="true"></span>';
    }
    const aberto = !recolhidos.has(l.id);
    return `<button type="button" class="Cat_ExpandBtn${aberto ? " is-open" : ""}" data-produto="${l.id}" aria-expanded="${aberto}" aria-label="${aberto ? "Recolher variações" : "Expandir variações"}" title="${aberto ? "Recolher" : "Expandir"}">
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>
    </button>`;
  }

  function renderEstoque(l) {
    if (l.tipo === "variante") return String(l.estoque ?? 0);
    if (produtoTemVariacoes(l)) {
      const recolhido = recolhidos.has(l.id);
      if (recolhido) {
        return `<span class="Cat_EstoqueTotal" title="Soma de todas as variações">${l.estoque_total ?? 0}</span>`;
      }
      return "—";
    }
    if (l.estoque == null) return "—";
    return String(l.estoque ?? 0);
  }

  async function carregarCategoriasFiltro() {
    const r = await fetch(`${BASE}/combos`);
    const j = await r.json();
    if (!r.ok || !j.success) return;
    const sel = el.filtroCategoria;
    const val = sel.value;
    sel.innerHTML = '<option value="">Todas</option>';
    (j.categorias || []).forEach((c) => {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = c.nome;
      sel.appendChild(o);
    });
    sel.value = val;
  }

  function montarUrl() {
    const p = new URLSearchParams({
      pagina: paginaAtual,
      porPagina,
      busca: (el.filtroBusca?.value || "").trim(),
      id_categoria: el.filtroCategoria?.value || "",
      tipo: el.filtroTipo?.value || "",
      ativos: el.filtroAtivos?.checked ? "sim" : "nao",
    });
    return `${BASE}/dados?${p}`;
  }

  function renderPaginacao() {
    if (el.paginaAtual) el.paginaAtual.textContent = String(paginaAtual);
    if (el.totalPaginas) el.totalPaginas.textContent = String(totalPaginas);
    if (el.totalRegistros) el.totalRegistros.textContent = String(totalRegistros);
    if (el.btnPrimeiro) el.btnPrimeiro.disabled = paginaAtual <= 1;
    if (el.btnAnterior) el.btnAnterior.disabled = paginaAtual <= 1;
    if (el.btnProximo) el.btnProximo.disabled = paginaAtual >= totalPaginas;
    if (el.btnUltimo) el.btnUltimo.disabled = paginaAtual >= totalPaginas;
  }

  function renderLinha(l, u) {
    const isVar = l.tipo === "variante";
    const isPaiVar = produtoTemVariacoes(l);
    const aberto = isPaiVar && !recolhidos.has(l.id);
    const rowCls = [
      isVar ? "Cat_RowVar" : "Cat_RowPai",
      (isVar ? l.ativo === false : l.publicado === false) ? "Cat_RowInativo" : "",
      isVar && l.primeira_variante ? "Cat_RowVar--first" : "",
      isVar && l.ultima_variante ? "Cat_RowVar--ultima" : "",
      isPaiVar ? "Cat_RowPai--com-var" : "",
      isPaiVar && !aberto ? "Cat_RowPai--recolhido" : "",
      isPaiVar && aberto ? "Cat_RowPai--aberto" : "",
    ]
      .filter(Boolean)
      .join(" ");

    const preco =
      !isVar && l.formato === "E" && l.preco_min !== l.preco_max && l.preco_max
        ? `${fmtMoeda(l.preco_min)} – ${fmtMoeda(l.preco_max)}`
        : fmtMoeda(l.preco);

    const nomeCell = isVar ? renderNomeVar(l) : renderNomePai(l);
    const expandCell = isVar ? '<span class="Cat_ExpandSpacer Cat_ExpandSpacer--var" aria-hidden="true"></span>' : renderExpand(l);

    const acoes = isVar
      ? `<button type="button" class="Cl_BtnAcao btnEditVar" data-id="${l.id}" data-produto="${l.id_produto}">${u.gerarIconeTech("editar")}</button>`
      : `<button type="button" class="Cl_BtnAcao btnEditar" data-id="${l.id}">${u.gerarIconeTech("editar")}</button>
         <button type="button" class="Cl_BtnAcao btnExcluir" data-id="${l.id}">${u.gerarIconeTech("excluir")}</button>`;

    return `<tr class="${rowCls}" data-tipo="${l.tipo}"${isVar ? ` data-id-variante="${l.id}" data-id-produto="${l.id_produto}"` : ` data-id-produto="${l.id}"`}>
      <td class="Cat_ColSel">${renderSelCell(l)}</td>
      <td class="Cat_ColExpand">${expandCell}</td>
      <td class="Cat_ColImg">${thumb(l.imagem_url)}</td>
      <td class="Cat_ColNome">${nomeCell}</td>
      <td class="Cat_ColSku">${escapeHtml(l.sku || "—")}</td>
      <td>${escapeHtml(l.unidade || "UN")}</td>
      <td class="Cat_Preco">${preco}</td>
      <td class="Cat_ColEstoque">${renderEstoque(l)}</td>
      <td class="Cl_TableActions">${acoes}</td>
    </tr>`;
  }

  function renderTabela() {
    const linhas = linhasVisiveis();
    if (!linhas.length) {
      el.tbody.innerHTML = '<tr><td colspan="9">Nenhum produto encontrado.</td></tr>';
      atualizarBtnExpandTodos();
      syncBulkBar();
      renderPaginacao();
      return;
    }
    const u = util();
    el.tbody.innerHTML = linhas.map((l) => renderLinha(l, u)).join("");
    window.lucide?.createIcons?.();
    atualizarBtnExpandTodos();
    syncBulkBar();
    renderPaginacao();
  }

  function atualizarResumoFiltro(total) {
    const elResumo = el.filtroResumo;
    if (!elResumo) return;
    const somenteAtivos = !!el.filtroAtivos?.checked;
    const qtd = Number(total || 0);
    if (somenteAtivos) {
      elResumo.textContent = `${qtd} produto(s) — somente publicados`;
    } else {
      elResumo.textContent = `${qtd} produto(s) — publicados e não publicados`;
    }
    elResumo.hidden = false;
  }

  async function carregar() {
    const r = await fetch(montarUrl());
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar.");
    totalPaginas = j.total_paginas || 1;
    totalRegistros = j.total || 0;
    atualizarResumoFiltro(totalRegistros);
    if (paginaAtual > totalPaginas) {
      paginaAtual = totalPaginas;
      return carregar();
    }
    linhasCompletas = j.linhas || j.dados || [];
    selecionados.clear();
    if (el.filtroTipo?.value !== "somente_variacoes") {
      syncRecolhidosPadrao(linhasCompletas);
    } else {
      recolhidos.clear();
    }
    renderTabela();
  }

  function toggleProduto(idProduto) {
    if (recolhidos.has(idProduto)) recolhidos.delete(idProduto);
    else recolhidos.add(idProduto);
    renderTabela();
  }

  function expandirTodos() {
    recolhidos.clear();
    renderTabela();
  }

  function recolherTodos() {
    idsPaisComVariacoes(linhasCompletas).forEach((id) => recolhidos.add(id));
    renderTabela();
  }

  function atualizarBtnExpandTodos() {
    const btn = el.btnToggleExpandTodos;
    if (!btn) return;
    const ids = idsPaisComVariacoes(linhasCompletas);
    if (!ids.length) {
      btn.hidden = true;
      return;
    }
    btn.hidden = false;
    const algumAberto = ids.some((id) => !recolhidos.has(id));
    btn.classList.toggle("is-open", algumAberto);
    btn.setAttribute("aria-expanded", algumAberto ? "true" : "false");
    const label = algumAberto ? "Recolher todos" : "Expandir todos";
    btn.title = label;
    btn.setAttribute("aria-label", label);
  }

  function toggleExpandTodos() {
    const ids = idsPaisComVariacoes(linhasCompletas);
    if (!ids.length) return;
    if (ids.some((id) => !recolhidos.has(id))) recolherTodos();
    else expandirTodos();
  }

  function abrirApoio(id) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: id ? `${BASE}/editar` : `${BASE}/incluir`,
      id: id || null,
      titulo: id ? "Editar produto" : "Novo produto",
      largura: 1280,
      altura: 800,
      nivel: 1,
    });
  }

  function abrirVariante(idVar, idProduto) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: `${BASE}/variante/editar?id_variante=${idVar}&id_produto=${idProduto}`,
      titulo: "Detalhes da variação",
      largura: 920,
      altura: 640,
      nivel: 2,
      id: idVar,
    });
  }

  async function excluir(id) {
    const c = await Swal.fire({
      title: "Excluir produto?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, excluir",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;
    const r = await fetch(`${BASE}/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await Swal.fire("Sucesso", j.message, "success");
    await carregar();
  }

  el.btnFiltrar?.addEventListener("click", () => {
    paginaAtual = 1;
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  el.btnLimpar?.addEventListener("click", () => {
    el.filtroBusca.value = "";
    el.filtroCategoria.value = "";
    if (el.filtroTipo) el.filtroTipo.value = "";
    if (el.filtroAtivos) el.filtroAtivos.checked = true;
    paginaAtual = 1;
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  el.btnToggleExpandTodos?.addEventListener("click", toggleExpandTodos);

  el.chkTodos?.addEventListener("change", () => {
    const visiveis = idsPaisVisiveis();
    if (el.chkTodos.checked) visiveis.forEach((id) => selecionados.add(id));
    else selecionados.clear();
    renderTabela();
  });

  el.btnIncluir?.addEventListener("click", () => abrirApoio(null));
  el.btnImportar?.addEventListener("click", () => {
    window.CatImportacao?.abrir?.();
  });
  el.btnExportar?.addEventListener("click", () => exportarLista().catch((e) => Swal.fire("Erro", e.message, "error")));

  window.addEventListener("catalogo:importacao-concluida", () => {
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  el.btnPrimeiro?.addEventListener("click", () => {
    paginaAtual = 1;
    carregar();
  });
  el.btnAnterior?.addEventListener("click", () => {
    if (paginaAtual > 1) {
      paginaAtual -= 1;
      carregar();
    }
  });
  el.btnProximo?.addEventListener("click", () => {
    if (paginaAtual < totalPaginas) {
      paginaAtual += 1;
      carregar();
    }
  });
  el.btnUltimo?.addEventListener("click", () => {
    paginaAtual = totalPaginas;
    carregar();
  });

  el.tbody.addEventListener("click", async (ev) => {
    const chk = ev.target.closest(".Cat_ChkRow");
    if (chk) {
      ev.stopPropagation();
      const pid = Number(chk.dataset.produto || 0);
      if (!pid) return;
      if (chk.checked) selecionados.add(pid);
      else selecionados.delete(pid);
      syncBulkBar();
      return;
    }
    const expandBtn = ev.target.closest(".Cat_ExpandBtn");
    if (expandBtn) {
      toggleProduto(Number(expandBtn.dataset.produto || 0));
      return;
    }
    const btn = ev.target.closest("button");
    if (!btn) return;
    try {
      if (btn.classList.contains("btnEditVar")) {
        return abrirVariante(+btn.dataset.id, +btn.dataset.produto);
      }
      const id = Number(btn.dataset.id || 0);
      if (!id) return;
      if (btn.classList.contains("btnEditar")) return abrirApoio(id);
      if (btn.classList.contains("btnExcluir")) return await excluir(id);
    } catch (e) {
      await Swal.fire("Erro", e.message, "error");
    }
  });

  window.addEventListener("message", (ev) => {
    if (ev.data?.grupo === "atualizarTabela") {
      carregar().catch((e) => Swal.fire("Erro",