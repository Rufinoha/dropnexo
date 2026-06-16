(function () {
  const badge = document.getElementById("bl_status_badge");
  const btnConectar = document.getElementById("bl_btn_conectar");
  const btnDesconectar = document.getElementById("bl_btn_desconectar");
  const painelConfig = document.getElementById("bl_painel_config");
  const painelImport = document.getElementById("bl_painel_import");
  const secLogs = document.getElementById("bl_sec_logs");
  const tituloModulo = document.getElementById("bl_titulo_modulo");
  const ctxInput = document.getElementById("bl_contexto_ativo");
  const logsEl = document.getElementById("bl_logs");
  const ultimaSync = document.getElementById("bl_ultima_sync");
  const btnSalvar = document.getElementById("bl_btn_salvar");
  const btnSyncTodos = document.getElementById("bl_btn_sync_todos");
  const btnSyncCategoria = document.getElementById("bl_btn_sync_categoria");
  const selectCategoria = document.getElementById("bl_categoria_bling");
  const chkSubcats = document.getElementById("bl_incluir_subcats");
  const selectProdutosModo = document.getElementById("bl_produtos_modo");

  let estado = { conectado: false, contexto_modulo: "fornecedor", configs: [] };
  let categoriasCarregadas = false;

  function cfgAtual() {
    return estado.configs.find((c) => c.contexto === estado.contexto_modulo) || {};
  }

  function modoPermiteImportacao() {
    const modo = selectProdutosModo?.value || cfgAtual().produtos_modo || "";
    return modo === "importar" || modo === "atualizar";
  }

  function atualizarPainelImport() {
    const mostrar = !!estado.conectado && modoPermiteImportacao();
    if (painelImport) painelImport.hidden = !mostrar;
    if (mostrar && !categoriasCarregadas) {
      carregarCategoriasBling();
    }
  }

  function aplicarConfigTela() {
    const cfg = cfgAtual();
    const map = {
      bl_modo_imagem: cfg.modo_imagem,
      bl_fonte: cfg.fonte_principal,
      bl_produtos_modo: cfg.produtos_modo,
      bl_estoque_modo: cfg.estoque_modo,
      bl_pedidos_modo: cfg.pedidos_modo,
    };
    Object.entries(map).forEach(([id, val]) => {
      const el = document.getElementById(id);
      if (el && val) el.value = val;
    });
    if (ctxInput) ctxInput.value = estado.contexto_modulo || "";
    if (tituloModulo && estado.contexto_modulo_rotulo) {
      tituloModulo.textContent = `Configuração — ${estado.contexto_modulo_rotulo}`;
    }
    if (ultimaSync) {
      ultimaSync.textContent = cfg.ultima_sync_produtos
        ? `Última sync produtos: ${new Date(cfg.ultima_sync_produtos).toLocaleString("pt-BR")}`
        : "";
    }
    atualizarPainelImport();
  }

  function renderStatus(data) {
    estado = data;
    const on = !!data.conectado;
    if (badge) {
      badge.textContent = on ? "Conectado" : "Desconectado";
      badge.className = "Bl_ConnBadge " + (on ? "is-on" : "is-off");
    }
    if (btnConectar) btnConectar.hidden = on;
    if (btnDesconectar) btnDesconectar.hidden = !on;
    if (painelConfig) painelConfig.hidden = !on;
    if (secLogs) secLogs.hidden = !on;

    if (!on) {
      categoriasCarregadas = false;
    }

    if (logsEl) {
      logsEl.innerHTML = (data.logs || [])
        .map(
          (l) =>
            `<li class="Bl_LogItem${l.status === "erro" ? " is-erro" : l.status === "aviso" ? " is-aviso" : ""}">` +
            `<strong>${l.status}</strong> — ${l.resumo || ""}` +
            (l.criado_em ? ` <span>(${new Date(l.criado_em).toLocaleString("pt-BR")})</span>` : "") +
            `</li>`
        )
        .join("") || '<li class="Bl_LogItem">Nenhum log ainda.</li>';
    }
    aplicarConfigTela();
  }

  async function carregarStatus() {
    const r = await fetch("/api/integracoes/bling/status");
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Falha ao carregar status.");
    renderStatus(j);
  }

  async function carregarCategoriasBling() {
    if (!selectCategoria) return;
    selectCategoria.disabled = true;
    if (btnSyncCategoria) btnSyncCategoria.disabled = true;
    selectCategoria.innerHTML = '<option value="">Carregando categorias…</option>';

    try {
      const r = await fetch("/api/integracoes/bling/categorias");
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao listar categorias.");

      const cats = j.categorias || [];
      if (!cats.length) {
        selectCategoria.innerHTML = '<option value="">Nenhuma categoria no Bling</option>';
        categoriasCarregadas = true;
        return;
      }

      selectCategoria.innerHTML =
        '<option value="">Selecione uma categoria…</option>' +
        cats
          .map((c) => `<option value="${c.id}">${escapeHtml(c.label || c.nome || c.id)}</option>`)
          .join("");
      selectCategoria.disabled = false;
      if (btnSyncCategoria) btnSyncCategoria.disabled = false;
      categoriasCarregadas = true;
    } catch (e) {
      selectCategoria.innerHTML = `<option value="">Erro: ${escapeHtml(e.message)}</option>`;
      categoriasCarregadas = false;
    }
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function salvarConfig() {
    const ctx = estado.contexto_modulo;
    const body = {
      contexto: ctx,
      fonte_principal: document.getElementById("bl_fonte")?.value,
      modo_imagem: document.getElementById("bl_modo_imagem")?.value,
      produtos_modo: document.getElementById("bl_produtos_modo")?.value,
      estoque_modo: document.getElementById("bl_estoque_modo")?.value,
      pedidos_modo: document.getElementById("bl_pedidos_modo")?.value,
    };
    const r = await fetch("/api/integracoes/bling/config/salvar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Erro ao salvar.");
    await Swal.fire({ icon: "success", title: "Salvo", timer: 1400, showConfirmButton: false });
    await carregarStatus();
  }

  function setBotoesImport(disabled) {
    if (btnSyncTodos) btnSyncTodos.disabled = disabled;
    if (btnSyncCategoria) btnSyncCategoria.disabled = disabled || !selectCategoria?.value;
  }

  async function syncProdutos(opcoes = {}) {
    const body = {
      contexto: estado.contexto_modulo,
      incluir_subcategorias: !!chkSubcats?.checked,
    };
    if (opcoes.id_categoria_bling) {
      body.id_categoria_bling = opcoes.id_categoria_bling;
    }

    const r = await fetch("/api/integracoes/bling/sync/produtos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Falha na sincronização.");

    const dados = j.dados || {};
    const erros = (dados.erros || []).slice(0, 5).join("\n");
    const cats = dados.categorias != null ? `\nCategorias sincronizadas: ${dados.categorias}` : "";

    await Swal.fire({
      icon: erros ? "warning" : "success",
      title: "Importação concluída",
      text: j.message + cats + (erros ? `\n\n${erros}` : ""),
      confirmButtonColor: "#021F81",
    });
    await carregarStatus();
  }

  btnSalvar?.addEventListener("click", async () => {
    try {
      await salvarConfig();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    }
  });

  selectProdutosModo?.addEventListener("change", () => {
    atualizarPainelImport();
  });

  selectCategoria?.addEventListener("change", () => {
    if (btnSyncCategoria) {
      btnSyncCategoria.disabled = !selectCategoria.value;
    }
  });

  btnSyncTodos?.addEventListener("click", async () => {
    try {
      setBotoesImport(true);
      await syncProdutos();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    } finally {
      setBotoesImport(false);
    }
  });

  btnSyncCategoria?.addEventListener("click", async () => {
    const catId = selectCategoria?.value;
    if (!catId) {
      Swal.fire({ icon: "info", title: "Selecione uma categoria", confirmButtonColor: "#021F81" });
      return;
    }
    try {
      setBotoesImport(true);
      await syncProdutos({ id_categoria_bling: catId });
    } catch (e) {
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    } finally {
      setBotoesImport(false);
    }
  });

  btnDesconectar?.addEventListener("click", async () => {
    const ok = await Swal.fire({
      title: "Desconectar Bling?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Desconectar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
    });
    if (!ok.isConfirmed) return;
    const r = await fetch("/api/integracoes/bling/desconectar", { method: "POST" });
    const j = await r.json();
    if (!j.success) {
      Swal.fire({ icon: "error", title: "Erro", text: j.message, confirmButtonColor: "#021F81" });
      return;
    }
    categoriasCarregadas = false;
    await carregarStatus();
  });

  if (new URLSearchParams(location.search).get("conectado") === "1") {
    Swal.fire({ icon: "success", title: "Conectado", timer: 1500, showConfirmButton: false });
    window.history.replaceState({}, "", location.pathname);
  }

  carregarStatus().catch((e) => {
    Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
  });

  window.lucide?.createIcons?.();
})();
