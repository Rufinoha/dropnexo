(function () {
  const grid = document.getElementById("fn_var_grid");
  const vazio = document.getElementById("fn_var_vazio");
  const modal = document.getElementById("fn_var_modal");
  const attrsBox = document.getElementById("fn_var_attrs");
  const titulo = document.getElementById("fn_var_modalTitulo");

  const el = {
    id: document.getElementById("fn_var_id"),
    nome: document.getElementById("fn_var_nome"),
    descricao: document.getElementById("fn_var_descricao"),
    btnNovo: document.getElementById("fn_var_btnNovo"),
    btnSalvar: document.getElementById("fn_var_btnSalvar"),
    btnExcluir: document.getElementById("fn_var_btnExcluir"),
    btnCancelar: document.getElementById("fn_var_btnCancelar"),
    btnFechar: document.getElementById("fn_var_btnFechar"),
    btnAddAttr: document.getElementById("fn_var_btnAddAttr"),
  };

  if (!grid || !modal) return;

  const BASE = "/fornecedor/variacoes";

  function rotuloAtributos(atributos) {
    if (!atributos?.length) return "—";
    return atributos
      .map((a) => `${a.nome}: ${(a.valores || []).join(", ")}`)
      .join(" · ");
  }

  function renderCard(item) {
    const tags = (item.atributos || [])
      .map((a) => `<span class="FnVar_Tag">${a.nome}</span>`)
      .join("");
    return `<article class="FnVar_Card" data-id="${item.id}">
      <h4 class="FnVar_CardTitulo">${item.nome}</h4>
      ${item.descricao ? `<p class="FnVar_CardDesc">${item.descricao}</p>` : ""}
      <div class="FnVar_CardTags">${tags}</div>
      <p class="FnVar_Hint" style="margin-top:10px;">${rotuloAtributos(item.atributos)}</p>
    </article>`;
  }

  async function carregar() {
    const r = await fetch(`${BASE}/dados`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Erro ao carregar.");
    const linhas = (j.linhas || []).filter((x) => x.ativo !== false);
    if (!linhas.length) {
      grid.innerHTML = "";
      vazio.hidden = false;
      return;
    }
    vazio.hidden = true;
    grid.innerHTML = linhas.map(renderCard).join("");
  }

  function addAttrRow(nome, valores) {
    const row = document.createElement("div");
    row.className = "FnVar_AttrRow";
    row.innerHTML = `
      <input type="text" class="fn_var_attr_nome" placeholder="Nome (ex. Cor)" value="${nome || ""}" />
      <input type="text" class="fn_var_attr_vals" placeholder="Opções: Azul, Verde" value="${valores || ""}" />
      <button type="button" class="FnVar_AttrRm" title="Remover">×</button>`;
    attrsBox.appendChild(row);
    row.querySelector(".FnVar_AttrRm").addEventListener("click", () => row.remove());
  }

  function limparModal() {
    el.id.value = "";
    el.nome.value = "";
    el.descricao.value = "";
    attrsBox.innerHTML = "";
    addAttrRow("", "");
    if (el.btnExcluir) el.btnExcluir.hidden = true;
    titulo.textContent = "Novo modelo";
  }

  function abrirModal() {
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    el.nome.focus();
  }

  function fecharModal() {
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
  }

  function coletarAtributos() {
    const rows = attrsBox.querySelectorAll(".FnVar_AttrRow");
    const out = [];
    rows.forEach((row) => {
      const nome = (row.querySelector(".fn_var_attr_nome")?.value || "").trim();
      const vals = (row.querySelector(".fn_var_attr_vals")?.value || "").trim();
      if (nome && vals) out.push({ nome, valores: vals });
    });
    return out;
  }

  function preencherModal(item) {
    el.id.value = item.id ? String(item.id) : "";
    el.nome.value = item.nome || "";
    el.descricao.value = item.descricao || "";
    attrsBox.innerHTML = "";
    (item.atributos || []).forEach((a) => {
      addAttrRow(a.nome, (a.valores || []).join(", "));
    });
    if (!item.atributos?.length) addAttrRow("", "");
    if (el.btnExcluir) el.btnExcluir.hidden = !item.id;
    titulo.textContent = item.id ? "Editar modelo" : "Novo modelo";
  }

  async function salvar() {
    const body = {
      id: el.id.value ? Number(el.id.value) : null,
      nome: (el.nome.value || "").trim(),
      descricao: (el.descricao.value || "").trim(),
      atributos: coletarAtributos(),
    };
    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    fecharModal();
    await carregar();
    await Swal.fire("Sucesso", j.message, "success");
  }

  async function excluir() {
    const id = Number(el.id.value);
    if (!id) return;
    const c = await Swal.fire({
      title: "Remover modelo?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, remover",
    });
    if (!c.isConfirmed) return;
    const r = await fetch(`${BASE}/excluir`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    fecharModal();
    await carregar();
    await Swal.fire("Sucesso", j.message, "success");
  }

  el.btnNovo?.addEventListener("click", () => {
    limparModal();
    abrirModal();
  });
  el.btnAddAttr?.addEventListener("click", () => addAttrRow("", ""));
  el.btnSalvar?.addEventListener("click", () => salvar().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnExcluir?.addEventListener("click", () => excluir().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnCancelar?.addEventListener("click", fecharModal);
  el.btnFechar?.addEventListener("click", fecharModal);
  grid.addEventListener("click", (ev) => {
    const card = ev.target.closest(".FnVar_Card");
    if (!card) return;
    fetch(`${BASE}/dados`, { credentials: "same-origin" })
      .then((r) => r.json())
      .then((j) => {
        const item = (j.linhas || []).find((x) => String(x.id) === card.dataset.id);
        if (!item) return;
        preencherModal(item);
        abrirModal();
      })
      .catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
})();
