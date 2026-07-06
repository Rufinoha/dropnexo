(function () {
  const el = {
    badge: document.getElementById("mp_status_badge"),
    btnConectar: document.getElementById("mp_btn_conectar"),
    btnDesconectar: document.getElementById("mp_btn_desconectar"),
    painel: document.getElementById("mp_painel_config"),
    guia: document.getElementById("mp_sec_guia"),
    devSec: document.getElementById("mp_sec_dev"),
    pix: document.getElementById("mp_aceita_pix"),
    cartao: document.getElementById("mp_aceita_cartao"),
    msg: document.getElementById("mp_msg"),
    webhook: document.getElementById("mp_webhook_url"),
    redirect: document.getElementById("mp_redirect_uri"),
    alertServidor: document.getElementById("mp_alert_servidor"),
    devStatus: document.getElementById("mp_dev_status"),
    contaInfo: document.getElementById("mp_conta_info"),
  };

  let salvando = false;

  function setConectado(on) {
    if (el.badge) {
      el.badge.textContent = on ? "Conectado" : "Desconectado";
      el.badge.classList.toggle("is-on", on);
      el.badge.classList.toggle("is-off", !on);
    }
    if (el.guia) el.guia.hidden = on;
    if (el.painel) el.painel.hidden = !on;
    if (el.devSec) el.devSec.hidden = on;
  }

  function setServidorConfigurado(ok) {
    if (el.alertServidor) el.alertServidor.hidden = !!ok;
    if (el.btnConectar && !ok) {
      el.btnConectar.classList.add("is-disabled");
      el.btnConectar.setAttribute("aria-disabled", "true");
      el.btnConectar.addEventListener("click", (ev) => {
        ev.preventDefault();
        alert("Integração indisponível no servidor. Peça ao administrador.");
      });
    }
    if (el.devStatus) {
      el.devStatus.textContent = ok
        ? "Servidor: credenciais OAuth detectadas."
        : "Servidor: credenciais OAuth ausentes no .env.";
      el.devStatus.classList.toggle("is-erro", !ok);
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

  async function salvarMeios() {
    if (salvando) return;
    if (!el.pix?.checked && !el.cartao?.checked) {
      mostrarMsg("Habilite ao menos PIX ou cartão.", true);
      return;
    }
    salvando = true;
    try {
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
    } finally {
      salvando = false;
    }
  }

  async function carregar() {
    try {
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
      const rotulo = [conta.email, conta.nickname].filter(Boolean).join(" · ");
      if (el.contaInfo) {
        if (on && rotulo) {
          el.contaInfo.textContent = `Conta conectada: ${rotulo}`;
          el.contaInfo.hidden = false;
        } else {
          el.contaInfo.hidden = true;
        }
      }
    } catch (e) {
      console.warn("MP status:", e);
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
      if (el.contaInfo) el.contaInfo.hidden = true;
    }
  });

  el.pix?.addEventListener("change", salvarMeios);
  el.cartao?.addEventListener("change", salvarMeios);

  carregar();
  window.lucide?.createIcons?.();
})();
