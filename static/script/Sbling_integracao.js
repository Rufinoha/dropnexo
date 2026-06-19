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

  let estado = { conectado: false, contexto_modulo: "fornecedor", configs: [] };

  function cfgAtual() {
    return estado.configs.find((c) => c.contexto === estado.contexto_modulo) || {};
  }

  function definirVisivel(el, visivel) {
    if (!el) return;
    el.hidden = !visivel;
    el.style.display = visivel ? "" : "none";
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

  const CRIAR_IGUAL = "__criar_igual__";

  async function carregarDepositos() {
    const tbody = document.getElementById("bl_tbl_depositos");
    if (!tbody) return;
    const r = await fetch("/api/integracoes/bling/depositos");
    const j = await r.json();
    if (!r.ok || !j.success) {
      tbody.innerHTML = `<tr><td colspan="3">${j.message || "Erro ao carregar depósitos."}</td></tr>`;
      return;
    }
    const dropOpts = (j.depositos_dropnexo || [])
      .map((d) => `<option value="${d.id}">${d.nome}</option>`)
      .join("");
    const bling = j.depositos_bling || [];
    if (!bling.length) {
      tbody.innerHTML = `<tr><td colspan="3">Nenhum depósito retornado pelo Bling.</td></tr>`;
      return;
    }
    const mapa = {};
    (j.mapa || []).forEach((m) => {
      mapa[m.id_bling_deposito] = m.id_deposito_dropnexo;
    });
    tbody.innerHTML = bling
      .map((b) => {
        const id = String(b.id || "");
        const nome = (b.descricao || b.nome || id).replace(/</g, "&lt;");
        const padrao = b.padrao ? "1" : "0";
        return `<tr data-bling="${id}" data-padrao="${padrao}">
          <td>${nome}</td>
          <td><select class="Bl_DepSelect"><option value="">— não vincular —</option><option value="${CRIAR_IGUAL}">— Criar igual —</option>${dropOpts}</select></td>
          <td><button type="button" class="Cl_BtnSalvar Bl_DepBtnSalvar">Salvar</button></td>
        </tr>`;
      })
      .join("");
    tbody.querySelectorAll("tr").forEach((tr) => {
      const idB = tr.dataset.bling;
      const sel = tr.querySelector(".Bl_DepSelect");
      if (sel && mapa[idB]) sel.value = String(mapa[idB]);
      tr.querySelector(".Bl_DepBtnSalvar")?.addEventListener("click", async () => {
        try {
          const valor = sel?.value || "";
          const criarIgual = valor === CRIAR_IGUAL;
          const resp = await fetch("/api/integracoes/bling/depositos/vincular", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              id_bling_deposito: idB,
              nome_bling: tr.cells[0]?.textContent?.trim(),
              id_deposito_dropnexo: criarIgual ? CRIAR_IGUAL : valor || null,
              criar_igual: criarIgual,
              padrao_bling: tr.dataset.padrao === "1",
            }),
          });
          const jj = await resp.json();
          if (!resp.ok || !jj.success) throw new Error(jj.message || "Erro.");
          await Swal.fire({
            icon: "success",
            title: jj.criou_deposito ? "Depósito criado" : "Vínculo salvo",
            text: jj.message || "",
            timer: jj.criou_deposito ? 1800 : 1200,
            showConfirmButton: false,
          });
          if (jj.criou_deposito) await carregarDepositos();
        } catch (e) {
          Swal.fire({ icon: "error", title: "Erro", text: e.message });
        }
      });
    });
  }

  function renderStatus(data) {
    estado = data;
    const on = !!data.conectado;
    if (badge) {
      badge.textContent = on ? "Conectado" : "Desconectado";
      badge.className = "Bl_ConnBadge " + (on ? "is-on" : "is-off");
    }
    definirVisivel(btnConectar, !on);
    definirVisivel(btnDesconectar, on);
    definirVisivel(painelConfig, on);
    definirVisivel(secLogs, on);

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
    if (on) carregarDepositos().catch(() => {});
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

  btnSalvar?.addEventListener("click", async () => {
    try {
      await salvarConfig();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
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
    const removido = !!j.instalacao_removida;
    const tokenMorto = !!j.token_inativo;
    const icon = removido ? "success" : tokenMorto || j.revogacao_bling ? "warning" : "warning";
    const title = removido
      ? "Desinstalado no Bling"
      : tokenMorto
        ? "Desconectado — token revogado"
        : "Desconectado no DropNexo";
    let html = `<p style="text-align:left;margin:0">${j.message || ""}</p>`;
    if (!removido) {
      html += `<hr style="margin:12px 0;border-color:#e2e8f0"><p style="text-align:left;margin:0;font-size:0.9em"><strong>No Bling (uma vez):</strong><br>Central de Extensões → Minhas instalações → DropNexo → ⋮ → <strong>Desinstalar aplicativo</strong></p>`;
    }
    if (j.revogacao_detalhes) {
      html += `<p style="text-align:left;margin:12px 0 0;font-size:0.75em;color:#64748b">${j.revogacao_detalhes}</p>`;
    }
    if (j.bling_client_id_prefix) {
      html += `<p style="text-align:left;margin:8px 0 0;font-size:0.75em;color:#64748b">Client ID servidor: ${j.bling_client_id_prefix}…</p>`;
    }
    await Swal.fire({
      icon,
      title,
      html,
      confirmButtonColor: "#021F81",
    });
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
