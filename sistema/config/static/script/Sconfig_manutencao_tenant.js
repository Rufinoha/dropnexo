(function () {
  const BASE = "/configuracoes/manutencao-tenant";
  const el = {
    q: document.getElementById("cfg_mt_q"),
    filtroTipo: document.getElementById("cfg_mt_filtro_tipo"),
    btnBuscar: document.getElementById("cfg_mt_btnBuscar"),
    tbody: document.getElementById("cfg_mt_tbody"),
    form: document.getElementById("cfg_mt_form"),
    formVazio: document.getElementById("cfg_mt_form_vazio"),
    formTitulo: document.getElementById("cfg_mt_form_titulo"),
    id: document.getElementById("cfg_mt_id"),
    nome: document.getElementById("cfg_mt_nome"),
    slug: document.getElementById("cfg_mt_slug"),
    tipo: document.getElementById("cfg_mt_tipo"),
    plano: document.getElementById("cfg_mt_plano"),
    documento: document.getElementById("cfg_mt_documento"),
    ativo: document.getElementById("cfg_mt_ativo"),
    limparSeg: document.getElementById("cfg_mt_limpar_seg"),
    wrapLimpar: document.getElementById("cfg_mt_wrap_limpar_seg"),
    counts: document.getElementById("cfg_mt_counts"),
    warn: document.getElementById("cfg_mt_warn"),
    msg: document.getElementById("cfg_mt_msg"),
  };

  let selecionado = null;
  let tipoOriginal = "";

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function badgeTipo(t) {
    const x = (t || "vendedor").toLowerCase();
    return `<span class="CfgMt_Badge CfgMt_Badge--${esc(x)}">${esc(x)}</span>`;
  }

  function mostrarMsg(texto, erro) {
    if (!el.msg) return;
    el.msg.hidden = !texto;
    el.msg.textContent = texto || "";
    el.msg.classList.toggle("CfgMt_MsgErro", !!erro);
    el.msg.classList.toggle("CfgMt_MsgOk", !!texto && !erro);
  }

  function atualizarLimparSeg() {
    const vaiVendedor = (el.tipo?.value || "") === "vendedor";
    const mudou = (el.tipo?.value || "") !== tipoOriginal;
    if (el.wrapLimpar) el.wrapLimpar.hidden = !(vaiVendedor && mudou);
    if (el.limparSeg && !(vaiVendedor && mudou)) el.limparSeg.checked = false;
    if (el.limparSeg && vaiVendedor && mudou && tipoOriginal === "fornecedor") {
      el.limparSeg.checked = true;
    }
  }

  async function carregarLista() {
    const qs = new URLSearchParams();
    const q = (el.q?.value || "").trim();
    const tipo = (el.filtroTipo?.value || "").trim();
    if (q) qs.set("q", q);
    if (tipo) qs.set("tipo", tipo);
    el.tbody.innerHTML = `<tr><td colspan="5" class="CfgMt_Hint">Carregando…</td></tr>`;
    try {
      const r = await fetch(`${BASE}/dados?${qs}`, { credentials: "same-origin" });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao listar.");
      const itens = j.itens || [];
      if (!itens.length) {
        el.tbody.innerHTML = `<tr><td colspan="5" class="CfgMt_Hint">Nenhum tenant encontrado.</td></tr>`;
        return;
      }
      el.tbody.innerHTML = itens
        .map(
          (t) => `
        <tr data-id="${t.id}" class="${selecionado === t.id ? "is-selected" : ""}">
          <td>${t.id}</td>
          <td><strong>${esc(t.nome)}</strong><br><small>${esc(t.slug)}</small></td>
          <td>${badgeTipo(t.tipo_negocio)}</td>
          <td>${esc(t.plano)}</td>
          <td>${t.ativo ? "Sim" : "Não"}</td>
        </tr>`
        )
        .join("");
    } catch (e) {
      el.tbody.innerHTML = `<tr><td colspan="5" class="CfgMt_Hint">${esc(e.message)}</td></tr>`;
    }
  }

  async function abrirTenant(id) {
    mostrarMsg("", false);
    try {
      const r = await fetch(`${BASE}/${id}`, { credentials: "same-origin" });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar.");
      const t = j.tenant;
      selecionado = t.id;
      tipoOriginal = t.tipo_negocio || "vendedor";
      el.id.value = t.id;
      el.nome.value = t.nome || "";
      el.slug.value = t.slug || "";
      el.tipo.value = t.tipo_negocio || "vendedor";
      el.plano.value = ["starter", "professional", "scale", "enterprise"].includes(t.plano)
        ? t.plano
        : "starter";
      el.documento.value = t.documento || "";
      el.ativo.checked = !!t.ativo;
      el.formTitulo.textContent = `#${t.id} · ${t.nome || ""}`;
      el.formVazio.hidden = true;
      el.form.hidden = false;

      const c = t.contagens || {};
      el.counts.hidden = false;
      el.counts.innerHTML = `
        <span>Produtos: <strong>${c.produtos || 0}</strong></span>
        <span>Segmentos forn.: <strong>${c.segmentos || 0}</strong></span>
        <span>Vínculos (como forn.): <strong>${c.vinculos_como_fornecedor || 0}</strong></span>
        <span>Vínculos (como vend.): <strong>${c.vinculos_como_vendedor || 0}</strong></span>
        <span>Pedidos (como forn.): <strong>${c.pedidos_como_fornecedor || 0}</strong></span>
        <span>Pedidos (como vend.): <strong>${c.pedidos_como_vendedor || 0}</strong></span>
      `;

      const risco =
        (c.produtos || 0) +
          (c.vinculos_como_fornecedor || 0) +
          (c.pedidos_como_fornecedor || 0) >
        0;
      el.warn.hidden = !risco;
      el.warn.textContent = risco
        ? "Este tenant já tem dados de fornecedor. Se for só erro de cadastro e os contadores forem baixos, ok. Se já opera como fornecedor, prefira Híbrido."
        : "";

      atualizarLimparSeg();
      el.tbody?.querySelectorAll("tr[data-id]").forEach((tr) => {
        tr.classList.toggle("is-selected", +tr.dataset.id === t.id);
      });
    } catch (e) {
      mostrarMsg(e.message, true);
    }
  }

  async function salvar(ev) {
    ev.preventDefault();
    const id = +el.id.value;
    if (!id) return;
    const body = {
      id,
      nome: el.nome.value.trim(),
      slug: el.slug.value.trim(),
      tipo_negocio: el.tipo.value,
      plano: el.plano.value,
      documento: el.documento.value.trim(),
      ativo: !!el.ativo.checked,
      limpar_segmentos_fornecedor: !!el.limparSeg?.checked,
    };
    if (body.tipo_negocio !== tipoOriginal) {
      const conf = await Swal.fire({
        icon: "warning",
        title: "Alterar tipo de negócio?",
        html: `De <strong>${esc(tipoOriginal)}</strong> para <strong>${esc(body.tipo_negocio)}</strong>.<br><small>O usuário precisará sair e entrar de novo.</small>`,
        showCancelButton: true,
        confirmButtonText: "Sim, alterar",
        cancelButtonText: "Cancelar",
        confirmButtonColor: "#021F81",
      });
      if (!conf.isConfirmed) return;
    }
    el.btnSalvar = document.getElementById("cfg_mt_btnSalvar");
    if (el.btnSalvar) el.btnSalvar.disabled = true;
    try {
      const r = await fetch(`${BASE}/salvar`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao salvar.");
      tipoOriginal = body.tipo_negocio;
      let texto = j.message || "Salvo.";
      if (j.avisos?.length) texto += " " + j.avisos.join(" ");
      await Swal.fire({
        icon: "success",
        title: "Atualizado",
        text: texto,
        confirmButtonColor: "#021F81",
      });
      mostrarMsg(texto, false);
      await carregarLista();
      await abrirTenant(id);
      if (j.sessao_atualizada) {
        // sessão do DEV no próprio tenant já foi atualizada no servidor
      }
    } catch (e) {
      await Swal.fire({
        icon: "error",
        title: "Erro",
        text: e.message,
        confirmButtonColor: "#021F81",
      });
      mostrarMsg(e.message, true);
    } finally {
      if (el.btnSalvar) el.btnSalvar.disabled = false;
    }
  }

  el.btnBuscar?.addEventListener("click", () => carregarLista());
  el.q?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      carregarLista();
    }
  });
  el.filtroTipo?.addEventListener("change", () => carregarLista());
  el.tbody?.addEventListener("click", (e) => {
    const tr = e.target.closest("tr[data-id]");
    if (tr) abrirTenant(+tr.dataset.id);
  });
  el.tipo?.addEventListener("change", atualizarLimparSeg);
  el.form?.addEventListener("submit", salvar);

  carregarLista();
})();
