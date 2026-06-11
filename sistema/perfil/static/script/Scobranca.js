/**
 * Scobranca.js — aba Forma de pagamento
 */
(function () {
  "use strict";

  const cfg = window.OSB_MEU_PERFIL || {};

  function el(id) {
    return document.getElementById(id);
  }

  function fmtValor(centavos) {
    const v = (centavos || 0) / 100;
    return "R$ " + v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  }

  function fmtData(iso) {
    if (!iso) return "—";
    try {
      const d = iso.length === 7 ? new Date(iso + "-01") : new Date(iso);
      return d.toLocaleDateString("pt-BR");
    } catch {
      return iso;
    }
  }

  function preencherDias() {
    const sel = el("cob-dia");
    if (!sel || sel.options.length) return;
    for (let d = 1; d <= 28; d++) {
      const o = document.createElement("option");
      o.value = String(d);
      o.textContent = String(d);
      sel.appendChild(o);
    }
  }

  function atualizarAviso(email) {
    const av = el("cob-aviso");
    if (!av) return;
    const em = email || "seu e-mail cadastrado";
    av.innerHTML =
      "<strong>Aviso:</strong> O boleto será enviado para <strong>" +
      em +
      "</strong> no início do mês da cobrança. Na falta de pagamento sua conta poderá ter funcionalidades reduzidas.";
    av.hidden = false;
  }

  async function carregar() {
    if (!cfg.apiCobranca) return;
    preencherDias();
    try {
      const r = await fetch(cfg.apiCobranca, { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.success || !j.config) return;
      const c = j.config;
      el("cob-plano").textContent = c.plano_nome || "—";
      el("cob-valor").textContent = fmtValor(c.valor_centavos);
      el("cob-periodo").textContent = c.periodicidade === "anual" ? "Anual" : "Mensal";
      el("cob-inicio").textContent = fmtData(c.inicio_cobranca);
      el("cob-forma").value = c.forma_pagamento || "boleto";
      el("cob-dia").value = String(c.dia_vencimento || 15);
      el("cob-email").value = c.email_cobranca || "";
      atualizarAviso(c.email_cobranca);
      const st = el("cob-efi-status");
      if (st) {
        st.textContent = c.efi_configurado
          ? "Integração Efi configurada."
          : "Efi não configurado — verifique o .env.";
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function salvar(ev) {
    ev.preventDefault();
    const body = {
      forma_pagamento: el("cob-forma").value,
      dia_vencimento: parseInt(el("cob-dia").value, 10),
      email_cobranca: el("cob-email").value.trim(),
    };
    try {
      const r = await fetch(cfg.apiCobrancaSalvar, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (typeof Swal !== "undefined") Swal.fire(j.success ? "Salvo" : "Erro", j.message || "", j.success ? "success" : "error");
      if (j.success) carregar();
    } catch (err) {
      if (typeof Swal !== "undefined") Swal.fire("Erro", err.message, "error");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!el("form-cobranca")) return;
    preencherDias();
    el("form-cobranca")?.addEventListener("submit", salvar);
    el("cob-email")?.addEventListener("input", function () {
      atualizarAviso(this.value.trim());
    });
    window.addEventListener("mp-tab-change", function (ev) {
      if (ev.detail.aba === "pagamento") carregar();
    });
    if ((cfg.abaInicial || "") === "pagamento") carregar();
  });
})();
