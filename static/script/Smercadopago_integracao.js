(function () {
  const el = {
    badge: document.getElementById("mp_status_badge"),
    btnConectar: document.getElementById("mp_btn_conectar"),
    btnDesconectar: document.getElementById("mp_btn_desconectar"),
    painel: document.getElementById("mp_painel_config"),
    pix: document.getElementById("mp_aceita_pix"),
    cartao: document.getElementById("mp_aceita_cartao"),
    msg: document.getElementById("mp_msg"),
    webhook: document.getElementById("mp_webhook_url"),
    redirect: document.getElementById("mp_redirect_uri"),
    alertServidor: document.getElementById("mp_alert_servidor"),
    devStatus: document.getElementById("mp_dev_status"),
    contaSec: document.getElementById("mp_sec_conta"),
    contaInfo: document.getElementById("mp_conta_info"),
  };

  function setConectado(on) {
    if (el.badge) {
      el.badge.textContent = on ? "Conectado" : "Desconectado";
      el.badge.classList.toggle("is-on", on);
      el.badge.classList.toggle("is-off", !on);
    }
    if (el.btnConectar) el.btnConectar.hidden = on;
    if (el.btnDesconectar) el.btnDesconectar.hidden = !on;
    if (el.painel) el.painel.hidden = !on;
  }

  function setServidorConfigurado(ok) {
    if (el.alertServidor) el.alertServidor.hidden = !!ok;
    if (el.btnConectar) {
      if (!ok) {
        el.btnConectar.classList.add("is-disabled");
        el.btnConectar.setAttribute("aria-disabled", "true");
        el.btnConectar.addEventListener("click", (ev) => {
          ev.preventDefault();
          alert("Servidor sem MP_CLIENT_ID / MP_CLIENT_SECRET no .env. Peça ao administrador.");
        });
      }
    }
    if (el.devStatus) {
      el.devStatus.textContent = ok
        ? "Servidor: credenciais MP detectadas no .env."
        : "Servidor: MP_CLIENT_ID ou MP_CLIENT_SECRET ausente no .env.";
      el.devStatus.classList.toggle("is-erro", !ok);
    }
  }

  function mostrarMsg(t, erro) {
    if (!el.msg) return;
    el.msg.textContent = t;
    el.msg.hidden = !t;
    el.msg.classList.toggle("is-erro", !!erro);
  }

  document.querySelectorAll(".Mp_CopyBtn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.dataset.copy;
      const node = document.getElementById(id);
      const text = node?.textContent?.trim();
      if (!text || text === "—") return;
      navigator.clipboard?.writeText(text).then(() => {
        const prev = btn.textContent;
        btn.textContent = "Copiado!";
        setTimeout(() => {
          btn.textContent = prev;
        }, 1500);
      });
    });
  });

  async function carregar() {
    const r = await fetch("/api/integracoes/mercadopago/status", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const on = j.status === "conectado";
    setConectado(on);
    setServidorConfigurado(!!j.configurado_servidor);
    if (el.pix) el.pix.checked = j.aceita_pix !== false;
    if (el.cartao) el.cartao.checked = j.aceita_cartao !== false;
    if (el.webhook) el.webhook.textContent = j.webhook_url || "—";
    if (el.redirect) el.redirect.textContent = j.redirect_uri || "—";
    const conta = j.conta || {};
    if (conta.email || conta.nickname) {
      el.contaSec.hidden = false;
      el.contaInfo.textContent = [conta.email, conta.nickname].filter(Boolean).join(" · ");
    }
  }

  el.btnDesconectar?.addEventListener("click", async () => {
    if (!confirm("Desconectar Mercado Pago?")) return;
    const r = await fetch("/api/integracoes/mercadopago/desconectar", {
      method: "POST",
      credentials: "same-origin",
    });
    const j = await r.json();
    mostrarMsg(j.message || "", !j.success);
    if (j.success) {
      setConectado(false);
      el.contaSec.hidden = true;
    }
  });

  document.getElementById("mp_btn_salvar")?.addEventListener("click", async () => {
    mostrarMsg("");
    const r = await fetch("/api/integracoes/mercadopago/config/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        aceita_pix: !!el.pix?.checked,
        aceita_cartao: !!el.cartao?.checked,
      }),
    });
    const j = await r.json();
    mostrarMsg(j.message || (j.success ? "Salvo." : "Erro."), !j.success);
  });

  carregar();
  window.lucide?.createIcons?.();
})();
