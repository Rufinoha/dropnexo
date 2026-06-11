/**
 * Smeu_perfil_tabs.js — navegação entre abas da conta
 */
(function () {
  "use strict";

  const cfg = window.OSB_MEU_PERFIL || {};

  function abaAtual() {
    const p = new URLSearchParams(window.location.search);
    return p.get("aba") || cfg.abaInicial || "perfil";
  }

  function ativarAba(codigo) {
    document.querySelectorAll(".mp-tab").forEach(function (t) {
      t.classList.toggle("is-active", t.dataset.aba === codigo);
    });
    document.querySelectorAll(".mp-tab-panel").forEach(function (p) {
      const on = p.dataset.aba === codigo;
      p.classList.toggle("is-active", on);
      p.hidden = !on;
    });
    window.dispatchEvent(new CustomEvent("mp-tab-change", { detail: { aba: codigo } }));
  }

  document.addEventListener("DOMContentLoaded", function () {
    ativarAba(abaAtual());

    document.querySelectorAll(".mp-tab[data-aba]").forEach(function (tab) {
      tab.addEventListener("click", function (ev) {
        const cod = tab.dataset.aba;
        if (!cod) return;
        ev.preventDefault();
        const url = new URL(window.location.href);
        url.searchParams.set("aba", cod);
        history.pushState({}, "", url.pathname + url.search);
        ativarAba(cod);
      });
    });

    window.addEventListener("popstate", function () {
      ativarAba(abaAtual());
    });
  });
})();
