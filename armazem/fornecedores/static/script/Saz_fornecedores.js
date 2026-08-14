(function () {
  const grid = document.getElementById("az_forn_grid");
  const vazio = document.getElementById("az_forn_vazio");
  const modal = document.getElementById("az_forn_modal");
  const form = document.getElementById("az_forn_form");
  const titulo = document.getElementById("az_forn_titulo");
  const busca = document.getElementById("az_forn_busca");
  const BASE = "/armazem/fornecedores";

  const el = {
    id: document.getElementById("az_forn_id"),
    nome: document.getElementById("az_forn_nome"),
    fantasia: document.getElementById("az_forn_fantasia"),
    doc: document.getElementById("az_forn_doc"),
    email: document.getElementById("az_forn_email"),
    tel: document.getElementById("az_forn_tel"),
    wa: document.getElementById("az_forn_wa"),
    obs: document.getElementById("az_forn_obs"),
    btnExcluir: document.getElementById("az_forn_btnExcluir"),
  };

  if (!grid || !modal) return;

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function abrirModal(dados) {
    el.id.value = dados?.id || "";
    el.nome.value = dados?.nome || "";
    el.fantasia.value = dados?.nome_fantasia || "";
    el.doc.value = dados?.documento || "";
    el.email.value = dados?.email || "";
    el.tel.value = dados?.telefone || "";
    el.wa.value = dados?.whatsapp || "";
    el.obs.value = dados?.observacoes || "";
    titulo.textContent = dados?.id ? "Editar fornecedor" : "Novo fornecedor";
    el.btnExcluir.hidden = !dados?.id;
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
  }

  function fecharModal() {
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
  }

  async function carregar() {
    const q = (busca?.value || "").trim();
    const url = q ? `${BASE}/dados?busca=${encodeURIComponent(q)}` : `${BASE}/dados`;
    const r = await fetch(url, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const lista = j.dados || [];
    if (!lista.length) {
      grid.innerHTML = "";
      if (vazio) vazio.hidden = false;
      return;
    }
    if (vazio) vazio.hidden = true;
    grid.innerHTML = lista
      .map(
        (f) => `
      <article class="AzForn_Card" data-id="${f.id}">
        <strong>${esc(f.nome_fantasia || f.nome)}</strong>
        <span>${esc(f.nome_fantasia && f.nome_fantasia !== f.nome ? f.nome : "")}</span>
        <span class="AzForn_Meta">${esc(f.documento || "Sem documento")}${f.email ? " · " + esc(f.email) : ""}</span>
      </article>`
      )
      .join("");
  }

  document.getElementById("az_forn_btnIncluir")?.addEventListener("click", () => abrirModal(null));
  document.getElementById("az_forn_btnFechar")?.addEventListener("click", fecharModal);
  document.getElementById("az_forn_btnCancelar")?.addEventListener("click", fecharModal);

  grid.addEventListener("dblclick", async (e) => {
    const card = e.target.closest("[data-id]");
    if (!card) return;
    const r = await fetch(`${BASE}/apoio`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: Number(card.dataset.id) }),
    });
    const j = await r.json();
    if (j.success) abrirModal(j.dados);
  });

  form?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = {
      id: el.id.value ? Number(el.id.value) : null,
      nome: el.nome.value,
      nome_fantasia: el.fantasia.value,
      documento: el.doc.value,
      email: el.email.value,
      telefone: el.tel.value,
      whatsapp: el.wa.value,
      observacoes: el.obs.value,
      ativo: true,
    };
    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (window.Util?.alertar) Util.alertar(j.message || (j.success ? "Salvo" : "Erro"), j.success ? "success" : "error");
    else if (window.Swal) Swal.fire(j.success ? "Salvo" : "Erro", j.message, j.success ? "success" : "error");
    if (j.success) {
      fecharModal();
      carregar();
    }
  });

  el.btnExcluir?.addEventListener("click", async () => {
    if (!el.id.value) return;
    const ok = window.Swal
      ? (await Swal.fire({ icon: "warning", title: "Excluir fornecedor?", showCancelButton: true, confirmButtonText: "Excluir", confirmButtonColor: "#b91c1c" })).isConfirmed
      : confirm("Excluir fornecedor?");
    if (!ok) return;
    const r = await fetch(`${BASE}/excluir`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: Number(el.id.value) }),
    });
    const j = await r.json();
    if (window.Util?.alertar) Util.alertar(j.message, j.success ? "success" : "error");
    if (j.success) {
      fecharModal();
      carregar();
    }
  });

  let t = null;
  busca?.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(carregar, 280);
  });

  carregar();
})();
