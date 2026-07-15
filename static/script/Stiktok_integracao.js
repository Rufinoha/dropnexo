(function () {
  const PANES = {
    pedidos: document.getElementById("tt_pane_pedidos"),
    produtos: document.getElementById("tt_pane_produtos"),
    estoque: document.getElementById("tt_pane_estoque"),
  };

  const el = {
    badge: document.getElementById("tt_status_badge"),
    alertSrv: document.getElementById("tt_alert_servidor"),
    secGuia: document.getElementById("tt_sec_guia"),
    painel: document.getElementById("tt_painel_config"),
    contaInfo: document.getElementById("tt_conta_info"),
    btnDesconectar: document.getElementById("tt_btn_desconectar"),
    btnConectar: document.getElementById("tt_btn_conectar"),
    btnSync: document.getElementById("tt_btn_sync"),
    btnMapearCategorias: document.getElementById("tt_btn_mapear_categorias"),
    btnSyncEstoque: document.getElementById("tt_btn_sync_estoque"),
    pedidosAuto: document.getElementById("tt_pedidos_auto"),
    produtosAuto: document.getElementById("tt_produtos_auto"),
    estoqueAuto: document.getElementById("tt_estoque_auto"),
    webhookUrl: document.getElementById("tt_webhook_url"),
    msg: document.getElementById("tt_msg"),
    subtabs: document.getElementById("tt_subtabs"),
    modalCat: document.getElementById("tt_modal_categorias"),
    tbodyCat: document.getElementById("tt_tbody_categorias"),
    btnModalCatSalvar: document.getElementById("tt_modal_cat_salvar"),
    btnModalCatFechar: document.getElementById("tt_modal_cat_fechar"),
    btnModalCatCancelar: document.getElementById("tt_modal_cat_cancelar"),
  };

  let categoriasMap = [];
  let salvando = false;

  function ativarAba(tab) {
    const id = tab in PANES ? tab : "pedidos";
    document.querySelectorAll(".Mp_SubTab").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.ttTab === id);
    });
    Object.entries(PANES).forEach(([k, pane]) => {
      if (pane) pane.hidden = k !== id;
    });
    try {
      localStorage.setItem("tt_integracao_aba", id);
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
        alert("Integração indisponível. Configure o app TikTok Shop no servidor.");
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
    const c = cfg.shop_info || cfg.conta || {};
    const nome = c.shop_name || c.name || cfg.shop_id || "";
    if (!nome) {
      el.contaInfo?.setAttribute("hidden", "");
      return;
    }
    if (el.contaInfo) {
      el.contaInfo.hidden = false;
      el.contaInfo.textContent = [nome, cfg.shop_id && `ID ${cfg.shop_id}`].filter(Boolean).join(" · ");
    }
  }

  function aplicarConfig(cfg) {
    if (el.pedidosAuto) el.pedidosAuto.checked = !!cfg.pedidos_importar_auto;
    if (el.produtosAuto) el.produtosAuto.checked = !!cfg.produtos_exportar_auto;
    if (el.estoqueAuto) el.estoqueAuto.checked = cfg.estoque_sync_ativo !== false;
    if (el.webhookUrl) el.webhookUrl.textContent = cfg.webhook_url || "—";
    const modo = cfg.produtos_modo || "vincular_sku";
    document.querySelectorAll('input[name="tt_produtos_modo"]').forEach((r) => {
      r.checked = r.value === modo;
    });
  }

  function payloadConfig() {
    const body = {};
    if (el.pedidosAuto) body.pedidos_importar_auto = el.pedidosAuto.checked;
    if (el.produtosAuto) body.produtos_exportar_auto = el.produtosAuto.checked;
    if (el.estoqueAuto) body.estoque_sync_ativo = el.estoqueAuto.checked;
    const modo = document.querySelector('input[name="tt_produtos_modo"]:checked');
    if (modo) body.produtos_modo = modo.value;
    return body;
  }

  async function salvarConfig() {
    if (salvando) return;
    salvando = true;
    try {
      const r = await fetch("/api/integracoes/tiktok/config/salvar", {
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
      const r = await fetch("/api/integracoes/tiktok/status", { credentials: "same-origin" });
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

  document.querySelectorAll("[data-tt-config]").forEach((inp) => {
    inp.addEventListener("change", () => salvarConfig());
  });
  document.querySelectorAll('input[name="tt_produtos_modo"]').forEach((inp) => {
    inp.addEventListener("change", () => salvarConfig());
  });

  el.subtabs?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-tt-tab]");
    if (btn) ativarAba(btn.dataset.ttTab);
  });

  document.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const id = btn.dataset.copy;
      const node = document.getElementById(id);
      const txt = (node?.textContent || "").trim();
      if (!txt || txt === "—") return;
      try {
        await navigator.clipboard.writeText(txt);
        mostrarMsg("URL copiada.", false);
      } catch {
        mostrarMsg("Não foi possível copiar.", true);
      }
    });
  });

  el.btnSync?.addEventListener("click", async () => {
    el.btnSync.disabled = true;
    try {
      const r = await fetch("/api/integracoes/tiktok/sync/pedidos", {
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
      const r = await fetch("/api/integracoes/tiktok/sync/estoque", {
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
      title: "Desconectar TikTok Shop?",
      text: "A loja deixará de sincronizar até reconectar.",
      showCancelButton: true,
      confirmButtonText: "Desconectar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
    });
    if (!conf.isConfirmed) return;
    const r = await fetch("/api/integracoes/tiktok/desconectar", {
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
    const r = await fetch("/api/integracoes/tiktok/categorias-mapeamento", { credentials: "same-origin" });
    const j = await r.json();
    if (!r.ok || !j.success) {
      await Swal.fire({ icon: "error", title: "Erro", text: j.message || "Falha.", confirmButtonColor: "#021F81" });
      return;
    }
    categoriasMap = j.itens || j.categorias || [];
    if (!el.tbodyCat) return;
    el.tbodyCat.innerHTML = categoriasMap
      .map(
        (c) => `
      <tr data-id-cat="${c.id_categoria || c.id}">
        <td>${(c.nome || c.categoria_nome || "").replace(/</g, "&lt;")}</td>
        <td><input type="text" class="Mp_Input" data-tt-cat-id value="${(c.tiktok_category_id || "").replace(/"/g, "")}" placeholder="ID TikTok" /></td>
        <td><input type="text" class="Mp_Input" data-tt-cat-nome value="${(c.tiktok_category_nome || "").replace(/"/g, "")}" placeholder="Nome" /></td>
      </tr>`
      )
      .join("") || '<tr><td colspan="3" class="Mp_Hint">Nenhuma categoria encontrada.</td></tr>';
    el.modalCat?.showModal?.();
  }

  el.btnMapearCategorias?.addEventListener("click", () => abrirModalCategorias().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnModalCatFechar?.addEventListener("click", () => el.modalCat?.close?.());
  el.btnModalCatCancelar?.addEventListener("click", () => el.modalCat?.close?.());
  el.btnModalCatSalvar?.addEventListener("click", async () => {
    const itens = [...(el.tbodyCat?.querySelectorAll("tr[data-id-cat]") || [])].map((tr) => ({
      id_categoria: +tr.dataset.idCat,
      tiktok_category_id: tr.querySelector("[data-tt-cat-id]")?.value?.trim() || "",
      tiktok_category_nome: tr.querySelector("[data-tt-cat-nome]")?.value?.trim() || "",
    }));
    const r = await fetch("/api/integracoes/tiktok/categorias-mapeamento/salvar", {
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
    ativarAba(localStorage.getItem("tt_integracao_aba") || "pedidos");
  } catch {
    ativarAba("pedidos");
  }
  carregarStatus();
  window.lucide?.createIcons?.();
})();
