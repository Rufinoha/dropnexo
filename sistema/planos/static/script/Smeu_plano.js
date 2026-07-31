/**
 * Smeu_plano.js — assinar plano via DropNexo Pay (checkout único)
 */
(function () {
  "use strict";

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("mpl_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
  }

  async function assinar(slugVitrine, valorCentavos, planoNome) {
    if (!cfg.apiAssinar) return;
    if (!window.DropNexoEfi || !DropNexoEfi.openCheckout) {
      if (window.Swal) {
        Swal.fire({
          icon: "error",
          title: "Pagamento",
          text: "Checkout não carregou. Recarregue a página.",
          confirmButtonColor: "#021F81",
        });
      }
      return;
    }

    const pay = await DropNexoEfi.openCheckout({
      payeeCode: cfg.efiPayeeCode || "",
      environment: cfg.efiEnvironment || "sandbox",
      valorCentavos: valorCentavos || 0,
      planoNome: planoNome || "Plano DropNexo",
      titulo: "Assinar plano",
    });
    if (!pay) return;

    if (window.Swal) {
      Swal.fire({ title: "Emitindo fatura…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    }

    try {
      const r = await fetch(cfg.apiAssinar, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({
          plano_slug: slugVitrine,
          forma_pagamento: pay.forma,
          payment_token: pay.payment_token || null,
          installments: pay.installments || 1,
        }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao assinar");
      const fat = j.fatura || {};
      let extra = "";
      if (fat.link_boleto) {
        extra =
          '<p><a href="' +
          fat.link_boleto +
          '" target="_blank" rel="noopener">Abrir boleto</a></p>';
      }
      if (window.Swal) {
        await Swal.fire({
          icon: "success",
          title: j.liberado ? "Plano liberado" : "Fatura emitida",
          html: "<p>" + (j.message || "") + "</p>" + extra,
          confirmButtonText: "Ir ao Financeiro",
          confirmButtonColor: "#021F81",
        });
      }
      if (cfg.urlFinanceiro) window.location.href = cfg.urlFinanceiro;
      else window.location.reload();
    } catch (e) {
      if (window.Swal) {
        Swal.fire({
          icon: "error",
          title: "Assinatura",
          text: e.message || "Erro",
          confirmButtonColor: "#021F81",
        });
      }
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".mpl-btn-assinar").forEach(function (btn) {
      btn.addEventListener("click", function () {
        assinar(
          btn.getAttribute("data-plano"),
          parseInt(btn.getAttribute("data-valor-centavos") || "0", 10) || 0,
          btn.getAttribute("data-plano-nome") || "Plano DropNexo"
        );
      });
    });
  });
})();
