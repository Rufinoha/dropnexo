(function () {
  "use strict";

  let nivelModal = 1;
  let chamadoUuid = "";
  let externalId = "";
  let tabAtual = "conversa";
  let podeResponder = false;
  let ultimoChamado = null;

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

  function refEncoded() {
    const ref = externalId || (chamadoUuid ? "dropnexo:chamado:" + chamadoUuid : "");
    return encodeURIComponent(ref);
  }

  function setTab(tab) {
    tabAtual = tab || "conversa";
    document.querySelectorAll(".dem-nav-item").forEach((btn) => {
      const on = btn.getAttribute("data-tab") === tabAtual;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".dem-tab").forEach((pane) => {
      const on = pane.getAttribute("data-tab-panel") === tabAtual;
      pane.classList.toggle("is-active", on);
      pane.hidden = !on;
    });
    const btnResp = el("dem_apoio_btnResponder");
    if (btnResp) btnResp.hidden = !(tabAtual === "conversa" && podeResponder);
  }

  function htmlAnexosMsg(anexos) {
    const arr = Array.isArray(anexos) ? anexos : [];
    if (!arr.length) return "";
    const itens = arr
      .map((a) => {
        const nome = esc(a.nome || "Anexo");
        const url = a.url || "";
        if (url) {
          return `<li><a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${nome}</a></li>`;
        }
        return `<li><span>${nome}</span></li>`;
      })
      .join("");
    return `<ul class="dem-msg-anexos">${itens}</ul>`;
  }

  function renderAnexosChamado(ch) {
    const lista = el("dem_anexosChamadoLista");
    const vazio = el("dem_anexosVazio");
    const hint = el("dem_anexosHint");
    const tit = el("dem_anexosVazioTitulo");
    const txt = el("dem_anexosVazioTxt");
    const metaNav = el("dem_navAnexosMeta");
    const arr = Array.isArray(ch?.anexos) ? [...ch.anexos] : [];
    const status = String(ch?.anexos_status || (arr.length ? "ok" : "vazio"));

    if (metaNav) {
      metaNav.textContent = arr.length
        ? arr.length + " arquivo(s)"
        : status === "indisponivel"
          ? "Indisponível"
          : "Nenhum arquivo";
    }
    if (!lista) return;

    if (!arr.length) {
      lista.innerHTML = "";
      lista.hidden = true;
      if (vazio) vazio.hidden = false;
      if (hint) hint.textContent = status === "indisponivel" ? "Indisponível" : "Nenhum";
      if (tit) tit.textContent = status === "indisponivel" ? "Anexos indisponíveis" : "Sem arquivos";
      if (txt) {
        txt.textContent =
          status === "indisponivel"
            ? ch.anexos_aviso || "Não há arquivos locais deste chamado."
            : "Nenhum anexo gravado neste chamado. Arquivos do abrir/responder aparecem aqui; os do HubSupport entram via webhook ou pelo botão abaixo.";
      }
      return;
    }

    lista.hidden = false;
    if (vazio) vazio.hidden = true;
    if (hint) hint.textContent = arr.length + " arquivo(s)";
    lista.innerHTML = arr
      .map((a) => {
        const nome = esc(a.nome || "Anexo");
        const url = a.url || "";
        const autor = esc(a.enviado_por || "—");
        const quando = esc(fmtData(a.enviado_em));
        const link = url
          ? `<a class="dem-anexo-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer"><span class="dem-anexo-nome">${nome}</span></a>`
          : `<span class="dem-anexo-link"><span class="dem-anexo-nome">${nome}</span></span>`;
        return `<li class="dem-anexo-card">${link}<div class="dem-anexo-meta"><span class="dem-anexo-autor">${autor}</span><span class="dem-anexo-data">${quando}</span></div></li>`;
      })
      .join("");
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
          `<div class="dem-msg-corpo">${esc(m.corpo || "")}</div>` +
          htmlAnexosMsg(m.anexos) +
          `</article>`
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

      ultimoChamado = j;
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
      renderAnexosChamado(j);
      if (el("dem_respostaBox")) el("dem_respostaBox").hidden = !podeResponder;
      const anexosInput = el("dem_respostaAnexos");
      if (anexosInput) anexosInput.disabled = !podeResponder;
      setTab(tabAtual || "conversa");
    } catch (e) {
      if (el("dem_thread")) {
        el("dem_thread").innerHTML = `<div class="dem-carregando">${esc(e.message || "Erro")}</div>`;
      }
      Swal.fire("Erro", e.message || "Falha ao carregar chamado.", "error");
    }
  }

  async function responder() {
    const corpo = (el("dem_respostaTxt")?.value || "").trim();
    const arquivos = el("dem_respostaAnexos")?.files ? Array.from(el("dem_respostaAnexos").files) : [];
    if (corpo.length < 2 && !arquivos.length) {
      Swal.fire("Atenção", "Digite uma resposta ou anexe um arquivo.", "warning");
      return;
    }
    Swal.fire({ title: "Enviando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
      let r;
      if (arquivos.length) {
        const fd = new FormData();
        fd.append("corpo", corpo || "(anexo)");
        arquivos.forEach((f) => fd.append("anexos", f, f.name));
        r = await fetch("/api/demandas/responder/" + refEncoded(), {
          method: "POST",
          credentials: "include",
          body: fd,
        });
      } else {
        r = await fetch("/api/demandas/responder/" + refEncoded(), {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify({ corpo }),
        });
      }
      const j = await r.json().catch(() => ({}));
      Swal.close();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao responder");
      if (el("dem_respostaTxt")) el("dem_respostaTxt").value = "";
      if (el("dem_respostaAnexos")) el("dem_respostaAnexos").value = "";
      if (el("dem_fileNome")) el("dem_fileNome").textContent = "PDF, imagem ou planilha · opcional";
      await carregar();
      window.parent.postMessage({ grupo: "atualizarTabela", nivel: nivelModal }, window.location.origin);
    } catch (e) {
      try {
        Swal.close();
      } catch (_) {}
      Swal.fire("Erro", e.message || "Falha ao responder.", "error");
    }
  }

  async function resgatarAnexosHs() {
    Swal.fire({
      title: "Espelhando anexos…",
      allowOutsideClick: false,
      didOpen: () => Swal.showLoading(),
    });
    try {
      const r = await fetch("/api/demandas/anexos/resgatar/" + refEncoded(), {
        method: "POST",
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const j = await r.json().catch(() => ({}));
      Swal.close();
      if (!r.ok || !j.success) {
        throw new Error(j.message || "HubSupport não retornou anexos.");
      }
      await Swal.fire("Sucesso", j.message || "Anexos espelhados.", "success");
      await carregar();
    } catch (e) {
      try {
        Swal.close();
      } catch (_) {}
      Swal.fire(
        "Aviso",
        (e && e.message) || "Corrija GET /anexos no HubSupport ou reenvie pela Conversa.",
        "warning"
      );
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
    el("dem_btnResgatarAnexos")?.addEventListener("click", resgatarAnexosHs);
    el("dem_respostaAnexos")?.addEventListener("change", function () {
      const n = this.files?.length || 0;
      if (el("dem_fileNome")) {
        el("dem_fileNome").textContent = n
          ? n + " arquivo(s) selecionado(s)"
          : "PDF, imagem ou planilha · opcional";
      }
    });

    setTab("conversa");

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
