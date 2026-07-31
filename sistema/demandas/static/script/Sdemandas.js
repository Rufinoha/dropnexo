(function () {
  "use strict";

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("dem_cfg")?.textContent || "{}");
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

  async function carregar() {
    const tbody = document.getElementById("dem_tbody");
    if (!tbody || !cfg.apiListar) return;
    tbody.innerHTML = '<tr><td colspan="7" class="Dem_Empty">Carregando…</td></tr>';
    try {
      const r = await fetch(cfg.apiListar, { credentials: "include", headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao listar");
      const lista = j.chamados || [];
      if (!lista.length) {
        tbody.innerHTML =
          '<tr><td colspan="7" class="Dem_Empty">Você ainda não abriu chamados. Clique em Novo chamado.</td></tr>';
        return;
      }
      tbody.innerHTML = lista
        .map(function (c) {
          const ref = encodeURIComponent(c.external_id || "");
          return (
            "<tr data-ref=\"" +
            esc(c.external_id) +
            "\">" +
            "<td>" +
            esc(c.protocolo || "—") +
            "</td>" +
            "<td>" +
            esc(c.titulo || "—") +
            "</td>" +
            "<td>" +
            esc(c.categoria_label || c.categoria || "—") +
            "</td>" +
            "<td>" +
            esc(c.status_label || c.status || "—") +
            "</td>" +
            "<td>" +
            esc(c.prioridade_label || c.prioridade || "—") +
            "</td>" +
            "<td>" +
            esc(fmtData(c.data_abertura)) +
            "</td>" +
            "<td>" +
            esc(fmtData(c.data_ultima_interacao)) +
            "</td>" +
            "</tr>"
          );
        })
        .join("");
      tbody.querySelectorAll("tr[data-ref]").forEach(function (tr) {
        tr.addEventListener("click", function () {
          const ref = tr.getAttribute("data-ref");
          if (ref) window.location.href = (cfg.urlDetalheBase || "/demandas") + "/" + encodeURIComponent(ref);
        });
      });
    } catch (e) {
      tbody.innerHTML =
        '<tr><td colspan="7" class="Dem_Empty">' + esc(e.message || "Erro ao carregar") + "</td></tr>";
    }
  }

  function abrirModal() {
    const modal = document.getElementById("dem_modal");
    const err = document.getElementById("dem_form_err");
    if (err) {
      err.hidden = true;
      err.textContent = "";
    }
    document.getElementById("dem_form")?.reset();
    document.getElementById("dem_prioridade").value = "normal";
    modal?.showModal();
  }

  function fecharModal() {
    document.getElementById("dem_modal")?.close();
  }

  async function enviar(e) {
    e.preventDefault();
    const err = document.getElementById("dem_form_err");
    const btn = document.getElementById("dem_enviar");
    const titulo = (document.getElementById("dem_titulo")?.value || "").trim();
    const mensagem = (document.getElementById("dem_mensagem")?.value || "").trim();
    if (titulo.length < 3 || mensagem.length < 5) {
      if (err) {
        err.hidden = false;
        err.textContent = "Preencha assunto (mín. 3) e descrição (mín. 5).";
      }
      return;
    }
    const fd = new FormData();
    fd.append("titulo", titulo);
    fd.append("mensagem", mensagem);
    fd.append("categoria", document.getElementById("dem_categoria")?.value || "duvida");
    fd.append("prioridade", document.getElementById("dem_prioridade")?.value || "normal");
    fd.append("modulo", document.getElementById("dem_modulo")?.value || "");
    fd.append("tela", document.getElementById("dem_tela")?.value || "");
    fd.append("url", window.location.pathname || "");
    const files = document.getElementById("dem_anexos")?.files;
    if (files) {
      for (let i = 0; i < files.length; i++) fd.append("anexos", files[i]);
    }
    btn.disabled = true;
    btn.textContent = "Enviando…";
    try {
      const r = await fetch(cfg.apiAbrir, { method: "POST", body: fd, credentials: "include" });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao abrir chamado");
      fecharModal();
      const proto = (j.chamado && j.chamado.protocolo) || "";
      if (window.Swal) {
        await Swal.fire({
          icon: "success",
          title: "Chamado aberto",
          text: proto ? "Protocolo: " + proto : "Sua demanda foi registrada.",
          confirmButtonColor: "#021F81",
        });
      }
      if (j.chamado && j.chamado.external_id) {
        window.location.href =
          (cfg.urlDetalheBase || "/demandas") + "/" + encodeURIComponent(j.chamado.external_id);
        return;
      }
      carregar();
    } catch (ex) {
      if (err) {
        err.hidden = false;
        err.textContent = ex.message || "Erro";
      }
    } finally {
      btn.disabled = false;
      btn.textContent = "Abrir chamado";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("dem_novo")?.addEventListener("click", abrirModal);
    document.getElementById("dem_cancelar")?.addEventListener("click", fecharModal);
    document.getElementById("dem_modal_close")?.addEventListener("click", fecharModal);
    document.getElementById("dem_form")?.addEventListener("submit", enviar);
    carregar();
  });
})();
