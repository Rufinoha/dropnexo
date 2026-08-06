(function () {
  let paginaAtual = 1;
  let totalPaginas = 1;
  let totalRegistros = 0;
  const porPagina = 100;
  let linhasCompletas = [];
  const recolhidos = new Set();
  const selecionados = new Set();
  let categoriasCache = [];
  /** Marketplaces conectados para exportação em lote (ml / tiktok / amazon). */
  let integracoesExportCache = null;

  const EXPORT_INTEGRACOES = {
    bling: { acao: "bling", nome: "Bling" },
    mercado_livre: { acao: "ml", nome: "Mercado Livre" },
    tiktok: { acao: "tiktok", nome: "TikTok Shop" },
    amazon: { acao: "amazon", nome: "Amazon" },
  };

  const el = {
    filtroBusca: document.getElementById("ob_filtroBusca"),
    filtroCategoria: document.getElementById("ob_filtroCategoria"),
    filtroTipo: document.getElementById("ob_filtroTipo"),
    filtroOrigem: document.getElementById("ob_filtroOrigem"),
    filtroIntegracao: document.getElementById("ob_filtroIntegracao"),
    filtroAtivos: document.getElementById("ob_filtroAtivos"),
    filtroResumo: document.getElementById("ob_filtroResumo"),
    btnFiltrar: document.getElementById("ob_btnFiltrar"),
    btnLimpar: document.getElementById("ob_btnLimpar"),
    btnIncluir: document.getElementById("ob_btnIncluir"),
    btnImportar: document.getElementById("ob_btnImportar"),
    btnExportar: document.getElementById("ob_btnExportar"),
    arquivoImport: document.getElementById("ob_arquivoImport"),
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
    modalMl: document.getElementById("ob_modalMl"),
    mlTitulo: document.getElementById("ob_mlTitulo"),
    mlSubtitulo: document.getElementById("ob_mlSubtitulo"),
    mlResumo: document.getElementById("ob_mlResumo"),
    mlLista: document.getElementById("ob_mlLista"),
    mlFechar: document.getElementById("ob_mlFechar"),
    mlBtnOk: document.getElementById("ob_mlBtnOk"),
  };
  if (!el.tbody) return;

  const BASE = "/meus-produtos";
  const KIT_BASE = "/meus-produtos/kits";

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

  function isKit(l) {
    return l.formato === "K" || Number(l.id) < 0;
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

  function badgePausado(l) {
    if (!l.pausado) return "";
    const tip = escapeHtml(l.pausado_msg || "Produto pausado");
    return `<span class="Cat_BadgePausado" title="${tip}">Pausado</span>`;
  }

  function badgeOrigem(l) {
    if (l.formato === "K") return "";
    const o = l.origem || "";
    if (o === "integrado") return '<span class="Cat_BadgeIntegrado" title="Produto da rede">Rede</span>';
    if (o === "proprio") return '<span class="Cat_BadgeProprio" title="Cadastro próprio">Próprio</span>';
    return "";
  }

  function renderNomePai(l) {
    let badge;
    if (l.formato === "K") {
      badge = '<span class="Cat_BadgeSimples">Kit</span>';
    } else if (l.formato === "E") {
      badge = `<span class="Cat_BadgeVar">${Number(l.qtd_variantes || 0)} variações</span>`;
    } else {
      badge = '<span class="Cat_BadgeSimples">Simples</span>';
    }
    const sit =
      l.origem === "proprio" ? badgeNaoPublicado(l.publicado) : badgeInativo(l.ativo);
    return `<div class="Cat_PaiCell"><strong class="Cat_PaiNome">${escapeHtml(l.nome)}</strong>${badge}${badgeOrigem(l)}${sit}${badgePausado(l)}</div>`;
  }

  function renderNomeVar(l) {
    const chips = renderAtributos(l.atributos);
    const inativo = badgeInativo(l.ativo);
    const pausado = badgePausado(l);
    if (chips) {
      return `<div class="Cat_VarCell"><span class="Cat_BadgeVarItem">Variação</span>${inativo}${pausado}<div class="Cat_VarAttrs">${chips}</div></div>`;
    }
    return `<div class="Cat_VarCell"><span class="Cat_BadgeVarItem">Variação</span>${inativo}${pausado}<span class="Cat_VarNome">${escapeHtml(l.nome)}</span></div>`;
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

  let menuIntegracoesEl = null;
  let menuIntegracoesAberto = false;

  function garantirMenuIntegracoesEl() {
    if (menuIntegracoesEl && document.body.contains(menuIntegracoesEl)) {
      return menuIntegracoesEl;
    }
    // Fora da tabela: th/td usam overflow:hidden e cortam o dropdown.
    menuIntegracoesEl = document.createElement("div");
    menuIntegracoesEl.className = "Cat_BulkIntMenu Cat_BulkIntMenu--portal";
    menuIntegracoesEl.setAttribute("role", "menu");
    menuIntegracoesEl.hidden = true;
    document.body.appendChild(menuIntegracoesEl);
    menuIntegracoesEl.addEventListener("click", async (ev) => {
      const b = ev.target.closest("[data-bulk]");
      if (!b || !menuIntegracoesEl.contains(b)) return;
      ev.preventDefault();
      ev.stopPropagation();
      const ids = [...selecionados];
      fecharMenuIntegracoes();
      if (!ids.length) return;
      try {
        if (b.dataset.bulk === "bling") await integrarBlingLote(ids);
        else if (b.dataset.bulk === "ml") await integrarMercadoLivreLote(ids);
        else if (b.dataset.bulk === "tiktok") await integrarTiktokLote(ids);
        else if (b.dataset.bulk === "amazon") await integrarAmazonLote(ids);
      } catch (e) {
        await Swal.fire("Erro", e.message, "error");
      }
    });
    return menuIntegracoesEl;
  }

  function posicionarMenuIntegracoes(btn) {
    const menu = garantirMenuIntegracoesEl();
    if (!btn) return;
    const r = btn.getBoundingClientRect();
    const largura = Math.max(200, menu.offsetWidth || 200);
    let left = r.right - largura;
    if (left < 8) left = 8;
    if (left + largura > window.innerWidth - 8) {
      left = Math.max(8, window.innerWidth - largura - 8);
    }
    let top = r.bottom + 6;
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    // Se não couber abaixo, abre para cima.
    requestAnimationFrame(() => {
      const mr = menu.getBoundingClientRect();
      if (mr.bottom > window.innerHeight - 8) {
        top = Math.max(8, r.top - mr.height - 6);
        menu.style.top = `${top}px`;
      }
    });
  }

  function fecharMenuIntegracoes() {
    const menu = menuIntegracoesEl;
    const wrap = el.bulkActions?.querySelector(".Cat_BulkIntWrap");
    const btn = el.bulkActions?.querySelector('[data-bulk="integrar"]');
    if (menu) menu.hidden = true;
    wrap?.classList.remove("is-open");
    btn?.setAttribute("aria-expanded", "false");
    menuIntegracoesAberto = false;
  }

  function aplicarIntegracoesFiltro(lista) {
    integracoesExportCache = (lista || [])
      .filter((o) => o && EXPORT_INTEGRACOES[o.valor])
      .map((o) => ({
        valor: o.valor,
        nome: EXPORT_INTEGRACOES[o.valor].nome || o.nome,
        acao: EXPORT_INTEGRACOES[o.valor].acao,
        icone_url: o.icone_url || "",
      }));
  }

  async function garantirIntegracoesExport() {
    if (integracoesExportCache) return integracoesExportCache;
    const r = await fetch(`${BASE}/combos`, { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar integrações.");
    aplicarIntegracoesFiltro(j.integracoes_filtro || []);
    if (!categoriasCache.length) categoriasCache = j.categorias || [];
    return integracoesExportCache;
  }

  function renderMenuIntegracoes(itens) {
    const menu = garantirMenuIntegracoesEl();
    if (!itens.length) {
      menu.innerHTML = `
        <p class="Cat_BulkIntEmpty">Nenhuma integração conectada.</p>
        <a class="Cat_BulkIntLink" href="/integracoes">Ir para Integrações</a>`;
      return;
    }
    menu.innerHTML = itens
      .map(
        (it) => `
        <button type="button" class="Cat_BulkIntItem" data-bulk="${escapeHtml(it.acao)}" role="menuitem">
          ${
            it.icone_url
              ? `<img src="${escapeHtml(it.icone_url)}" alt="" width="18" height="18" loading="lazy" />`
              : ""
          }
          <span>${escapeHtml(it.nome)}</span>
        </button>`
      )
      .join("");
  }

  async function abrirMenuIntegracoes(btn) {
    const wrap = el.bulkActions?.querySelector(".Cat_BulkIntWrap");
    if (!btn || !wrap) return;
    if (menuIntegracoesAberto) {
      fecharMenuIntegracoes();
      return;
    }
    const menu = garantirMenuIntegracoesEl();
    try {
      integracoesExportCache = null;
      const itens = await garantirIntegracoesExport();
      renderMenuIntegracoes(itens);
    } catch (e) {
      renderMenuIntegracoes([]);
      menu.insertAdjacentHTML(
        "beforeend",
        `<p class="Cat_BulkIntEmpty">${escapeHtml(e.message || "Erro ao carregar.")}</p>`
      );
    }
    menu.hidden = false;
    wrap.classList.add("is-open");
    btn.setAttribute("aria-expanded", "true");
    menuIntegracoesAberto = true;
    posicionarMenuIntegracoes(btn);
  }

  function initBulkActions() {
    if (!el.bulkActions || el.bulkActions.dataset.ready) return;
    el.bulkActions.dataset.ready = "1";

    const btnCat = document.createElement("button");
    btnCat.type = "button";
    btnCat.className = "Cl_BtnAcao Cat_BulkBtn";
    btnCat.dataset.bulk = "categoria";
    btnCat.title = "Associar categoria";
    btnCat.setAttribute("aria-label", "Associar categoria");
    window.Util?.gerarIconeTech?.({ dest: btnCat, nome: "categorias" });
    el.bulkActions.appendChild(btnCat);

    const wrapInt = document.createElement("div");
    wrapInt.className = "Cat_BulkIntWrap";
    const btnInt = document.createElement("button");
    btnInt.type = "button";
    btnInt.className = "Cl_BtnAcao Cat_BulkBtn";
    btnInt.dataset.bulk = "integrar";
    btnInt.title = "Integrar marketplaces";
    btnInt.setAttribute("aria-label", "Integrar marketplaces");
    btnInt.setAttribute("aria-haspopup", "menu");
    btnInt.setAttribute("aria-expanded", "false");
    window.Util?.gerarIconeTech?.({ dest: btnInt, nome: "vincular_clientes" });
    wrapInt.appendChild(btnInt);
    el.bulkActions.appendChild(wrapInt);

    const btnExc = document.createElement("button");
    btnExc.type = "button";
    btnExc.className = "Cl_BtnAcao Cat_BulkBtn Cat_BulkBtn--danger";
    btnExc.dataset.bulk = "excluir";
    btnExc.title = "Excluir selecionados";
    btnExc.setAttribute("aria-label", "Excluir selecionados");
    window.Util?.gerarIconeTech?.({ dest: btnExc, nome: "excluir" });
    el.bulkActions.appendChild(btnExc);

    el.bulkActions.addEventListener("click", async (ev) => {
      const intBtn = ev.target.closest('[data-bulk="integrar"]');
      if (intBtn && el.bulkActions.contains(intBtn)) {
        ev.preventDefault();
        ev.stopPropagation();
        await abrirMenuIntegracoes(intBtn);
        return;
      }
      const b = ev.target.closest("[data-bulk]");
      if (!b || !el.bulkActions.contains(b)) return;
      const ids = [...selecionados];
      if (!ids.length) return;
      fecharMenuIntegracoes();
      try {
        if (b.dataset.bulk === "excluir") await excluirLote(ids);
        else if (b.dataset.bulk === "categoria") await associarCategoriaLote(ids);
      } catch (e) {
        await Swal.fire("Erro", e.message, "error");
      }
    });

    document.addEventListener(
      "pointerdown",
      (ev) => {
        if (!menuIntegracoesAberto) return;
        const t = ev.target;
        if (menuIntegracoesEl?.contains(t)) return;
        if (el.bulkActions?.querySelector(".Cat_BulkIntWrap")?.contains(t)) return;
        fecharMenuIntegracoes();
      },
      true
    );
    document.addEventListener("keydown", (ev) => {
      if (ev.key === "Escape") fecharMenuIntegracoes();
    });
    window.addEventListener("resize", () => {
      if (menuIntegracoesAberto) fecharMenuIntegracoes();
    });
    window.addEventListener(
      "scroll",
      () => {
        if (menuIntegracoesAberto) fecharMenuIntegracoes();
      },
      true
    );
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
    if (!categoriasCache.length) {
      const r = await fetch(`${BASE}/combos`);
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar categorias.");
      categoriasCache = j.categorias || [];
    }
    if (!categoriasCache.length) {
      throw new Error("Cadastre categorias em Categorias antes de associar.");
    }
    const res = await Swal.fire({
      html: montarHtmlAssociarCategoria(categoriasCache, ids.length),
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

  async function associarCategoriaUm(idProduto) {
    await associarCategoriaLote([idProduto]);
  }

  function fecharModalMl() {
    el.modalMl?.close();
  }

  function abrirModalMlResultado(jj) {
    if (!el.modalMl || !el.mlLista) return;

    const resultados = jj.resultados || [];
    const criados =
      resultados.filter((r) => r.status === "ok" && r.acao === "criado").length ||
      Number(jj.exportados || 0);
    const atualizados =
      resultados.filter((r) => r.status === "ok" && r.acao === "atualizado").length ||
      Number(jj.atualizados || 0);
    const ok = resultados.filter((r) => r.status === "ok").length || criados + atualizados;
    const erros = resultados.filter((r) => r.status === "erro").length || Number(jj.erros || 0);
    const parcial = ok > 0 && erros > 0;

    if (el.mlTitulo) {
      el.mlTitulo.textContent = parcial
        ? "Integração parcialmente concluída"
        : ok > 0
          ? "Integração concluída"
          : "Não foi possível integrar";
    }
    if (el.mlSubtitulo) {
      el.mlSubtitulo.textContent = jj.message || "Resultado da publicação no Mercado Livre.";
    }

    if (el.mlResumo) {
      el.mlResumo.hidden = false;
      el.mlResumo.classList.toggle("Ob_MlResumo--4", true);
      el.mlResumo.innerHTML = `
        <div class="Ob_MlResumoCard Ob_MlResumoCard--ok"><strong>${criados}</strong><span>Criados</span></div>
        <div class="Ob_MlResumoCard Ob_MlResumoCard--upd"><strong>${atualizados}</strong><span>Atualizados</span></div>
        <div class="Ob_MlResumoCard Ob_MlResumoCard--erro"><strong>${erros}</strong><span>Com erro</span></div>
        <div class="Ob_MlResumoCard Ob_MlResumoCard--tot"><strong>${resultados.length || ok + erros}</strong><span>Total</span></div>`;
    }

    const icones = { ok: "✓", erro: "!", ignorado: "·" };
    const itens =
      resultados.length > 0
        ? resultados
        : (jj.detalhes_erros || []).map((msg) => ({
            titulo: "Produto",
            status: "erro",
            mensagem: msg,
          }));

    if (!itens.length && jj.message) {
      itens.push({ titulo: "Resumo", status: ok > 0 ? "ok" : "erro", mensagem: jj.message });
    }

    el.mlLista.innerHTML = itens
      .map((r) => {
        const st = r.status === "ok" || r.status === "erro" || r.status === "ignorado" ? r.status : "erro";
        const acaoTxt =
          r.acao === "criado" ? "Criado" : r.acao === "atualizado" ? "Atualizado" : "";
        const meta = [
          acaoTxt,
          r.sku && `SKU ${escapeHtml(r.sku)}`,
          r.ml_item_id && `Anúncio ${escapeHtml(r.ml_item_id)}`,
        ]
          .filter(Boolean)
          .join(" · ");
        return `<li class="Ob_MlItem Ob_MlItem--${st}">
          <span class="Ob_MlItemIcon" aria-hidden="true">${icones[st] || "!"}</span>
          <div>
            <p class="Ob_MlItemTitulo">${escapeHtml(r.titulo || "Produto")}</p>
            ${meta ? `<p class="Ob_MlItemMeta">${meta}</p>` : ""}
            <p class="Ob_MlItemMsg">${escapeHtml(r.mensagem || "")}</p>
          </div>
        </li>`;
      })
      .join("");

    el.modalMl.showModal();
  }

  el.mlFechar?.addEventListener("click", fecharModalMl);
  el.mlBtnOk?.addEventListener("click", fecharModalMl);
  el.modalMl?.addEventListener("cancel", (ev) => {
    ev.preventDefault();
    fecharModalMl();
  });

  function htmlProgressoMl(atual, total, criados, atualizados, erros, nomeAtual) {
    const pct = total > 0 ? Math.round((atual / total) * 100) : 0;
    const nome = escapeHtml(nomeAtual || "produto");
    return `
      <div style="text-align:left;font-size:13px;line-height:1.45;">
        <p style="margin:0 0 10px;color:#64748b;">Processando <strong>${atual}</strong> de <strong>${total}</strong></p>
        <div style="height:10px;background:#e2e8f0;border-radius:999px;overflow:hidden;margin-bottom:10px;">
          <div style="height:100%;width:${pct}%;background:#2563eb;transition:width .2s ease;"></div>
        </div>
        <p style="margin:0 0 8px;font-size:12px;color:#0f172a;">${nome}</p>
        <p style="margin:0;font-size:12px;color:#64748b;">
          Criados: <strong style="color:#047857">${criados}</strong>
          · Atualizados: <strong style="color:#1d4ed8">${atualizados}</strong>
          · Erros: <strong style="color:#b91c1c">${erros}</strong>
        </p>
      </div>`;
  }

  async function publicarUmProdutoMl(idProduto) {
    const resp = await fetch(`${BASE}/mercado-livre/publicar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: [idProduto] }),
    });
    let jj = {};
    try {
      jj = await resp.json();
    } catch {
      return {
        success: false,
        message: resp.status >= 500 ? "Erro no servidor." : "Resposta inválida.",
        resultados: [
          {
            id_produto: idProduto,
            titulo: `Produto #${idProduto}`,
            status: "erro",
            mensagem: resp.status >= 500 ? "Erro no servidor." : "Resposta inválida.",
          },
        ],
      };
    }
    if (!resp.ok || !jj.success) {
      const msg = jj.message || "Falha na integração.";
      const resultados = jj.resultados?.length
        ? jj.resultados
        : [
            {
              id_produto: idProduto,
              titulo: `Produto #${idProduto}`,
              status: "erro",
              mensagem: msg,
            },
          ];
      return { ...jj, success: false, message: msg, resultados };
    }
    return jj;
  }

  async function integrarBlingLote(ids) {
    const c = await Swal.fire({
      title: `Exportar ${ids.length} produto(s) ao Bling?`,
      html: `<p style="text-align:left;font-size:13px;margin:0;">Cria ou atualiza o produto no Bling (dados completos) e sincroniza o estoque.</p>`,
      icon: "question",
      showCancelButton: true,
      confirmButtonText: "Exportar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
    });
    if (!c.isConfirmed) return;
    Swal.fire({
      title: "Exportando ao Bling…",
      html: htmlProgressoMl(0, ids.length, 0, 0, 0, "Preparando"),
      allowOutsideClick: false,
      showConfirmButton: false,
      didOpen: () => Swal.showLoading(),
    });
    const resp = await fetch(`${BASE}/bling/publicar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    const jj = await resp.json().catch(() => ({}));
    if (!resp.ok || !jj.success) {
      throw new Error(jj.message || "Falha ao exportar ao Bling.");
    }
    const resultados = jj.resultados || [];
    let criados = Number(jj.exportados || 0);
    let atualizados = Number(jj.atualizados || 0);
    let erros = Number(jj.total_falhas || 0);
    if (resultados.length) {
      criados = resultados.filter((r) => r.status === "ok" && r.acao === "exportado").length || criados;
      atualizados =
        resultados.filter((r) => r.status === "ok" && r.acao === "atualizado").length || atualizados;
      erros = resultados.filter((r) => r.status === "erro").length || erros;
    }
    abrirModalMlResultado({
      ...jj,
      message: jj.message || "Exportação Bling concluída.",
      exportados: criados,
      atualizados,
      erros,
      resultados: resultados.length
        ? resultados
        : ids.map((id) => ({
            id_produto: id,
            titulo: `Produto #${id}`,
            status: erros ? "erro" : "ok",
            acao: "atualizado",
            mensagem: jj.message || "OK",
          })),
    });
    selecionados.clear();
    syncBulkBar();
    await carregar();
  }

  async function integrarMercadoLivreLote(ids) {
    const c = await Swal.fire({
      title: `Integrar ${ids.length} produto(s) ao Mercado Livre?`,
      html: `<p style="text-align:left;font-size:13px;margin:0;">O mesmo botão cria anúncios novos ou atualiza os já vinculados (fotos, descrição, preço e estoque).</p>`,
      icon: "question",
      showCancelButton: true,
      confirmButtonText: "Integrar",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;

    const total = ids.length;
    let criados = 0;
    let atualizados = 0;
    let erros = 0;
    const resultados = [];
    const detalhesErros = [];

    Swal.fire({
      title: "Integrando ao Mercado Livre…",
      html: htmlProgressoMl(0, total, 0, 0, 0, "Iniciando…"),
      allowOutsideClick: false,
      showConfirmButton: false,
      didOpen: () => Swal.showLoading(),
    });

    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      Swal.update({
        html: htmlProgressoMl(i, total, criados, atualizados, erros, `Produto #${id}…`),
      });

      const jj = await publicarUmProdutoMl(id);
      const itens = jj.resultados?.length
        ? jj.resultados
        : [
            {
              id_produto: id,
              titulo: `Produto #${id}`,
              status: jj.success ? "ok" : "erro",
              mensagem: jj.message || "",
            },
          ];

      for (const r of itens) {
        resultados.push(r);
        if (r.status === "ok" && r.acao === "criado") criados += 1;
        else if (r.status === "ok" && r.acao === "atualizado") atualizados += 1;
        else if (r.status === "ok") {
          if (Number(jj.exportados || 0) > 0) {
            r.acao = "criado";
            criados += 1;
          } else {
            r.acao = "atualizado";
            atualizados += 1;
          }
        } else {
          erros += 1;
          if (r.mensagem && !detalhesErros.includes(r.mensagem)) detalhesErros.push(r.mensagem);
        }
      }

      const ultimo = itens[itens.length - 1];
      Swal.update({
        html: htmlProgressoMl(
          i + 1,
          total,
          criados,
          atualizados,
          erros,
          ultimo?.titulo || `Produto #${id}`
        ),
      });
    }

    Swal.close();

    const partes = [];
    if (criados) partes.push(`${criados} criado(s)`);
    if (atualizados) partes.push(`${atualizados} atualizado(s)`);
    if (erros) partes.push(`${erros} com erro`);
    const message = partes.length
      ? partes.join(" · ") + " no Mercado Livre."
      : "Nenhum produto processado.";

    selecionados.clear();
    syncBulkBar();
    abrirModalMlResultado({
      success: criados + atualizados > 0,
      message,
      exportados: criados,
      atualizados,
      erros,
      resultados,
      detalhes_erros: detalhesErros.slice(0, 8),
    });
    await carregar();
  }

  async function publicarUmProdutoTiktok(idProduto) {
    const resp = await fetch(`${BASE}/tiktok/publicar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: [idProduto] }),
    });
    let jj = {};
    try {
      jj = await resp.json();
    } catch {
      return {
        success: false,
        message: resp.status >= 500 ? "Erro no servidor." : "Resposta inválida.",
        resultados: [
          {
            id_produto: idProduto,
            titulo: `Produto #${idProduto}`,
            status: "erro",
            mensagem: resp.status >= 500 ? "Erro no servidor." : "Resposta inválida.",
          },
        ],
      };
    }
    if (!resp.ok || !jj.success) {
      const msg = jj.message || "Falha na integração.";
      const resultados = jj.resultados?.length
        ? jj.resultados
        : [
            {
              id_produto: idProduto,
              titulo: `Produto #${idProduto}`,
              status: "erro",
              mensagem: msg,
            },
          ];
      return { ...jj, success: false, message: msg, resultados };
    }
    return jj;
  }

  async function integrarTiktokLote(ids) {
    const c = await Swal.fire({
      title: `Integrar ${ids.length} produto(s) ao TikTok Shop?`,
      html: `<p style="text-align:left;font-size:13px;margin:0;">Cria anúncios novos ou atualiza os já vinculados.</p>`,
      icon: "question",
      showCancelButton: true,
      confirmButtonText: "Integrar",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;

    const total = ids.length;
    let criados = 0;
    let atualizados = 0;
    let erros = 0;
    const resultados = [];
    const detalhesErros = [];

    Swal.fire({
      title: "Integrando ao TikTok Shop…",
      html: htmlProgressoMl(0, total, 0, 0, 0, "Iniciando…"),
      allowOutsideClick: false,
      showConfirmButton: false,
      didOpen: () => Swal.showLoading(),
    });

    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      Swal.update({
        html: htmlProgressoMl(i, total, criados, atualizados, erros, `Produto #${id}…`),
      });

      const jj = await publicarUmProdutoTiktok(id);
      const itens = jj.resultados?.length
        ? jj.resultados
        : [
            {
              id_produto: id,
              titulo: `Produto #${id}`,
              status: jj.success ? "ok" : "erro",
              mensagem: jj.message || "",
            },
          ];

      for (const r of itens) {
        resultados.push(r);
        if (r.status === "ok" && r.acao === "criado") criados += 1;
        else if (r.status === "ok" && r.acao === "atualizado") atualizados += 1;
        else if (r.status === "ok") {
          if (Number(jj.exportados || 0) > 0) {
            r.acao = "criado";
            criados += 1;
          } else {
            r.acao = "atualizado";
            atualizados += 1;
          }
        } else {
          erros += 1;
          if (r.mensagem && !detalhesErros.includes(r.mensagem)) detalhesErros.push(r.mensagem);
        }
      }

      const ultimo = itens[itens.length - 1];
      Swal.update({
        html: htmlProgressoMl(
          i + 1,
          total,
          criados,
          atualizados,
          erros,
          ultimo?.titulo || `Produto #${id}`
        ),
      });
    }

    Swal.close();

    const partes = [];
    if (criados) partes.push(`${criados} criado(s)`);
    if (atualizados) partes.push(`${atualizados} atualizado(s)`);
    if (erros) partes.push(`${erros} com erro`);
    const message = partes.length
      ? partes.join(" · ") + " no TikTok Shop."
      : "Nenhum produto processado.";

    selecionados.clear();
    syncBulkBar();
    abrirModalMlResultado({
      success: criados + atualizados > 0,
      message,
      exportados: criados,
      atualizados,
      erros,
      resultados,
      detalhes_erros: detalhesErros.slice(0, 8),
    });
    await carregar();
  }

  async function publicarUmProdutoAmazon(idProduto) {
    const resp = await fetch(`${BASE}/amazon/publicar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: [idProduto] }),
    });
    const jj = await resp.json().catch(() => ({}));
    if (!resp.ok || !jj.success) {
      const msg = jj.message || "Erro ao integrar na Amazon.";
      const resultados = jj.resultados?.length
        ? jj.resultados
        : [
            {
              id_produto: idProduto,
              titulo: `Produto #${idProduto}`,
              status: "erro",
              mensagem: msg,
            },
          ];
      return { ...jj, success: false, message: msg, resultados };
    }
    return jj;
  }

  async function integrarAmazonLote(ids) {
    const c = await Swal.fire({
      title: `Integrar ${ids.length} produto(s) à Amazon?`,
      html: `<p style="text-align:left;font-size:13px;margin:0;">Vincula por SKU ou cria/atualiza anúncios (conforme Integrações → Amazon).</p>`,
      icon: "question",
      showCancelButton: true,
      confirmButtonText: "Integrar",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;

    const total = ids.length;
    let criados = 0;
    let atualizados = 0;
    let erros = 0;
    const resultados = [];
    const detalhesErros = [];

    Swal.fire({
      title: "Integrando à Amazon…",
      html: htmlProgressoMl(0, total, 0, 0, 0, "Iniciando…"),
      allowOutsideClick: false,
      showConfirmButton: false,
      didOpen: () => Swal.showLoading(),
    });

    for (let i = 0; i < ids.length; i++) {
      const id = ids[i];
      Swal.update({
        html: htmlProgressoMl(i, total, criados, atualizados, erros, `Produto #${id}…`),
      });

      const jj = await publicarUmProdutoAmazon(id);
      const itens = jj.resultados?.length
        ? jj.resultados
        : [
            {
              id_produto: id,
              titulo: `Produto #${id}`,
              status: jj.success ? "ok" : "erro",
              mensagem: jj.message || "",
            },
          ];

      for (const r of itens) {
        resultados.push(r);
        if (r.status === "ok" && r.acao === "criado") criados += 1;
        else if (r.status === "ok" && (r.acao === "atualizado" || r.acao === "vinculado")) atualizados += 1;
        else if (r.status === "ok") {
          if (Number(jj.exportados || 0) > 0) {
            r.acao = "criado";
            criados += 1;
          } else {
            r.acao = "atualizado";
            atualizados += 1;
          }
        } else {
          erros += 1;
          if (r.mensagem && !detalhesErros.includes(r.mensagem)) detalhesErros.push(r.mensagem);
        }
      }

      const ultimo = itens[itens.length - 1];
      Swal.update({
        html: htmlProgressoMl(
          i + 1,
          total,
          criados,
          atualizados,
          erros,
          ultimo?.titulo || `Produto #${id}`
        ),
      });
    }

    Swal.close();

    const partes = [];
    if (criados) partes.push(`${criados} criado(s)`);
    if (atualizados) partes.push(`${atualizados} atualizado(s)/vinculado(s)`);
    if (erros) partes.push(`${erros} com erro`);
    const message = partes.length
      ? partes.join(" · ") + " na Amazon."
      : "Nenhum produto processado.";

    selecionados.clear();
    syncBulkBar();
    abrirModalMlResultado({
      success: criados + atualizados > 0,
      message,
      exportados: criados,
      atualizados,
      erros,
      resultados,
      detalhes_erros: detalhesErros.slice(0, 8),
    });
    await carregar();
  }

  function renderCategoriaCell(l) {
    if (l.tipo !== "pai" || isKit(l)) return "—";
    const nome = (l.categoria || "").trim();
    if (!nome) {
      return `<button type="button" class="Cat_CatPicker Cat_CatPicker--vazio" data-cat-prod="${l.id}" title="Escolher categoria">Escolher</button>`;
    }
    return `<button type="button" class="Cat_CatPicker" data-cat-prod="${l.id}" title="Alterar categoria">${escapeHtml(nome)}</button>`;
  }

  async function excluirLote(ids) {
    const c = await Swal.fire({
      title: `Excluir ${ids.length} item(ns)?`,
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, excluir",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
    });
    if (!c.isConfirmed) return;
    for (const id of ids) {
      const r = await fetch(`${BASE}/delete`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      });
      let j = {};
      try {
        j = await r.json();
      } catch {
        throw new Error(r.status === 500 ? "Erro no servidor ao excluir." : "Resposta inválida do servidor.");
      }
      if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    }
    selecionados.clear();
    syncBulkBar();
    await Swal.fire("Sucesso", "Itens removidos.", "success");
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

  function renderIntegracoesCell(l) {
    const ints = l.integracoes || [];
    if (!ints.length) return '<span class="Cat_IntVazio" title="Sem integração">—</span>';
    const nomes = ints.map((i) => i.nome).join(", ");
    const icons = ints
      .map(
        (i) =>
          `<img class="Cat_IntIcon" src="${escapeHtml(i.icone_url)}" alt="${escapeHtml(i.nome)}" width="20" height="20" loading="lazy" />`
      )
      .join("");
    return `<span class="Cat_IntIcons" title="${escapeHtml(nomes)}">${icons}</span>`;
  }

  async function carregarCategoriasFiltro() {
    const r = await fetch(`${BASE}/combos`);
    const j = await r.json();
    if (!r.ok || !j.success) return;
    const sel = el.filtroCategoria;
    const val = sel.value;
    sel.innerHTML = '<option value="">Todas</option><option value="sem">Sem Filtros</option>';
    (j.categorias || []).forEach((c) => {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = c.nome;
      sel.appendChild(o);
    });
    categoriasCache = j.categorias || [];
    sel.value = val;

    const selInt = el.filtroIntegracao;
    if (selInt) {
      const valInt = selInt.value;
      selInt.innerHTML = "";
      (j.integracoes_filtro || [
        { valor: "", nome: "Todas" },
        { valor: "sem", nome: "Sem integração" },
      ]).forEach((opt) => {
        const o = document.createElement("option");
        o.value = opt.valor;
        o.textContent = opt.nome;
        selInt.appendChild(o);
      });
      selInt.value = valInt;
    }
    aplicarIntegracoesFiltro(j.integracoes_filtro || []);
  }

  function montarUrl() {
    const p = new URLSearchParams({
      pagina: paginaAtual,
      porPagina,
      busca: (el.filtroBusca?.value || "").trim(),
      id_categoria: el.filtroCategoria?.value || "",
      tipo: el.filtroTipo?.value || "",
      origem: el.filtroOrigem?.value || "",
      integracao: el.filtroIntegracao?.value || "",
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
      (isVar
        ? l.ativo === false
        : l.origem === "proprio"
          ? l.publicado === false
          : l.ativo === false)
        ? "Cat_RowInativo"
        : "",
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
      <td class="Cat_ColCategoria">${renderCategoriaCell(l)}</td>
      <td class="Cat_Preco">${preco}</td>
      <td class="Cat_ColEstoque">${renderEstoque(l)}</td>
      <td class="Cat_ColIntegracoes">${renderIntegracoesCell(l)}</td>
      <td class="Cl_TableActions">${acoes}</td>
    </tr>`;
  }

  function renderTabela() {
    const linhas = linhasVisiveis();
    if (!linhas.length) {
      el.tbody.innerHTML = '<tr><td colspan="11">Nenhum produto encontrado.</td></tr>';
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
    elResumo.textContent = somenteAtivos
      ? `${qtd} produto(s) — somente ativos`
      : `${qtd} produto(s) — ativos e inativos`;
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

  function abrirApoioProduto(id) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: id ? `${BASE}/editar` : `${BASE}/incluir`,
      id: id || null,
      titulo: id ? "Editar produto" : "Novo produto",
      largura: 1280,
      altura: 800,
      nivel: 1,
    });
  }

  function abrirApoioKit(idKit) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: idKit ? `${KIT_BASE}/editar` : `${KIT_BASE}/incluir`,
      id: idKit || null,
      titulo: idKit ? "Editar kit" : "Novo kit",
      largura: 960,
      altura: 720,
      nivel: 1,
    });
  }

  async function abrirNovo() {
    const res = await Swal.fire({
      title: "Novo item",
      text: "Escolha o tipo de cadastro.",
      showDenyButton: true,
      showCancelButton: true,
      confirmButtonText: "Produto",
      denyButtonText: "Kit",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
    });
    if (res.isConfirmed) abrirApoioProduto(null);
    else if (res.isDenied) abrirApoioKit(null);
  }

  function abrirApoio(id) {
    if (Number(id) < 0) {
      abrirApoioKit(Math.abs(Number(id)));
      return;
    }
    abrirApoioProduto(id);
  }

  function abrirVariante(idVar, idProduto) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: `${BASE}/variante/editar?id_variante=${idVar}&id_produto=${idProduto}`,
      titulo: "Editar variação na vitrine",
      largura: 920,
      altura: 640,
      nivel: 2,
      id: idVar,
    });
  }

  async function excluir(id) {
    const titulo = Number(id) < 0 ? "Excluir kit?" : "Remover produto da vitrine?";
    const c = await Swal.fire({
      title: titulo,
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
    let j = {};
    try {
      j = await r.json();
    } catch {
      throw new Error(r.status === 500 ? "Erro no servidor ao excluir." : "Resposta inválida do servidor.");
    }
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
    if (el.filtroOrigem) el.filtroOrigem.value = "";
    if (el.filtroIntegracao) el.filtroIntegracao.value = "";
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

  async function exportarMeusProdutos() {
    const escolha = await Swal.fire({
      title: "Exportar Meus produtos",
      text: "Somente produtos próprios, conforme o filtro da tela (nunca o catálogo do fornecedor).",
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

  async function importarMeusProdutosArquivo(file) {
    if (!file) return;
    const fd = new FormData();
    fd.append("arquivo", file);
    Swal.fire({ title: "Importando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
      const r = await fetch(`${BASE}/importar/arquivo`, { method: "POST", body: fd, credentials: "include" });
      const j = await r.json();
      Swal.close();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha na importação.");
      await Swal.fire({
        icon: (j.rejeitadas || 0) > 0 ? "warning" : "success",
        title: "Concluído",
        text: j.message,
        confirmButtonColor: "#021F81",
      });
      await carregar();
    } catch (e) {
      Swal.close();
      await Swal.fire("Erro", e.message, "error");
    } finally {
      if (el.arquivoImport) el.arquivoImport.value = "";
    }
  }

  el.btnExportar?.addEventListener("click", () => exportarMeusProdutos().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnImportar?.addEventListener("click", () => el.arquivoImport?.click());
  el.arquivoImport?.addEventListener("change", () => {
    const f = el.arquivoImport?.files?.[0];
    if (f) importarMeusProdutosArquivo(f);
  });

  el.btnIncluir?.addEventListener("click", () => {
    abrirNovo().catch((e) => Swal.fire("Erro", e.message, "error"));
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
      if (btn.classList.contains("Cat_CatPicker")) {
        const pid = Number(btn.dataset.catProd || 0);
        if (pid) await associarCategoriaUm(pid);
        return;
      }
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

  initBulkActions();
  syncTheadStickyOffset();
  window.addEventListener("resize", syncTheadStickyOffset);
  carregarCategoriasFiltro()
    .then(() => carregar())
    .catch((e) => Swal.fire("Erro", e.message, "error"));
})();
