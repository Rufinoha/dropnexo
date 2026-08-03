(() => {
  "use strict";

  const BASE = "/fornecedor/importacao/layout";
  const MODULO = "catalogo_produto";
  let campos = [];

  const qs = (s, r = document) => r.querySelector(s);

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function paramsUrl() {
    return new URLSearchParams(window.location.search);
  }

  function modoImagens() {
    return qs("#impLayModoImg")?.value === "unico" ? "unico" : "colunas";
  }

  function syncModoUi() {
    const unico = modoImagens() === "unico";
    const wrap = qs("#impLayDelimWrap");
    if (wrap) wrap.hidden = !unico;
  }

  function notificarPai() {
    try {
      window.parent?.postMessage({ grupo: "import_layout_atualizar" }, window.location.origin);
    } catch {
      /* ignore */
    }
  }

  function renderCampos(filtro = "") {
    const tbody = qs("#impLayTblCampos");
    if (!tbody) return;
    const termo = filtro.trim().toLowerCase();
    const lista = campos.filter(
      (c) => !termo || String(c.campo_interno || "").toLowerCase().includes(termo)
    );
    if (!lista.length) {
      tbody.innerHTML = `<tr><td colspan="4">${termo ? "Nenhum campo encontrado." : "Nenhum campo carregado."}</td></tr>`;
      return;
    }
    tbody.innerHTML = lista
      .map((c, idx) => {
        const realIdx = campos.indexOf(c);
        const rotulo = c.rotulo ? ` <span class="imp-hint">(${esc(c.rotulo)})</span>` : "";
        const badge = c.obrigatorio
          ? '<span class="imp-badge-obrig">Obrigatório</span>'
          : '<span class="imp-badge-opc">Opcional</span>';
        return `<tr data-idx="${realIdx}">
          <td><input class="imp-layout-input-sm" type="number" min="1" data-k="ordem" value="${esc(c.ordem ?? idx + 1)}" /></td>
          <td><code>${esc(c.campo_interno)}</code>${rotulo}</td>
          <td><input class="imp-layout-input-sm imp-layout-input-grow" type="text" data-k="coluna_arquivo" value="${esc(c.coluna_arquivo || c.campo_interno || "")}" /></td>
          <td>${badge}</td>
        </tr>`;
      })
      .join("");
  }

  function lerCamposDaTabela() {
    const tbody = qs("#impLayTblCampos");
    if (!tbody) return;
    tbody.querySelectorAll("tr[data-idx]").forEach((tr) => {
      const idx = Number(tr.dataset.idx);
      if (!campos[idx]) return;
      const ordem = tr.querySelector('[data-k="ordem"]')?.value;
      const col = tr.querySelector('[data-k="coluna_arquivo"]')?.value;
      if (ordem != null && ordem !== "") campos[idx].ordem = Number(ordem);
      if (col != null) campos[idx].coluna_arquivo = String(col).trim();
    });
  }

  async function carregarCamposBase({ preservarMapa = false } = {}) {
    const mapaAntigo = {};
    if (preservarMapa) {
      lerCamposDaTabela();
      campos.forEach((c) => {
        if (c.campo_interno) mapaAntigo[c.campo_interno] = c.coluna_arquivo;
      });
    }
    const modo = modoImagens();
    const r = await fetch(
      `${BASE}/campos_base?modulo=${encodeURIComponent(MODULO)}&modo_imagens=${encodeURIComponent(modo)}`,
      { credentials: "include" }
    );
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar campos.");
    campos = (j.dados || []).map((c) => ({
      campo_interno: c.campo_interno,
      coluna_arquivo: mapaAntigo[c.campo_interno] || c.coluna_arquivo || c.campo_interno,
      obrigatorio: !!c.obrigatorio,
      rotulo: c.rotulo || "",
      ordem: c.ordem,
    }));
    renderCampos(qs("#impLayFiltro")?.value || "");
    qs("#impLayInfo").textContent = `${campos.length} campo(s) carregado(s).`;
  }

  async function carregarLayout(id) {
    const r = await fetch(`${BASE}/apoio?modulo=${encodeURIComponent(MODULO)}&id=${id}`, { credentials: "include" });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Layout não encontrado.");
    const layout = j.dados?.layout || {};
    qs("#impLayId").value = layout.id || id;
    qs("#impLayNome").value = layout.nome || layout.nome_layout || "";
    qs("#impLayDesc").value = layout.descricao || "";
    qs("#impLayAtivo").checked = layout.ativo !== false;
    qs("#impLayPadrao").checked = !!layout.padrao;
    qs("#impLayModoImg").value = layout.modo_imagens === "unico" ? "unico" : "colunas";
    qs("#impLayDelim").value = layout.delimitador_imagens || ";";
    syncModoUi();
    campos = (j.dados?.campos || layout.campos || []).map((c) => ({
      campo_interno: c.campo_interno,
      coluna_arquivo: c.coluna_arquivo || c.campo_interno,
      obrigatorio: !!c.obrigatorio,
      rotulo: c.rotulo || "",
      ordem: c.ordem,
    }));
    renderCampos();
    qs("#impLayInfo").textContent = `Editando layout #${layout.id}.`;
  }

  async function salvar() {
    lerCamposDaTabela();
    const nome = (qs("#impLayNome")?.value || "").trim();
    if (!nome) {
      await Swal.fire({ icon: "warning", title: "Atenção", text: "Informe o nome do layout." });
      return;
    }
    if (!campos.length) {
      await Swal.fire({ icon: "warning", title: "Atenção", text: "Carregue os campos antes de salvar." });
      return;
    }
    const idRaw = qs("#impLayId")?.value;
    const body = {
      id: idRaw ? Number(idRaw) : null,
      modulo: MODULO,
      nome,
      descricao: (qs("#impLayDesc")?.value || "").trim(),
      ativo: qs("#impLayAtivo")?.checked === true,
      padrao: qs("#impLayPadrao")?.checked === true,
      modo_imagens: modoImagens(),
      delimitador_imagens: (qs("#impLayDelim")?.value || ";").trim() || ";",
      campos,
    };
    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "include",
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao salvar.");
    notificarPai();
    await Swal.fire({ icon: "success", title: "Salvo", text: j.message, timer: 1400, showConfirmButton: false });
    if (window.GlobalUtils?.fecharJanelaApoio) {
      GlobalUtils.fecharJanelaApoio(2);
    } else if (window.parent !== window) {
      window.parent.postMessage({ grupo: "import_layout_fechar" }, window.location.origin);
    }
  }

  function bind() {
    qs("#impLayBtnCampos")?.addEventListener("click", () =>
      carregarCamposBase({ preservarMapa: true }).catch((e) => Swal.fire("Erro", e.message, "error"))
    );
    qs("#impLayFiltro")?.addEventListener("input", (ev) => renderCampos(ev.target.value || ""));
    qs("#impLayModoImg")?.addEventListener("change", () => {
      syncModoUi();
      carregarCamposBase({ preservarMapa: true }).catch((e) => Swal.fire("Erro", e.message, "error"));
    });
    qs("#impLayBtnSalvar")?.addEventListener("click", () => salvar().catch((e) => Swal.fire("Erro", e.message, "error")));
    qs("#impLayBtnCancelar")?.addEventListener("click", () => {
      if (window.GlobalUtils?.fecharJanelaApoio) GlobalUtils.fecharJanelaApoio(2);
    });
  }

  function resolverIdLayout() {
    if (window.__apoioContexto__?.id) return Number(window.__apoioContexto__.id);
    const p = paramsUrl().get("id");
    return p ? Number(p) : null;
  }

  let layoutApoioCarregado = false;

  async function initFromContext() {
    if (layoutApoioCarregado) return;
    const id = resolverIdLayout();
    try {
      syncModoUi();
      if (id) {
        await carregarLayout(id);
        layoutApoioCarregado = true;
      } else if (document.readyState !== "loading") {
        qs("#impLayInfo").textContent = "Novo layout — campos base DropNexo.";
        await carregarCamposBase();
        layoutApoioCarregado = true;
      }
    } catch (e) {
      await Swal.fire("Erro", e.message, "error");
    }
  }

  if (window.GlobalUtils?.receberDadosApoio) {
    GlobalUtils.receberDadosApoio(() => initFromContext());
  }

  document.addEventListener("DOMContentLoaded", () => {
    bind();
    initFromContext();
  });
})();
