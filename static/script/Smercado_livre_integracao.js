(function () {
  const PANES = {
    pedidos: document.getElementById("ml_pane_pedidos"),
    produtos: document.getElementById("ml_pane_produtos"),
    estoque: document.getElementById("ml_pane_estoque"),
  };

  const el = {
    badge: document.getElementById("ml_status_badge"),
    alertSrv: document.getElementById("ml_alert_servidor"),
    secGuia: document.getElementById("ml_sec_guia"),
    painel: document.getElementById("ml_painel_config"),
    contaInfo: document.getElementById("ml_conta_info"),
    btnDesconectar: document.getElementById("ml_btn_desconectar"),
    btnConectar: document.getElementById("ml_btn_conectar"),
    btnSync: document.getElementById("ml_btn_sync"),
    btnMapearCategorias: document.getElementById("ml_btn_mapear_categorias"),
    btnSyncEstoque: document.getElementById("ml_btn_sync_estoque"),
    pedidosAuto: document.getElementById("ml_pedidos_auto"),
    produtosAuto: document.getElementById("ml_produtos_auto"),
    estoqueAuto: document.getElementById("ml_estoque_auto"),
    freteGratis: document.getElementById("ml_frete_gratis"),
    garantiaTipo: document.getElementById("ml_garantia_tipo"),
    garantiaTempo: document.getElementById("ml_garantia_tempo"),
    webhookUrl: document.getElementById("ml_webhook_url"),
    msg: document.getElementById("ml_msg"),
    msgModal: document.getElementById("ml_msg_modal"),
    subtabs: document.getElementById("ml_subtabs"),
    modalCat: document.getElementById("ml_modal_categorias"),
    tbodyCat: document.getElementById("ml_tbody_categorias"),
    btnModalCatSalvar: document.getElementById("ml_modal_cat_salvar"),
    btnModalCatSugerirTodas: document.getElementById("ml_modal_cat_sugerir_todas"),
    btnModalCatFechar: document.getElementById("ml_modal_cat_fechar"),
    btnModalCatCancelar: document.getElementById("ml_modal_cat_cancelar"),
    avisoGratis: document.getElementById("ml_aviso_gratis"),
    pickerModal: document.getElementById("ml_modal_picker_cat"),
    pickerBusca: document.getElementById("ml_picker_busca"),
    pickerLista: document.getElementById("ml_picker_lista"),
    pickerHint: document.getElementById("ml_picker_hint"),
    btnPickerFechar: document.getElementById("ml_picker_fechar"),
    btnPickerCancelar: document.getElementById("ml_picker_cancelar"),
  };

  let categoriasMap = [];
  let salvando = false;
  let cfgAtual = {};
  /** Cache temporário das sugestões ML enquanto o modal está aberto. */
  const sugestoesCache = new Map();
  const sugestoesInflight = new Map();
  let prefetchSeq = 0;

  function ativarAba(tab) {
    const id = tab in PANES ? tab : "pedidos";
    document.querySelectorAll(".Mp_SubTab").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.mlTab === id);
    });
    Object.entries(PANES).forEach(([k, pane]) => {
      if (pane) pane.hidden = k !== id;
    });
    try {
      localStorage.setItem("ml_integracao_aba", id);
    } catch {
      /* ignore */
    }
  }

  function listingTypeSelecionado() {
    return document.querySelector('input[name="ml_listing_type"]:checked')?.value || "auto";
  }

  function atualizarAvisoGratis() {
    if (!el.avisoGratis) return;
    el.avisoGratis.hidden = listingTypeSelecionado() !== "free";
  }

  function setConectado(on) {
    if (el.badge) {
      el.badge.textContent = on ? "Conectado" : "Desconectado";
      el.badge.classList.toggle("is-on", on);
      el.badge.classList.toggle("is-off", !on);
    }
    el.secGuia?.toggleAttribute("hidden", on);
    el.painel?.toggleAttribute("hidden", !on);
  }

  function setServidorConfigurado(ok) {
    if (el.alertSrv) el.alertSrv.hidden = !!ok;
    if (el.btnConectar && !ok) {
      el.btnConectar.classList.add("is-disabled");
      el.btnConectar.setAttribute("aria-disabled", "true");
      el.btnConectar.addEventListener("click", (ev) => {
        ev.preventDefault();
        alert("Integração indisponível. Configure o app Mercado Livre no servidor.");
      });
    }
  }

  function mostrarMsg(t, erro) {
    if (!el.msg) return;
    el.msg.textContent = t;
    el.msg.hidden = !t;
    el.msg.classList.toggle("is-erro", !!erro);
  }

  function modalAberto() {
    return !!(el.modalCat && el.modalCat.open);
  }

  function mostrarMsgModal(t, erro) {
    if (!el.msgModal) {
      if (t) mostrarMsg(t, erro);
      return;
    }
    el.msgModal.textContent = t || "";
    el.msgModal.hidden = !t;
    el.msgModal.classList.toggle("is-erro", !!erro);
  }

  function feedbackCat(t, erro) {
    if (modalAberto()) mostrarMsgModal(t, erro);
    else mostrarMsg(t, erro);
  }

  function renderConta(cfg) {
    const c = cfg.conta || {};
    const nick = c.nickname || "";
    const nome = [c.first_name, c.last_name].filter(Boolean).join(" ").trim();
    const site = cfg.ml_site_id || c.site_id || "";
    if (!nick && !nome) {
      el.contaInfo?.setAttribute("hidden", "");
      return;
    }
    if (el.contaInfo) {
      el.contaInfo.hidden = false;
      el.contaInfo.textContent = [nick && `@${nick}`, nome, site && `(${site})`].filter(Boolean).join(" · ");
    }
  }

  function aplicarConfig(cfg) {
    cfgAtual = cfg || {};
    if (el.pedidosAuto) el.pedidosAuto.checked = !!cfg.pedidos_importar_auto;
    if (el.produtosAuto) el.produtosAuto.checked = !!cfg.produtos_exportar_auto;
    if (el.estoqueAuto) el.estoqueAuto.checked = !!cfg.estoque_sync_ativo;
    if (el.freteGratis) el.freteGratis.checked = !!cfg.frete_gratis;
    if (el.garantiaTipo) el.garantiaTipo.value = cfg.garantia_tipo_padrao || "";
    if (el.garantiaTempo) el.garantiaTempo.value = cfg.garantia_tempo_padrao || "";
    if (el.webhookUrl) {
      el.webhookUrl.textContent = cfg.webhook_url || "—";
    }
    const modo = cfg.produtos_modo || "vincular_sku";
    document.querySelectorAll('input[name="ml_produtos_modo"]').forEach((r) => {
      r.checked = r.value === modo;
    });
    const lt = cfg.listing_type_padrao || "auto";
    document.querySelectorAll('input[name="ml_listing_type"]').forEach((r) => {
      r.checked = r.value === lt;
    });
    atualizarAvisoGratis();
  }

  function payloadConfig(parcial) {
    const body = { ...parcial };
    if (el.pedidosAuto) body.pedidos_importar_auto = el.pedidosAuto.checked;
    if (el.produtosAuto) body.produtos_exportar_auto = el.produtosAuto.checked;
    if (el.estoqueAuto) body.estoque_sync_ativo = el.estoqueAuto.checked;
    if (el.freteGratis) body.frete_gratis = el.freteGratis.checked;
    if (el.garantiaTipo) body.garantia_tipo_padrao = el.garantiaTipo.value || "";
    if (el.garantiaTempo) body.garantia_tempo_padrao = el.garantiaTempo.value || "";
    const modo = document.querySelector('input[name="ml_produtos_modo"]:checked');
    if (modo) body.produtos_modo = modo.value;
    const lt = document.querySelector('input[name="ml_listing_type"]:checked');
    if (lt) body.listing_type_padrao = lt.value;
    return body;
  }

  async function salvarConfig(parcial) {
    if (salvando) return;
    salvando = true;
    try {
      const r = await fetch("/api/integracoes/mercado-livre/config/salvar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payloadConfig(parcial || {})),
      });
      let j = {};
      try {
        j = await r.json();
      } catch {
        throw new Error(r.status >= 500 ? "Erro no servidor ao salvar." : "Resposta inválida do servidor.");
      }
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao salvar.");
      mostrarMsg(j.message || "Preferências salvas.", false);
      Object.assign(cfgAtual, payloadConfig({}));
    } catch (e) {
      mostrarMsg(e.message, true);
    } finally {
      salvando = false;
    }
  }

  async function carregarStatus() {
    try {
      const r = await fetch("/api/integracoes/mercado-livre/status", { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success) return;
      const cfg = j.config || {};
      setServidorConfigurado(!!cfg.configurado_servidor);
      setConectado(!!cfg.conectado);
      aplicarConfig(cfg);
      renderConta(cfg);
    } catch {
      /* silencioso */
    }
  }

  el.subtabs?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".Mp_SubTab");
    if (!btn?.dataset.mlTab) return;
    ativarAba(btn.dataset.mlTab);
  });

  [el.pedidosAuto, el.produtosAuto, el.estoqueAuto, el.freteGratis, el.garantiaTipo, el.garantiaTempo].forEach((inp) => {
    inp?.addEventListener("change", () => salvarConfig());
  });
  document.querySelectorAll('input[name="ml_produtos_modo"]').forEach((r) => {
    r.addEventListener("change", () => salvarConfig());
  });
  document.querySelectorAll('input[name="ml_listing_type"]').forEach((r) => {
    r.addEventListener("change", () => {
      salvarConfig();
      atualizarAvisoGratis();
    });
  });

  el.btnDesconectar?.addEventListener("click", async () => {
    if (!confirm("Desconectar Mercado Livre deste vendedor?")) return;
    try {
      const r = await fetch("/api/integracoes/mercado-livre/desconectar", {
        method: "POST",
        credentials: "same-origin",
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha.");
      setConectado(false);
      mostrarMsg(j.message, false);
    } catch (e) {
      mostrarMsg(e.message, true);
    }
  });

  async function postSync(url, btn, loading) {
    if (!btn) return;
    btn.disabled = true;
    mostrarMsg(loading, false);
    try {
      const r = await fetch(url, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      let j = {};
      try {
        j = await r.json();
      } catch {
        throw new Error(r.status >= 500 ? "Erro no servidor." : "Resposta inválida do servidor.");
      }
      if (!r.ok || !j.success) throw new Error(j.message || "Falha.");
      let msg = j.message || "Concluído.";
      if (j.detalhes_erros?.length) {
        msg += " " + j.detalhes_erros.slice(0, 2).join(" · ");
      }
      mostrarMsg(msg, false);
    } catch (e) {
      mostrarMsg(e.message, true);
    } finally {
      btn.disabled = false;
    }
  }

  el.btnSync?.addEventListener("click", () =>
    postSync("/api/integracoes/mercado-livre/sync/pedidos", el.btnSync, "Buscando pedidos no Mercado Livre…")
  );

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function valorCategoriaMlLinha(tr) {
    return (tr.querySelector(".ml-hid-cat")?.value || "").trim().toUpperCase();
  }

  function setCategoriaMlLinha(tr, categoryId, categoryNome) {
    const hid = tr.querySelector(".ml-hid-cat");
    const label = tr.querySelector(".ml-lbl-cat");
    const id = String(categoryId || "").trim().toUpperCase();
    const nome = String(categoryNome || "").trim();
    if (hid) hid.value = id;
    if (label) {
      if (id && nome) {
        label.textContent = nome;
        label.classList.remove("is-empty", "is-invalid");
        label.title = id;
      } else if (id && !nome) {
        label.textContent = "Categoria sem nome no cache — escolha novamente";
        label.classList.add("is-empty", "is-invalid");
        label.title = "";
        hid.value = "";
      } else {
        label.textContent = "Nenhuma categoria selecionada";
        label.classList.add("is-empty");
        label.classList.remove("is-invalid");
        label.title = "";
      }
    }
  }

  function renderTabelaCategorias() {
    if (!el.tbodyCat) return;
    if (!categoriasMap.length) {
      el.tbodyCat.innerHTML =
        '<tr><td colspan="2" class="Mp_Hint">Cadastre categorias em Categorias antes de mapear.</td></tr>';
      return;
    }
    el.tbodyCat.innerHTML = categoriasMap
      .map((c) => {
        const id = c.id_categoria;
        const mlId = (c.ml_category_id || "").trim().toUpperCase();
        const mlNome = (c.ml_category_nome || "").trim();
        const label =
          mlId && mlNome
            ? esc(mlNome)
            : mlId
              ? "Categoria sem nome no cache — escolha novamente"
              : "Nenhuma categoria selecionada";
        const emptyCls = mlId && mlNome ? "" : " is-empty";
        const invalidCls = mlId && !mlNome ? " is-invalid" : "";
        const hidVal = mlId && mlNome ? mlId : "";
        return `<tr data-cat-id="${id}">
          <td>${esc(c.nome)}</td>
          <td class="ml-cell-cat">
            <input type="hidden" class="ml-hid-cat" value="${esc(hidVal)}" />
            <div class="Mp_CatPick">
              <span class="ml-lbl-cat${emptyCls}${invalidCls}" title="${esc(hidVal)}">${label}</span>
              <button type="button" class="Cl_botaoFiltro Mp_CatMapBtn ml-btn-escolher">Escolher</button>
            </div>
          </td>
        </tr>`;
      })
      .join("");
  }

  function coletarItensMapeamento() {
    const itens = [];
    el.tbodyCat?.querySelectorAll("tr[data-cat-id]").forEach((tr) => {
      const id = parseInt(tr.dataset.catId, 10);
      if (!id) return;
      const ml = valorCategoriaMlLinha(tr);
      if (ml) itens.push({ id_categoria: id, ml_category_id: ml });
    });
    return itens;
  }

  function limparCacheSugestoes() {
    prefetchSeq += 1;
    sugestoesCache.clear();
    sugestoesInflight.clear();
  }

  function chaveCacheSugestao(idCategoria, termo) {
    return `${idCategoria || 0}::${String(termo || "").trim().toLowerCase()}`;
  }

  async function carregarMapeamentoCategorias() {
    const r = await fetch("/api/integracoes/mercado-livre/categorias-mapeamento", {
      credentials: "same-origin",
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar categorias.");
    categoriasMap = j.itens || [];
    renderTabelaCategorias();
  }

  function atualizarProgressoPrefetch() {
    if (!modalAberto()) return;
    const total = categoriasMap.filter((c) => (c.nome || "").trim().length >= 3).length;
    if (!total) return;
    const idsProntos = new Set(
      [...sugestoesCache.keys()].map((k) => String(k).split("::")[0]).filter((id) => id && id !== "0")
    );
    const n = idsProntos.size;
    if (n < total) {
      mostrarMsgModal(`Preparando sugestões… ${n}/${total}`, false);
    } else {
      mostrarMsgModal("Sugestões prontas — use «Sugerir não mapeadas».", false);
    }
  }

  function linhasSemMapeamento() {
    const rows = [];
    el.tbodyCat?.querySelectorAll("tr[data-cat-id]").forEach((tr) => {
      if (valorCategoriaMlLinha(tr)) return;
      const nome = tr.querySelector("td")?.textContent?.trim() || "";
      if (nome.length < 3) return;
      rows.push(tr);
    });
    return rows;
  }

  async function sugerirTodasNaoMapeadas() {
    const pendentes = linhasSemMapeamento();
    if (!pendentes.length) {
      feedbackCat("Todas as linhas já têm categoria ML. Nada a sugerir.", false);
      return;
    }
    const btn = el.btnModalCatSugerirTodas;
    if (btn) {
      btn.disabled = true;
      btn.classList.add("is-loading");
    }
    let ok = 0;
    let falhas = 0;
    const nomesFalha = [];
    try {
      for (let i = 0; i < pendentes.length; i++) {
        if (!modalAberto()) break;
        const tr = pendentes[i];
        const nome = tr.querySelector("td")?.textContent?.trim() || "";
        const idCategoria = parseInt(tr.dataset.catId, 10) || null;
        if (btn) btn.textContent = `Sugerindo… ${i + 1}/${pendentes.length}`;
        feedbackCat(`Sugerindo «${nome}»… (${i + 1}/${pendentes.length})`, false);
        try {
          const j = await obterSugestoesCategoria(nome, idCategoria);
          const picked = (j.itens || []).find((x) => x.nome && x.category_id);
          if (!picked) {
            falhas += 1;
            if (nomesFalha.length < 4) nomesFalha.push(nome);
            continue;
          }
          aplicarSugestaoNaLinha(tr, picked);
          ok += 1;
        } catch {
          falhas += 1;
          if (nomesFalha.length < 4) nomesFalha.push(nome);
        }
      }
      let msg = `${ok} categoria(s) sugerida(s).`;
      if (falhas) {
        msg += ` ${falhas} sem sugestão`;
        if (nomesFalha.length) {
          msg += ` (${nomesFalha.join(", ")}${falhas > nomesFalha.length ? "…" : ""})`;
        }
        msg += ". Use Escolher para buscar pelo nome.";
      } else {
        msg += " Revise e salve o mapeamento.";
      }
      feedbackCat(msg, falhas > 0 && ok === 0);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.classList.remove("is-loading");
        btn.textContent = "Sugerir não mapeadas";
      }
    }
  }

  async function aquecerCacheSugestoes() {
    const seq = prefetchSeq;
    const pendentes = (categoriasMap || []).filter((c) => (c.nome || "").trim().length >= 3);
    if (!pendentes.length) return;
    atualizarProgressoPrefetch();
    for (const c of pendentes) {
      if (seq !== prefetchSeq || !modalAberto()) return;
      const termo = String(c.nome || "").trim();
      const key = chaveCacheSugestao(c.id_categoria, termo);
      if (sugestoesCache.has(key)) {
        atualizarProgressoPrefetch();
        continue;
      }
      try {
        await obterSugestoesCategoria(termo, c.id_categoria, { forcarRede: false });
      } catch {
        /* aquecimento não bloqueia */
      }
      if (seq !== prefetchSeq) return;
      atualizarProgressoPrefetch();
    }
  }

  async function abrirModalCategorias() {
    if (!el.modalCat) return;
    limparCacheSugestoes();
    el.modalCat.showModal();
    mostrarMsgModal("Carregando categorias…", false);
    try {
      await carregarMapeamentoCategorias();
      mostrarMsgModal("Preparando sugestões…", false);
      aquecerCacheSugestoes();
    } catch (e) {
      mostrarMsgModal(e.message, true);
    }
  }

  function fecharModalCategorias() {
    limparCacheSugestoes();
    mostrarMsgModal("", false);
    el.modalCat?.close();
  }

  async function salvarMapeamentoCategorias() {
    if (!el.btnModalCatSalvar) return;
    const itens = coletarItensMapeamento();
    if (!itens.length) {
      feedbackCat("Escolha ao menos uma categoria Mercado Livre.", true);
      return;
    }
    el.btnModalCatSalvar.disabled = true;
    try {
      const r = await fetch("/api/integracoes/mercado-livre/categorias-mapeamento/salvar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ itens }),
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao salvar.");
      fecharModalCategorias();
      mostrarMsg(j.message || "Mapeamento salvo.", false);
    } catch (e) {
      feedbackCat(e.message, true);
    } finally {
      el.btnModalCatSalvar.disabled = false;
    }
  }

  async function apiBuscarCategoriasMl(termo, idCategoria, signal) {
    const qs = new URLSearchParams({ q: termo });
    if (idCategoria) qs.set("id_categoria", String(idCategoria));
    const r = await fetch(`/api/integracoes/mercado-livre/categorias/buscar?${qs}`, {
      credentials: "same-origin",
      signal,
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha na busca de categorias ML.");
    return j;
  }

  async function obterSugestoesCategoria(termo, idCategoria, opts = {}) {
    const forcarRede = !!opts.forcarRede;
    const key = chaveCacheSugestao(idCategoria, termo);
    if (!forcarRede && sugestoesCache.has(key)) {
      return sugestoesCache.get(key);
    }
    if (sugestoesInflight.has(key)) {
      return sugestoesInflight.get(key);
    }
    const ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    const timer =
      ctrl &&
      setTimeout(() => {
        try {
          ctrl.abort();
        } catch {
          /* ignore */
        }
      }, 15000);
    const prom = (async () => {
      try {
        const j = await apiBuscarCategoriasMl(termo, idCategoria, ctrl?.signal);
        const payload = {
          termo,
          itens: (j.itens || []).filter((x) => x.nome && x.category_id),
          message: j.message || "",
          fromCache: false,
        };
        sugestoesCache.set(key, { ...payload, fromCache: true });
        return payload;
      } catch (e) {
        if (e?.name === "AbortError") {
          throw new Error("A busca demorou demais. Tente de novo.");
        }
        throw e;
      } finally {
        if (timer) clearTimeout(timer);
        sugestoesInflight.delete(key);
      }
    })();
    sugestoesInflight.set(key, prom);
    return prom;
  }

  function aplicarSugestaoNaLinha(tr, picked) {
    if (!picked?.category_id || !picked?.nome) return;
    setCategoriaMlLinha(tr, picked.category_id, picked.nome);
    tr.classList.remove("is-sugerido");
    void tr.offsetWidth;
    tr.classList.add("is-sugerido");
    feedbackCat(picked.nome, false);
  }

  let pickerTr = null;
  let pickerTimer = null;

  function fecharPickerCat() {
    pickerTr = null;
    el.pickerModal?.close();
  }

  function renderPickerLista(itens, message) {
    if (!el.pickerLista) return;
    if (el.pickerHint) {
      el.pickerHint.hidden = !message;
      el.pickerHint.textContent = message || "";
    }
    if (!itens.length) {
      el.pickerLista.innerHTML =
        '<p class="Mp_Hint">Nenhum resultado. Ajuste a busca ou rode o cache em Tarefas secundárias.</p>';
      return;
    }
    el.pickerLista.innerHTML = itens
      .map(
        (x) => `<button type="button" class="Mp_PickerItem" role="option"
          data-id="${esc(x.category_id)}" data-nome="${esc(x.nome)}">
          <strong>${esc(x.nome)}</strong>
          ${x.path_nomes ? `<span>${esc(x.path_nomes)}</span>` : ""}
        </button>`
      )
      .join("");
  }

  async function buscarPicker(termo) {
    const qs = new URLSearchParams();
    if (termo) qs.set("q", termo);
    const r = await fetch(`/api/integracoes/mercado-livre/categorias/cache/buscar?${qs}`, {
      credentials: "same-origin",
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha na busca.");
    renderPickerLista(j.itens || [], j.message || "");
  }

  function abrirPickerCat(tr) {
    pickerTr = tr;
    if (!el.pickerModal) return;
    if (el.pickerBusca) el.pickerBusca.value = "";
    renderPickerLista([], "Digite para filtrar ou aguarde a lista…");
    el.pickerModal.showModal();
    buscarPicker("").catch((e) => renderPickerLista([], e.message));
    setTimeout(() => el.pickerBusca?.focus(), 50);
  }

  el.btnMapearCategorias?.addEventListener("click", () => abrirModalCategorias());
  el.btnModalCatSugerirTodas?.addEventListener("click", (ev) => {
    ev.preventDefault();
    sugerirTodasNaoMapeadas();
  });
  el.btnModalCatSalvar?.addEventListener("click", (ev) => {
    ev.preventDefault();
    salvarMapeamentoCategorias();
  });
  el.btnModalCatFechar?.addEventListener("click", () => fecharModalCategorias());
  el.btnModalCatCancelar?.addEventListener("click", () => fecharModalCategorias());
  el.modalCat?.addEventListener("close", () => {
    limparCacheSugestoes();
    mostrarMsgModal("", false);
  });
  el.tbodyCat?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".ml-btn-escolher");
    if (!btn) return;
    const tr = btn.closest("tr[data-cat-id]");
    if (tr) abrirPickerCat(tr);
  });
  el.btnPickerFechar?.addEventListener("click", () => fecharPickerCat());
  el.btnPickerCancelar?.addEventListener("click", () => fecharPickerCat());
  el.pickerModal?.addEventListener("close", () => {
    pickerTr = null;
    if (pickerTimer) {
      clearTimeout(pickerTimer);
      pickerTimer = null;
    }
  });
  el.pickerBusca?.addEventListener("input", () => {
    if (pickerTimer) clearTimeout(pickerTimer);
    pickerTimer = setTimeout(() => {
      const termo = (el.pickerBusca?.value || "").trim();
      buscarPicker(termo).catch((e) => renderPickerLista([], e.message));
    }, 280);
  });
  el.pickerLista?.addEventListener("click", (ev) => {
    const item = ev.target.closest(".Mp_PickerItem");
    if (!item || !pickerTr) return;
    setCategoriaMlLinha(pickerTr, item.dataset.id || "", item.dataset.nome || "");
    fecharPickerCat();
  });

  el.btnSyncEstoque?.addEventListener("click", () =>
    postSync(
      "/api/integracoes/mercado-livre/sync/estoque",
      el.btnSyncEstoque,
      "Enviando estoque ao Mercado Livre…"
    )
  );

  const params = new URLSearchParams(location.search);
  let aba = "pedidos";
  try {
    aba = localStorage.getItem("ml_integracao_aba") || "pedidos";
  } catch {
    /* ignore */
  }
  ativarAba(aba);

  if (params.get("conectado") === "1") {
    window.history.replaceState({}, "", location.pathname);
    if (window.Swal) {
      Swal.fire({
        icon: "success",
        title: "Conectado",
        text: "Conta Mercado Livre vinculada com sucesso.",
        confirmButtonColor: "#021F81",
      });
    }
  }
  carregarStatus();

  document.querySelectorAll(".Mp_CopyBtn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-copy");
      const node = id ? document.getElementById(id) : null;
      const text = (node?.textContent || "").trim();
      if (!text || text === "—") return;
      navigator.clipboard?.writeText(text).then(() => {
        const prev = btn.textContent;
        btn.textContent = "Copiado!";
        setTimeout(() => {
          btn.textContent = prev || "Copiar";
        }, 1200);
      });
    });
  });
})();
