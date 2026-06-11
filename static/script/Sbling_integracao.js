(function () {
  const badge = document.getElementById("bl_status_badge");
  const btnConectar = document.getElementById("bl_btn_conectar");
  const btnDesconectar = document.getElementById("bl_btn_desconectar");
  const painelConfig = document.getElementById("bl_painel_config");
  const secLogs = document.getElementById("bl_sec_logs");
  const tituloModulo = document.getElementById("bl_titulo_modulo");
  const ctxInput = document.getElementById("bl_contexto_ativo");
  const logsEl = document.getElementById("bl_logs");
  const ultimaSync = document.getElementById("bl_ultima_sync");
  const btnSalvar = document.getElementById("bl_btn_salvar");
  const btnSync = document.getElementById("bl_btn_sync");

  let estado = { conectado: false, contexto_modulo: "fornecedor", configs: [] };

  function cfgAtual() {
    return estado.configs.find((c) => c.contexto === estado.contexto_modulo) || {};
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

  async function syncProdutos() {
    const r = await fetch("/api/integracoes/bling/sync/produtos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ contexto: estado.contexto_modulo }),
    });
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Falha na sincronização.");
    const erros = (j.dados?.erros || []).slice(0, 5).join("\n");
    await Swal.fire({
      icon: erros ? "warning" : "success",
      title: "Sincronização concluída",
      text: j.message + (erros ? `\n\n${erros}` : ""),
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

  btnSync?.addEventListener("click", async () => {
    try {
      btnSync.disabled = true;
      await syncProdutos();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    } finally {
      btnSync.disabled = false;
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
