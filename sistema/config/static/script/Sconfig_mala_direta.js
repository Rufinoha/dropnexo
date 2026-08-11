(function () {
  const BASE = "/configuracoes/mala-direta";
  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("cfg_md_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
  }

  const tbody = document.getElementById("cfg_md_tbody");
  const histBody = document.getElementById("cfg_md_hist_tbody");
  const contagem = document.getElementById("cfg_md_contagem");
  const chkTodos = document.getElementById("cfg_md_todos");
  const hiddenCorpo = document.getElementById("cfg_md_corpo");
  let itens = [];
  let selecionados = new Set();
  let quill = null;

  /* Período de cadastro — padrão em branco (todos) */
  const periodoState = {
    de: null, // Date local ou null
    ate: null,
    draftDe: null,
    draftAte: null,
    viewYm: null, // Date no 1º dia do mês esquerdo
    open: false,
  };

  function util() {
    return window.Util || { gerarIconeTech: () => "…" };
  }

  function toast(icon, title) {
    if (window.Swal) Swal.fire({ icon, title, timer: 2200, showConfirmButton: false });
    else alert(title);
  }

  function isEmptyHtml(html) {
    const stripped = (html || "")
      .replace(/<p><br><\/p>/gi, "")
      .replace(/<p>\s*<\/p>/gi, "")
      .replace(/&nbsp;/gi, " ")
      .replace(/<br\s*\/?>/gi, "")
      .replace(/<[^>]+>/g, "")
      .trim();
    return !stripped;
  }

  function normalizeQuillHtml(html) {
    if (isEmptyHtml(html)) return "";
    return (html || "").trim();
  }

  function getCorpoHtml() {
    let html = "";
    if (quill) html = normalizeQuillHtml(quill.root.innerHTML);
    else html = (hiddenCorpo?.value || "").trim();
    if (hiddenCorpo) hiddenCorpo.value = html;
    return html;
  }

  function initEditor() {
    const host = document.getElementById("cfg_md_editor");
    if (!host || typeof Quill === "undefined") return;
    quill = new Quill("#cfg_md_editor", {
      theme: "snow",
      placeholder: "Escreva a mensagem do e-mail…",
      modules: {
        toolbar: [
          [{ header: [2, 3, false] }],
          ["bold", "italic", "underline", "strike"],
          [{ color: [] }, { background: [] }],
          [{ align: [] }],
          [{ list: "ordered" }, { list: "bullet" }],
          ["blockquote", "link"],
          ["clean"],
        ],
      },
    });
    quill.on("text-change", () => {
      if (hiddenCorpo) hiddenCorpo.value = normalizeQuillHtml(quill.root.innerHTML);
    });
  }

  async function api(url, opts) {
    const r = await fetch(url, {
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      ...opts,
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.success === false) throw new Error(j.message || `Erro ${r.status}`);
    return j;
  }

  function atualizarContagem() {
    contagem.textContent = `${selecionados.size} selecionado(s)`;
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtDataCadastro(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleDateString("pt-BR");
  }

  function startOfDay(d) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }

  function toISODate(d) {
    if (!d) return "";
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${y}-${m}-${day}`;
  }

  function fromISODate(s) {
    if (!s || !/^\d{4}-\d{2}-\d{2}$/.test(s)) return null;
    const [y, m, d] = s.split("-").map(Number);
    const dt = new Date(y, m - 1, d);
    return Number.isNaN(dt.getTime()) ? null : startOfDay(dt);
  }

  function fmtBR(d) {
    if (!d) return "";
    return d.toLocaleDateString("pt-BR");
  }

  function parseBR(s) {
    const m = String(s || "")
      .trim()
      .match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/);
    if (!m) return null;
    const d = Number(m[1]);
    const mo = Number(m[2]);
    const y = Number(m[3]);
    const dt = new Date(y, mo - 1, d);
    if (dt.getFullYear() !== y || dt.getMonth() !== mo - 1 || dt.getDate() !== d) return null;
    return startOfDay(dt);
  }

  function sameDay(a, b) {
    return a && b && a.getTime() === b.getTime();
  }

  function between(d, a, b) {
    if (!d || !a || !b) return false;
    const lo = a.getTime() <= b.getTime() ? a : b;
    const hi = a.getTime() <= b.getTime() ? b : a;
    return d.getTime() > lo.getTime() && d.getTime() < hi.getTime();
  }

  function syncHidden() {
    const deEl = document.getElementById("cfg_md_de");
    const ateEl = document.getElementById("cfg_md_ate");
    if (deEl) deEl.value = toISODate(periodoState.de);
    if (ateEl) ateEl.value = toISODate(periodoState.ate);
  }

  function syncLabel() {
    const label = document.getElementById("cfg_md_periodo_label");
    const btn = document.getElementById("cfg_md_periodo_btn");
    if (!label) return;
    if (!periodoState.de && !periodoState.ate) {
      label.textContent = "Todo o período";
      btn?.classList.add("is-empty");
      return;
    }
    btn?.classList.remove("is-empty");
    if (periodoState.de && periodoState.ate && sameDay(periodoState.de, periodoState.ate)) {
      label.textContent = fmtBR(periodoState.de);
      return;
    }
    label.textContent = `${fmtBR(periodoState.de) || "…"} - ${fmtBR(periodoState.ate) || "…"}`;
  }

  function syncDraftInputs() {
    const deTxt = document.getElementById("cfg_md_de_txt");
    const ateTxt = document.getElementById("cfg_md_ate_txt");
    if (deTxt) deTxt.value = fmtBR(periodoState.draftDe);
    if (ateTxt) ateTxt.value = fmtBR(periodoState.draftAte);
  }

  function monthLabel(ym) {
    return ym.toLocaleDateString("pt-BR", { month: "long", year: "numeric" });
  }

  function renderMonth(ym, side) {
    const y = ym.getFullYear();
    const m = ym.getMonth();
    const first = new Date(y, m, 1);
    // Segunda = 0 no grid (Se Te Qu Qu Se Sá Do)
    let startDow = first.getDay() - 1;
    if (startDow < 0) startDow = 6;
    const daysInMonth = new Date(y, m + 1, 0).getDate();
    const cells = [];
    for (let i = 0; i < startDow; i++) cells.push(null);
    for (let d = 1; d <= daysInMonth; d++) cells.push(new Date(y, m, d));
    while (cells.length % 7 !== 0) cells.push(null);

    const navLeft =
      side === "left"
        ? `<button type="button" class="CfgMd_CalNav" data-cal-nav="-1" aria-label="Mês anterior">‹</button>`
        : `<span style="width:1.7rem"></span>`;
    const navRight =
      side === "right"
        ? `<button type="button" class="CfgMd_CalNav" data-cal-nav="1" aria-label="Próximo mês">›</button>`
        : `<span style="width:1.7rem"></span>`;

    const dow = ["Se", "Te", "Qu", "Qu", "Se", "Sá", "Do"]
      .map((x) => `<span>${x}</span>`)
      .join("");

    const grid = cells
      .map((d) => {
        if (!d) return `<button type="button" class="CfgMd_CalDay" disabled></button>`;
        const iso = toISODate(d);
        const isStart = sameDay(d, periodoState.draftDe);
        const isEnd = sameDay(d, periodoState.draftAte);
        const inRange = between(d, periodoState.draftDe, periodoState.draftAte);
        const cls = [
          "CfgMd_CalDay",
          isStart ? "is-start" : "",
          isEnd ? "is-end" : "",
          inRange ? "is-inrange" : "",
        ]
          .filter(Boolean)
          .join(" ");
        return `<button type="button" class="${cls}" data-day="${iso}">${d.getDate()}</button>`;
      })
      .join("");

    return `
      <div class="CfgMd_CalMonth" data-side="${side}">
        <div class="CfgMd_CalHead">${navLeft}<strong>${escapeHtml(monthLabel(ym))}</strong>${navRight}</div>
        <div class="CfgMd_CalDow">${dow}</div>
        <div class="CfgMd_CalGrid">${grid}</div>
      </div>`;
  }

  function renderCalendars() {
    const host = document.getElementById("cfg_md_calendars");
    if (!host || !periodoState.viewYm) return;
    const left = periodoState.viewYm;
    const right = new Date(left.getFullYear(), left.getMonth() + 1, 1);
    host.innerHTML = renderMonth(left, "left") + renderMonth(right, "right");
  }

  function applyPreset(key) {
    const hoje = startOfDay(new Date());
    let de = null;
    let ate = null;
    if (key === "hoje") {
      de = ate = hoje;
    } else if (key === "ontem") {
      de = ate = startOfDay(new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate() - 1));
    } else if (key === "7d") {
      de = startOfDay(new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate() - 6));
      ate = hoje;
    } else if (key === "30d") {
      de = startOfDay(new Date(hoje.getFullYear(), hoje.getMonth(), hoje.getDate() - 29));
      ate = hoje;
    } else if (key === "mes") {
      de = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
      ate = new Date(hoje.getFullYear(), hoje.getMonth() + 1, 0);
    } else if (key === "mes_ate_hoje") {
      de = new Date(hoje.getFullYear(), hoje.getMonth(), 1);
      ate = hoje;
    } else if (key === "mes_passado") {
      de = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
      ate = new Date(hoje.getFullYear(), hoje.getMonth(), 0);
    } else if (key === "3m") {
      de = startOfDay(new Date(hoje.getFullYear(), hoje.getMonth() - 2, 1));
      ate = hoje;
    } else if (key === "ano") {
      de = new Date(hoje.getFullYear(), 0, 1);
      ate = hoje;
    }
    periodoState.draftDe = de;
    periodoState.draftAte = ate;
    if (de) periodoState.viewYm = new Date(de.getFullYear(), de.getMonth(), 1);
    syncDraftInputs();
    renderCalendars();
  }

  function pickDay(iso) {
    const d = fromISODate(iso);
    if (!d) return;
    if (!periodoState.draftDe || (periodoState.draftDe && periodoState.draftAte)) {
      periodoState.draftDe = d;
      periodoState.draftAte = null;
    } else if (d.getTime() < periodoState.draftDe.getTime()) {
      periodoState.draftAte = periodoState.draftDe;
      periodoState.draftDe = d;
    } else {
      periodoState.draftAte = d;
    }
    syncDraftInputs();
    renderCalendars();
  }

  function openPeriodo() {
    const pop = document.getElementById("cfg_md_periodo_pop");
    const btn = document.getElementById("cfg_md_periodo_btn");
    if (!pop) return;
    periodoState.draftDe = periodoState.de;
    periodoState.draftAte = periodoState.ate;
    const base = periodoState.draftDe || startOfDay(new Date());
    periodoState.viewYm = new Date(base.getFullYear(), base.getMonth(), 1);
    syncDraftInputs();
    renderCalendars();
    pop.hidden = false;
    periodoState.open = true;
    btn?.classList.add("is-open");
    btn?.setAttribute("aria-expanded", "true");
    window.lucide?.createIcons?.();
  }

  function closePeriodo() {
    const pop = document.getElementById("cfg_md_periodo_pop");
    const btn = document.getElementById("cfg_md_periodo_btn");
    if (pop) pop.hidden = true;
    periodoState.open = false;
    btn?.classList.remove("is-open");
    btn?.setAttribute("aria-expanded", "false");
  }

  function confirmarPeriodo() {
    let de = periodoState.draftDe;
    let ate = periodoState.draftAte || periodoState.draftDe;
    if (de && ate && de.getTime() > ate.getTime()) {
      const t = de;
      de = ate;
      ate = t;
    }
    periodoState.de = de;
    periodoState.ate = ate;
    syncHidden();
    syncLabel();
    closePeriodo();
    carregarTenants().catch((e) => toast("error", e.message));
  }

  function limparPeriodo() {
    periodoState.de = null;
    periodoState.ate = null;
    periodoState.draftDe = null;
    periodoState.draftAte = null;
    syncHidden();
    syncLabel();
    syncDraftInputs();
    renderCalendars();
    closePeriodo();
    carregarTenants().catch((e) => toast("error", e.message));
  }

  function initPeriodo() {
    syncHidden();
    syncLabel();
    document.getElementById("cfg_md_periodo_btn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      if (periodoState.open) closePeriodo();
      else openPeriodo();
    });
    document.getElementById("cfg_md_periodo_ok")?.addEventListener("click", confirmarPeriodo);
    document.getElementById("cfg_md_periodo_limpar")?.addEventListener("click", limparPeriodo);
    document.getElementById("cfg_md_presets")?.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-preset]");
      if (!btn) return;
      applyPreset(btn.getAttribute("data-preset"));
    });
    document.getElementById("cfg_md_calendars")?.addEventListener("click", (e) => {
      const nav = e.target.closest("[data-cal-nav]");
      if (nav) {
        const delta = Number(nav.getAttribute("data-cal-nav") || 0);
        const cur = periodoState.viewYm || startOfDay(new Date());
        periodoState.viewYm = new Date(cur.getFullYear(), cur.getMonth() + delta, 1);
        renderCalendars();
        return;
      }
      const day = e.target.closest("[data-day]");
      if (day) pickDay(day.getAttribute("data-day"));
    });
    document.getElementById("cfg_md_de_txt")?.addEventListener("change", () => {
      const d = parseBR(document.getElementById("cfg_md_de_txt").value);
      if (d) {
        periodoState.draftDe = d;
        periodoState.viewYm = new Date(d.getFullYear(), d.getMonth(), 1);
        renderCalendars();
      }
      syncDraftInputs();
    });
    document.getElementById("cfg_md_ate_txt")?.addEventListener("change", () => {
      const d = parseBR(document.getElementById("cfg_md_ate_txt").value);
      if (d) {
        periodoState.draftAte = d;
        renderCalendars();
      }
      syncDraftInputs();
    });
    // Impede que cliques internos (incl. dias que re-renderizam o grid) borbulhem
    // até o document e disparem o "clique fora".
    document.getElementById("cfg_md_periodo_root")?.addEventListener("click", (e) => {
      e.stopPropagation();
    });
    document.addEventListener("click", (e) => {
      if (!periodoState.open) return;
      const root = document.getElementById("cfg_md_periodo_root");
      if (!root) return;
      // Após re-render do calendário, e.target pode estar desconectado do DOM
      // e root.contains(e.target) vira false — não fechar nesses casos.
      if (e.target && !e.target.isConnected) return;
      if (!root.contains(e.target)) closePeriodo();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && periodoState.open) closePeriodo();
    });
  }

  function renderLista() {
    if (!itens.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="CfgMd_Hint">Nenhum tenant encontrado.</td></tr>`;
      return;
    }
    tbody.innerHTML = itens
      .map((t) => {
        const checked = selecionados.has(t.id) ? "checked" : "";
        const muted = t.sem_email ? "is-muted" : "";
        return `<tr class="${muted}" data-id="${t.id}">
          <td><input type="checkbox" class="cfg-md-chk" data-id="${t.id}" ${checked} ${t.sem_email ? "disabled" : ""} /></td>
          <td>${t.id}</td>
          <td>${escapeHtml(t.nome)}</td>
          <td>${escapeHtml(t.tipo_negocio)}</td>
          <td>${escapeHtml(fmtDataCadastro(t.criado_em))}</td>
          <td>${t.sem_email ? "<em>sem e-mail</em>" : escapeHtml(t.email)}</td>
        </tr>`;
      })
      .join("");
    atualizarContagem();
  }

  async function carregarTenants() {
    const q = document.getElementById("cfg_md_q").value.trim();
    const tipo = document.getElementById("cfg_md_filtro").value;
    const qs = new URLSearchParams({ q, tipo });
    const de = document.getElementById("cfg_md_de")?.value || "";
    const ate = document.getElementById("cfg_md_ate")?.value || "";
    if (de) qs.set("de", de);
    if (ate) qs.set("ate", ate);
    tbody.innerHTML = `<tr><td colspan="6" class="CfgMd_Hint">Carregando…</td></tr>`;
    const j = await api(`${BASE}/tenants?${qs}`);
    itens = j.itens || [];
    const idsValidos = new Set(itens.filter((t) => !t.sem_email).map((t) => t.id));
    selecionados = new Set([...selecionados].filter((id) => idsValidos.has(id)));
    if (chkTodos) chkTodos.checked = false;
    renderLista();
  }

  function abrirDisparoApoio(idEnvio, assunto) {
    if (!window.GlobalUtils?.abrirJanelaApoioModal) {
      toast("error", "Modal de apoio indisponível.");
      return;
    }
    const id = Number(idEnvio) || 0;
    if (!id) {
      toast("error", "Disparo inválido.");
      return;
    }
    // id_envio precisa ir na query: o apoio lê do servidor (não do postMessage).
    const base = cfg.rotaDisparoApoio || `${BASE}/disparo/apoio`;
    const sep = base.includes("?") ? "&" : "?";
    const rota = `${base}${sep}id_envio=${id}`;
    GlobalUtils.abrirJanelaApoioModal({
      rota,
      id,
      titulo: assunto ? `Disparo — ${assunto}` : `Disparo #${id}`,
      largura: 980,
      altura: 720,
      nivel: 1,
    });
  }

  async function carregarHistorico() {
    const u = util();
    histBody.innerHTML = `<tr><td colspan="8" class="CfgMd_Hint">Carregando…</td></tr>`;
    const j = await api(`${BASE}/disparos`);
    const rows = j.itens || [];
    if (!rows.length) {
      histBody.innerHTML = `<tr><td colspan="8" class="CfgMd_Hint">Nenhum disparo ainda.</td></tr>`;
      return;
    }
    histBody.innerHTML = rows
      .map((d) => {
        const dt = d.dt_envio ? new Date(d.dt_envio).toLocaleString("pt-BR") : "—";
        return `<tr data-envio="${d.id_envio}">
          <td>${escapeHtml(dt)}</td>
          <td>${escapeHtml(d.assunto)}</td>
          <td>${d.total}</td>
          <td>${d.entregues}</td>
          <td>${d.abertos}</td>
          <td>${d.bounces}</td>
          <td>${d.erros}</td>
          <td class="Cl_TableActions">
            <button type="button" class="Cl_BtnAcao btnVerDisparo" data-envio="${d.id_envio}" data-assunto="${escapeHtml(d.assunto)}" title="Ver destinatários">${u.gerarIconeTech("visualizar")}</button>
          </td>
        </tr>`;
      })
      .join("");
    u.gerarIconeTech?.refresh?.();
  }

  document.querySelectorAll(".CfgMd_Tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".CfgMd_Tab").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      const tab = btn.getAttribute("data-tab");
      document.getElementById("cfg_md_panel_novo").hidden = tab !== "novo";
      document.getElementById("cfg_md_panel_historico").hidden = tab !== "historico";
      document.getElementById("cfg_md_panel_novo").classList.toggle("is-active", tab === "novo");
      if (tab === "historico") carregarHistorico().catch((e) => toast("error", e.message));
    });
  });

  document.getElementById("cfg_md_btnBuscar")?.addEventListener("click", () => {
    carregarTenants().catch((e) => toast("error", e.message));
  });
  document.getElementById("cfg_md_q")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      carregarTenants().catch((err) => toast("error", err.message));
    }
  });
  document.getElementById("cfg_md_filtro")?.addEventListener("change", () => {
    carregarTenants().catch((e) => toast("error", e.message));
  });

  tbody?.addEventListener("change", (e) => {
    const chk = e.target.closest(".cfg-md-chk");
    if (!chk) return;
    const id = Number(chk.getAttribute("data-id"));
    if (chk.checked) selecionados.add(id);
    else selecionados.delete(id);
    atualizarContagem();
  });

  chkTodos?.addEventListener("change", () => {
    selecionados = new Set();
    if (chkTodos.checked) {
      itens.forEach((t) => {
        if (!t.sem_email) selecionados.add(t.id);
      });
    }
    renderLista();
  });

  document.getElementById("cfg_md_enviar")?.addEventListener("click", async () => {
    const assunto = document.getElementById("cfg_md_assunto").value.trim();
    const corpo = getCorpoHtml();
    if (!assunto || !corpo) return toast("warning", "Preencha assunto e mensagem.");
    if (!selecionados.size && !chkTodos?.checked) return toast("warning", "Selecione ao menos um tenant.");

    const conf = window.Swal
      ? await Swal.fire({
          icon: "question",
          title: "Enviar mala direta?",
          text: `${selecionados.size || "todos da lista"} destinatário(s).`,
          showCancelButton: true,
          confirmButtonText: "Enviar",
          cancelButtonText: "Cancelar",
        })
      : { isConfirmed: confirm("Enviar?") };
    if (!conf.isConfirmed) return;

    try {
      const j = await api(`${BASE}/enviar`, {
        method: "POST",
        body: JSON.stringify({
          assunto,
          corpo_html: corpo,
          filtro_tipo: document.getElementById("cfg_md_filtro").value,
          ids_tenant: [...selecionados],
          selecionar_todos: false,
        }),
      });
      toast("success", j.message || "Enviado");
      if (j.id_envio) {
        document.querySelector('.CfgMd_Tab[data-tab="historico"]')?.click();
        setTimeout(() => abrirDisparoApoio(j.id_envio, assunto), 350);
      }
    } catch (e) {
      toast("error", e.message);
    }
  });

  document.getElementById("cfg_md_enviar_teste")?.addEventListener("click", async () => {
    const assunto = document.getElementById("cfg_md_assunto").value.trim();
    const corpo = getCorpoHtml();
    if (!assunto || !corpo) return toast("warning", "Preencha assunto e mensagem.");

    const conf = window.Swal
      ? await Swal.fire({
          icon: "question",
          title: "Enviar e-mail teste?",
          html: "Será enviado <strong>somente</strong> para <code>hazael@h74.com.br</code>, com a mesma formatação do disparo.",
          showCancelButton: true,
          confirmButtonText: "Enviar teste",
          cancelButtonText: "Cancelar",
        })
      : { isConfirmed: confirm("Enviar teste para hazael@h74.com.br?") };
    if (!conf.isConfirmed) return;

    try {
      const j = await api(`${BASE}/enviar-teste`, {
        method: "POST",
        body: JSON.stringify({ assunto, corpo_html: corpo }),
      });
      toast("success", j.message || "Teste enviado");
    } catch (e) {
      toast("error", e.message);
    }
  });

  histBody?.addEventListener("click", (e) => {
    const btn = e.target.closest(".btnVerDisparo");
    if (!btn) return;
    e.preventDefault();
    abrirDisparoApoio(Number(btn.getAttribute("data-envio")), btn.getAttribute("data-assunto") || "");
  });

  document.getElementById("cfg_md_refresh_hist")?.addEventListener("click", () => {
    carregarHistorico().catch((e) => toast("error", e.message));
  });

  document.getElementById("cfg_md_copiar_webhook")?.addEventListener("click", async () => {
    const url = document.getElementById("cfg_md_webhook")?.textContent || "";
    try {
      await navigator.clipboard.writeText(url);
      toast("success", "URL copiada");
    } catch {
      toast("info", url);
    }
  });

  initEditor();
  initPeriodo();
  carregarTenants().catch((e) => toast("error", e.message));
  window.lucide?.createIcons?.();
})();
