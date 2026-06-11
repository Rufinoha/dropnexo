(() => {
  "use strict";

  let aberto = false;
  let dados = [];
  let naoLidas = 0;

  const EL = {};

  function init() {
    if (!document.getElementById("fg_btnNovidades")) return;
    criarPainel();
    cachear();
    bind();
    carregar();
    document.addEventListener("visibilitychange", () => {
      if (document.visibilityState === "visible") atualizarBadge();
    });
  }

  function criarPainel() {
    const overlay = document.createElement("div");
    overlay.className = "nv-overlay";
    overlay.id = "nv_overlay";
    const painel = document.createElement("div");
    painel.className = "nv-painel";
    painel.id = "nv_painel";
    painel.innerHTML = `
      <div class="nv-header">
        <div class="nv-header-left">
          <h2>Novidades</h2>
          <span class="nv-badge-header" id="nv_badgeHeader"></span>
        </div>
        <button type="button" class="nv-btn-fechar" id="nv_btnFechar" aria-label="Fechar">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 6 6 18M6 6l12 12"/></svg>
        </button>
      </div>
      <div class="nv-acoes">
        <button type="button" class="nv-btn-lidas" id="nv_btnLidas">Marcar todas como lidas</button>
      </div>
      <div class="nv-lista" id="nv_lista"></div>`;
    document.body.appendChild(overlay);
    document.body.appendChild(painel);
  }

  function cachear() {
    EL.overlay = document.getElementById("nv_overlay");
    EL.painel = document.getElementById("nv_painel");
    EL.lista = document.getElementById("nv_lista");
    EL.btnFechar = document.getElementById("nv_btnFechar");
    EL.btnLidas = document.getElementById("nv_btnLidas");
    EL.badgeHeader = document.getElementById("nv_badgeHeader");
    EL.badgeIcone = document.getElementById("fg_novidadesBadge");
    EL.btnNovidades = document.getElementById("fg_btnNovidades");
  }

  function bind() {
    EL.btnNovidades?.addEventListener("click", (e) => {
      e.stopPropagation();
      aberto ? fechar() : abrir();
    });
    EL.btnFechar?.addEventListener("click", fechar);
    EL.overlay?.addEventListener("click", fechar);
    EL.btnLidas?.addEventListener("click", marcarLidas);
  }

  function abrir() {
    aberto = true;
    EL.overlay?.classList.add("open");
    EL.painel?.classList.add("open");
    carregar();
  }

  function fechar() {
    aberto = false;
    EL.overlay?.classList.remove("open");
    EL.painel?.classList.remove("open");
  }

  async function carregar() {
    try {
      const r = await fetch("/api/novidades");
      const j = await r.json();
      if (!r.ok) return;
      dados = j.novidades || [];
      naoLidas = j.nao_lidas || 0;
      renderLista();
      renderBadges();
    } catch (e) {
      console.warn("Novidades:", e);
    }
  }

  async function atualizarBadge() {
    try {
      const r = await fetch("/api/novidades");
      const j = await r.json();
      if (!r.ok) return;
      dados = j.novidades || [];
      naoLidas = j.nao_lidas || 0;
      renderBadges();
      if (aberto) renderLista();
    } catch (_) {}
  }

  function renderBadges() {
    const txt = naoLidas > 0 ? String(naoLidas > 99 ? "99+" : naoLidas) : "";
    if (EL.badgeHeader) EL.badgeHeader.textContent = txt;
    if (EL.badgeIcone) {
      EL.badgeIcone.textContent = txt;
      if (naoLidas > 0) {
        EL.badgeIcone.removeAttribute("hidden");
        EL.badgeIcone.classList.add("fg-novidades-badge--pulse");
      } else {
        EL.badgeIcone.setAttribute("hidden", "");
        EL.badgeIcone.classList.remove("fg-novidades-badge--pulse");
      }
    }
  }

  function renderLista() {
    if (!EL.lista) return;
    if (!dados.length) {
      EL.lista.innerHTML = '<div class="nv-vazio"><p>Nenhuma novidade por enquanto.</p></div>';
      return;
    }
    EL.lista.innerHTML = dados
      .map((n) => {
        const ini = (n.modulo || "DN").substring(0, 2).toUpperCase();
        const cls = n.lida ? "nv-card" : "nv-card nv-nao-lida";
        return `
        <div class="${cls}">
          <div class="nv-card-icone">${ini}</div>
          <div class="nv-card-corpo">
            <div class="nv-card-modulo">${esc(n.modulo)}</div>
            <div class="nv-card-desc">${esc(n.descricao)}</div>
            <div class="nv-card-data">${fmtData(n.emissao)}</div>
          </div>
        </div>`;
      })
      .join("");
  }

  async function marcarLidas() {
    if (!dados.length) return;
    const maxId = Math.max(...dados.map((n) => n.id));
    await fetch("/api/novidades/marcar-lidas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ultimo_id: maxId }),
    });
    dados.forEach((n) => { n.lida = true; });
    naoLidas = 0;
    renderLista();
    renderBadges();
  }

  function fmtData(iso) {
    if (!iso) return "";
    try {
      const d = new Date(iso);
      if (!Number.isNaN(d.getTime())) {
        return d.toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit", year: "numeric" });
      }
    } catch (_) {}
    return iso.slice(0, 10).split("-").reverse().join("/");
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
