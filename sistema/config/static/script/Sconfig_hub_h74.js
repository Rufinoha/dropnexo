(function () {
  "use strict";

  const MASCARA = "****************";
  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("hn_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
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
    const box = document.getElementById("hn_status");
    const txt = document.getElementById("hn_statusTxt");
    if (!box || !txt) return;
    box.classList.remove("is-ok", "is-warn", "is-err");
    if (d.configurado) {
      box.classList.add("is-ok");
      txt.textContent =
        "Hub H74 configurado — URL, tokens NF-e/NFS-e e ambiente definidos.";
    } else if (d.url_configurada || d.token_configurado || d.token_nfse_configurado) {
      box.classList.add("is-warn");
      txt.textContent =
        "Configuração incompleta — informe URL, token NF-e e token NFS-e, depois salve.";
    } else {
      box.classList.add("is-err");
      txt.textContent =
        "Cole a URL e os dois tokens do H74 Painel NF-e e clique em Salvar.";
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

  function aplicarPainel(d) {
    document.getElementById("hn_baseUrl").value = d.base_url || "";
    if (d.x_sistema) document.getElementById("hn_xSistema").textContent = d.x_sistema;
    if (d.dica) document.getElementById("hn_dica").textContent = d.dica;
    const amb = d.ambiente === "producao" ? "producao" : "homologacao";
    const sel = document.getElementById("hn_ambiente");
    if (sel) sel.value = amb;
    const ambEl = document.getElementById("hn_ambienteAtual");
    if (ambEl) {
      ambEl.textContent =
        "Atual: " +
        (amb === "producao" ? "Produção" : "Homologação") +
        " (" +
        (d.fonte_ambiente || "?") +
        ")";
    }
    aplicarSegredo(document.getElementById("hn_token"), !!d.token_configurado);
    aplicarSegredo(document.getElementById("hn_tokenNfse"), !!d.token_nfse_configurado);
    renderAtual(
      document.getElementById("hn_urlAtual"),
      !!d.url_configurada,
      d.base_url || "",
      d.fonte_url
    );
    renderAtual(
      document.getElementById("hn_tokenAtual"),
      !!d.token_configurado,
      d.token_mascara,
      d.fonte_token
    );
    renderAtual(
      document.getElementById("hn_tokenNfseAtual"),
      !!d.token_nfse_configurado,
      d.token_nfse_mascara,
      d.fonte_token_nfse
    );
    renderStatus(d);
  }

  async function carregar() {
    const r = await fetch(cfg.apiDados, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Falha ao carregar");
    aplicarPainel(j);
  }

  async function salvar() {
    const payload = {
      base_url: (document.getElementById("hn_baseUrl")?.value || "").trim(),
      token: valorParaSalvar(document.getElementById("hn_token")),
      token_nfse: valorParaSalvar(document.getElementById("hn_tokenNfse")),
      ambiente: document.getElementById("hn_ambiente")?.value || "homologacao",
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
      Swal.fire({
        icon: "success",
        title: "Salvo",
        text: j.message || "Configuração atualizada.",
        confirmButtonColor: "#021F81",
      });
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
    bindSegredo(document.getElementById("hn_token"));
    bindSegredo(document.getElementById("hn_tokenNfse"));
    document.getElementById("hn_btnSalvar")?.addEventListener("click", function () {
      salvar().catch(function (e) {
        if (window.Swal)
          Swal.fire({
            icon: "error",
            title: "Erro",
            text: e.message,
            confirmButtonColor: "#021F81",
          });
        else alert(e.message);
      });
    });
    document.getElementById("hn_btnTestar")?.addEventListener("click", function () {
      testar().catch(function (e) {
        if (window.Swal)
          Swal.fire({
            icon: "error",
            title: "Erro",
            text: e.message,
            confirmButtonColor: "#021F81",
          });
      });
    });
    carregar().catch(function (e) {
      document.getElementById("hn_statusTxt").textContent = e.message || "Erro ao carregar";
      document.getElementById("hn_status")?.classList.add("is-err");
    });
  });
})();
