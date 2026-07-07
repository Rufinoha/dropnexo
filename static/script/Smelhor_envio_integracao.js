(function () {
  const el = {
    badge: document.getElementById("me_status_badge"),
    alertSrv: document.getElementById("me_alert_servidor"),
    secGuia: document.getElementById("me_sec_guia"),
    painel: document.getElementById("me_painel_config"),
    contaInfo: document.getElementById("me_conta_info"),
    btnDesconectar: document.getElementById("me_btn_desconectar"),
    btnConectar: document.getElementById("me_btn_conectar"),
    opcaoRecebimento: document.getElementById("me_opcao_recebimento"),
    opcaoMaosProprias: document.getElementById("me_opcao_maos_proprias"),
    msg: document.getElementById("me_msg"),
    diagCred: document.getElementById("me_diag_cred"),
    callbackUrl: document.getElementById("me_callback_url"),
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
        alert("Integração indisponível. Entre em contato com o suporte DropNexo.");
      });
    }
  }

  function mostrarMsg(t, erro) {
    if (!el.msg) return;
    el.msg.textContent = t;
    el.msg.hidden = !t;
    el.msg.classList.toggle("is-erro", !!erro);
    if (t && !erro) {
      setTimeout(() => {
        if (el.msg.textContent === t) el.msg.hidden = true;
      }, 2500);
    }
  }

  async function salvarPreferencias() {
    if (salvando) return;
    salvando = true;
    try {
      const r = await fetch("/api/integracoes/melhor-envio/config/salvar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          opcao_recebimento: !!el.opcaoRecebimento?.checked,
          opcao_maos_proprias: !!el.opcaoMaosProprias?.checked,
        }),
      });
      const j = await r.json();
      mostrarMsg(j.message || (j.success ? "Preferências salvas." : "Erro."), !j.success);
    } finally {
      salvando = false;
    }
  }

  async function carregarDiagnostico() {
    try {
      const r = await fetch("/api/integracoes/melhor-envio/oauth/diagnostico", { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success || !j.diagnostico) return;
      const d = j.diagnostico;
      if (el.callbackUrl && d.redirect_uri) el.callbackUrl.textContent = d.redirect_uri;
      if (el.diagCred && d.teste_credenciais) {
        const t = d.teste_credenciais;
        el.diagCred.hidden = false;
        el.diagCred.textContent = `Servidor (${d.modo_producao ? "produção" : "homologação"}): ${t.mensagem || ""}`;
        el.diagCred.classList.toggle("Mp_Hint--warn", t.ok === false);
      }
    } catch {
      /* silencioso */
    }
  }

  async function carregarStatus() {
    try {
      const r = await fetch("/api/integracoes/melhor-envio/status", { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success) return;
      const on = j.status === "conectado";
      setConectado(on);
      setServidorConfigurado(!!j.configurado_servidor);
      if (el.opcaoRecebimento) el.opcaoRecebimento.checked = !!j.opcao_recebimento;
      if (el.opcaoMaosProprias) el.opcaoMaosProprias.checked = !!j.opcao_maos_proprias;

      const conta = j.conta || {};
      const rotulo = [conta.name || conta.firstname, conta.email].filter(Boolean).join(" · ");
      if (el.contaInfo) {
        if (on && rotulo) {
          el.contaInfo.textContent = `Conta conectada: ${rotulo}`;
          el.contaInfo.hidden = false;
        } else {
          el.contaInfo.hidden = true;
        }
      }
    } catch {
      /* silencioso */
    }
  }

  el.opcaoRecebimento?.addEventListener("change", salvarPreferencias);
  el.opcaoMaosProprias?.addEventListener("change", salvarPreferencias);

  el.btnDesconectar?.addEventListener("click", async () => {
    const ok = await Swal.fire({
      title: "Desconectar Melhor Envio?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonColor: "#021F81",
      cancelButtonText: "Cancelar",
      confirmButtonText: "Desconectar",
    });
    if (!ok.isConfirmed) return;
    const r = await fetch("/api/integracoes/melhor-envio/desconectar", { method: "POST" });
    const j = await r.json();
    if (j.success) {
      setConectado(false);
      Swal.fire({ icon: "success", title: "Desconectado", timer: 1800, showConfirmButton: false });
    } else {
      Swal.fire({ icon: "error", title: "Erro", text: j.message || "Falha ao desconectar." });
    }
  });

  carregarStatus();
  carregarDiagnostico();
})();
