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

  function abrirDisparoApoio(idEnvio, assunto) {
    if (!window.GlobalUtils?.abrirJanelaApoioModal) {
      toast("error", "Modal de apoio indisponível.");
      return;
    }
    const rota = cfg.rotaDisparoApoio || `${BASE}/disparo-apoio`;
    GlobalUtils.abrirJanelaApoioModal({
      rota,
      id: idEnvio,
      titulo: assunto ? `Disparo — ${assunto}` : `Disparo #${idEnvio}`,
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
  carregarTenants().catch((e) => toast("error", e.message));
})();
