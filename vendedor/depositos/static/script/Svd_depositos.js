(function () {
  const grid = document.getElementById("vd_dep_grid");
  const vazio = document.getElementById("vd_dep_vazio");
  const modal = document.getElementById("vd_dep_modal");
  const form = document.getElementById("vd_dep_form");
  const secEnd = document.getElementById("vd_dep_secEndereco");
  const secFoot = document.getElementById("vd_dep_secFoot");
  const titulo = document.getElementById("vd_dep_modalTitulo");

  const el = {
    id: document.getElementById("vd_dep_id"),
    espelho: document.getElementById("vd_dep_espelho"),
    cep: document.getElementById("vd_dep_cep"),
    nome: document.getElementById("vd_dep_nome"),
    logradouro: document.getElementById("vd_dep_logradouro"),
    numero: document.getElementById("vd_dep_numero"),
    complemento: document.getElementById("vd_dep_complemento"),
    bairro: document.getElementById("vd_dep_bairro"),
    cidade: document.getElementById("vd_dep_cidade"),
    uf: document.getElementById("vd_dep_uf"),
    principal: document.getElementById("vd_dep_principal"),
    btnCep: document.getElementById("vd_dep_btnCep"),
    btnIncluir: document.getElementById("vd_dep_btnIncluir"),
    btnFechar: document.getElementById("vd_dep_btnFechar"),
    btnCancelar: document.getElementById("vd_dep_btnCancelar"),
    btnExcluir: document.getElementById("vd_dep_btnExcluir"),
    btnSalvar: document.getElementById("vd_dep_btnSalvar"),
  };

  if (!grid || !modal) return;

  const U = window.Util || {};
  const BASE = "/vendedor/depositos";

  function soDigitos(v) {
    return (v || "").replace(/\D/g, "");
  }

  function fmtCep(cep) {
    const d = soDigitos(cep);
    if (d.length !== 8) return cep || "";
    return U.formatarCEP ? U.formatarCEP(d) : d.slice(0, 5) + "-" + d.slice(5);
  }

  function alertar(msg, tipo) {
    if (U.alertar) return U.alertar(msg, tipo || "info");
    return Swal.fire("Atenção", msg, "warning");
  }

  function fecharModal() {
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
  }

  function abrirModal() {
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    el.cep.focus();
  }

  function limparForm() {
    if (el.id) el.id.value = "";
    if (el.espelho) el.espelho.value = "";
    ["cep", "nome", "logradouro", "numero", "complemento", "bairro", "cidade", "uf"].forEach((k) => {
      if (el[k]) el[k].value = "";
    });
    if (el.principal) el.principal.checked = false;
    if (el.btnExcluir) el.btnExcluir.hidden = true;
    if (el.btnSalvar) el.btnSalvar.disabled = false;
    secEnd.hidden = true;
    secFoot.hidden = true;
    titulo.textContent = "Novo depósito";
    ["cep", "nome", "logradouro", "numero", "complemento", "bairro", "cidade", "uf", "principal"].forEach((k) => {
      if (el[k]) el[k].disabled = false;
    });
  }

  function mostrarEndereco() {
    secEnd.hidden = false;
    secFoot.hidden = false;
    if (!el.nome.value.trim()) {
      const c = (el.cidade.value || "").trim();
      const u = (el.uf.value || "").trim();
      if (c && u) el.nome.value = "Filial " + c + (u ? " " + u : "");
    }
    if (el.nome && !el.nome.dataset.touched) el.nome.focus();
  }

  function preencherEndereco(d) {
    const espelho = !!d.espelho_somente_leitura;
    if (el.espelho) el.espelho.value = espelho ? "1" : "";
    el.logradouro.value = d.logradouro || "";
    el.bairro.value = d.bairro || "";
    el.cidade.value = d.cidade || "";
    el.uf.value = d.uf || "";
    el.numero.value = d.numero || "";
    el.complemento.value = d.complemento || "";
    el.nome.value = d.nome || "";
    if (el.principal) el.principal.checked = !!d.principal;
    if (el.id) el.id.value = d.id ? String(d.id) : "";
    if (el.cep) el.cep.value = fmtCep(d.cep);
    if (el.btnExcluir) el.btnExcluir.hidden = !d.id || espelho;
    if (el.btnSalvar) el.btnSalvar.disabled = espelho;
    ["cep", "nome", "logradouro", "numero", "complemento", "bairro", "cidade", "uf", "principal"].forEach((k) => {
      if (el[k]) el[k].disabled = espelho;
    });
    if (el.btnCep) el.btnCep.disabled = espelho;
    titulo.textContent = espelho ? "Depósito espelhado (somente leitura)" : "Editar depósito";
    mostrarEndereco();
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function carregarLista() {
    const r = await fetch(BASE + "/dados", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      alertar(j.message || "Erro ao carregar.", "error");
      return;
    }
    const lista = j.dados || [];
    if (!lista.length) {
      grid.innerHTML = "";
      vazio.hidden = false;
      return;
    }
    vazio.hidden = true;
    grid.innerHTML = lista
      .map((d) => {
        const end = [d.logradouro, d.numero, d.bairro].filter(Boolean).join(", ");
        const loc = (d.cidade || "") + (d.uf ? " / " + d.uf : "");
        const espelho = !!d.espelho_somente_leitura;
        return `
        <article class="FnDep_Card${d.principal ? " is-principal" : ""}${espelho ? " is-espelho" : ""}" tabindex="0" data-id="${d.id}" title="${espelho ? "Espelho do fornecedor" : "Duplo clique para editar"}">
          ${espelho ? '<span class="FnDep_CardBadge">Espelho fornecedor</span>' : d.principal ? '<span class="FnDep_CardBadge">Principal</span>' : ""}
          <h3 class="FnDep_CardNome">${escapeHtml(d.nome)}</h3>
          <p class="FnDep_CardCep">CEP ${fmtCep(d.cep)}</p>
          <p class="FnDep_CardEndereco">${escapeHtml(end)}<br>${escapeHtml(loc)}</p>
          <p class="FnDep_CardHint">${espelho ? "Somente leitura" : "Duplo clique para editar"}</p>
        </article>`;
      })
      .join("");
  }

  async function buscarCep() {
    const cep = soDigitos(el.cep.value);
    if (cep.length !== 8) {
      alertar("Informe um CEP com 8 dígitos.", "warning");
      return;
    }
    try {
      const r = await fetch("https://viacep.com.br/ws/" + cep + "/json/");
      const j = await r.json();
      if (j.erro) throw new Error("CEP não encontrado.");
      el.logradouro.value = j.logradouro || "";
      el.bairro.value = j.bairro || "";
      el.cidade.value = j.localidade || "";
      el.uf.value = j.uf || "";
      mostrarEndereco();
    } catch (e) {
      alertar(e.message || "Não foi possível buscar o CEP.", "error");
    }
  }

  async function abrirEdicao(id) {
    limparForm();
    const r = await fetch(BASE + "/apoio", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!j.success || !j.dados) {
      alertar(j.message || "Erro ao abrir depósito.", "error");
      return;
    }
    preencherEndereco(j.dados);
    abrirModal();
  }

  function abrirNovo() {
    limparForm();
    abrirModal();
  }

  async function salvar(e) {
    e.preventDefault();
    if (el.espelho && el.espelho.value === "1") {
      alertar("Depósito espelhado do fornecedor não pode ser alterado.", "warning");
      return;
    }
    const body = {
      id: el.id.value ? parseInt(el.id.value, 10) : null,
      cep: soDigitos(el.cep.value),
      nome: (el.nome.value || "").trim(),
      logradouro: (el.logradouro.value || "").trim(),
      numero: (el.numero.value || "S/N").trim(),
      complemento: (el.complemento.value || "").trim(),
      bairro: (el.bairro.value || "").trim(),
      cidade: (el.cidade.value || "").trim(),
      uf: (el.uf.value || "").trim(),
      principal: el.principal.checked,
      ativo: true,
    };
    if (!body.nome) {
      alertar("Dê um nome ao depósito (ex.: Filial SP).", "warning");
      return;
    }
    const r = await fetch(BASE + "/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.success) {
      alertar(j.message || "Erro ao salvar.", "error");
      return;
    }
    alertar(j.message || "Salvo.", "success");
    fecharModal();
    carregarLista();
  }

  async function excluir() {
    const id = parseInt(el.id.value, 10);
    if (!id) return;
    const ok = await Swal.fire({
      title: "Excluir depósito?",
      text: "Esta ação não pode ser desfeita.",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Excluir",
      cancelButtonText: "Cancelar",
    });
    if (!ok.isConfirmed) return;
    const r = await fetch(BASE + "/excluir", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!j.success) {
      alertar(j.message || "Erro ao excluir.", "error");
      return;
    }
    fecharModal();
    carregarLista();
  }

  grid.addEventListener("dblclick", (e) => {
    const card = e.target.closest("[data-id]");
    if (card) abrirEdicao(Number(card.dataset.id));
  });

  if (el.btnIncluir) el.btnIncluir.addEventListener("click", abrirNovo);
  if (el.btnFechar) el.btnFechar.addEventListener("click", fecharModal);
  if (el.btnCancelar) el.btnCancelar.addEventListener("click", fecharModal);
  if (el.btnCep) el.btnCep.addEventListener("click", buscarCep);
  if (el.btnExcluir) el.btnExcluir.addEventListener("click", excluir);
  if (form) form.addEventListener("submit", salvar);
  if (el.nome) {
    el.nome.addEventListener("input", () => {
      el.nome.dataset.touched = "1";
    });
  }

  carregarLista();
})();
