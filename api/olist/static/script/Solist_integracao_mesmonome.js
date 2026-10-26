(function () {
  const page = document.getElementById("ol_page");
  if (!page) return;
  const EH_DEV = page.dataset.dev === "1";
  let estado = { conectado: false, config: {}, armazenamento: {} };
  let tabAtiva = "config";

  const badge = document.getElementById("ol_status_badge");
  const btnConectar = document.getElementById("ol_btn_conectar");
  const btnSair = document.getElementById("ol_btn_desconectar");
  const painel = document.getElementById("ol_painel_config");
  const panes = {
    config: document.getElementById("ol_pane_config"),
    pedidos: document.getElementById("ol_pane_pedidos"),
    status: document.getElementById("ol_pane_status"),
    produtos: document.getElementById("ol_pane_produtos"),
    depositos: document.getElementById("ol_pane_depositos"),
    imagens: document.getElementById("ol_pane_imagens"),
    categorias: document.getElementById("ol_pane_categorias"),
    logs: document.getElementById("ol_pane_logs"),
  };

  function visivel(el, on) {
    if (!el) return;
    el.hidden = !on;
  }

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function pickTab(tab) {
    if (tab === "logs" && !EH_DEV) tab = "config";
    tabAtiva = tab;
    document.querySelectorAll(".Bl_SubTab").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.olTab === tab);
    });
    Object.entries(panes).forEach(([nome, el]) => visivel(el, nome === tab || (nome === "logs" && EH_DEV && tab === "config")));
    if (tab === "status") carregarStatusPadrao().catch(() => {});
    if (tab === "depositos") carregarDepositos().catch(() => {});
    if (tab === "categorias") carregarCategorias().catch(() => {});
  }

  document.getElementById("ol_subtabs")?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-ol-tab]");
    if (!btn) return;
    pickTab(btn.dataset.olTab);
  });

  async function jsonFetch(url, opts) {
    const r = await fetch(url, opts);
    const data = await r.json().catch(() => ({}));
    if (!r.ok || data.success === false) throw new Error(data.message || "Não foi possível concluir.");
    return data;
  }

  function aplicarConfig() {
    const cfg = estado.config || {};
    const op = cfg.opcoes || {};
    const fonte = document.getElementById("ol_fonte");
    const prod = document.getElementById("ol_produtos_modo");
    const est = document.getElementById("ol_estoque_modo");
    if (fonte) fonte.value = cfg.fonte_principal || "olist";
    if (prod) prod.value = cfg.produtos_modo || "importar";
    if (est) est.value = cfg.estoque_modo || "importar";
    const exp = document.getElementById("ol_pedidos_exportar");
    const auto = document.getElementById("ol_pedidos_exportar_auto");
    if (exp) exp.checked = op.pedidos_exportar !== undefined ? !!op.pedidos_exportar : true;
    if (auto) auto.checked = op.pedidos_exportar_auto !== undefined ? !!op.pedidos_exportar_auto : true;
    const rec = document.getElementById("ol_estoque_receber");
    const baixa = document.getElementById("ol_estoque_baixa");
    if (rec) rec.checked = op.estoque_importar_olist !== undefined ? !!op.estoque_importar_olist : true;
    if (baixa) baixa.checked = op.estoque_baixa_pedido !== undefined ? !!op.estoque_baixa_pedido : true;
    const arm = document.getElementById("ol_armazenamento_hint");
    if (arm) {
      const bytes = Number(estado.armazenamento?.bytes_imagens || 0);
      const mb = bytes / (1024 * 1024);
      const txt = mb >= 1024 ? `${(mb / 1024).toFixed(2)} GB` : `${mb.toFixed(1)} MB`;
      arm.textContent = `Espaço de imagens neste tenant: ${txt}`;
    }
    const ult = document.getElementById("ol_ultima_sync");
    if (ult) {
      ult.textContent = cfg.ultima_sync_produtos
        ? `Última importação de produtos: ${new Date(cfg.ultima_sync_produtos).toLocaleString("pt-BR")}`
        : "";
    }
    const ped = document.getElementById("ol_ultima_sync_pedidos");
    if (ped) {
      ped.textContent = cfg.ultima_sync_pedidos
        ? `Última exportação: ${new Date(cfg.ultima_sync_pedidos).toLocaleString("pt-BR")}`
        : "";
    }
    const recTxt = document.getElementById("ol_sync_recebido");
    const envTxt = document.getElementById("ol_sync_enviado");
    if (recTxt) {
      recTxt.textContent = cfg.ultima_sync_estoque
        ? `Recebido do Olist: ${new Date(cfg.ultima_sync_estoque).toLocaleString("pt-BR")}`
        : "Recebido do Olist: nunca";
    }
    if (envTxt) envTxt.textContent = "Enviado ao Olist: nunca";
    const logsEl = document.getElementById("ol_logs");
    if (logsEl) {
      logsEl.innerHTML =
        (estado.logs || [])
          .map(
            (l) =>
              `<li class="Bl_LogItem${l.status === "erro" ? " is-erro" : ""}">` +
              `<span class="Bl_LogStatus">${esc(l.status)}</span>` +
              `<span class="Bl_LogCorpo">${esc(l.resumo)}${l.detalhe ? ` — ${esc(l.detalhe)}` : ""}</span>` +
              (l.criado_em ? `<span class="Bl_LogData">${new Date(l.criado_em).toLocaleString("pt-BR")}</span>` : "") +
              `</li>`
          )
          .join("") || '<li class="Bl_LogItem">Nenhum log ainda.</li>';
    }
  }

  async function carregarStatus() {
    const data = await jsonFetch("/api/integracoes/olist/status");
    estado = data;
    const on = !!data.conectado;
    if (badge) {
      badge.textContent = on ? "Conectado" : "Desconectado";
      badge.className = "Bl_ConnBadge " + (on ? "is-on" : "is-off");
    }
    visivel(btnConectar, !on);
    visivel(btnSair, on);
    visivel(painel, on);
    const conta = document.getElementById("ol_conta");
    if (conta) {
      conta.hidden = !data.conta_nome;
      conta.innerHTML = data.conta_nome ? `Conta: <strong>${esc(data.conta_nome)}</strong>` : "";
    }
    aplicarConfig();
    const campoId = document.getElementById("ol_client_id");
    if (campoId && document.activeElement !== campoId) campoId.value = data.client_id || "";
  }

  async function salvarAplicativo() {
    const clientId = document.getElementById("ol_client_id")?.value || "";
    const clientSecret = document.getElementById("ol_client_secret")?.value || "";
    const data = await jsonFetch("/api/integracoes/olist/aplicativo", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ client_id: clientId, client_secret: clientSecret }),
    });
    const segredo = document.getElementById("ol_client_secret");
    if (segredo) segredo.value = "";
    await Swal.fire({ icon: "success", title: "Aplicativo salvo", text: data.message || "Aplicativo salvo.", confirmButtonColor: "#021F81" });
    if (data.desconectou) window.location.reload();
    else await carregarStatus();
  }

  async function salvar(extra) {
    const body = {
      fonte_principal: document.getElementById("ol_fonte")?.value || "olist",
      modo_imagem: "download",
      produtos_modo: document.getElementById("ol_produtos_modo")?.value || "importar",
      estoque_modo: document.getElementById("ol_estoque_modo")?.value || "importar",
      pedidos_modo: document.getElementById("ol_pedidos_exportar")?.checked ? "exportar" : "importar",
      opcoes: {
        pedidos_exportar: document.getElementById("ol_pedidos_exportar")?.checked !== false,
        pedidos_exportar_auto: document.getElementById("ol_pedidos_exportar_auto")?.checked === true,
        estoque_importar_olist: document.getElementById("ol_estoque_receber")?.checked !== false,
        estoque_baixa_pedido: document.getElementById("ol_estoque_baixa")?.checked === true,
        ...(extra || {}),
      },
    };
    await jsonFetch("/api/integracoes/olist/config/salvar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    await Swal.fire({ icon: "success", title: "Salvo", timer: 1400, showConfirmButton: false });
    await carregarStatus();
  }

  document.getElementById("ol_btn_salvar_app")?.addEventListener("click", () => salvarAplicativo().catch((e) => Swal.fire({ icon: "error", title: "Olist", text: e.message, confirmButtonColor: "#021F81" })));
  document.getElementById("ol_btn_salvar")?.addEventListener("click", () => salvar().catch((e) => Swal.fire({ icon: "error", title: "Olist", text: e.message, confirmButtonColor: "#021F81" })));
  document.getElementById("ol_btn_salvar_pedidos")?.addEventListener("click", () => salvar().catch((e) => Swal.fire({ icon: "error", title: "Olist", text: e.message, confirmButtonColor: "#021F81" })));
  document.getElementById("ol_btn_salvar_estoque")?.addEventListener("click", () => salvar().catch((e) => Swal.fire({ icon: "error", title: "Olist", text: e.message, confirmButtonColor: "#021F81" })));

  async function carregarStatusPadrao() {
    const hint = document.getElementById("ol_status_hint");
    const el = document.getElementById("ol_status_map");
    if (hint) hint.textContent = "Carregando mapeamento padrão…";
    const data = await jsonFetch("/api/integracoes/olist/status-padrao");
    const linhas = data.linhas || [];
    if (el) {
      el.innerHTML = linhas
        .map((row) => {
          const aliases = (row.aliases || []).filter(Boolean);
          const extra = aliases.length ? ` <span class="Bl_StatusAliases">(+ ${esc(aliases.join(", "))})</span>` : "";
          return `<div class="Bl_StatusRow" role="row">
            <div class="Bl_StatusDn"><strong>${esc(row.status_dn_label || row.status_dn)}</strong></div>
            <div class="Bl_StatusBling"><strong class="Bl_StatusBlingOk">${esc(row.status_externo || "—")}</strong>${extra}</div>
            <div class="Bl_StatusDesc">${esc(row.descricao || "")}</div>
          </div>`;
        })
        .join("");
    }
    if (hint) hint.textContent = "Amarração padrão da plataforma (somente leitura).";
  }

  async function carregarDepositos() {
    const tb = document.getElementById("ol_tbl_depositos");
    if (!tb) return;
    tb.innerHTML = '<tr><td colspan="3">Carregando…</td></tr>';
    let data;
    try {
      data = await jsonFetch("/api/integracoes/olist/depositos");
    } catch (e) {
      tb.innerHTML = `<tr><td colspan="3">${esc(e.message)}</td></tr>`;
      return;
    }
    const alerta = document.getElementById("ol_estoque_alert_dep");
    if (alerta) alerta.hidden = Number(data.vinculados || 0) > 0;
    const locais = data.dropnexo || [];
    if (!(data.olist || []).length) {
      tb.innerHTML = '<tr><td colspan="3">Nenhum depósito no Olist.</td></tr>';
      return;
    }
    tb.innerHTML = data.olist
      .map((dep) => {
        const opts = ['<option value="">— escolher —</option>']
          .concat(
            locais.map(
              (d) =>
                `<option value="${d.id}"${Number(dep.id_deposito) === Number(d.id) ? " selected" : ""}>${esc(d.nome)}</option>`
            )
          )
          .join("");
        return `<tr data-id="${esc(dep.id)}" data-nome="${esc(dep.nome)}">
          <td>${esc(dep.nome)}</td>
          <td><select class="Bl_CatBulkSel ol-dep-sel">${opts}</select></td>
          <td><button type="button" class="Cl_BtnSalvar ol-dep-salvar">Salvar</button></td>
        </tr>`;
      })
      .join("");
    tb.querySelectorAll(".ol-dep-salvar").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const tr = btn.closest("tr");
        try {
          await jsonFetch("/api/integracoes/olist/depositos/vincular", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              id_olist: tr.dataset.id,
              nome: tr.dataset.nome,
              id_deposito: tr.querySelector(".ol-dep-sel").value,
            }),
          });
          await Swal.fire({ icon: "success", title: "Vínculo salvo", timer: 1200, showConfirmButton: false });
          await carregarDepositos();
        } catch (e) {
          Swal.fire({ icon: "error", title: "Olist", text: e.message, confirmButtonColor: "#021F81" });
        }
      });
    });
  }

  async function carregarCategorias() {
    const tb = document.getElementById("ol_tbl_categorias");
    if (!tb) return;
    tb.innerHTML = '<tr><td colspan="5">Buscando categorias no Olist…</td></tr>';
    let data;
    try {
      data = await jsonFetch("/api/integracoes/olist/categorias");
    } catch (e) {
      tb.innerHTML = `<tr><td colspan="5">${esc(e.message)}</td></tr>`;
      throw e;
    }
    const segs = data.segmentos || [];
    const locais = data.dropnexo || [];
    if (!(data.olist || []).length) {
      tb.innerHTML = '<tr><td colspan="5">Nenhuma categoria no Olist.</td></tr>';
      return;
    }
    tb.innerHTML = data.olist
      .map((cat) => {
        const segOpts = ['<option value="">— segmento —</option>']
          .concat(
            segs.map(
              (s) =>
                `<option value="${s.id}"${Number(cat.id_segmento) === Number(s.id) ? " selected" : ""}>${esc(s.nome)}</option>`
            )
          )
          .join("");
        const dropOpts = ['<option value="">— categoria —</option>']
          .concat(
            locais.map(
              (d) =>
                `<option value="${d.id}"${Number(cat.id_categoria) === Number(d.id) ? " selected" : ""}>${esc(d.nome)}</option>`
            )
          )
          .join("");
        const acao = cat.acao || "";
        return `<tr data-id="${esc(cat.id)}" data-nome="${esc(cat.nome)}">
          <td>${esc(cat.caminho || cat.nome)}</td>
          <td><select class="Bl_CatBulkSel ol-cat-seg">${segOpts}</select></td>
          <td><select class="Bl_CatBulkSel ol-cat-acao">
            <option value="" ${acao === "" ? "selected" : ""}>— ação —</option>
            <option value="vincular" ${acao === "vincular" ? "selected" : ""}>Vincular existente</option>
            <option value="criar" ${acao === "criar" ? "selected" : ""}>Criar no DropNexo</option>
            <option value="ignorar" ${acao === "ignorar" ? "selected" : ""}>Não importar</option>
          </select></td>
          <td><select class="Bl_CatBulkSel ol-cat-drop">${dropOpts}</select></td>
          <td><button type="button" class="Cl_BtnSalvar ol-cat-salvar">Salvar</button></td>
        </tr>`;
      })
      .join("");
    tb.querySelectorAll(".ol-cat-salvar").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const tr = btn.closest("tr");
        try {
          await jsonFetch("/api/integracoes/olist/categorias/salvar", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              id_olist: tr.dataset.id,
              nome: tr.dataset.nome,
              id_segmento: tr.querySelector(".ol-cat-seg").value,
              acao: tr.querySelector(".ol-cat-acao").value || "ignorar",
              id_categoria: tr.querySelector(".ol-cat-drop").value,
            }),
          });
          await Swal.fire({ icon: "success", title: "Categoria salva", timer: 1200, showConfirmButton: false });
          await carregarCategorias();
        } catch (e) {
          Swal.fire({ icon: "error", title: "Olist", text: e.message, confirmButtonColor: "#021F81" });
        }
      });
    });
  }

  btnSair?.addEventListener("click", async () => {
    const ok = await Swal.fire({
      title: "Desconectar o Olist?",
      text: "Os produtos já importados permanecem no catálogo.",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Desconectar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
    });
    if (!ok.isConfirmed) return;
    try {
      await jsonFetch("/api/integracoes/olist/desconectar", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
      window.location.reload();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Olist", text: e.message, confirmButtonColor: "#021F81" });
    }
  });

  const paramsPagina = new URLSearchParams(window.location.search);
  const aba = paramsPagina.get("aba");
  if (aba && panes[aba]) pickTab(aba);
  const erroOAuth = paramsPagina.get("erro");
  if (erroOAuth) {
    Swal.fire({
      icon: "error",
      title: "Não foi possível conectar",
      text: erroOAuth,
      confirmButtonColor: "#021F81",
    });
    window.history.replaceState({}, "", location.pathname);
  }

  carregarStatus().catch((e) => {
    Swal.fire({ icon: "error", title: "Olist", text: e.message, confirmButtonColor: "#021F81" });
  });
  window.lucide?.createIcons?.();
})();
