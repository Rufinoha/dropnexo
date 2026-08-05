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
    btnModalCatFechar: document.getElementById("ml_modal_cat_fechar"),
    btnModalCatCancelar: document.getElementById("ml_modal_cat_cancelar"),
    avisoGratis: document.getElementById("ml_aviso_gratis"),
  };

  let categoriasMap = [];
  let salvando = false;
  let cfgAtual = {};

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

  function rotuloFonte(fonte) {
    if (fonte === "busca") return "Busca";
    if (fonte === "filtro") return "Filtro";
    return "Predictor";
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

  function renderTabelaCategorias() {
    if (!el.tbodyCat) return;
    if (!categoriasMap.length) {
      el.tbodyCat.innerHTML =
        '<tr><td colspan="4" class="Mp_Hint">Cadastre categorias em Categorias antes de mapear.</td></tr>';
      return;
    }
    el.tbodyCat.innerHTML = categoriasMap
      .map(
        (c) => `<tr data-cat-id="${c.id_categoria}">
          <td>${esc(c.nome)}</td>
          <td><input type="text" class="ml-inp-cat" value="${esc(c.ml_category_id || "")}" placeholder="MLB1234" /></td>
          <td><input type="text" class="ml-inp-fam" value="${esc(c.family_name || "")}" placeholder="Família (máx. 60)" maxlength="60" /></td>
          <td><button type="button" class="Cl_botaoFiltro Mp_CatMapBtn ml-btn-sugerir">Sugerir</button></td>
        </tr>`
      )
      .join("");
  }

  function coletarItensMapeamento() {
    const itens = [];
    el.tbodyCat?.querySelectorAll("tr[data-cat-id]").forEach((tr) => {
      const id = parseInt(tr.dataset.catId, 10);
      if (!id) return;
      const ml = tr.querySelector(".ml-inp-cat")?.value?.trim() || "";
      const fam = tr.querySelector(".ml-inp-fam")?.value?.trim() || "";
      if (ml) itens.push({ id_categoria: id, ml_category_id: ml, family_name: fam });
    });
    return itens;
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

  async function abrirModalCategorias() {
    if (!el.modalCat) return;
    el.modalCat.showModal();
    mostrarMsgModal("Carregando categorias…", false);
    try {
      await carregarMapeamentoCategorias();
      mostrarMsgModal("", false);
    } catch (e) {
      mostrarMsgModal(e.message, true);
    }
  }

  async function salvarMapeamentoCategorias() {
    if (!el.btnModalCatSalvar) return;
    const itens = coletarItensMapeamento();
    if (!itens.length) {
      feedbackCat("Informe ao menos uma categoria ML.", true);
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
      el.modalCat?.close();
      mostrarMsgModal("", false);
      mostrarMsg(j.message || "Mapeamento salvo.", false);
    } catch (e) {
      feedbackCat(e.message, true);
    } finally {
      el.btnModalCatSalvar.disabled = false;
    }
  }

  async function apiBuscarCategoriasMl(termo, idCategoria) {
    const qs = new URLSearchParams({ q: termo });
    if (idCategoria) qs.set("id_categoria", String(idCategoria));
    const r = await fetch(`/api/integracoes/mercado-livre/categorias/buscar?${qs}`, {
      credentials: "same-origin",
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha na busca de categorias ML.");
    return j;
  }

  function aplicarSugestaoNaLinha(tr, picked, nomeCategoria) {
    const inpCat = tr.querySelector(".ml-inp-cat");
    const inpFam = tr.querySelector(".ml-inp-fam");
    if (inpCat) inpCat.value = picked.category_id;
    if (inpFam && !inpFam.value.trim()) inpFam.value = (nomeCategoria || "").slice(0, 60);
    tr.classList.remove("is-sugerido");
    void tr.offsetWidth;
    tr.classList.add("is-sugerido");
    feedbackCat(`${picked.category_id} — ${picked.nome}`, false);
  }

  function htmlListaSugestoes(lista, selectedId) {
    if (!lista.length) {
      return `<div class="swal-ml-sugestao__vazio">Nenhum resultado ainda. Ajuste o termo e clique em <strong>Buscar de novo</strong>.</div>`;
    }
    return `<ul class="swal-ml-sugestao__lista" id="swalMlLista">${lista
      .map((x, i) => {
        const id = esc(x.category_id);
        const checked = (selectedId ? x.category_id === selectedId : i === 0) ? " checked" : "";
        const fonte = esc(x.fonte || "predictor");
        return `<li>
          <label class="swal-ml-sugestao__item">
            <input type="radio" name="swalMlCatPick" value="${id}"${checked} />
            <span>
              <span class="swal-ml-sugestao__nome">${esc(x.nome)}</span>
              <div class="swal-ml-sugestao__meta">${id}</div>
            </span>
            <span class="swal-ml-sugestao__badge is-${fonte}">${esc(rotuloFonte(x.fonte))}</span>
          </label>
        </li>`;
      })
      .join("")}</ul>`;
  }

  async function escolherSugestaoMl(nomeCategoria, idCategoria, listaInicial, termoInicial, msgVazia) {
    if (!window.Swal) {
      return listaInicial[0] || null;
    }
    let lista = Array.isArray(listaInicial) ? listaInicial.slice() : [];
    let termoAtual = termoInicial || nomeCategoria;

    const montarHtml = () =>
      `<div class="swal-ml-sugestao">
        <label class="swal-ml-sugestao__label" for="swalMlTermo">Termo de busca (pode editar)</label>
        <div class="swal-ml-sugestao__row">
          <input id="swalMlTermo" class="swal-ml-sugestao__input" value="${esc(termoAtual)}" maxlength="120" />
          <button type="button" class="Cl_botaoFiltro" id="swalMlBuscar">Buscar</button>
        </div>
        <div id="swalMlResultados">${htmlListaSugestoes(lista)}</div>
        ${
          !lista.length && msgVazia
            ? `<p class="swal-ml-sugestao__vazio" id="swalMlHint">${esc(msgVazia)}</p>`
            : `<p class="swal-ml-sugestao__vazio" id="swalMlHint" hidden></p>`
        }
      </div>`;

    async function refazerBusca() {
      const input = document.getElementById("swalMlTermo");
      const hint = document.getElementById("swalMlHint");
      const btn = document.getElementById("swalMlBuscar");
      const novo = (input?.value || "").trim();
      if (novo.length < 3) {
        Swal.showValidationMessage("Digite ao menos 3 caracteres.");
        return;
      }
      Swal.resetValidationMessage();
      if (btn) {
        btn.disabled = true;
        btn.textContent = "…";
      }
      try {
        const j = await apiBuscarCategoriasMl(novo, idCategoria);
        lista = j.itens || [];
        termoAtual = novo;
        const box = document.getElementById("swalMlResultados");
        if (box) box.innerHTML = htmlListaSugestoes(lista);
        if (hint) {
          if (!lista.length) {
            hint.hidden = false;
            hint.textContent =
              j.message || "Nenhuma categoria encontrada. Tente um termo mais específico.";
          } else {
            hint.hidden = true;
            hint.textContent = "";
          }
        }
      } catch (e) {
        Swal.showValidationMessage(e.message || "Falha na busca.");
      } finally {
        if (btn) {
          btn.disabled = false;
          btn.textContent = "Buscar";
        }
      }
    }

    const res = await Swal.fire({
      title: `Sugerir para «${nomeCategoria}»`,
      html: montarHtml(),
      width: 560,
      showCancelButton: true,
      confirmButtonText: "Usar esta",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
      focusConfirm: false,
      didOpen: () => {
        const input = document.getElementById("swalMlTermo");
        input?.focus();
        input?.addEventListener("keydown", (ev) => {
          if (ev.key === "Enter") {
            ev.preventDefault();
            refazerBusca();
          }
        });
        document.getElementById("swalMlBuscar")?.addEventListener("click", (ev) => {
          ev.preventDefault();
          refazerBusca();
        });
      },
      preConfirm: () => {
        const picked = document.querySelector('input[name="swalMlCatPick"]:checked')?.value;
        if (!picked) {
          Swal.showValidationMessage("Selecione uma categoria ML na lista (ou busque com outro termo).");
          return false;
        }
        return picked;
      },
    });

    if (!res.isConfirmed || !res.value) return null;
    return lista.find((x) => x.category_id === res.value) || { category_id: res.value, nome: res.value };
  }

  async function sugerirCategoriaMl(tr) {
    const nome = tr.querySelector("td")?.textContent?.trim() || "";
    const idCategoria = parseInt(tr.dataset.catId, 10) || null;
    if (nome.length < 3) {
      feedbackCat("Nome da categoria muito curto para sugerir.", true);
      return;
    }
    const btn = tr.querySelector(".ml-btn-sugerir");
    if (btn) {
      btn.disabled = true;
      btn.classList.add("is-loading");
      btn.textContent = "Buscando…";
    }
    feedbackCat(`Buscando categoria ML para «${nome}»…`, false);
    try {
      const j = await apiBuscarCategoriasMl(nome, idCategoria);
      const lista = j.itens || [];
      let picked = null;
      if (lista.length === 1 && window.Swal) {
        const conf = await Swal.fire({
          icon: "success",
          title: "Sugestão encontrada",
          html: `<p><strong>${esc(lista[0].category_id)}</strong> — ${esc(lista[0].nome)}</p>
                 <p style="font-size:0.82rem;color:#64748b;margin-top:0.5rem">Fonte: ${esc(
                   rotuloFonte(lista[0].fonte)
                 )}</p>`,
          showCancelButton: true,
          confirmButtonText: "Usar",
          cancelButtonText: "Ver outras / editar termo",
          confirmButtonColor: "#021F81",
        });
        if (conf.isConfirmed) picked = lista[0];
        else if (conf.dismiss === Swal.DismissReason.cancel) {
          picked = await escolherSugestaoMl(nome, idCategoria, lista, nome, j.message);
        }
      } else {
        picked = await escolherSugestaoMl(nome, idCategoria, lista, nome, j.message);
      }
      if (!picked) {
        if (!lista.length) feedbackCat(j.message || `Nenhuma categoria ML para «${nome}».`, true);
        else feedbackCat("", false);
        return;
      }
      aplicarSugestaoNaLinha(tr, picked, nome);
    } catch (e) {
      feedbackCat(e.message, true);
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.classList.remove("is-loading");
        btn.textContent = "Sugerir";
      }
    }
  }

  el.btnMapearCategorias?.addEventListener("click", () => abrirModalCategorias());
  el.btnModalCatSalvar?.addEventListener("click", (ev) => {
    ev.preventDefault();
    salvarMapeamentoCategorias();
  });
  el.btnModalCatFechar?.addEventListener("click", () => el.modalCat?.close());
  el.btnModalCatCancelar?.addEventListener("click", () => el.modalCat?.close());
  el.tbodyCat?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".ml-btn-sugerir");
    if (!btn) return;
    const tr = btn.closest("tr[data-cat-id]");
    if (tr) sugerirCategoriaMl(tr);
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
