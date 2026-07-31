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

  function icone(nome) {
    return window.Util?.gerarIconeTech?.(nome) ?? window.GlobalUtils?.gerarIconeTech?.(nome) ?? "";
  }

  const Hub = {
    cache: [],
    filtrado: [],
    paginaAtual: 1,
    porPagina: 20,
    totalPaginas: 1,

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
        const btn = ev.target.closest("button[data-acao]");
        if (!btn) return;
        const uuid = btn.dataset.uuid || "";
        if (!uuid) return;
        if (btn.dataset.acao === "editar") {
          this.abrirDetalhe(uuid, btn.dataset.titulo || "");
        }
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
        titulo: "Novo chamado • Central de Demandas",
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
        titulo: titulo ? `Chamado — ${titulo}` : "Chamado • Central de Demandas",
        largura: 1140,
        altura: 860,
        nivel: 1,
        modulo: "DEMANDAS",
      });
    },

    async carregar() {
      const tbody = el("dem_tbody");
      if (tbody) {
        tbody.innerHTML = `<tr class="Cl_Carregando"><td colspan="8">Carregando chamados…</td></tr>`;
      }
      try {
        const r = await fetch("/api/demandas/listar?page=1&per_page=200", {
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        const j = await r.json().catch(() => ({}));
        if (!r.ok || !j.success) throw new Error(j.message || `Erro ao carregar (${r.status}).`);
        this.cache = Array.isArray(j.chamados) ? j.chamados : [];
        this.paginaAtual = 1;
        this.aplicarFiltroPaginacao();
      } catch (e) {
        if (tbody) {
          tbody.innerHTML = `<tr><td colspan="8">${esc(e.message || "Erro ao carregar.")}</td></tr>`;
        }
      }
    },

    aplicarFiltroPaginacao() {
      const fAss = (el("dem_filtroAssunto")?.value || "").trim().toLowerCase();
      const fSt = (el("dem_filtroStatus")?.value || "").trim().toLowerCase();
      let lista = this.cache.slice();
      if (fAss) lista = lista.filter((c) => String(c.titulo || "").toLowerCase().includes(fAss));
      if (fSt) lista = lista.filter((c) => String(c.status || "").toLowerCase() === fSt);
      this.filtrado = lista;
      this.totalPaginas = lista.length ? Math.ceil(lista.length / this.porPagina) : 1;
      if (this.paginaAtual > this.totalPaginas) this.paginaAtual = this.totalPaginas;
      this.renderTabela();
      this.atualizarPaginacaoUI();
    },

    renderTabela() {
      const tbody = el("dem_tbody");
      if (!tbody) return;
      tbody.innerHTML = "";
      if (!this.filtrado.length) {
        tbody.innerHTML =
          `<tr><td colspan="8">Você ainda não abriu chamados. Clique em «+ Novo chamado».</td></tr>`;
        return;
      }
      const ini = (this.paginaAtual - 1) * this.porPagina;
      const pagina = this.filtrado.slice(ini, ini + this.porPagina);
      for (const c of pagina) {
        const uuid = c.uuid || "";
        const titulo = c.titulo || "Sem título";
        const tr = document.createElement("tr");
        tr.innerHTML = `
          <td>${esc(c.protocolo || "—")}</td>
          <td title="${esc(titulo)}">${esc(titulo)}</td>
          <td>${esc(c.categoria_label || c.categoria || "—")}</td>
          <td>${esc(c.status_label || c.status || "—")}</td>
          <td>${esc(c.prioridade_label || c.prioridade || "—")}</td>
          <td>${fmtData(c.data_abertura)}</td>
          <td>${fmtData(c.data_ultima_interacao || c.updated_at)}</td>
          <td class="col-acoes">
            <button type="button" class="Cl_BtnAcao" data-acao="editar" data-uuid="${esc(uuid)}"
              data-titulo="${esc(titulo)}" title="Visualizar e responder" aria-label="Visualizar chamado">
              ${icone("editar") || "👁"}
            </button>
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
