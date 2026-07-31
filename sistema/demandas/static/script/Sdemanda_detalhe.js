(function () {
  "use strict";

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("dem_det_cfg")?.textContent || "{}");
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
    if (!v) return "";
    try {
      return new Date(v).toLocaleString("pt-BR");
    } catch {
      return String(v);
    }
  }

  function renderThread(interacoes) {
    const box = document.getElementById("dem_thread");
    if (!box) return;
    const lista = interacoes || [];
    if (!lista.length) {
      box.innerHTML = '<p class="Dem_Empty">Nenhuma mensagem ainda.</p>';
      return;
    }
    box.innerHTML = lista
      .map(function (m) {
        const tipo = (m.tipo_autor || "cliente").toLowerCase();
        const cls = tipo === "agente" ? "is-agente" : "is-cliente";
        return (
          '<article class="Dem_Msg ' +
          cls +
          '">' +
          '<div class="Dem_MsgHead"><strong>' +
          esc(m.nome_autor || (tipo === "agente" ? "Suporte" : "Você")) +
          "</strong><span>" +
          esc(fmtData(m.created_at)) +
          "</span></div>" +
          '<div class="Dem_MsgBody">' +
          esc(m.corpo || "") +
          "</div></article>"
        );
      })
      .join("");
  }

  async function carregar() {
    const load = document.getElementById("dem_detalhe_load");
    const root = document.getElementById("dem_detalhe");
    if (!cfg.apiDetalhe) {
      if (load) load.textContent = "Configuração inválida.";
      return;
    }
    try {
      const r = await fetch(cfg.apiDetalhe, { credentials: "include", headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao carregar");
      if (load) load.hidden = true;
      if (root) root.hidden = false;
      document.getElementById("dem_protocolo").textContent = j.protocolo || "Sem protocolo";
      document.getElementById("dem_titulo").textContent = j.titulo || "Chamado";
      document.getElementById("dem_status").textContent = j.status_label || j.status || "—";
      document.getElementById("dem_meta").textContent = [
        j.categoria_label || j.categoria,
        j.prioridade_label || j.prioridade,
        j.solicitante_nome ? "Aberto por " + j.solicitante_nome : "",
        j.data_abertura ? "em " + fmtData(j.data_abertura) : "",
      ]
        .filter(Boolean)
        .join(" · ");
      renderThread(j.interacoes);
      const pode = !!j.pode_responder;
      document.getElementById("dem_resposta_box").hidden = !pode;
      document.getElementById("dem_fechado_msg").hidden = pode;
    } catch (e) {
      if (load) load.textContent = e.message || "Erro ao carregar chamado";
    }
  }

  async function responder() {
    const err = document.getElementById("dem_resp_err");
    const btn = document.getElementById("dem_enviar_resp");
    const corpo = (document.getElementById("dem_corpo")?.value || "").trim();
    if (corpo.length < 2) {
      if (err) {
        err.hidden = false;
        err.textContent = "Digite uma resposta.";
      }
      return;
    }
    btn.disabled = true;
    try {
      const r = await fetch(cfg.apiResponder, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        credentials: "include",
        body: JSON.stringify({ corpo: corpo }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao responder");
      document.getElementById("dem_corpo").value = "";
      if (err) err.hidden = true;
      await carregar();
    } catch (e) {
      if (err) {
        err.hidden = false;
        err.textContent = e.message || "Erro";
      }
    } finally {
      btn.disabled = false;
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("dem_enviar_resp")?.addEventListener("click", responder);
    carregar();
  });
})();
