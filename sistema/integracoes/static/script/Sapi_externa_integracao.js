(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MASCARA = "****************";
  let docs = { markdown: "", prompt_ai: "" };
  let ultimoToken = "";

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

  function mostrarToken(token) {
    const pre = $("ae_dn_token");
    const empty = $("ae_dn_empty");
    const btn = $("ae_btnCopiarToken");
    ultimoToken = token || "";
    if (token) {
      if (empty) empty.hidden = true;
      if (pre) {
        pre.hidden = false;
        pre.textContent = token;
      }
      if (btn) btn.hidden = false;
    } else {
      if (pre) {
        pre.hidden = true;
        pre.textContent = "";
      }
      if (btn) btn.hidden = true;
      if (empty) empty.hidden = false;
    }
  }

  function aplicar(cfg) {
    if (!cfg) return;
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
    $("ae_dn_hint").textContent = cfg.dn_token_configurado
      ? "Token atual: " + (cfg.dn_token_hint || "••••") + (cfg.dn_token_gerado_em ? " · gerado em " + cfg.dn_token_gerado_em : "")
      : "Nenhum token gerado ainda.";
    if (!ultimoToken) {
      const empty = $("ae_dn_empty");
      if (empty) {
        empty.hidden = !!cfg.dn_token_configurado;
        empty.textContent = cfg.dn_token_configurado
          ? "Token já gerado (valor completo oculto). Gere um novo se precisar reenviar."
          : "Nenhum token gerado ainda.";
      }
    }
    $("ae_ultima").textContent = cfg.ultima_sync_em
      ? `Última sync: ${cfg.ultima_sync_em} — ${cfg.ultima_mensagem || ""}`
      : "Nenhuma sincronização ainda.";
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
        <td>${l.dt_criacao || ""}</td>
        <td>${l.evento || ""}</td>
        <td><span class="${ok ? "Ae_LogOk" : "Ae_LogFail"}">${ok ? "OK" : "Falha"}</span></td>
        <td>${(l.mensagem || "").replace(/</g, "&lt;")}</td>
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

  $("ae_btnToken")?.addEventListener("click", async () => {
    try {
      const j = await api("/api/integracoes/api-externa/gerar-token", { method: "POST", body: "{}" });
      aplicar(j.dados || {});
      mostrarToken(j.token || "");
      toast("Token gerado", "Copie agora — não será exibido de novo.", "success");
    } catch (e) {
      toast("Erro", e.message, "error");
    }
  });

  $("ae_btnCopiarToken")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(ultimoToken || "");
      toast("Copiado", "Token copiado.", "success");
    } catch {
      toast("Atenção", "Não foi possível copiar automaticamente.", "warning");
    }
  });

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
