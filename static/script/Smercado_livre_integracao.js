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
    msg: document.getElementById("ml_msg"),
    subtabs: document.getElementById("ml_subtabs"),
    modalCat: document.getElementById("ml_modal_categorias"),
    tbodyCat: document.getElementById("ml_tbody_categorias"),
    btnModalCatSalvar: document.getElementById("ml_modal_cat_salvar"),
    btnModalCatFechar: document.getElementById("ml_modal_cat_fechar"),
    btnModalCatCancelar: document.getElementById("ml_modal_cat_cancelar"),
    taxaPreco: document.getElementById("ml_taxa_preco"),
    taxaCategoria: document.getElementById("ml_taxa_categoria"),
    btnSimularTaxas: document.getElementById("ml_btn_simular_taxas"),
    taxasResultado: document.getElementById("ml_taxas_resultado"),
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
    if (id === "produtos" && cfgAtual.conectado) {
      preencherCategoriaTaxaPadrao().then(() => simularTaxas());
    }
  }

  function fmtMoeda(v) {
    if (v == null || Number.isNaN(v)) return "—";
    return v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function parsePrecoBr(s) {
    const t = String(s || "")
      .replace(/[^\d,.-]/g, "")
      .replace(/\./g, "")
      .replace(",", ".");
    const n = parseFloat(t);
    return Number.isFinite(n) ? n : 0;
  }

  function listingTypeSelecionado() {
    return document.querySelector('input[name="ml_listing_type"]:checked')?.value || "auto";
  }

  function atualizarAvisoGratis() {
    if (!el.avisoGratis) return;
    el.avisoGratis.hidden = listingTypeSelecionado() !== "free";
  }

  async function preencherCategoriaTaxaPadrao() {
    if (!el.taxaCategoria || el.taxaCategoria.value.trim()) return;
    try {
      const r = await fetch("/api/integracoes/mercado-livre/categorias-mapeamento", {
        credentials: "same-origin",
      });
      const j = await r.json();
      if (!r.ok || !j.success) return;
      const cat = (j.itens || []).find((c) => (c.ml_category_id || "").trim());
      if (cat?.ml_category_id) el.taxaCategoria.value = cat.ml_category_id;
    } catch {
      /* silencioso */
    }
  }

  function renderTabelaTaxas(itens) {
    if (!el.taxasResultado) return;
    const sel = listingTypeSelecionado();
    if (!itens?.length) {
      el.taxasResultado.hidden = false;
      el.taxasResultado.innerHTML =
        '<p class="Mp_Hint">Nenhuma taxa retornada para este preço/categoria. O tipo Grátis pode não estar disponível.</p>';
      return;
    }
    const rows = itens
      .map((x) => {
        const isSel = sel !== "auto" && x.listing_type_id === sel;
        const pct = x.comissao_pct != null ? `${x.comissao_pct}%` : "—";
        const fixa = x.taxa_fixa != null && x.taxa_fixa > 0 ? fmtMoeda(x.taxa_fixa) : "—";
        return `<tr class="${isSel ? "is-sel" : ""}" data-lid="${esc(x.listing_type_id)}">
          <td>${esc(x.nome || x.listing_type_id)}</td>
          <td>${pct}</td>
          <td>${fmtMoeda(x.taxa_venda)}</td>
          <td>${fixa}</td>
          <td>${fmtMoeda(x.recebe_aprox)}</td>
        </tr>`;
      })
      .join("");
    el.taxasResultado.hidden = false;
    el.taxasResultado.innerHTML = `<table class="Mp_TaxasTable">
      <thead><tr>
        <th>Tipo</th><th>Comissão</th><th>Total taxas*</th><th>Taxa fixa</th><th>Você recebe~</th>
      </tr></thead>
      <tbody>${rows}</tbody>
    </table>
    <p class="Mp_Hint Mp_Hint--note">* Comissão na venda; não inclui frete grátis nem custos logísticos. Valores oficiais do Mercado Livre.</p>`;
  }

  async function simularTaxas() {
    if (!cfgAtual.conectado || !el.taxasResultado) return;
    const preco = parsePrecoBr(el.taxaPreco?.value);
    if (preco <= 0) {
      mostrarMsg("Informe um preço de referência válido.", true);
      return;
    }
    const cat = (el.taxaCategoria?.value || "").trim();
    if (el.btnSimularTaxas) el.btnSimularTaxas.disabled = true;
    try {
      const qs = new URLSearchParams({ price: String(preco) });
      if (cat) qs.set("category_id", cat);
      const r = await fetch(`/api/integracoes/mercado-livre/listing-prices?${qs}`, {
        credentials: "same-origin",
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha na simulação.");
      renderTabelaTaxas(j.itens || []);
    } catch (e) {
      mostrarMsg(e.message, true);
    } finally {
      if (el.btnSimularTaxas) el.btnSimularTaxas.disabled = false;
    }
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
      if (cfg.conectado) {
        const abaAtual = localStorage.getItem("ml_integracao_aba") || "pedidos";
        if (abaAtual === "produtos") {
          preencherCategoriaTaxaPadrao().then(() => simularTaxas());
        }
      }
    } catch {
      /* silencioso */
    }
  }

  el.subtabs?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".Mp_SubTab");
    if (!btn?.dataset.mlTab) return;
    ativarAba(btn.dataset.mlTab);
  });

  [el.pedidosAuto, el.produtosAuto, el.estoqueAuto, el.freteGratis].forEach((inp) => {
    inp?.addEventListener("change", () => salvarConfig());
  });
  document.querySelectorAll('input[name="ml_produtos_modo"]').forEach((r) => {
    r.addEventListener("change", () => salvarConfig());
  });
  document.querySelectorAll('input[name="ml_listing_type"]').forEach((r) => {
    r.addEventListener("change", () => {
      salvarConfig();
      atualizarAvisoGratis();
      const sel = listingTypeSelecionado();
      el.taxasResultado?.querySelectorAll("tbody tr").forEach((tr) => {
        tr.classList.toggle("is-sel", sel !== "auto" && tr.dataset.lid === sel);
      });
    });
  });

  el.btnSimularTaxas?.addEventListener("click", () => simularTaxas());

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
    mostrarMsg("Carregando categorias…", false);
    try {
      await carregarMapeamentoCategorias();
      mostrarMsg("", false);
      el.modalCat.showModal();
    } catch (e) {
      mostrarMsg(e.message, true);
    }
  }

  async function salvarMapeamentoCategorias() {
    if (!el.btnModalCatSalvar) return;
    const itens = coletarItensMapeamento();
    if (!itens.length) {
      mostrarMsg("Informe ao menos uma categoria ML.", true);
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
      mostrarMsg(j.message || "Mapeamento salvo.", false);
      el.modalCat?.close();
    } catch (e) {
      mostrarMsg(e.message, true);
    } finally {
      el.btnModalCatSalvar.disabled = false;
    }
  }

  async function sugerirCategoriaMl(tr) {
    const nome = tr.querySelector("td")?.textContent?.trim() || "";
    if (nome.length < 3) {
      mostrarMsg("Nome da categoria muito curto para sugerir.", true);
      return;
    }
    const btn = tr.querySelector(".ml-btn-sugerir");
    if (btn) btn.disabled = true;
    try {
      const r = await fetch(
        `/api/integracoes/mercado-livre/categorias/buscar?q=${encodeURIComponent(nome)}`,
        { credentials: "same-origin" }
      );
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha na busca.");
      const lista = j.itens || [];
      if (!lista.length) {
        mostrarMsg(`Nenhuma categoria ML sugerida para «${nome}».`, true);
        return;
      }
      let picked = lista.length === 1 ? lista[0] : null;
      if (!picked && window.Swal) {
        const opts = lista
          .map((x) => `<option value="${esc(x.category_id)}">${esc(x.category_id)} — ${esc(x.nome)}</option>`)
          .join("");
        const res = await Swal.fire({
          title: "Categoria Mercado Livre",
          html: `<select id="swalMlCat" class="swal2-select" style="width:100%">${opts}</select>`,
          showCancelButton: true,
          confirmButtonText: "Usar",
          preConfirm: () => document.getElementById("swalMlCat")?.value,
        });
        if (!res.isConfirmed || !res.value) return;
        picked = lista.find((x) => x.category_id === res.value) || lista[0];
      } else if (!picked) {
        picked = lista[0];
      }
      const inpCat = tr.querySelector(".ml-inp-cat");
      const inpFam = tr.querySelector(".ml-inp-fam");
      if (inpCat) inpCat.value = picked.category_id;
      if (inpFam && !inpFam.value.trim()) inpFam.value = nome.slice(0, 60);
      mostrarMsg(`Sugerido: ${picked.category_id}`, false);
    } catch (e) {
      mostrarMsg(e.message, true);
    } finally {
      if (btn) btn.disabled = false;
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
})();
