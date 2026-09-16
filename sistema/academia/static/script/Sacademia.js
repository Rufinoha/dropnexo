(function () {
  "use strict";

  if (window.__ACADEMIA_INIT__) return;
  window.__ACADEMIA_INIT__ = true;

  const wrap = document.querySelector(".aca-wrap");
  const podeGerenciar = wrap?.getAttribute("data-pode-gerenciar") === "1";

  const St = {
    categoria: "__TODOS__",
    q: "",
  };

  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function getVal(id) {
    return (document.getElementById(id)?.value || "").toString();
  }

  function openPlayer(id) {
    if (!(id > 0)) return;
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: `/academia/player?id=${id}`,
      titulo: "Academia DropNexo",
      largura: 1400,
      altura: 700,
      nivel: 1,
      id,
    });
  }

  function openEditar(id) {
    if (!(id > 0) || !podeGerenciar) return;
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: `/academia/editar?id=${id}`,
      titulo: "Academia DropNexo — Editar vídeo",
      largura: 760,
      altura: 720,
      nivel: 1,
      id,
    });
  }

  function openIncluir() {
    if (!podeGerenciar) return;
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: "/academia/incluir",
      titulo: "Academia DropNexo — Novo vídeo",
      largura: 760,
      altura: 720,
      nivel: 1,
    });
  }

  function bind() {
    document.getElementById("ob_btnFiltrar")?.addEventListener("click", () => {
      St.q = getVal("ob_q").trim();
      carregar();
    });

    document.getElementById("ob_q")?.addEventListener("keydown", (ev) => {
      if (ev.key !== "Enter") return;
      St.q = getVal("ob_q").trim();
      carregar();
    });

    document.getElementById("ob_btnIncluir")?.addEventListener("click", openIncluir);

    window.addEventListener("message", (event) => {
      if (!event.data) return;
      if (
        event.data.grupo === "academia:atualizar" ||
        event.data.grupo === "atualizarAcademia" ||
        event.data.grupo === "atualizarTabela"
      ) {
        carregar();
      }
    });
  }

  async function carregar() {
    const lista = document.getElementById("ob_listaCards");

    if (lista) lista.innerHTML = `<div class="aca-carregando">Carregando…</div>`;

    const r = await window.GlobalUtils?.requestJSON?.({
      url: "/academia/dados",
      method: "POST",
      payload: { categoria: St.categoria, q: St.q },
    });

    if (!r) return;
    if (!r.ok) {
      if (window.Swal?.fire) {
        Swal.fire("Erro", r.json?.message || "Falha ao carregar.", "error");
      }
      if (lista) lista.innerHTML = `<div class="aca-carregando">Falha ao carregar.</div>`;
      return;
    }

    if (r.json?.aviso) {
      if (lista) lista.innerHTML = `<div class="aca-carregando">${esc(r.json.aviso)}</div>`;
      return;
    }

    renderCategorias(r.json?.categorias || []);
    renderCards(r.json?.itens || []);
  }

  function renderCategorias(cats) {
    const elWrap = document.getElementById("ob_listaCategorias");
    if (!elWrap) return;

    const uniq = Array.from(
      new Set((cats || []).map((x) => String(x || "").trim()).filter(Boolean))
    );

    elWrap.innerHTML = [
      `<div class="aca-side-item ${St.categoria === "__TODOS__" ? "ativo" : ""}" data-cat="__TODOS__">Todos</div>`,
      ...uniq.map(
        (c) =>
          `<div class="aca-side-item ${St.categoria === c ? "ativo" : ""}" data-cat="${esc(c)}">${esc(c)}</div>`
      ),
    ].join("");

    elWrap.querySelectorAll(".aca-side-item").forEach((el) => {
      el.addEventListener("click", () => {
        elWrap.querySelectorAll(".aca-side-item").forEach((x) => x.classList.remove("ativo"));
        el.classList.add("ativo");
        St.categoria = el.getAttribute("data-cat") || "__TODOS__";
        carregar();
      });
    });
  }

  function renderCards(itens) {
    const lista = document.getElementById("ob_listaCards");
    if (!lista) return;

    if (!Array.isArray(itens) || !itens.length) {
      lista.innerHTML = `<div class="aca-carregando">Nenhum vídeo encontrado.</div>`;
      return;
    }

    lista.innerHTML = itens
      .map((v) => {
        const id = Number(v.id || 0) || 0;
        const menu = podeGerenciar
          ? `
          <button class="aca-card-menu" type="button" aria-label="Ações do vídeo" aria-haspopup="menu" aria-expanded="false" data-id="${id}">
            <span class="aca-ellipsis">⋯</span>
          </button>
          <div class="aca-card-submenu" role="menu" aria-hidden="true">
            <button type="button" class="aca-subitem" data-acao="editar" data-id="${id}">Editar</button>
            <button type="button" class="aca-subitem" data-acao="excluir" data-id="${id}">Inativar</button>
          </div>`
          : "";

        return `
        <article class="aca-card" tabindex="0" role="button" data-id="${id}">
          ${menu}
          <h3 class="aca-card-titulo">${esc(v.titulo || "")}</h3>
          <p class="aca-card-desc">${esc(v.descricao || "")}</p>
          <div class="aca-card-rodape">
            <span class="aca-chip">${esc(v.categoria || "")}</span>
            <span class="aca-duracao">${esc(v.duracao_txt || "")}</span>
          </div>
        </article>`;
      })
      .join("");

    lista.querySelectorAll(".aca-card").forEach((card) => {
      card.addEventListener("click", (ev) => {
        if (ev.target.closest(".aca-card-menu") || ev.target.closest(".aca-card-submenu")) return;
        openPlayer(Number(card.getAttribute("data-id") || 0) || 0);
      });

      card.addEventListener("keydown", (ev) => {
        if (ev.key !== "Enter" && ev.key !== " ") return;
        ev.preventDefault();
        card.click();
      });

      if (podeGerenciar) {
        card.addEventListener("contextmenu", (ev) => {
          ev.preventDefault();
          openEditar(Number(card.getAttribute("data-id") || 0) || 0);
        });
      }
    });

    if (!podeGerenciar) return;

    const closeAllMenus = () => {
      lista.querySelectorAll(".aca-card").forEach((c) => {
        c.classList.remove("menu-open");
        const btn = c.querySelector(".aca-card-menu");
        const sm = c.querySelector(".aca-card-submenu");
        if (btn) btn.setAttribute("aria-expanded", "false");
        if (sm) sm.setAttribute("aria-hidden", "true");
      });
    };

    const toggleMenu = (card) => {
      const jaAberto = card.classList.contains("menu-open");
      closeAllMenus();
      if (jaAberto) return;
      card.classList.add("menu-open");
      card.querySelector(".aca-card-menu")?.setAttribute("aria-expanded", "true");
      card.querySelector(".aca-card-submenu")?.setAttribute("aria-hidden", "false");
    };

    lista.querySelectorAll(".aca-card-menu").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        const card = btn.closest(".aca-card");
        if (card) toggleMenu(card);
      });
    });

    lista.querySelectorAll(".aca-card-submenu").forEach((sm) => {
      sm.addEventListener("click", (ev) => ev.stopPropagation());
    });

    lista.querySelectorAll(".aca-subitem").forEach((item) => {
      item.addEventListener("click", async (ev) => {
        ev.preventDefault();
        ev.stopPropagation();

        const id = Number(item.getAttribute("data-id") || 0) || 0;
        const acao = (item.getAttribute("data-acao") || "").toLowerCase();
        closeAllMenus();
        if (!(id > 0)) return;

        if (acao === "editar") {
          openEditar(id);
          return;
        }

        if (acao === "excluir") {
          if (!window.Swal?.fire) return;
          const c = await Swal.fire({
            title: "Inativar vídeo?",
            text: "O vídeo deixa de aparecer no catálogo.",
            icon: "warning",
            showCancelButton: true,
            confirmButtonText: "Inativar",
            cancelButtonText: "Cancelar",
          });
          if (!c.isConfirmed) return;

          const r = await window.GlobalUtils?.requestJSON?.({
            url: "/academia/deletar",
            method: "POST",
            payload: { id },
          });
          if (!r) return;
          if (!r.ok) {
            Swal.fire("Erro", r.json?.message || "Falha ao inativar.", "error");
            return;
          }
          Swal.fire("Sucesso", r.json?.message || "Vídeo inativado.", "success");
          carregar();
        }
      });
    });

    if (!lista.dataset.menuBound) {
      lista.dataset.menuBound = "1";
      document.addEventListener("click", (ev) => {
        if (ev.target.closest(".aca-card-menu") || ev.target.closest(".aca-card-submenu")) return;
        closeAllMenus();
      });
      document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") closeAllMenus();
      });
    }
  }

  function init() {
    bind();
    carregar();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
