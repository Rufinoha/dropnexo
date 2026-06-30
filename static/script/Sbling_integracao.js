(function () {
  const badge = document.getElementById("bl_status_badge");
  const btnConectar = document.getElementById("bl_btn_conectar");
  const btnDesconectar = document.getElementById("bl_btn_desconectar");
  const painelConfig = document.getElementById("bl_painel_config");
  const tituloModulo = document.getElementById("bl_titulo_modulo");
  const ctxInput = document.getElementById("bl_contexto_ativo");
  const logsEl = document.getElementById("bl_logs");
  const ultimaSync = document.getElementById("bl_ultima_sync");
  const btnSalvar = document.getElementById("bl_btn_salvar");
  const btnSalvarEstoque = document.getElementById("bl_btn_salvar_estoque");
  const paneConfig = document.getElementById("bl_pane_config");
  const paneEstoque = document.getElementById("bl_pane_estoque");
  const paneLogs = document.getElementById("bl_pane_logs");
  const alertDep = document.getElementById("bl_estoque_alert_dep");
  const webhookHint = document.getElementById("bl_webhook_hint");
  const syncRecebido = document.getElementById("bl_sync_recebido");
  const syncEnviado = document.getElementById("bl_sync_enviado");
  const chkReceber = document.getElementById("bl_estoque_receber");
  const chkBaixa = document.getElementById("bl_estoque_baixa");
  const syncVisual = document.getElementById("bl_sync_visual");

  let estado = {
    conectado: false,
    contexto_modulo: "fornecedor",
    configs: [],
    depositos: { vinculados: 0, pendentes: 0 },
    webhook_url: "",
    bling_conta: null,
  };

  let tabAtiva = "config";

  function cfgAtual() {
    return estado.configs.find((c) => c.contexto === estado.contexto_modulo) || {};
  }

  function cfgFornecedor() {
    return estado.configs.find((c) => c.contexto === "fornecedor") || {};
  }

  function definirVisivel(el, visivel) {
    if (!el) return;
    el.hidden = !visivel;
    el.style.display = visivel ? "" : "none";
  }

  function fmtSync(iso, rotulo) {
    if (!iso) return `${rotulo}: nunca`;
    try {
      return `${rotulo}: ${new Date(iso).toLocaleString("pt-BR")}`;
    } catch {
      return `${rotulo}: —`;
    }
  }

  function atualizarAnimacaoEstoque() {
    if (!syncVisual) return;
    const baixa = chkBaixa?.checked === true;
    const importar = chkReceber?.checked === true;
    const ativo = baixa || importar;

    syncVisual.classList.toggle("inativo", !ativo);
    syncVisual.classList.toggle("sync-out", baixa);
    syncVisual.classList.toggle("sync-in", importar);
    syncVisual.classList.toggle("sync-both", baixa && importar);
    syncVisual.setAttribute("aria-hidden", ativo ? "false" : "true");
  }

  function pickTab(tab) {
    tabAtiva = tab;
    document.querySelectorAll(".Bl_SubTab").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.blTab === tab);
    });
    definirVisivel(paneConfig, tab === "config");
    definirVisivel(paneEstoque, tab === "estoque");
    definirVisivel(paneLogs, tab === "logs");
    if (tab === "estoque") carregarDepositos().catch(() => {});
  }

  function aplicarEstoqueTela() {
    const cfg = cfgFornecedor();
    const opcoes = cfg.opcoes || {};
    if (chkReceber) {
      chkReceber.checked =
        opcoes.estoque_importar_bling !== undefined ? !!opcoes.estoque_importar_bling : true;
    }
    if (chkBaixa) chkBaixa.checked = !!opcoes.estoque_baixa_pedido;

    const vinc = Number(estado.depositos?.vinculados || 0);
    if (alertDep) alertDep.hidden = vinc > 0;

    if (syncRecebido) {
      syncRecebido.textContent = fmtSync(cfg.ultima_sync_estoque_recebido, "Recebido do Bling");
    }
    if (syncEnviado) {
      syncEnviado.textContent = fmtSync(cfg.ultima_sync_estoque_enviado, "Enviado ao Bling");
    }
    if (webhookHint) {
      const url = estado.webhook_url || "";
      webhookHint.textContent = url
        ? `Configure o webhook de Estoque no app DropNexo (Central de Extensões Bling) apontando para: ${url}`
        : "";
    }
    atualizarAnimacaoEstoque();
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
    if (tituloModulo) tituloModulo.textContent = "Configurações";
    if (ultimaSync) {
      ultimaSync.textContent = cfg.ultima_sync_produtos
        ? `Última sync produtos: ${new Date(cfg.ultima_sync_produtos).toLocaleString("pt-BR")}`
        : "";
    }
    aplicarEstoqueTela();
  }

  const CRIAR_IGUAL = "__criar_igual__";

  async function pollSyncJob(jobId) {
    const poll = async () => {
      const r = await fetch(`/api/integracoes/bling/estoque/sync-progresso/${encodeURIComponent(jobId)}`);
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Erro no progresso.");
      const p = j.progresso || {};
      Swal.update({
        html: `<p>${p.mensagem || "Sincronizando…"}</p><p><strong>${p.processados || 0}/${p.total || "?"}</strong> · ok: ${p.sincronizados || 0}</p>`,
      });
      if (p.status === "concluido") {
        await carregarStatus();
        Swal.fire({
          icon: "success",
          title: "Estoque sincronizado",
          text: p.resumo || p.mensagem || "Concluído.",
          confirmButtonColor: "#021F81",
        });
        return;
      }
      if (p.status === "erro") throw new Error(p.mensagem || "Falha na sync.");
      setTimeout(poll, 1200);
    };
    Swal.fire({
      title: "Sincronizando estoque…",
      html: "Aguarde…",
      allowOutsideClick: false,
      didOpen: () => Swal.showLoading(),
    });
    try {
      await poll();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    }
  }

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
          await carregarStatus();
          if (jj.sync_job_id && valor) {
            await pollSyncJob(jj.sync_job_id);
          } else {
            await Swal.fire({
              icon: "success",
              title: jj.criou_deposito ? "Depósito criado" : "Vínculo salvo",
              text: jj.message || "",
              timer: 1400,
              showConfirmButton: false,
            });
          }
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
    if (on && tabAtiva === "estoque") carregarDepositos().catch(() => {});
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

  async function salvarEstoque() {
    const body = {
      estoque_baixa_pedido: chkBaixa?.checked === true,
      estoque_importar_bling: chkReceber?.checked === true,
    };
    const r = await fetch("/fornecedor/importacao/bling/estoque", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "include",
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar estoque.");
    await Swal.fire({ icon: "success", title: "Salvo", timer: 1400, showConfirmButton: false });
    await carregarStatus();
  }

  document.getElementById("bl_subtabs")?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".Bl_SubTab");
    if (!btn) return;
    pickTab(btn.dataset.blTab || "config");
  });

  chkReceber?.addEventListener("change", atualizarAnimacaoEstoque);
  chkBaixa?.addEventListener("change", atualizarAnimacaoEstoque);

  btnSalvar?.addEventListener("click", async () => {
    try {
      await salvarConfig();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    }
  });

  btnSalvarEstoque?.addEventListener("click", async () => {
    try {
      await salvarEstoque();
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
    await Swal.fire({ icon: "success", title: "Desconectado", timer: 1500, showConfirmButton: false });
    await carregarStatus();
  });

  const params = new URLSearchParams(location.search);
  if (params.get("conectado") === "1") {
    Swal.fire({ icon: "success", title: "Conectado", timer: 1500, showConfirmButton: false });
    window.history.replaceState({}, "", location.pathname);
  }
  const aba = params.get("aba");
  if (aba === "estoque" || aba === "logs" || aba === "config") pickTab(aba);

  carregarStatus().catch((e) => {
    Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
  });

  window.lucide?.createIcons?.();
})();
