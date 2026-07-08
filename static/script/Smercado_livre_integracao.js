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
    btnSyncProdutos: document.getElementById("ml_btn_sync_produtos"),
    btnSyncEstoque: document.getElementById("ml_btn_sync_estoque"),
    pedidosAuto: document.getElementById("ml_pedidos_auto"),
    produtosAuto: document.getElementById("ml_produtos_auto"),
    estoqueAuto: document.getElementById("ml_estoque_auto"),
    msg: document.getElementById("ml_msg"),
    subtabs: document.getElementById("ml_subtabs"),
  };

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
    const modo = cfg.produtos_modo || "vincular_sku";
    document.querySelectorAll('input[name="ml_produtos_modo"]').forEach((r) => {
      r.checked = r.value === modo;
    });
  }

  function payloadConfig(parcial) {
    const body = { ...parcial };
    if (el.pedidosAuto) body.pedidos_importar_auto = el.pedidosAuto.checked;
    if (el.produtosAuto) body.produtos_exportar_auto = el.produtosAuto.checked;
    if (el.estoqueAuto) body.estoque_sync_ativo = el.estoqueAuto.checked;
    const modo = document.querySelector('input[name="ml_produtos_modo"]:checked');
    if (modo) body.produtos_modo = modo.value;
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

  [el.pedidosAuto, el.produtosAuto, el.estoqueAuto].forEach((inp) => {
    inp?.addEventListener("change", () => salvarConfig());
  });
  document.querySelectorAll('input[name="ml_produtos_modo"]').forEach((r) => {
    r.addEventListener("change", () => salvarConfig());
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
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha.");
      mostrarMsg(j.message || "Concluído.", false);
    } catch (e) {
      mostrarMsg(e.message, true);
    } finally {
      btn.disabled = false;
    }
  }

  el.btnSync?.addEventListener("click", () =>
    postSync("/api/integracoes/mercado-livre/sync/pedidos", el.btnSync, "Buscando pedidos no Mercado Livre…")
  );
  el.btnSyncProdutos?.addEventListener("click", () =>
    postSync(
      "/api/integracoes/mercado-livre/sync/produtos",
      el.btnSyncProdutos,
      "Preparando sincronização de produtos…"
    )
  );
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
