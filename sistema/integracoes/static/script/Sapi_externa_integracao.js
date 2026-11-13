(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MASCARA = "****************";
  let docs = { markdown: "", prompt_ai: "" };
  let ultimoToken = "";
  let tokenCfg = null;
  let menuAbertoEm = 0;

  async function api(url, opts) {
    const r = await fetch(url, {
      credentials: "include",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...(opts || {}),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.success === false) throw new Error(j.message || "Falha na requisição");
    return j;
  }

  function toast(title, text, icon) {
    if (window.Swal) Swal.fire({ icon: icon || "info", title, text, confirmButtonColor: "#021F81" });
    else alert(title + (text ? "\n" + text : ""));
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtData(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return String(iso);
    return d.toLocaleString("pt-BR", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function setBadge(cfg) {
    const el = $("ae_badge");
    if (!el) return;
    el.classList.remove("is-ativo", "is-erro", "is-atencao");
    const st = String(cfg.status || "desligado");
    if (st === "ativo") el.classList.add("is-ativo");
    else if (st === "erro") el.classList.add("is-erro");
    else if (st === "atencao") el.classList.add("is-atencao");
    el.textContent = cfg.ativo ? (cfg.status || "ativo") : "desligado";
  }

  function fecharMenuToken() {
    const menu = $("ae_token_menu");
    if (menu) menu.hidden = true;
    document.querySelectorAll(".Ae_MenuBtn[aria-expanded='true']").forEach((b) => {
      b.setAttribute("aria-expanded", "false");
    });
  }

  function posicionarMenu(menu, btn) {
    const r = btn.getBoundingClientRect();
    menu.hidden = false;
    const mw = menu.offsetWidth || 210;
    const mh = menu.offsetHeight || 120;
    let left = r.right - mw;
    let top = r.bottom + 6;
    if (left < 8) left = 8;
    if (left + mw > window.innerWidth - 8) left = window.innerWidth - mw - 8;
    if (top + mh > window.innerHeight - 8) top = Math.max(8, r.top - mh - 6);
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    menuAbertoEm = Date.now();
    btn.setAttribute("aria-expanded", "true");
  }

  function abrirMenuToken(btn) {
    const menu = $("ae_token_menu");
    const btnCopiar = $("ae_menu_copiar");
    if (!menu) return;
    if (btnCopiar) {
      btnCopiar.disabled = !ultimoToken;
      btnCopiar.title = ultimoToken
        ? "Copia o valor gerado nesta sessão"
        : "Valor completo só fica disponível logo após gerar";
    }
    if (!menu.hidden && btn.getAttribute("aria-expanded") === "true") {
      fecharMenuToken();
      return;
    }
    fecharMenuToken();
    posicionarMenu(menu, btn);
  }

  function mostrarReveal(token) {
    ultimoToken = token || "";
    const box = $("ae_dn_reveal");
    const code = $("ae_dn_token_plain");
    if (!box || !code) return;
    if (!token) {
      box.hidden = true;
      code.textContent = "";
      return;
    }
    code.textContent = token;
    box.hidden = false;
  }

  function renderTokenTable(cfg) {
    const tbody = $("ae_token_tbody");
    if (!tbody) return;
    if (!cfg || !cfg.dn_token_configurado) {
      tbody.innerHTML = '<tr><td colspan="4" class="Ae_EmptyCell">Nenhum token gerado ainda.</td></tr>';
      return;
    }
    const hint = cfg.dn_token_hint || "••••…••••";
    tbody.innerHTML = `<tr>
      <td><span class="Ae_TokenHint">${esc(hint)}</span></td>
      <td><span class="Ae_TokenMeta">${esc(fmtData(cfg.dn_token_gerado_em))}</span></td>
      <td><span class="Ae_TokenStatus">Ativo</span></td>
      <td class="Ae_ColAcoes">
        <div class="Ae_Acoes">
          <button type="button" class="Ae_MenuBtn" data-ae-token-menu="1" aria-label="Ações do token" aria-haspopup="menu" aria-expanded="false" title="Ações">
            <span></span><span></span><span></span>
          </button>
        </div>
      </td>
    </tr>`;
  }

  function aplicar(cfg) {
    if (!cfg) return;
    tokenCfg = cfg;
    $("ae_base_url").value = cfg.base_url || "";
    $("ae_auth_tipo").value = cfg.auth_tipo || "bearer";
    $("ae_ambiente").value = cfg.ambiente === "producao" ? "producao" : "homologacao";
    $("ae_webhook").value = cfg.webhook_url || "";
    $("ae_contato").value = cfg.contato_tecnico || "";
    $("ae_ativo").checked = !!cfg.ativo;
    $("ae_cap_prod_cad").checked = cfg.cap_produtos_cadastrar !== false;
    $("ae_cap_prod_upd").checked = cfg.cap_produtos_atualizar !== false;
    $("ae_cap_est_upd").checked = cfg.cap_estoque_atualizar !== false;
    $("ae_cap_ped_env").checked = !!cfg.cap_pedidos_enviar;
    $("ae_cap_ped_st").checked = !!cfg.cap_pedidos_status;
    if (cfg.token_parceiro_configurado) {
      $("ae_token").value = MASCARA;
      $("ae_token_hint").textContent = "Configurado: " + (cfg.token_parceiro_hint || "••••");
    } else {
      $("ae_token").value = "";
      $("ae_token_hint").textContent = "Ainda não informado.";
    }
    if (cfg.webhook_secret_configurado) $("ae_webhook_secret").value = MASCARA;
    else $("ae_webhook_secret").value = "";
    $("ae_ultima").textContent = cfg.ultima_sync_em
      ? `Última sync: ${cfg.ultima_sync_em} — ${cfg.ultima_mensagem || ""}`
      : "Nenhuma sincronização ainda.";
    renderTokenTable(cfg);
    setBadge(cfg);
  }

  function renderLogs(itens) {
    const box = $("ae_logs");
    if (!box) return;
    if (!itens || !itens.length) {
      box.innerHTML = '<div class="Ae_Empty">Sem eventos ainda.</div>';
      return;
    }
    box.innerHTML = `<table><thead><tr><th>Quando</th><th>Evento</th><th>Status</th><th>Mensagem</th></tr></thead><tbody>${itens
      .map((l) => {
        const ok = !!l.sucesso;
        return `<tr>
        <td>${esc(l.dt_criacao || "")}</td>
        <td>${esc(l.evento || "")}</td>
        <td><span class="${ok ? "Ae_LogOk" : "Ae_LogFail"}">${ok ? "OK" : "Falha"}</span></td>
        <td>${esc(l.mensagem || "")}</td>
      </tr>`;
      })
      .join("")}</tbody></table>`;
  }

  function ativarAba(nome) {
    document.querySelectorAll(".Ae_Tab").forEach((btn) => {
      btn.classList.toggle("is-active", btn.getAttribute("data-ae-tab") === nome);
    });
    document.querySelectorAll("[data-ae-pane]").forEach((pane) => {
      pane.hidden = pane.getAttribute("data-ae-pane") !== nome;
    });
    fecharMenuToken();
  }

  document.getElementById("ae_tabs")?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-ae-tab]");
    if (!btn) return;
    ativarAba(btn.getAttribute("data-ae-tab"));
  });

  async function carregar() {
    const j = await api("/api/integracoes/api-externa/status");
    docs = j.docs || {};
    if ($("ae_prompt")) $("ae_prompt").textContent = docs.prompt_ai || "";
    aplicar(j.dados || {});
    const logs = await api("/api/integracoes/api-externa/logs");
    renderLogs(logs.dados || []);
  }

  function payloadSalvar() {
    const token = ($("ae_token").value || "").trim();
    const secret = ($("ae_webhook_secret").value || "").trim();
    return {
      base_url: ($("ae_base_url").value || "").trim(),
      auth_tipo: $("ae_auth_tipo").value || "bearer",
      ambiente: $("ae_ambiente").value || "homologacao",
      webhook_url: ($("ae_webhook").value || "").trim(),
      contato_tecnico: ($("ae_contato").value || "").trim(),
      ativo: !!$("ae_ativo").checked,
      cap_produtos_cadastrar: !!$("ae_cap_prod_cad").checked,
      cap_produtos_atualizar: !!$("ae_cap_prod_upd").checked,
      cap_estoque_atualizar: !!$("ae_cap_est_upd").checked,
      cap_pedidos_enviar: !!$("ae_cap_ped_env").checked,
      cap_pedidos_status: !!$("ae_cap_ped_st").checked,
      token_parceiro: token === MASCARA ? "" : token,
      webhook_secret: secret === MASCARA ? "" : secret,
    };
  }

  async function salvar(msgOk) {
    const j = await api("/api/integracoes/api-externa/salvar", {
      method: "POST",
      body: JSON.stringify(payloadSalvar()),
    });
    aplicar(j.dados || {});
    toast("Salvo", msgOk || j.message || "Configuração atualizada.", "success");
    const logs = await api("/api/integracoes/api-externa/logs");
    renderLogs(logs.dados || []);
  }

  async function gerarToken(confirmar) {
    if (confirmar && tokenCfg && tokenCfg.dn_token_configurado) {
      const ok = window.Swal
        ? (
            await Swal.fire({
              icon: "warning",
              title: "Gerar novo token?",
              text: "O token atual deixa de valer imediatamente.",
              showCancelButton: true,
              confirmButtonText: "Gerar novo",
              cancelButtonText: "Cancelar",
              confirmButtonColor: "#021F81",
            })
          ).isConfirmed
        : confirm("Gerar novo token? O atual deixa de valer.");
      if (!ok) return;
    }
    const j = await api("/api/integracoes/api-externa/gerar-token", { method: "POST", body: "{}" });
    aplicar(j.dados || {});
    mostrarReveal(j.token || "");
    toast("Token gerado", "Copie agora — não será exibido de novo.", "success");
    const logs = await api("/api/integracoes/api-externa/logs");
    renderLogs(logs.dados || []);
  }

  async function revogarToken() {
    const ok = window.Swal
      ? (
          await Swal.fire({
            icon: "warning",
            title: "Revogar token?",
            text: "Integrações que usam este token param de autenticar.",
            showCancelButton: true,
            confirmButtonText: "Revogar",
            cancelButtonText: "Cancelar",
            confirmButtonColor: "#991b1b",
          })
        ).isConfirmed
      : confirm("Revogar token?");
    if (!ok) return;
    const j = await api("/api/integracoes/api-externa/revogar-token", { method: "POST", body: "{}" });
    ultimoToken = "";
    mostrarReveal("");
    aplicar(j.dados || {});
    toast("Revogado", "Token removido.", "success");
    const logs = await api("/api/integracoes/api-externa/logs");
    renderLogs(logs.dados || []);
  }

  async function copiarToken() {
    if (!ultimoToken) {
      toast("Indisponível", "O valor completo só aparece uma vez após gerar. Gere um novo se precisar.", "info");
      return;
    }
    try {
      await navigator.clipboard.writeText(ultimoToken);
      toast("Copiado", "Token copiado.", "success");
    } catch {
      toast("Atenção", "Não foi possível copiar automaticamente.", "warning");
    }
  }

  $("ae_btnSalvar")?.addEventListener("click", async () => {
    try {
      await salvar("Conexão atualizada.");
    } catch (e) {
      toast("Erro", e.message, "error");
    }
  });

  $("ae_btnSalvarTarefas")?.addEventListener("click", async () => {
    try {
      await salvar("Tarefas atualizadas.");
    } catch (e) {
      toast("Erro", e.message, "error");
    }
  });

  $("ae_btnTestar")?.addEventListener("click", async () => {
    try {
      await api("/api/integracoes/api-externa/salvar", {
        method: "POST",
        body: JSON.stringify(payloadSalvar()),
      });
      const j = await api("/api/integracoes/api-externa/testar", { method: "POST", body: "{}" });
      aplicar(j.dados || {});
      toast(j.ok || j.success ? "Conexão OK" : "Falha", j.message || "", j.ok || j.success ? "success" : "error");
      const logs = await api("/api/integracoes/api-externa/logs");
      renderLogs(logs.dados || []);
    } catch (e) {
      toast("Erro", e.message, "error");
    }
  });

  async function sync(url, titulo) {
    try {
      const j = await api(url, { method: "POST", body: "{}" });
      aplicar(j.dados || {});
      toast(titulo, j.message || "", j.ok || j.success ? "success" : "warning");
      const logs = await api("/api/integracoes/api-externa/logs");
      renderLogs(logs.dados || []);
    } catch (e) {
      toast("Erro", e.message, "error");
    }
  }

  $("ae_btnSyncProd")?.addEventListener("click", () =>
    sync("/api/integracoes/api-externa/sync/produtos", "Produtos")
  );
  $("ae_btnSyncEst")?.addEventListener("click", () =>
    sync("/api/integracoes/api-externa/sync/estoque", "Estoque")
  );

  $("ae_btnToken")?.addEventListener("click", () => {
    gerarToken(true).catch((e) => toast("Erro", e.message, "error"));
  });

  $("ae_btnCopiarToken")?.addEventListener("click", () => {
    copiarToken().catch((e) => toast("Erro", e.message, "error"));
  });

  $("ae_btnFecharReveal")?.addEventListener("click", () => {
    mostrarReveal("");
  });

  document.addEventListener("click", (ev) => {
    const menuBtn = ev.target.closest("[data-ae-token-menu]");
    if (menuBtn) {
      ev.stopPropagation();
      abrirMenuToken(menuBtn);
      return;
    }
    const acao = ev.target.closest("#ae_token_menu [data-ae-token-acao]");
    if (acao) {
      const tipo = acao.getAttribute("data-ae-token-acao");
      fecharMenuToken();
      if (tipo === "copiar") copiarToken().catch((e) => toast("Erro", e.message, "error"));
      else if (tipo === "gerar") gerarToken(true).catch((e) => toast("Erro", e.message, "error"));
      else if (tipo === "revogar") revogarToken().catch((e) => toast("Erro", e.message, "error"));
      return;
    }
    if (!ev.target.closest("#ae_token_menu")) fecharMenuToken();
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") fecharMenuToken();
  });

  window.addEventListener(
    "scroll",
    () => {
      if (Date.now() - menuAbertoEm < 250) return;
      fecharMenuToken();
    },
    true
  );

  $("ae_btnCopiarPrompt")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(docs.prompt_ai || $("ae_prompt")?.textContent || "");
      toast("Copiado", "Prompt para AI copiado.", "success");
    } catch {
      toast("Atenção", "Não foi possível copiar automaticamente.", "warning");
    }
  });

  $("ae_btnRefreshLogs")?.addEventListener("click", async () => {
    try {
      const logs = await api("/api/integracoes/api-externa/logs");
      renderLogs(logs.dados || []);
      toast("Logs", "Atualizado.", "success");
    } catch (e) {
      toast("Erro", e.message, "error");
    }
  });

  carregar().catch((e) => toast("Erro", e.message, "error"));
})();
