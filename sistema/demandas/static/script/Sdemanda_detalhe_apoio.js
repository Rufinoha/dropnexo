(function () {
  "use strict";

  let nivelModal = 1;
  let chamadoUuid = "";
  let externalId = "";
  let podeResponder = false;

  function el(id) {
    return document.getElementById(id);
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
      const d = new Date(v);
      if (Number.isNaN(d.getTime())) return String(v);
      return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
    } catch {
      return String(v);
    }
  }

  function setTab(tab) {
    document.querySelectorAll(".dem-nav-item").forEach((btn) => {
      const on = btn.getAttribute("data-tab") === tab;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".dem-tab").forEach((pane) => {
      const on = pane.getAttribute("data-tab-panel") === tab;
      pane.classList.toggle("is-active", on);
      pane.hidden = !on;
    });
    const btnResp = el("dem_apoio_btnResponder");
    if (btnResp) btnResp.hidden = !(tab === "conversa" && podeResponder);
  }

  function renderThread(interacoes) {
    const box = el("dem_thread");
    const hint = el("dem_threadHint");
    const lista = interacoes || [];
    if (hint) hint.textContent = lista.length ? lista.length + " mensagem(ns)" : "Sem mensagens";
    if (el("dem_navConversaMeta")) {
      el("dem_navConversaMeta").textContent = lista.length ? lista.length + " mensagem(ns)" : "Mensagens";
    }
    if (!box) return;
    if (!lista.length) {
      box.innerHTML = '<div class="dem-carregando">Nenhuma mensagem ainda.</div>';
      return;
    }
    box.innerHTML = lista
      .map((m) => {
        const tipo = (m.tipo_autor || "cliente").toLowerCase();
        const cls = tipo === "agente" ? "dem-msg--agente" : "dem-msg--cliente";
        return (
          `<article class="dem-msg ${cls}">` +
          `<div class="dem-msg-top"><span class="dem-msg-autor">${esc(
            m.nome_autor || (tipo === "agente" ? "Suporte" : "Você")
          )}</span>` +
          `<span class="dem-msg-data">${esc(fmtData(m.created_at))}</span></div>` +
          `<div class="dem-msg-corpo">${esc(m.corpo || "")}</div></article>`
        );
      })
      .join("");
  }

  async function carregar() {
    if (!chamadoUuid && !externalId) return;
    const ref = externalId || "dropnexo:chamado:" + chamadoUuid;
    try {
      const r = await fetch("/api/demandas/detalhe/" + encodeURIComponent(ref), {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar");

      externalId = j.external_id || ref;
      chamadoUuid = j.uuid || chamadoUuid;
      podeResponder = !!j.pode_responder;

      if (el("id")) el("id").value = j.protocolo || "—";
      if (el("tituloPagina")) el("tituloPagina").textContent = j.titulo || "Chamado";
      if (el("dem_campoTitulo")) el("dem_campoTitulo").value = j.titulo || "";
      if (el("dem_campoStatus")) el("dem_campoStatus").value = j.status_label || j.status || "";
      if (el("dem_campoPrioridade")) el("dem_campoPrioridade").value = j.prioridade_label || j.prioridade || "";
      if (el("dem_campoCategoria")) el("dem_campoCategoria").value = j.categoria_label || j.categoria || "";
      if (el("dem_campoAbertura")) el("dem_campoAbertura").value = fmtData(j.data_abertura);
      if (el("dem_campoUltima")) el("dem_campoUltima").value = fmtData(j.data_ultima_interacao);
      if (el("dem_campoSolicitante")) el("dem_campoSolicitante").value = j.solicitante_nome || "—";
      if (el("dem_apoio_status")) el("dem_apoio_status").textContent = j.status_label || j.status || "—";

      const nav = el("dem_navStatus");
      if (nav) {
        nav.className = "dem-nav-status";
        if (j.status) nav.classList.add("is-" + String(j.status).toLowerCase());
      }

      renderThread(j.interacoes);
      if (el("dem_respostaBox")) el("dem_respostaBox").hidden = !podeResponder;
      const btnResp = el("dem_apoio_btnResponder");
      if (btnResp && document.querySelector(".dem-nav-item.is-active")?.dataset.tab === "conversa") {
        btnResp.hidden = !podeResponder;
      }
    } catch (e) {
      if (el("dem_thread")) {
        el("dem_thread").innerHTML = `<div class="dem-carregando">${esc(e.message || "Erro")}</div>`;
      }
      Swal.fire("Erro", e.message || "Falha ao carregar chamado.", "error");
    }
  }

  async function responder() {
    const corpo = (el("dem_respostaTxt")?.value || "").trim();
    if (corpo.length < 2) {
      Swal.fire("Atenção", "Digite uma resposta.", "warning");
      return;
    }
    const ref = externalId || "dropnexo:chamado:" + chamadoUuid;
    Swal.fire({ title: "Enviando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
      const r = await fetch("/api/demandas/responder/" + encodeURIComponent(ref), {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ corpo }),
      });
      const j = await r.json().catch(() => ({}));
      Swal.close();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao responder");
      el("dem_respostaTxt").value = "";
      await carregar();
      window.parent.postMessage({ grupo: "atualizarTabela", nivel: nivelModal }, window.location.origin);
    } catch (e) {
      try {
        Swal.close();
      } catch (_) {}
      Swal.fire("Erro", e.message || "Falha ao responder.", "error");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll(".dem-nav-item").forEach((btn) => {
      btn.addEventListener("click", () => setTab(btn.getAttribute("data-tab")));
    });
    el("dem_apoio_btnFechar")?.addEventListener("click", () => {
      if (window.GlobalUtils?.fecharJanelaApoio) GlobalUtils.fecharJanelaApoio(nivelModal);
    });
    el("dem_apoio_btnResponder")?.addEventListener("click", responder);

    if (window.GlobalUtils?.receberDadosApoio) {
      GlobalUtils.receberDadosApoio((id, nivel) => {
        if (nivel) nivelModal = nivel;
        chamadoUuid = id || "";
        carregar();
      });
    } else {
      const q = new URLSearchParams(window.location.search);
      chamadoUuid = q.get("id") || "";
      carregar();
    }
  });
})();
