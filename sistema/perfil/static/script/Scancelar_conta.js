/**
 * Scancelar_conta.js — fluxo cancelar conta (3 etapas)
 */
(function () {
  "use strict";

  const cfg = window.OSB_MEU_PERFIL || {};

  function el(id) {
    return document.getElementById(id);
  }

  function showStep(n) {
    [1, 2, 3].forEach(function (i) {
      const s = el("can-step-" + i);
      if (s) {
        s.hidden = i !== n;
        s.classList.toggle("is-active", i === n);
      }
    });
  }

  function syncStep2() {
    const ok = el("can-entendi")?.checked && (el("can-motivo")?.value || "").trim().length >= 5;
    if (el("can-btn-confirmar")) el("can-btn-confirmar").disabled = !ok;
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!el("can-step-1")) return;
    showStep(1);

    el("can-btn-prosseguir")?.addEventListener("click", async function () {
      try {
        const r = await fetch(cfg.apiCancelarIniciar, { method: "POST", headers: { Accept: "application/json" } });
        const j = await r.json();
        if (j.success) showStep(2);
        else if (typeof Swal !== "undefined") Swal.fire("Erro", j.message, "error");
      } catch (e) {
        console.error(e);
      }
    });

    el("can-motivo")?.addEventListener("input", syncStep2);
    el("can-entendi")?.addEventListener("change", syncStep2);

    el("can-btn-confirmar")?.addEventListener("click", async function () {
      try {
        const r = await fetch(cfg.apiCancelarConfirmar, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ motivo: el("can-motivo").value.trim() }),
        });
        const j = await r.json();
        if (j.success) showStep(3);
        else if (typeof Swal !== "undefined") Swal.fire("Erro", j.message, "error");
      } catch (e) {
        console.error(e);
      }
    });

    el("can-btn-exportar")?.addEventListener("click", async function () {
      try {
        const r = await fetch(cfg.apiCancelarExportar, { headers: { Accept: "application/json" } });
        const j = await r.json();
        if (!j.success) return;
        const blob = new Blob([JSON.stringify(j.dados, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "dropnexo-export-" + new Date().toISOString().slice(0, 10) + ".json";
        a.click();
        URL.revokeObjectURL(a.href);
      } catch (e) {
        console.error(e);
      }
    });

    el("can-final")?.addEventListener("change", function () {
      if (el("can-btn-concluir")) el("can-btn-concluir").disabled = !this.checked;
    });

    el("can-btn-concluir")?.addEventListener("click", async function () {
      const conf =
        typeof Swal !== "undefined"
          ? await Swal.fire({
              title: "Cancelar definitivamente?",
              icon: "warning",
              showCancelButton: true,
              confirmButtonText: "Sim, cancelar",
              confirmButtonColor: "#b91c1c",
            }).then(function (r) {
              return r.isConfirmed;
            })
          : confirm("Cancelar conta definitivamente?");
      if (!conf) return;
      try {
        const r = await fetch(cfg.apiCancelarConcluir, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ confirmar: true }),
        });
        const j = await r.json();
        if (j.success && j.redirect) {
          window.location.href = j.redirect;
          return;
        }
        if (typeof Swal !== "undefined") Swal.fire(j.success ? "Conta cancelada" : "Erro", j.message || "", j.success ? "success" : "error");
      } catch (e) {
        console.error(e);
      }
    });
  });
})();
