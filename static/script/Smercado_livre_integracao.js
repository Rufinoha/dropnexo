(function () {
  const el = {
    badge: document.getElementById("ml_status_badge"),
    alertSrv: document.getElementById("ml_alert_servidor"),
    secGuia: document.getElementById("ml_sec_guia"),
    painel: document.getElementById("ml_painel_config"),
    contaInfo: document.getElementById("ml_conta_info"),
    btnDesconectar: document.getElementById("ml_btn_desconectar"),
    btnConectar: document.getElementById("ml_btn_conectar"),
    btnSync: document.getElementById("ml_btn_sync"),
    pedidosAuto: document.getElementById("ml_pedidos_auto"),
    msg: document.getElementById("ml_msg"),
  };

  let salvando = false;

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

  async function salvarConfig() {
    if (salvando || !el.pedidosAuto) return;
    salvando = true;
    try {
      const r = await fetch("/api/integracoes/mercado-livre/config/salvar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pedidos_importar_auto: el.pedidosAuto.checked }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao salvar.");
      mostrarMsg(j.message || "Salvo.", false);
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
      if (el.pedidosAuto) el.pedidosAuto.checked = !!cfg.pedidos_importar_auto;
      renderConta(cfg);
    } catch {
      /* silencioso */
    }
  }

  el.pedidosAuto?.addEventListener("change", () => salvarConfig());

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

  el.btnSync?.addEventListener("click", async () => {
    if (!el.btnSync) return;
    el.btnSync.disabled = true;
    mostrarMsg("Buscando pedidos no Mercado Livre…", false);
    try {
      const r = await fetch("/api/integracoes/mercado-livre/sync/pedidos", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha na busca.");
      mostrarMsg(j.message || "Concluído.", false);
    } catch (e) {
      mostrarMsg(e.message, true);
    } finally {
      el.btnSync.disabled = false;
    }
  });

  const params = new URLSearchParams(location.search);
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
    carregarStatus();
  } else {
    carregarStatus();
  }
})();
