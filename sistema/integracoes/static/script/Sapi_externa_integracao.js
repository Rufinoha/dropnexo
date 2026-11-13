(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  const MASCARA = "****************";
  let docs = { markdown: "", prompt_ai: "" };

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
    $("ae_ultima").textContent = cfg.ultima_sync_em
      ? `Última sync: ${cfg.ultima_sync_em} — ${cfg.ultima_mensagem || ""}`
      : "Nenhuma sincronização ainda.";
    setBadge(cfg);
  }

  function renderLogs(itens) {
    const box = $("ae_logs");
    if (!itens || !itens.length) {
      box.innerHTML = '<p class="Ae_Hint">Sem eventos ainda.</p>';
      return;
    }
    box.innerHTML = `<table><thead><tr><th>Quando</th><th>Evento</th><th>OK</th><th>Mensagem</th></tr></thead><tbody>${itens
      .map(
        (l) => `<tr>
        <td>${l.dt_criacao || ""}</td>
        <td>${l.evento || ""}</td>
        <td>${l.sucesso ? "sim" : "não"}</td>
        <td>${(l.mensagem || "").replace(/</g, "&lt;")}</td>
      </tr>`
      )
      .join("")}</tbody></table>`;
  }

  async function carregar() {
    const j = await api("/api/integracoes/api-externa/status");
    docs = j.docs || {};
    $("ae_doc").textContent = docs.markdown || "";
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

  $("ae_btnSalvar")?.addEventListener("click", async () => {
    try {
      const j = await api("/api/integracoes/api-externa/salvar", {
        method: "POST",
        body: JSON.stringify(payloadSalvar()),
      });
      aplicar(j.dados || {});
      toast("Salvo", j.message || "Configuração atualizada.", "success");
      const logs = await api("/api/integracoes/api-externa/logs");
      renderLogs(logs.dados || []);
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
      const pre = $("ae_dn_token");
      pre.hidden = false;
      pre.textContent = j.token || "";
      toast("Token gerado", "Copie agora — não será exibido de novo.", "success");
    } catch (e) {
      toast("Erro", e.message, "error");
    }
  });

  async function copiar(texto, okMsg) {
    try {
      await navigator.clipboard.writeText(texto || "");
      toast("Copiado", okMsg, "success");
    } catch {
      toast("Atenção", "Não foi possível copiar automaticamente.", "warning");
    }
  }

  $("ae_btnCopiarDoc")?.addEventListener("click", () =>
    copiar(docs.markdown || $("ae_doc").textContent, "Documentação copiada.")
  );
  $("ae_btnCopiarPrompt")?.addEventListener("click", () =>
    copiar(docs.prompt_ai || "", "Prompt para AI copiado.")
  );

  carregar().catch((e) => toast("Erro", e.message, "error"));
})();
