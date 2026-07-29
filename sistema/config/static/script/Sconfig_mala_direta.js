(function () {
  const BASE = "/configuracoes/mala-direta";
  const tbody = document.getElementById("cfg_md_tbody");
  const histBody = document.getElementById("cfg_md_hist_tbody");
  const contagem = document.getElementById("cfg_md_contagem");
  const chkTodos = document.getElementById("cfg_md_todos");
  let itens = [];
  let selecionados = new Set();

  function toast(icon, title) {
    if (window.Swal) Swal.fire({ icon, title, timer: 2200, showConfirmButton: false });
    else alert(title);
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

  function renderLista() {
    if (!itens.length) {
      tbody.innerHTML = `<tr><td colspan="5" class="CfgMd_Hint">Nenhum tenant encontrado.</td></tr>`;
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
          <td>${t.sem_email ? "<em>sem e-mail</em>" : escapeHtml(t.email)}</td>
        </tr>`;
      })
      .join("");
    atualizarContagem();
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function carregarTenants() {
    const q = document.getElementById("cfg_md_q").value.trim();
    const tipo = document.getElementById("cfg_md_filtro").value;
    const qs = new URLSearchParams({ q, tipo });
    tbody.innerHTML = `<tr><td colspan="5" class="CfgMd_Hint">Carregando…</td></tr>`;
    const j = await api(`${BASE}/tenants?${qs}`);
    itens = j.itens || [];
    const idsValidos = new Set(itens.filter((t) => !t.sem_email).map((t) => t.id));
    selecionados = new Set([...selecionados].filter((id) => idsValidos.has(id)));
    renderLista();
  }

  function statusClass(st) {
    const s = String(st || "").toLowerCase();
    if (s.includes("open") || s.includes("click")) return "is-open";
    if (s.includes("bounce") || s.includes("error") || s.includes("fail") || s.includes("spam") || s.includes("block") || s.includes("invalid"))
      return "is-err";
    if (s.includes("deliver") || s === "enviado" || s === "request") return "is-ok";
    return "";
  }

  async function carregarHistorico() {
    histBody.innerHTML = `<tr><td colspan="7" class="CfgMd_Hint">Carregando…</td></tr>`;
    const j = await api(`${BASE}/disparos`);
    const rows = j.itens || [];
    if (!rows.length) {
      histBody.innerHTML = `<tr><td colspan="7" class="CfgMd_Hint">Nenhum disparo ainda.</td></tr>`;
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
        </tr>`;
      })
      .join("");
  }

  async function abrirDetalhe(idEnvio) {
    const vazio = document.getElementById("cfg_md_detalhe_vazio");
    const corpo = document.getElementById("cfg_md_detalhe_corpo");
    const titulo = document.getElementById("cfg_md_detalhe_titulo");
    const meta = document.getElementById("cfg_md_detalhe_meta");
    const tb = document.getElementById("cfg_md_detalhe_tbody");
    const j = await api(`${BASE}/disparos/${idEnvio}`);
    const d = j.disparo;
    titulo.textContent = d.assunto || `Disparo #${idEnvio}`;
    vazio.hidden = true;
    corpo.hidden = false;
    const dt = d.dt_envio ? new Date(d.dt_envio).toLocaleString("pt-BR") : "—";
    meta.innerHTML = `
      <div><dt>Data</dt><dd>${escapeHtml(dt)}</dd></div>
      <div><dt>Tag Brevo</dt><dd>${escapeHtml(d.tag)}</dd></div>
      <div><dt>Filtro</dt><dd>${escapeHtml(d.filtro_tipo || "—")}</dd></div>
      <div><dt>Total</dt><dd>${d.total}</dd></div>`;
    tb.innerHTML = (d.destinatarios || [])
      .map((x) => {
        const ev = x.dt_ultimo_evento ? new Date(x.dt_ultimo_evento).toLocaleString("pt-BR") : "—";
        const cls = statusClass(x.status);
        return `<tr>
          <td>${escapeHtml(x.nome_tenant || (x.id_tenant ? `#${x.id_tenant}` : "—"))}</td>
          <td>${escapeHtml(x.email)}</td>
          <td><span class="CfgMd_Status ${cls}">${escapeHtml(x.status)}</span></td>
          <td>${escapeHtml(ev)}</td>
        </tr>`;
      })
      .join("");
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
    const corpo = document.getElementById("cfg_md_corpo").value.trim();
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
        setTimeout(() => abrirDetalhe(j.id_envio).catch(() => {}), 400);
      }
    } catch (e) {
      toast("error", e.message);
    }
  });

  histBody?.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-envio]");
    if (!tr) return;
    histBody.querySelectorAll("tr").forEach((r) => r.classList.remove("is-selected"));
    tr.classList.add("is-selected");
    abrirDetalhe(Number(tr.getAttribute("data-envio"))).catch((err) => toast("error", err.message));
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

  carregarTenants().catch((e) => toast("error", e.message));
})();
