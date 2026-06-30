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

  function pctSync(p) {
    const total = Number(p.total) || 0;
    const proc = Number(p.processados) || 0;
    if (p.status === "concluido") return 100;
    if (!total) return proc > 0 ? 5 : 0;
    return Math.min(100, Math.round((proc / total) * 100));
  }

  function htmlProgSync(mensagem) {
    const msg = mensagem || "Iniciando…";
    return (
      `<div class="Bl_DepProg">` +
      `<div class="Bl_DepProgTrack"><div class="Bl_DepProgBar" style="width:0%"></div></div>` +
      `<span class="Bl_DepProgLabel">${msg}</span></div>`
    );
  }

  async function pollSyncDeposito(tr, jobId) {
    const cell = tr.querySelector(".Bl_DepSyncCell");
    const btnSave = tr.querySelector(".Bl_DepBtnSalvar");
    if (!cell) return;
    if (btnSave) btnSave.disabled = true;
    cell.innerHTML = htmlProgSync("Iniciando…");

    const poll = async () => {
      const r = await fetch(`/api/integracoes/bling/estoque/sync-progresso/${encodeURIComponent(jobId)}`);
      const j = await r.json();
      if (r.status === 404) {
        setTimeout(poll, 1500);
        return;
      }
      if (!r.ok || !j.success) throw new Error(j.message || "Erro no progresso.");
      const p = j.progresso || {};
      const bar = cell.querySelector(".Bl_DepProgBar");
      const label = cell.querySelector(".Bl_DepProgLabel");
      const pct = pctSync(p);
      if (bar) bar.style.width = `${pct}%`;
      if (label) {
        label.textContent = p.mensagem || `Processados ${p.processados || 0}/${p.total || "?"}`;
      }
      if (p.status === "concluido") {
        cell.innerHTML = `<span class="Bl_DepSyncOk">Sincronização do depósito efetuada com sucesso</span>`;
        if (btnSave) btnSave.disabled = false;
        tr.dataset.syncPendente = "0";
        await carregarStatus();
        return;
      }
      if (p.status === "erro") throw new Error(p.mensagem || "Falha na sincronização.");
      setTimeout(poll, 1200);
    };

    try {
      await poll();
    } catch (e) {
      if (btnSave) btnSave.disabled = false;
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
      await carregarDepositos();
    }
  }

  async function iniciarSyncDeposito(tr, idBling) {
    const cell = tr.querySelector(".Bl_DepSyncCell");
    const btnSave = tr.querySelector(".Bl_DepBtnSalvar");
    if (btnSave) btnSave.disabled = true;
    if (cell) cell.innerHTML = htmlProgSync("Preparando…");

    const resp = await fetch("/api/integracoes/bling/depositos/sincronizar-estoque", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_bling_deposito: idBling }),
    });
    const jj = await resp.json();
    if (!resp.ok || !jj.success) throw new Error(jj.message || "Erro ao iniciar sincronização.");
    await pollSyncDeposito(tr, jj.sync_job_id);
  }

  function renderCelulaSync(tr, meta) {
    const cell = tr.querySelector(".Bl_DepSyncCell");
    const btnSave = tr.querySelector(".Bl_DepBtnSalvar");
    if (!cell) return;

    const vinculado = meta?.id_deposito_dropnexo;
    const pendente = !!meta?.estoque_sync_pendente;
    const job = meta?.sync_job;

    if (job?.job_id) {
      pollSyncDeposito(tr, job.job_id).catch(() => {});
      return;
    }

    if (!vinculado) {
      cell.innerHTML = "";
      if (btnSave) btnSave.disabled = false;
      tr.dataset.syncPendente = "0";
      return;
    }

    if (pendente) {
      cell.innerHTML = `<button type="button" class="Bl_DepBtnSync">Atualizar estoque</button>`;
      tr.dataset.syncPendente = "1";
      if (btnSave) btnSave.disabled = false;
      cell.querySelector(".Bl_DepBtnSync")?.addEventListener("click", async () => {
        try {
          await iniciarSyncDeposito(tr, tr.dataset.bling || "");
        } catch (e) {
          Swal.fire({ icon: "error", title: "Erro", text: e.message });
        }
      });
      return;
    }

    cell.innerHTML = "";
    tr.dataset.syncPendente = "0";
    if (btnSave) btnSave.disabled = false;
  }

  async function carregarDepositos() {
    const tbody = document.getElementById("bl_tbl_depositos");
    if (!tbody) return;
    const r = await fetch("/api/integracoes/bling/depositos");
    const j = await r.json();
    if (!r.ok || !j.success) {
      tbody.innerHTML = `<tr><td colspan="4">${j.message || "Erro ao carregar depósitos."}</td></tr>`;
      return;
    }
    const avisoBling = j.aviso_bling || "";
    const painelDep = document.getElementById("bl_painel_depositos");
    let avisoEl = document.getElementById("bl_dep_aviso_bling");
    if (avisoBling && painelDep) {
      if (!avisoEl) {
        avisoEl = document.createElement("div");
        avisoEl.id = "bl_dep_aviso_bling";
        avisoEl.className = "Bl_SyncAlert";
        avisoEl.setAttribute("role", "alert");
        painelDep.insertBefore(avisoEl, painelDep.querySelector(".Bl_DepTblWrap"));
      }
      avisoEl.textContent =
        "Lista do Bling temporariamente indisponível — exibindo depósitos já conhecidos. Tente atualizar a página em alguns minutos.";
      avisoEl.hidden = false;
    } else if (avisoEl) {
      avisoEl.hidden = true;
    }
    const dropOpts = (j.depositos_dropnexo || [])
      .map((d) => `<option value="${d.id}">${d.nome}</option>`)
      .join("");
    const bling = j.depositos_bling || [];
    if (!bling.length) {
      tbody.innerHTML = `<tr><td colspan="4">Nenhum depósito retornado pelo Bling.</td></tr>`;
      return;
    }
    const mapa = {};
    (j.mapa || []).forEach((m) => {
      mapa[m.id_bling_deposito] = m;
    });
    tbody.innerHTML = bling
      .map((b) => {
        const id = String(b.id || "");
        const nome = (b.descricao || b.nome || id).replace(/</g, "&lt;");
        const padrao = b.padrao ? "1" : "0";
        return `<tr data-bling="${id}" data-padrao="${padrao}" data-saved-drop="">
          <td>${nome}</td>
          <td><select class="Bl_DepSelect"><option value="">— não vincular —</option><option value="${CRIAR_IGUAL}">— Criar igual —</option>${dropOpts}</select></td>
          <td class="Bl_DepSyncCell"></td>
          <td><button type="button" class="Cl_BtnSalvar Bl_DepBtnSalvar">Salvar</button></td>
        </tr>`;
      })
      .join("");
    tbody.querySelectorAll("tr").forEach((tr) => {
      const idB = tr.dataset.bling;
      const meta = mapa[idB] || {};
      const sel = tr.querySelector(".Bl_DepSelect");
      const saved = meta.id_deposito_dropnexo ? String(meta.id_deposito_dropnexo) : "";
      if (sel && saved) sel.value = saved;
      tr.dataset.savedDrop = saved;

      renderCelulaSync(tr, meta);

      sel?.addEventListener("change", () => {
        const mudou = (sel.value || "") !== (tr.dataset.savedDrop || "");
        if (!mudou && tr.dataset.syncPendente !== "1") {
          renderCelulaSync(tr, { ...meta, id_deposito_dropnexo: saved || null, estoque_sync_pendente: false });
        }
      });

      tr.querySelector(".Bl_DepBtnSalvar")?.addEventListener("click", async () => {
        try {
          const valor = sel?.value || "";
          if (valor === (tr.dataset.savedDrop || "") && valor) {
            await Swal.fire({
              icon: "info",
              title: "Sem alterações",
              text: "O vínculo deste depósito não foi alterado.",
              timer: 1400,
              showConfirmButton: false,
            });
            return;
          }
          if (!valor && !(tr.dataset.savedDrop || "")) {
            return;
          }
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
          if (!jj.alterado) {
            await Swal.fire({
              icon: "info",
              title: "Sem alterações",
              text: jj.message || "Nenhuma alteração no vínculo.",
              timer: 1400,
              showConfirmButton: false,
            });
            return;
          }
          if (jj.criou_deposito) {
            await carregarDepositos();
            return;
          }
          tr.dataset.savedDrop = jj.id_deposito_dropnexo ? String(jj.id_deposito_dropnexo) : "";
          if (sel && jj.id_deposito_dropnexo) sel.value = String(jj.id_deposito_dropnexo);
          renderCelulaSync(tr, {
            id_deposito_dropnexo: jj.id_deposito_dropnexo,
            estoque_sync_pendente: !!jj.estoque_sync_pendente,
          });
          await Swal.fire({
            icon: "success",
            title: "Vínculo salvo",
            text: jj.id_deposito_dropnexo
              ? "Use «Atualizar estoque» para importar os saldos deste depósito."
              : jj.message || "",
            timer: 2200,
            showConfirmButton: false,
          });
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
