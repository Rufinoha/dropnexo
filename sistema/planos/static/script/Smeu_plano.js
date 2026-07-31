/**
 * Smeu_plano.js — assinar plano (boleto / cartão via tokenizador Efi)
 */
(function () {
  "use strict";

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("mpl_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
  }

  async function escolherForma() {
    const { value: forma } = await Swal.fire({
      title: "Assinar plano",
      html:
        "<p>Escolha a forma de pagamento. O plano só é liberado após a confirmação.</p>" +
        '<select id="mpl_forma" class="swal2-select">' +
        '<option value="boleto">Boleto bancário</option>' +
        '<option value="cartao">Cartão de crédito</option>' +
        "</select>" +
        '<p style="margin:0.75rem 0 0;font-size:0.8rem;color:#94a3b8">PIX em breve.</p>',
      showCancelButton: true,
      confirmButtonText: "Continuar",
      confirmButtonColor: "#021F81",
      preConfirm: function () {
        return document.getElementById("mpl_forma")?.value || "boleto";
      },
    });
    return forma || null;
  }

  async function assinar(slugVitrine, valorCentavos) {
    if (!cfg.apiAssinar || !window.Swal) return;

    const forma = await escolherForma();
    if (!forma) return;

    let payment_token = null;
    let installments = 1;

    if (forma === "cartao") {
      if (!window.DropNexoEfi || !DropNexoEfi.promptCartao) {
        Swal.fire({
          icon: "error",
          title: "Cartão",
          text: "Script do cartão não carregou. Recarregue a página.",
          confirmButtonColor: "#021F81",
        });
        return;
      }
      const tok = await DropNexoEfi.promptCartao({
        payeeCode: cfg.efiPayeeCode || "",
        environment: cfg.efiEnvironment || "sandbox",
        valorCentavos: valorCentavos || 0,
        titulo: "Pagar assinatura",
      });
      if (!tok) return;
      payment_token = tok.payment_token;
      installments = tok.installments || 1;
    }

    Swal.fire({ title: "Emitindo fatura…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
      const r = await fetch(cfg.apiAssinar, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          plano_slug: slugVitrine,
          forma_pagamento: forma,
          payment_token: payment_token,
          installments: installments,
        }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao assinar");
      const fat = j.fatura || {};
      let extra = "";
      if (fat.link_boleto) {
        extra = '<p><a href="' + fat.link_boleto + '" target="_blank" rel="noopener">Abrir boleto</a></p>';
      }
      await Swal.fire({
        icon: "success",
        title: j.liberado ? "Plano liberado" : "Fatura emitida",
        html: "<p>" + (j.message || "") + "</p>" + extra,
        confirmButtonText: "Ir ao Financeiro",
        confirmButtonColor: "#021F81",
      });
      if (cfg.urlFinanceiro) window.location.href = cfg.urlFinanceiro;
      else window.location.reload();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Assinatura", text: e.message || "Erro", confirmButtonColor: "#021F81" });
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".mpl-btn-assinar").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const slug = btn.getAttribute("data-plano");
        const valor = parseInt(btn.getAttribute("data-valor-centavos") || "0", 10) || 0;
        assinar(slug, valor);
      });
    });
  });
})();
