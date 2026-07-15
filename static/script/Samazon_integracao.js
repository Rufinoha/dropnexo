(function () {
  const PANES = {
    pedidos: document.getElementById("amz_pane_pedidos"),
    produtos: document.getElementById("amz_pane_produtos"),
    estoque: document.getElementById("amz_pane_estoque"),
  };

  const el = {
    badge: document.getElementById("amz_status_badge"),
    alertSrv: document.getElementById("amz_alert_servidor"),
    secGuia: document.getElementById("amz_sec_guia"),
    painel: document.getElementById("amz_painel_config"),
    contaInfo: document.getElementById("amz_conta_info"),
    btnDesconectar: document.getElementById("amz_btn_desconectar"),
    btnConectar: document.getElementById("amz_btn_conectar"),
    btnSync: document.getElementById("amz_btn_sync"),
    btnMapearCategorias: document.getElementById("amz_btn_mapear_categorias"),
    btnSyncEstoque: document.getElementById("amz_btn_sync_estoque"),
    pedidosAuto: document.getElementById("amz_pedidos_auto"),
    produtosAuto: document.getElementById("amz_produtos_auto"),
    estoqueAuto: document.getElementById("amz_estoque_auto"),
    msg: document.getElementById("amz_msg"),
    subtabs: document.getElementById("amz_subtabs"),
    modalCat: document.getElementById("amz_modal_categorias"),
    tbodyCat: document.getElementById("amz_tbody_categorias"),
    btnModalCatSalvar: document.getElementById("amz_modal_cat_salvar"),
    btnModalCatFechar: document.getElementById("amz_modal_cat_fechar"),
    btnModalCatCancelar: document.getElementById("amz_modal_cat_cancelar"),
    ptBusca: document.getElementById("amz_pt_busca"),
    btnBuscarPt: document.getElementById("amz_btn_buscar_pt"),
    ptSugestoes: document.getElementById("amz_pt_sugestoes"),
  };

  let salvando = false;

  function ativarAba(tab) {
    const id = tab in PANES ? tab : "pedidos";
    document.querySelectorAll(".Mp_SubTab").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.amzTab === id);
    });
    Object.entries(PANES).forEach(([k, pane]) => {
      if (pane) pane.hidden = k !== id;
    });
    try {
      localStorage.setItem("amz_integracao_aba", id);
    } catch {
      /* ignore */
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
        alert("Integração indisponível. Configure o app Amazon no servidor.");
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
    const c = cfg.seller_info || cfg.conta || {};
    const nome = c.name || c.seller_name || cfg.seller_id || "";
    if (!nome && !cfg.seller_id) {
      el.contaInfo?.setAttribute("hidden", "");
      return;
    }
    if (el.contaInfo) {
      el.contaInfo.hidden = false;
      el.contaInfo.textContent = [nome, cfg.seller_id && `Seller ${cfg.seller_id}`]
        .filter(Boolean)
        .join(" · ");
    }
  }

  function aplicarConfig(cfg) {
    if (el.pedidosAuto) el.pedidosAuto.checked = !!cfg.pedidos_importar_auto;
    if (el.produtosAuto) el.produtosAuto.checked = !!cfg.produtos_exportar_auto;
    if (el.estoqueAuto) el.estoqueAuto.checked = cfg.estoque_sync_ativo !== false;
    const modo = cfg.produtos_modo || "vincular_sku";
    document.querySelectorAll('input[name="amz_produtos_modo"]').forEach((r) => {
      r.checked = r.value === modo;
    });
  }

  function payloadConfig() {
    const body = {};
    if (el.pedidosAuto) body.pedidos_importar_auto = el.pedidosAuto.checked;
    if (el.produtosAuto) body.produtos_exportar_auto = el.produtosAuto.checked;
    if (el.estoqueAuto) body.estoque_sync_ativo = el.estoqueAuto.checked;
    const modo = document.querySelector('input[name="amz_produtos_modo"]:checked');
    if (modo) body.produtos_modo = modo.value;
    return body;
  }

  async function salvarConfig() {
    if (salvando) return;
    salvando = true;
    try {
      const r = await fetch("/api/integracoes/amazon/config/salvar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payloadConfig()),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao salvar.");
      mostrarMsg(j.message || "Preferências salvas.", false);
    } catch (e) {
      mostrarMsg(e.message, true);
    } finally {
      salvando = false;
    }
  }

  async function carregarStatus() {
    try {
      const r = await fetch("/api/integracoes/amazon/status", { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success) return;
      const cfg = j.config || {};
      setServidorConfigurado(!!(cfg.configurado_servidor ?? cfg.configurado));
      setConectado(!!cfg.conectado);
      aplicarConfig(cfg);
      renderConta(cfg);
    } catch {
      /* silencioso */
    }
  }

  document.querySelectorAll("[data-amz-config]").forEach((inp) => {
    inp.addEventListener("change", () => salvarConfig());
  });
  document.querySelectorAll('input[name="amz_produtos_modo"]').forEach((inp) => {
    inp.addEventListener("change", () => salvarConfig());
  });

  el.subtabs?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-amz-tab]");
    if (btn) ativarAba(btn.dataset.amzTab);
  });

  el.btnSync?.addEventListener("click", async () => {
    el.btnSync.disabled = true;
    try {
      const r = await fetch("/api/integracoes/amazon/sync/pedidos", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha na sincronização.");
      await Swal.fire({
        icon: "success",
        title: "Pedidos",
        text: j.message || "Sincronização concluída.",
        confirmButtonColor: "#021F81",
      });
    } catch (e) {
      await Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    } finally {
      el.btnSync.disabled = false;
    }
  });

  el.btnSyncEstoque?.addEventListener("click", async () => {
    el.btnSyncEstoque.disabled = true;
    try {
      const r = await fetch("/api/integracoes/amazon/sync/estoque", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha na sincronização.");
      await Swal.fire({
        icon: "success",
        title: "Estoque",
        text: j.message || "Estoque sincronizado.",
        confirmButtonColor: "#021F81",
      });
    } catch (e) {
      await Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    } finally {
      el.btnSyncEstoque.disabled = false;
    }
  });

  el.btnDesconectar?.addEventListener("click", async () => {
    const conf = await Swal.fire({
      icon: "warning",
      title: "Desconectar Amazon?",
      text: "A conta deixará de sincronizar até reconectar.",
      showCancelButton: true,
      confirmButtonText: "Desconectar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
    });
    if (!conf.isConfirmed) return;
    const r = await fetch("/api/integracoes/amazon/desconectar", {
      method: "POST",
      credentials: "same-origin",
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) {
      await Swal.fire({ icon: "error", title: "Erro", text: j.message || "Falha.", confirmButtonColor: "#021F81" });
      return;
    }
    setConectado(false);
    mostrarMsg("Desconectado.", false);
  });

  async function abrirModalCategorias() {
    const r = await fetch("/api/integracoes/amazon/categorias-mapeamento", { credentials: "same-origin" });
    const j = await r.json();
    if (!r.ok || !j.success) {
      await Swal.fire({ icon: "error", title: "Erro", text: j.message || "Falha.", confirmButtonColor: "#021F81" });
      return;
    }
    const categoriasMap = j.itens || j.categorias || [];
    if (!el.tbodyCat) return;
    el.tbodyCat.innerHTML =
      categoriasMap
        .map(
          (c) => `
      <tr data-id-cat="${c.id_categoria || c.id}">
        <td>${(c.nome || c.categoria_nome || "").replace(/</g, "&lt;")}</td>
        <td><input type="text" class="Mp_Input" data-amz-pt value="${(c.amazon_product_type || "").replace(/"/g, "")}" placeholder="ex.: SHIRT" /></td>
      </tr>`
        )
        .join("") || '<tr><td colspan="2" class="Mp_Hint">Nenhuma categoria encontrada.</td></tr>';
    if (el.ptSugestoes) el.ptSugestoes.hidden = true;
    el.modalCat?.showModal?.();
  }

  async function buscarProductTypes() {
    const q = (el.ptBusca?.value || "").trim();
    if (!q) {
      mostrarMsg("Digite um termo para buscar product types.", true);
      return;
    }
    const r = await fetch(
      `/api/integracoes/amazon/product-types/buscar?q=${encodeURIComponent(q)}`,
      { credentials: "same-origin" }
    );
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) {
      await Swal.fire({ icon: "error", title: "Erro", text: j.message || "Falha na busca.", confirmButtonColor: "#021F81" });
      return;
    }
    const lista = j.itens || j.product_types || [];
    if (!el.ptSugestoes) return;
    if (!lista.length) {
      el.ptSugestoes.hidden = false;
      el.ptSugestoes.textContent = "Nenhum product type encontrado.";
      return;
    }
    el.ptSugestoes.hidden = false;
    el.ptSugestoes.innerHTML =
      "Sugestões (clique para usar): " +
      lista
        .slice(0, 12)
        .map((pt) => {
          const nome = typeof pt === "string" ? pt : pt.name || pt.productType || pt.product_type || "";
          return `<button type="button" class="Cl_botaoFiltro" data-amz-sugerir="${String(nome).replace(/"/g, "")}" style="margin:2px">${String(nome).replace(/</g, "&lt;")}</button>`;
        })
        .join(" ");
  }

  el.btnMapearCategorias?.addEventListener("click", () =>
    abrirModalCategorias().catch((e) => Swal.fire("Erro", e.message, "error"))
  );
  el.btnModalCatFechar?.addEventListener("click", () => el.modalCat?.close?.());
  el.btnModalCatCancelar?.addEventListener("click", () => el.modalCat?.close?.());
  el.btnBuscarPt?.addEventListener("click", () => buscarProductTypes().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.ptSugestoes?.addEventListener("click", (ev) => {
    const b = ev.target.closest("[data-amz-sugerir]");
    if (!b) return;
    const val = b.dataset.amzSugerir || "";
    const input = el.tbodyCat?.querySelector("tr input[data-amz-pt]:not([value]), tr input[data-amz-pt]");
    const firstEmpty = [...(el.tbodyCat?.querySelectorAll("input[data-amz-pt]") || [])].find((i) => !i.value.trim());
    (firstEmpty || input).value = val;
  });

  el.btnModalCatSalvar?.addEventListener("click", async () => {
    const itens = [...(el.tbodyCat?.querySelectorAll("tr[data-id-cat]") || [])].map((tr) => ({
      id_categoria: +tr.dataset.idCat,
      amazon_product_type: tr.querySelector("[data-amz-pt]")?.value?.trim() || "",
    }));
    const r = await fetch("/api/integracoes/amazon/categorias-mapeamento/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itens }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) {
      await Swal.fire({ icon: "error", title: "Erro", text: j.message || "Falha.", confirmButtonColor: "#021F81" });
      return;
    }
    el.modalCat?.close?.();
    mostrarMsg(j.message || "Categorias salvas.", false);
  });

  try {
    ativarAba(localStorage.getItem("amz_integracao_aba") || "pedidos");
  } catch {
    ativarAba("pedidos");
  }
  carregarStatus();
  window.lucide?.createIcons?.();
})();
