(function () {
  "use strict";

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("md_ev_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
  }

  const nivelModal = 2;
  const titulo = document.getElementById("md_ev_titulo");
  const meta = document.getElementById("md_ev_meta");
  const list = document.getElementById("md_ev_list");

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function toast(icon, title) {
    if (window.Swal) Swal.fire({ icon, title, timer: 2200, showConfirmButton: false });
    else alert(title);
  }

  function rotuloEvento(tipo) {
    const t = String(tipo || "").toLowerCase();
    const map = {
      request: "Enviado (aceito pelo Brevo)",
      enviado: "Enviado",
      delivered: "Entregue",
      opened: "Aberto",
      unique_opened: "Aberto (único)",
      first_opening: "Primeira abertura",
      click: "Clique em link",
      soft_bounce: "Bounce suave",
      hard_bounce: "Bounce duro",
      bounce: "Bounce",
      blocked: "Bloqueado",
      spam: "Marcado como spam",
      invalid: "E-mail inválido",
      error: "Erro",
      falha: "Falha",
      deferred: "Adiado",
      unsubscribed: "Descadastro",
    };
    return map[t] || tipo || "Evento";
  }

  function gu() {
    return window.parent?.GlobalUtils || window.GlobalUtils;
  }

  async function carregar() {
    const idDest = Number(cfg.idDestinatario || 0);
    if (!idDest) {
      list.innerHTML = `<li class="CfgMd_Hint">Destinatário inválido.</li>`;
      return;
    }
    list.innerHTML = `<li class="CfgMd_Hint">Carregando…</li>`;
    const url =
      cfg.apiEventos ||
      `/configuracoes/mala-direta/destinatarios/${idDest}/eventos`;
    const r = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.success === false) throw new Error(j.message || `Erro ${r.status}`);

    const d = j.destinatario || {};
    titulo.textContent = d.email || "Linha do tempo";
    meta.textContent = [
      d.nome_tenant ? `Tenant: ${d.nome_tenant}` : null,
      d.assunto ? `Assunto: ${d.assunto}` : null,
      d.status_atual ? `Status atual: ${rotuloEvento(d.status_atual)}` : null,
    ]
      .filter(Boolean)
      .join(" · ");

    const eventos = j.eventos || [];
    if (!eventos.length) {
      list.innerHTML =
        `<li class="CfgMd_Hint">Ainda sem eventos do webhook. Quando o Brevo enviar delivered/opened/click, eles aparecem aqui em ordem.</li>`;
      return;
    }
    list.innerHTML = eventos
      .map((ev) => {
        const dt = ev.data ? new Date(ev.data).toLocaleString("pt-BR") : "—";
        const msg = ev.mensagem
          ? `<span class="CfgMd_TlMsg">${esc(ev.mensagem)}</span>`
          : "";
        return `<li>
          <span class="CfgMd_TlTipo">${esc(rotuloEvento(ev.tipo))}</span>
          <span class="CfgMd_TlData">${esc(dt)}</span>
          ${msg}
        </li>`;
      })
      .join("");
  }

  document.getElementById("md_ev_atualizar")?.addEventListener("click", () => {
    carregar().catch((err) => toast("error", err.message));
  });

  document.getElementById("md_ev_fechar")?.addEventListener("click", () => {
    gu()?.fecharJanelaApoio?.(nivelModal);
  });

  carregar().catch((err) => toast("error", err.message));
})();
