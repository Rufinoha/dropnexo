(() => {
  "use strict";

  const BASE = "/fornecedor/importacao";
  const qs = (s) => document.querySelector(s);

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  let idLote = null;

  function resolverIdLote() {
    if (window.__apoioContexto__?.id) return Number(window.__apoioContexto__.id);
    const p = new URLSearchParams(window.location.search).get("id");
    return p ? Number(p) : null;
  }

  async function carregar() {
    idLote = resolverIdLote();
    const intro = qs("#impErroIntro");
    const tbody = qs("#impErroTbl");
    if (!idLote) {
      if (intro) intro.textContent = "Lote não informado.";
      if (tbody) tbody.innerHTML = `<tr><td colspan="4">Informe o lote.</td></tr>`;
      return;
    }

    const r = await fetch(`${BASE}/lote/${idLote}`, { credentials: "include" });
    const j = await r.json();
    if (!r.ok || !j.success) {
      if (intro) intro.textContent = j.message || "Erro ao carregar.";
      if (tbody) tbody.innerHTML = `<tr><td colspan="4">—</td></tr>`;
      return;
    }

    const lote = j.lote || {};
    const erros = j.erros || [];
    if (intro) {
      intro.textContent = `Lote ${lote.numero || idLote} · ${erros.length} registro(s) com erro`;
    }
    if (!erros.length) {
      tbody.innerHTML = `<tr><td colspan="4">Nenhum erro neste lote.</td></tr>`;
      return;
    }
    tbody.innerHTML = erros
      .map(
        (e) =>
          `<tr>
            <td>${esc(e.linha_arquivo || e.ref_externa || "—")}</td>
            <td>${esc(e.nome || "—")}</td>
            <td>${esc(e.sku || "—")}</td>
            <td>${esc(e.mensagem)}</td>
          </tr>`
      )
      .join("");
  }

  if (window.GlobalUtils?.receberDadosApoio) {
    GlobalUtils.receberDadosApoio(() => carregar());
  }

  document.addEventListener("DOMContentLoaded", carregar);
})();
