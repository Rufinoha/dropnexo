(function () {
  "use strict";

  const MASCARA = "****************";
  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("hs_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
  }

  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function fmtData(v) {
    if (!v) return "—";
    try {
      return new Date(v).toLocaleString("pt-BR");
    } catch {
      return String(v);
    }
  }

  function aplicarSegredo(input, configurado) {
    if (!input) return;
    input.dataset.hasSecret = configurado ? "1" : "0";
    if (configurado) {
      input.value = MASCARA;
      input.dataset.masked = "1";
      input.classList.add("is-preenchido");
    } else {
      input.value = "";
      input.dataset.masked = "0";
      input.classList.remove("is-preenchido");
    }
  }

  function valorParaSalvar(input) {
    if (!input) return "";
    if (input.dataset.masked === "1") return "";
    const v = (input.value || "").trim();
    if (v === MASCARA) return "";
    return v;
  }

  function bindSegredo(input) {
    if (!input || input.dataset.bound === "1") return;
    input.dataset.bound = "1";
    input.addEventListener("focus", function () {
      if (input.dataset.masked === "1") {
        input.value = "";
        input.dataset.masked = "0";
        input.classList.remove("is-preenchido");
      }
    });
    input.addEventListener("blur", function () {
      if (input.dataset.hasSecret === "1" && !(input.value || "").trim()) {
        aplicarSegredo(input, true);
      }
    });
  }

  function renderStatus(d) {
    const box = document.getElementById("hs_status");
    const txt = document.getElementById("hs_statusTxt");
    if (!box || !txt) return;
    box.classList.remove("is-ok", "is-warn", "is-err");
    if (d.configurado && d.webhook_configurado) {
      box.classList.add("is-ok");
      txt.textContent = "Integração configurada — API e webhook secret definidos.";
    } else if (d.configurado) {
      box.classList.add("is-warn");
      txt.textContent = "API configurada — falta o secret do webhook (copie a URL e cadastre no HubSupport).";
    } else {
      box.classList.add("is-err");
      txt.textContent = "Cole a chave hs_live_… criada no HubSupport e clique em Salvar.";
    }
  }

  function renderAtual(el, ok, mascara, fonte) {
    if (!el) return;
    el.classList.remove("is-ok", "is-vazio");
    if (ok) {
      el.classList.add("is-ok");
      el.textContent = "Configurado — " + (mascara || "••••") + " (" + (fonte || "?") + ")";
    } else {
      el.classList.add("is-vazio");
      el.textContent = "Não configurado — informe e salve.";
    }
  }

  function renderStats(stats) {
    const box = document.getElementById("hs_stats");
    if (!box) return;
    const s = stats || {};
    const items = [
      ["Chamados locais", s.chamados_locais],
      ["Clientes mapeados", s.map_empresa],
      ["Usuários mapeados", s.map_usuario],
      ["Webhooks OK", s.webhooks_ok],
    ];
    box.innerHTML = items
      .map(function (it) {
        return (
          '<div class="HsCfg_Stat"><strong>' +
          esc(it[1] ?? 0) +
          "</strong><span>" +
          esc(it[0]) +
          "</span></div>"
        );
      })
      .join("");
  }

  function renderLogs(apiLogs, whLogs) {
    const apiBox = document.getElementById("hs_apiLogs");
    const whBox = document.getElementById("hs_whLogs");
    if (apiBox) {
      const rows = apiLogs || [];
      if (!rows.length) {
        apiBox.innerHTML = '<p class="HsCfg_Empty">Nenhum log de API ainda.</p>';
      } else {
        apiBox.innerHTML =
          '<table class="HsCfg_Tabela"><thead><tr><th>Quando</th><th>Operação</th><th>OK</th><th>HTTP</th><th>Mensagem</th></tr></thead><tbody>' +
          rows
            .map(function (r) {
              return (
                "<tr><td>" +
                esc(fmtData(r.criado_em)) +
                "</td><td>" +
                esc(r.operacao) +
                "</td><td>" +
                (r.sucesso ? "sim" : "não") +
                "</td><td>" +
                esc(r.http_status ?? "—") +
                "</td><td>" +
                esc((r.mensagem || "").slice(0, 160)) +
                "</td></tr>"
              );
            })
            .join("") +
          "</tbody></table>";
      }
    }
    if (whBox) {
      const rows = whLogs || [];
      if (!rows.length) {
        whBox.innerHTML = '<p class="HsCfg_Empty">Nenhum webhook recebido ainda.</p>';
      } else {
        whBox.innerHTML =
          '<table class="HsCfg_Tabela"><thead><tr><th>Quando</th><th>Evento</th><th>External ID</th></tr></thead><tbody>' +
          rows
            .map(function (r) {
              return (
                "<tr><td>" +
                esc(fmtData(r.processado_em)) +
                "</td><td>" +
                esc(r.evento) +
                "</td><td>" +
                esc(r.external_id || "—") +
                "</td></tr>"
              );
            })
            .join("") +
          "</tbody></table>";
      }
    }
  }

  function aplicarPainel(d) {
    document.getElementById("hs_baseUrl").value = d.base_url || "";
    document.getElementById("hs_webhookUrl").value = d.webhook_url || "";
    if (d.portal) document.getElementById("hs_portal").textContent = d.portal;
    aplicarSegredo(document.getElementById("hs_apiToken"), !!d.configurado);
    aplicarSegredo(document.getElementById("hs_webhookSecret"), !!d.webhook_configurado);
    renderAtual(document.getElementById("hs_tokenAtual"), !!d.configurado, d.token_mascara, d.fonte_token);
    renderAtual(
      document.getElementById("hs_webhookAtual"),
      !!d.webhook_configurado,
      d.webhook_mascara,
      d.fonte_webhook
    );
    renderStatus(d);
    renderStats(d.stats);
    renderLogs(d.api_logs, d.logs);
  }

  async function carregar() {
    const r = await fetch(cfg.apiDados, { credentials: "include", headers: { Accept: "application/json" } });
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Falha ao carregar");
    aplicarPainel(j);
  }

  async function salvar() {
    const payload = {
      base_url: (document.getElementById("hs_baseUrl")?.value || "").trim(),
      api_token: valorParaSalvar(document.getElementById("hs_apiToken")),
      webhook_secret: valorParaSalvar(document.getElementById("hs_webhookSecret")),
    };
    const r = await fetch(cfg.apiSalvar, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Falha ao salvar");
    aplicarPainel(j);
    if (window.Swal) {
      Swal.fire({ icon: "success", title: "Salvo", text: j.message || "Configuração atualizada.", confirmButtonColor: "#021F81" });
    }
  }

  async function testar() {
    const r = await fetch(cfg.apiTestar, {
      method: "POST",
      headers: { Accept: "application/json" },
      credentials: "include",
    });
    const j = await r.json();
    if (window.Swal) {
      Swal.fire({
        icon: j.ok || j.success ? "success" : "error",
        title: j.ok || j.success ? "Conexão OK" : "Falha",
        text: j.message || "",
        confirmButtonColor: "#021F81",
      });
    } else {
      alert(j.message || "");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    bindSegredo(document.getElementById("hs_apiToken"));
    bindSegredo(document.getElementById("hs_webhookSecret"));
    document.getElementById("hs_btnSalvar")?.addEventListener("click", function () {
      salvar().catch(function (e) {
        if (window.Swal) Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
        else alert(e.message);
      });
    });
    document.getElementById("hs_btnTestar")?.addEventListener("click", function () {
      testar().catch(function (e) {
        if (window.Swal) Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
      });
    });
    document.getElementById("hs_btnRecarregar")?.addEventListener("click", function () {
      carregar().catch(function () {});
    });
    document.getElementById("hs_btnCopiar")?.addEventListener("click", async function () {
      const url = document.getElementById("hs_webhookUrl")?.value || "";
      try {
        await navigator.clipboard.writeText(url);
        if (window.Swal) Swal.fire({ icon: "success", title: "URL copiada", timer: 1400, showConfirmButton: false });
      } catch {
        document.getElementById("hs_webhookUrl")?.select();
      }
    });
    carregar().catch(function (e) {
      document.getElementById("hs_statusTxt").textContent = e.message || "Erro ao carregar";
      document.getElementById("hs_status")?.classList.add("is-err");
    });
  });
})();
