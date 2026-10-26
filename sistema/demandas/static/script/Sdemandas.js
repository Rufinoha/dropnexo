(function () {
  "use strict";

  if (window.__DEMANDAS_INIT__) return;
  window.__DEMANDAS_INIT__ = true;

  function el(id) {
    return document.getElementById(id);
  }

  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function fmtData(v) {
    if (!v) return "—";
    try {
      const d = new Date(v);
      if (Number.isNaN(d.getTime())) return esc(String(v));
      return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
    } catch {
      return esc(String(v));
    }
  }

  const Hub = {
    cache: [],
    filtrado: [],
    paginaAtual: 1,
    porPagina: 20,
    totalPaginas: 1,
    operador: false,

    colspan() {
      return this.operador ? 7 : 6;
    },

    fecharMenus() {
      document.querySelectorAll(".Dem_MenuLista").forEach((menu) => {
        menu.hidden = true;
      });
      document.querySelectorAll(".Dem_MenuBtn[aria-expanded='true']").forEach((btn) => {
        btn.setAttribute("aria-expanded", "false");
      });
    },

    abrirMenu(btn) {
      const menu = btn.parentElement?.querySelector(".Dem_MenuLista");
      if (!menu) return;
      this.fecharMenus();
      menu.hidden = false;
      btn.setAttribute("aria-expanded", "true");
      const rect = btn.getBoundingClientRect();
      const largura = menu.offsetWidth || 168;
      const altura = menu.offsetHeight || 44;
      let left = rect.right - largura;
      if (left < 8) left = 8;
      let top = rect.bottom + 4;
      if (top + altura > window.innerHeight - 8) top = Math.max(8, rect.top - altura - 4);
      menu.style.left = left + "px";
      menu.style.top = top + "px";
    },

    init() {
      this.bind();
      this.carregar();
    },

    bind() {
      el("dem_btnNovo")?.addEventListener("click", () => this.abrirNovo());

      el("dem_btnFiltrar")?.addEventListener("click", () => {
        this.paginaAtual = 1;
        this.aplicarFiltroPaginacao();
      });

      el("dem_btnLimpar")?.addEventListener("click", () => {
        if (el("dem_filtroAssunto")) el("dem_filtroAssunto").value = "";
        if (el("dem_filtroStatus")) el("dem_filtroStatus").value = "";
        this.paginaAtual = 1;
        this.aplicarFiltroPaginacao();
      });

      const pag = [
        ["dem_btnPrimeiro", () => { this.paginaAtual = 1; }],
        ["dem_btnAnterior", () => { if (this.paginaAtual > 1) this.paginaAtual -= 1; }],
        ["dem_btnProximo", () => { if (this.paginaAtual < this.totalPaginas) this.paginaAtual += 1; }],
        ["dem_btnUltimo", () => { this.paginaAtual = this.totalPaginas; }],
      ];
      pag.forEach(([id, fn]) => {
        el(id)?.addEventListener("click", () => {
          fn();
          this.renderTabela();
          this.atualizarPaginacaoUI();
        });
      });

      el("dem_tbody")?.addEventListener("click", (ev) => {
        const menuBtn = ev.target.closest(".Dem_MenuBtn");
        if (menuBtn) {
          ev.stopPropagation();
          if (menuBtn.getAttribute("aria-expanded") === "true") this.fecharMenus();
          else this.abrirMenu(menuBtn);
          return;
        }
        const btn = ev.target.closest("button[data-acao]");
        if (!btn) return;
        ev.stopPropagation();
        const uuid = btn.dataset.uuid || "";
        this.fecharMenus();
        if (!uuid) return;
        if (btn.dataset.acao === "editar") {
          this.abrirDetalhe(uuid, btn.dataset.titulo || "");
        }
      });

      document.addEventListener("click", () => this.fecharMenus());
      window.addEventListener("resize", () => this.fecharMenus());
      document.querySelector(".fg-content")?.addEventListener("scroll", () => this.fecharMenus());
      el("content-area-Demandas")?.addEventListener("scroll", () => this.fecharMenus());
      document.addEventListener("keydown", (ev) => {
        if (ev.key === "Escape") this.fecharMenus();
      });

      window.addEventListener("message", (ev) => {
        if (ev.origin !== window.location.origin) return;
        const g = ev?.data?.grupo;
        if (g === "atualizarTabela" || g === "demandas_atualizar") {
          this.carregar();
        }
      });
    },

    abrirNovo() {
      if (!window.GlobalUtils?.abrirJanelaApoioModal) {
        Swal.fire("Erro", "Modal institucional não disponível.", "error");
        return;
      }
      GlobalUtils.abrirJanelaApoioModal({
        rota: "/demandas/apoio",
        titulo: "Novo chamado • Central de Chamados",
        largura: 760,
        altura: 680,
        nivel: 1,
        modulo: "DEMANDAS",
      });
    },

    abrirDetalhe(uuid, titulo) {
      if (!window.GlobalUtils?.abrirJanelaApoioModal) {
        Swal.fire("Erro", "Modal institucional não disponível.", "error");
        return;
      }
      GlobalUtils.abrirJanelaApoioModal({
        rota: "/demandas/apoio/detalhe",
        id: uuid,
        titulo: titulo ? `Chamado — ${titulo}` : "Chamado • Central de Chamados",
        largura: 1140,
        altura: 860,
        nivel: 1,
        modulo: "DEMANDAS",
      });
    },

    async carregar() {
      const tbody = el("dem_tbody");
      if (tbody) {
        tbody.innerHTML = `<tr class="Cl_Carregando"><td colspan="${this.colspan()}">Carregando chamados…</td></tr>`;
      }
      try {
        const r = await fetch("/api/demandas/listar?page=1&per_page=200", {
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.success) throw new Error(j.message || `Erro ao carregar (${r.status}).`);
        this.operador = !!j.operador;
        const col = el("dem_colConta");
        if (col) col.hidden = !this.operador;
        const sub = el("dem_sub");
        if (sub && this.operador) {
          sub.textContent = "Chamados de todas as contas. A resposta sai como Suporte DropNexo.";
        }
        this.cache = Array.isArray(j.chamados) ? j.chamados : [];
        this.paginaAtual = 1;
        this.aplicarFiltroPaginacao();
      } catch (e) {
        if (tbody) {
          tbody.innerHTML = `<tr><td colspan="${this.colspan()}">${esc(e.message || "Erro ao carregar.")}</td></tr>`;
        }
      }
    },

    aplicarFiltroPaginacao() {
      const fAss = (el("dem_filtroAssunto")?.value || "").trim().toLowerCase();
      const fSt = (el("dem_filtroStatus")?.value || "").trim().toLowerCase();
      let lista = this.cache.slice();
      if (fAss) {
        lista = lista.filter((c) => {
          const titulo = String(c.titulo || "").toLowerCase();
          const conta = String(c.tenant_nome || "").toLowerCase();
          return titulo.includes(fAss) || conta.includes(fAss);
        });
      }
      if (fSt) lista = lista.filter((c) => String(c.status || "").toLowerCase() === fSt);
      this.filtrado = lista;
      this.totalPaginas = lista.length ? Math.ceil(lista.length / this.porPagina) : 1;
      if (this.paginaAtual > this.totalPaginas) this.paginaAtual = this.totalPaginas;
      this.renderTabela();
      this.atualizarPaginacaoUI();
    },

    badgeStatus(c) {
      const cod = String(c.status || "").toLowerCase();
      const conhecidos = ["aberto", "em_atendimento", "aguardando_suporte", "aguardando_cliente", "fechado", "cancelado"];
      const cls = conhecidos.indexOf(cod) >= 0 ? cod : "outro";
      return `<span class="Dem_Badge Dem_Badge--${cls}">${esc(c.status_label || c.status || "—")}</span>`;
    },

    renderTabela() {
      const tbody = el("dem_tbody");
      if (!tbody) return;
      tbody.innerHTML = "";
      if (!this.filtrado.length) {
        tbody.innerHTML =
          `<tr><td colspan="${this.colspan()}">${
            this.operador
              ? "Nenhum chamado."
              : "Você ainda não abriu chamados. Clique em «+ Novo chamado»."
          }</td></tr>`;
        return;
      }
      const ini = (this.paginaAtual - 1) * this.porPagina;
      const pagina = this.filtrado.slice(ini, ini + this.porPagina);
      for (const c of pagina) {
        const uuid = c.uuid || "";
        const titulo = c.titulo || "Sem título";
        const tr = document.createElement("tr");
        const conta = this.operador
          ? `<td class="dem-col-conta" title="${esc(c.tenant_nome || "")}">${esc(c.tenant_nome || "—")}</td>`
          : "";
        tr.innerHTML = `
          <td class="dem-col-proto">${esc(c.protocolo || "—")}</td>
          ${conta}
          <td class="dem-col-assunto" title="${esc(titulo)}">${esc(titulo)}</td>
          <td class="dem-col-status Dem_Status">${this.badgeStatus(c)}</td>
          <td class="dem-col-data">${fmtData(c.data_abertura)}</td>
          <td class="dem-col-data">${fmtData(c.data_ultima_interacao || c.updated_at)}</td>
          <td class="dem-col-menu">
            <div class="Dem_Menu">
              <button type="button" class="Dem_MenuBtn" aria-label="Ações do chamado" aria-haspopup="menu" aria-expanded="false">⋮</button>
              <div class="Dem_MenuLista" role="menu" hidden>
                <button type="button" role="menuitem" data-acao="editar" data-uuid="${esc(uuid)}" data-titulo="${esc(titulo)}">Editar</button>
              </div>
            </div>
          </td>`;
        tbody.appendChild(tr);
      }
      try {
        window.GlobalUtils?.refreshIcons?.();
      } catch (_) {}
    },

    atualizarPaginacaoUI() {
      const set = (id, val) => {
        const n = el(id);
        if (n) n.textContent = String(val);
      };
      set("dem_paginaAtual", this.paginaAtual);
      set("dem_totalPaginas", this.totalPaginas);
      const desPrimeiro = this.paginaAtual <= 1;
      const desUltimo = this.paginaAtual >= this.totalPaginas;
      if (el("dem_btnPrimeiro")) el("dem_btnPrimeiro").disabled = desPrimeiro;
      if (el("dem_btnAnterior")) el("dem_btnAnterior").disabled = desPrimeiro;
      if (el("dem_btnProximo")) el("dem_btnProximo").disabled = desUltimo;
      if (el("dem_btnUltimo")) el("dem_btnUltimo").disabled = desUltimo;
    },
  };

  document.addEventListener("DOMContentLoaded", () => Hub.init());
})();
