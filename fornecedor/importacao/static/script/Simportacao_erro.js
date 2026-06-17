(() => {
  "use strict";

  const BASE = "/fornecedor/importacao";
  const qs = (s) => document.querySelector(s);

  let idLote = null;
  let errosCache = [];

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function prettyJson(obj) {
    if (obj == null) return "—";
    try {
      return JSON.stringify(obj, null, 2);
    } catch {
      return String(obj);
    }
  }

  function resolverIdLote() {
    if (window.__apoioContexto__?.id) return Number(window.__apoioContexto__.id);
    const p = new URLSearchParams(window.location.search).get("id");
    return p ? Number(p) : null;
  }

  function badgeCategoria(cat) {
    const c = esc(cat || "Importação");
    return `<span class="imp-erro-badge">${c}</span>`;
  }

  function abrirDetalhe(erro) {
    if (!erro) return;
    const pl = erro.payload || {};
    const tecnica = erro.mensagem_tecnica || pl.mensagem_tecnica || erro.mensagem || "—";
    const ref = erro.ref_externa || erro.linha_arquivo || "—";
    const dica = erro.dica || pl.dica || "Corrija o registro na origem e repita a importação.";
    const categoria = erro.categoria || pl.categoria || "Importação";

    const blocos = [
      { titulo: "Resumo Bling / linha", dados: pl.bling_resumo || pl.job || null },
      { titulo: "Payload completo", dados: pl },
    ].filter((b) => b.dados && Object.keys(b.dados).length);

    const jsonSections = blocos
      .map(
        (b) => `
        <details class="imp-erro-json-block" ${blocos.length === 1 ? "open" : ""}>
          <summary>${esc(b.titulo)}</summary>
          <pre class="imp-erro-pre">${esc(prettyJson(b.dados))}</pre>
        </details>`
      )
      .join("");

    const trace = pl.traceback
      ? `
      <details class="imp-erro-json-block imp-erro-trace">
        <summary>Stack trace (suporte técnico)</summary>
        <pre class="imp-erro-pre imp-erro-pre--muted">${esc(pl.traceback)}</pre>
      </details>`
      : "";

    Swal.fire({
      icon: "warning",
      title: "Detalhe do erro",
      width: 720,
      confirmButtonText: "Fechar",
      customClass: { popup: "imp-erro-swal" },
      html: `
        <div class="imp-erro-detalhe">
          <div class="imp-erro-detalhe-head">
            ${badgeCategoria(categoria)}
            <span class="imp-erro-ref">Ref. ${esc(ref)}</span>
          </div>
          <h4 class="imp-erro-detalhe-nome">${esc(erro.nome || "—")}</h4>
          <p class="imp-erro-detalhe-sku">SKU: <code>${esc(erro.sku || "—")}</code></p>

          <div class="imp-erro-card imp-erro-card--motivo">
            <div class="imp-erro-card-label">O que aconteceu</div>
            <p>${esc(erro.mensagem)}</p>
          </div>

          <div class="imp-erro-card imp-erro-card--dica">
            <div class="imp-erro-card-label">O que fazer</div>
            <p>${esc(dica)}</p>
          </div>

          <details class="imp-erro-json-block">
            <summary>Mensagem técnica</summary>
            <pre class="imp-erro-pre imp-erro-pre--muted">${esc(tecnica)}</pre>
          </details>

          ${jsonSections}
          ${trace}
        </div>
      `,
    });
  }

  function renderTabela(erros) {
    const tbody = qs("#impErroTbl");
    const hint = qs("#impErroHint");
    if (!tbody) return;

    if (hint) {
      hint.hidden = !erros.length;
    }

    if (!erros.length) {
      tbody.innerHTML = `<tr><td colspan="4">Nenhum erro neste lote.</td></tr>`;
      return;
    }

    tbody.innerHTML = erros
      .map((e, idx) => {
        const ref = e.linha_arquivo || e.ref_externa || "—";
        const cat = e.categoria || (e.payload && e.payload.categoria) || "";
        return `<tr class="imp-erro-row" data-idx="${idx}" title="Duplo clique para ver detalhes">
            <td>${esc(ref)}</td>
            <td>${esc(e.nome || "—")}</td>
            <td>${esc(e.sku || "—")}</td>
            <td class="imp-erro-motivo">
              ${cat ? badgeCategoria(cat) : ""}
              <span class="imp-erro-motivo-txt">${esc(e.mensagem)}</span>
            </td>
          </tr>`;
      })
      .join("");

    tbody.querySelectorAll(".imp-erro-row").forEach((tr) => {
      tr.addEventListener("dblclick", () => {
        const idx = Number(tr.dataset.idx);
        abrirDetalhe(errosCache[idx]);
      });
    });
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
    errosCache = j.erros || [];
    if (intro) {
      intro.textContent = `Lote ${lote.numero || idLote} · ${errosCache.length} registro(s) com erro`;
    }
    renderTabela(errosCache);
  }

  if (window.GlobalUtils?.receberDadosApoio) {
    GlobalUtils.receberDadosApoio(() => carregar());
  }

  document.addEventListener("DOMContentLoaded", carregar);
})();
