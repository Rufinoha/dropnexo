(function () {
  const badge = document.getElementById("me_status_badge");
  const alertSrv = document.getElementById("me_alert_servidor");
  const secGuia = document.getElementById("me_sec_guia");
  const painel = document.getElementById("me_painel_config");
  const contaInfo = document.getElementById("me_conta_info");
  const btnDesconectar = document.getElementById("me_btn_desconectar");
  const redirectEl = document.getElementById("me_redirect_uri");
  const webhookEl = document.getElementById("me_webhook_url");
  const devStatus = document.getElementById("me_dev_status");

  function setConectado(on) {
    if (badge) {
      badge.textContent = on ? "Conectado" : "Desconectado";
      badge.classList.toggle("is-on", on);
      badge.classList.toggle("is-off", !on);
    }
    secGuia?.toggleAttribute("hidden", on);
    painel?.toggleAttribute("hidden", !on);
  }

  async function carregarStatus() {
    try {
      const r = await fetch("/api/integracoes/melhor-envio/status");
      const j = await r.json();
      if (!j.success) return;
      if (!j.configurado_servidor) alertSrv?.removeAttribute("hidden");
      setConectado(j.status === "conectado");
      if (redirectEl) redirectEl.textContent = j.redirect_uri || "—";
      if (webhookEl) webhookEl.textContent = j.webhook_url || "—";
      if (devStatus) {
        devStatus.textContent = j.configurado_servidor
          ? "Credenciais do app configuradas no servidor."
          : "Credenciais ME ausentes no .env.";
      }
      const conta = j.conta || {};
      const nome = conta.name || conta.firstname || conta.email;
      if (nome && contaInfo) {
        contaInfo.textContent = `Conta: ${nome}`;
        contaInfo.hidden = false;
      }
    } catch {
      /* silencioso */
    }
  }

  document.querySelectorAll("[data-copy]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-copy");
      const el = document.getElementById(id);
      const txt = el?.textContent?.trim();
      if (!txt || txt === "—") return;
      navigator.clipboard?.writeText(txt);
    });
  });

  btnDesconectar?.addEventListener("click", async () => {
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
})();
