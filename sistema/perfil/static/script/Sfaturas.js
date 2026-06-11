/**
 * Sfaturas.js — aba Pagamentos (faturas)
 */
(function () {
  "use strict";

  const cfg = window.OSB_MEU_PERFIL || {};
  let paginaAtual = 1;

  function el(id) {
    return document.getElementById(id);
  }

  function badgeStatus(st) {
    const map = {
      pendente: "mp-badge--warn",
      pago: "mp-badge--ok",
      vencido: "mp-badge--danger",
      cancelado: "mp-badge--muted",
    };
    const cls = map[st] || "mp-badge--muted";
    const lbl = { pendente: "Pendente", pago: "Pago", vencido: "Vencido", cancelado: "Cancelado" }[st] || st;
    return '<span class="mp-badge ' + cls + '">' + lbl + "</span>";
  }

  function fmtData(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleDateString("pt-BR");
    } catch {
      return iso;
    }
  }

  function renderLista(j) {
    const corpo = el("fat-corpo");
    if (!corpo) return;
    const lista = j.faturas || [];
    if (!lista.length) {
      corpo.innerHTML = '<tr><td colspan="5" class="mp-empty">Nenhuma fatura emitida ainda.</td></tr>';
      return;
    }
    corpo.innerHTML = lista
      .map(function (f) {
        let acao = "";
        if (f.link_boleto && f.status === "pendente") {
          acao =
            '<a href="' +
            f.link_boleto +
            '" target="_blank" rel="noopener" class="Cl_botaoFiltro">Ver boleto</a>';
        }
        return (
          "<tr><td>" +
          f.referencia +
          "</td><td>" +
          (f.valor_formatado || "") +
          "</td><td>" +
          fmtData(f.vencimento_em) +
          "</td><td>" +
          badgeStatus(f.status) +
          "</td><td>" +
          acao +
          "</td></tr>"
        );
      })
      .join("");
    const pag = el("fat-paginacao");
    if (pag && j.total_paginas > 1) {
      pag.hidden = false;
      pag.textContent = "Página " + j.pagina + " de " + j.total_paginas;
    }
  }

  async function carregar(page) {
    paginaAtual = page || 1;
    if (!cfg.apiFaturas) return;
    try {
      const r = await fetch(cfg.apiFaturas + "?page=" + paginaAtual, { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (j.success) renderLista(j);
    } catch (e) {
      console.error(e);
    }
  }

  async function gerar() {
    if (!cfg.apiFaturasGerar) return;
    const ok =
      typeof Swal !== "undefined"
        ? await Swal.fire({
            title: "Gerar cobrança?",
            text: "Será criada a fatura do mês atual via Efi.",
            icon: "question",
            showCancelButton: true,
            confirmButtonText: "Gerar",
          }).then(function (r) {
            return r.isConfirmed;
          })
        : confirm("Gerar cobrança do mês?");
    if (!ok) return;
    try {
      const r = await fetch(cfg.apiFaturasGerar, { method: "POST", headers: { Accept: "application/json" } });
      const j = await r.json();
      if (typeof Swal !== "undefined") {
        Swal.fire(j.success ? "OK" : "Erro", j.message || "", j.success ? "success" : "error");
      }
      if (j.success) carregar(1);
    } catch (err) {
      console.error(err);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!el("fat-tabela")) return;
    const btn = el("fat-btn-gerar");
    if (btn) btn.hidden = false;
    btn?.addEventListener("click", gerar);
    window.addEventListener("mp-tab-change", function (ev) {
      if (ev.detail.aba === "faturas") carregar(1);
    });
    if ((cfg.abaInicial || "") === "faturas") carregar(1);
  });
})();
