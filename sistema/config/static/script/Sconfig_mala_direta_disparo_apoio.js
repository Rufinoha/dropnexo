(function () {
  "use strict";

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("md_disp_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
  }

  const nivelModal = 1;
  const tbody = document.getElementById("md_disp_tbody");
  const titulo = document.getElementById("md_disp_titulo");
  const meta = document.getElementById("md_disp_meta");

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

  function statusClass(st) {
    const s = String(st || "").toLowerCase();
    if (s.includes("open") || s.includes("click")) return "is-open";
    if (
      s.includes("bounce") ||
      s.includes("error") ||
      s.includes("fail") ||
      s.includes("spam") ||
      s.includes("block") ||
      s.includes("invalid")
    )
      return "is-err";
    if (s.includes("deliver") || s === "enviado" || s === "request") return "is-ok";
    return "";
  }

  function rotuloEvento(tipo) {
    const t = String(tipo || "").toLowerCase();
    const map = {
      request: "Enviado (Brevo)",
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
      spam: "Spam",
      invalid: "Inválido",
      error: "Erro",
      falha: "Falha",
      deferred: "Adiado",
      unsubscribed: "Descadastro",
    };
    return map[t] || tipo || "—";
  }

  function gu() {
    return window.parent?.GlobalUtils || window.GlobalUtils;
  }

  function abrirTimeline(idDest) {
    const base = cfg.rotaEventoApoio || "/configuracoes/mala-direta/destinatario/apoio";
    const rota = `${base}?id_destinatario=${idDest}`;
    const api = gu();
    if (!api?.abrirJanelaApoioModal) {
      toast("error", "GlobalUtils indisponível.");
      return;
    }
    api.abrirJanelaApoioModal({
      rota,
      titulo: "Linha do tempo do e-mail",
      largura: 720,
      altura: 560,
      nivel: 2,
      id: idDest,
    });
  }

  async function carregar() {
    const idEnvio = Number(cfg.idEnvio || 0);
    if (!idEnvio) {
      tbody.innerHTML = `<tr><td colspan="4" class="CfgMd_Hint">Disparo inválido.</td></tr>`;
      return;
    }
    tbody.innerHTML = `<tr><td colspan="4" class="CfgMd_Hint">Carregando…</td></tr>`;
    const url = `/configuracoes/mala-direta/disparos/${idEnvio}`;
    const r = await fetch(url, { credentials: "same-origin", headers: { Accept: "application/json" } });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.success === false) throw new Error(j.message || `Erro ${r.status}`);

    const d = j.disparo || {};
    titulo.textContent = d.assunto || `Disparo #${idEnvio}`;
    const dt = d.dt_envio ? new Date(d.dt_envio).toLocaleString("pt-BR") : "—";
    meta.textContent = [
      `Data: ${dt}`,
      d.tag ? `Tag: ${d.tag}` : null,
      d.filtro_tipo ? `Filtro: ${d.filtro_tipo}` : null,
      `Total: ${d.total ?? 0}`,
    ]
      .filter(Boolean)
      .join(" · ");

    const dests = d.destinatarios || [];
    if (!dests.length) {
      tbody.innerHTML = `<tr><td colspan="4" class="CfgMd_Hint">Nenhum destinatário neste disparo.</td></tr>`;
      return;
    }
    tbody.innerHTML = dests
      .map((x) => {
        const ev = x.dt_ultimo_evento
          ? new Date(x.dt_ultimo_evento).toLocaleString("pt-BR")
          : "—";
        const cls = statusClass(x.status);
        const st = rotuloEvento(x.status);
        return `<tr>
          <td>${esc(x.nome_tenant || (x.id_tenant ? `#${x.id_tenant}` : "—"))}</td>
          <td>${esc(x.email)}</td>
          <td>
            <button type="button" class="CfgMd_Status is-clickable ${cls}" data-dest="${x.id_destinatario}" title="Abrir linha do tempo">
              ${esc(st)}
            </button>
          </td>
          <td>${esc(ev)}</td>
        </tr>`;
      })
      .join("");
  }

  tbody?.addEventListener("click", (e) => {
    const btn = e.target.closest(".CfgMd_Status[data-dest]");
    if (!btn) return;
    e.preventDefault();
    abrirTimeline(Number(btn.getAttribute("data-dest")));
  });

  document.getElementById("md_disp_atualizar")?.addEventListener("click", () => {
    carregar().catch((err) => toast("error", err.message));
  });

  document.getElementById("md_disp_fechar")?.addEventListener("click", () => {
    gu()?.fecharJanelaApoio?.(nivelModal);
  });

  carregar().catch((err) => toast("error", err.message));
})();
