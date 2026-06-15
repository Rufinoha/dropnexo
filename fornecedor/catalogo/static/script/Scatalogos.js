(function () {
  let paginaAtual = 1;
  let totalPaginas = 1;
  let totalRegistros = 0;
  const porPagina = 100;
  let linhasCompletas = [];
  /** IDs de produtos pai com variações recolhidas */
  const recolhidos = new Set();

  const el = {
    filtroBusca: document.getElementById("ob_filtroBusca"),
    filtroCategoria: document.getElementById("ob_filtroCategoria"),
    filtroTipo: document.getElementById("ob_filtroTipo"),
    filtroAtivos: document.getElementById("ob_filtroAtivos"),
    btnFiltrar: document.getElementById("ob_btnFiltrar"),
    btnLimpar: document.getElementById("ob_btnLimpar"),
    btnIncluir: document.getElementById("ob_btnIncluir"),
    btnImportar: document.getElementById("ob_btnImportar"),
    btnExpandirTodos: document.getElementById("ob_btnExpandirTodos"),
    btnRecolherTodos: document.getElementById("ob_btnRecolherTodos"),
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

  const BASE = "/catalogos";

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

  function renderNomePai(l) {
    const badge =
      l.formato === "E"
        ? `<span class="Cat_BadgeVar">${Number(l.qtd_variantes || 0)} variações</span>`
        : `<span class="Cat_BadgeSimples">Simples</span>`;
    return `<div class="Cat_PaiCell"><strong class="Cat_PaiNome">${escapeHtml(l.nome)}</strong>${badge}</div>`;
  }

  function renderNomeVar(l) {
    const chips = renderAtributos(l.atributos);
    if (chips) {
      return `<div class="Cat_VarCell"><span class="Cat_BadgeVarItem">Variação</span><div class="Cat_VarAttrs">${chips}</div></div>`;
    }
    return `<div class="Cat_VarCell"><span class="Cat_BadgeVarItem">Variação</span><span class="Cat_VarNome">${escapeHtml(l.nome)}</span></div>`;
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
      el.tbody.innerHTML = '<tr><td colspan="8">Nenhum produto encontrado.</td></tr>';
      renderPaginacao();
      return;
    }
    const u = util();
    el.tbody.innerHTML = linhas.map((l) => renderLinha(l, u)).join("");
    window.lucide?.createIcons?.();
    renderPaginacao();
  }

  async function carregar() {
    const r = await fetch(montarUrl());
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar.");
    totalPaginas = j.total_paginas || 1;
    totalRegistros = j.total || 0;
    if (paginaAtual > totalPaginas) {
      paginaAtual = totalPaginas;
      return carregar();
    }
    linhasCompletas = j.linhas || j.dados || [];
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
      largura: 880,
      altura: 580,
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
  el.filtroAtivos?.addEventListener("change", () => {
    paginaAtual = 1;
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  el.btnExpandirTodos?.addEventListener("click", expandirTodos);
  el.btnRecolherTodos?.addEventListener("click", recolherTodos);
  el.btnIncluir?.addEventListener("click", () => abrirApoio(null));
  el.btnImportar?.addEventListener("click", () => {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: `${BASE}/importar`,
      titulo: "Importar CSV",
      largura: 640,
      altura: 420,
      nivel: 1,
    });
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
      carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
    }
  });

  carregarCategoriasFiltro()
    .then(() => carregar())
    .catch((e) => Swal.fire("Erro", e.message, "error"));
})();
