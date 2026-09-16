(function () {
  const grid = document.getElementById("az_dep_grid");
  const vazio = document.getElementById("az_dep_vazio");
  const modal = document.getElementById("az_dep_modal");
  const form = document.getElementById("az_dep_form");
  const secEnd = document.getElementById("az_dep_secEndereco");
  const secFoot = document.getElementById("az_dep_secFoot");
  const secBling = document.getElementById("az_dep_secBling");
  const titulo = document.getElementById("az_dep_modalTitulo");

  const el = {
    id: document.getElementById("az_dep_id"),
    cep: document.getElementById("az_dep_cep"),
    nome: document.getElementById("az_dep_nome"),
    logradouro: document.getElementById("az_dep_logradouro"),
    numero: document.getElementById("az_dep_numero"),
    complemento: document.getElementById("az_dep_complemento"),
    bairro: document.getElementById("az_dep_bairro"),
    cidade: document.getElementById("az_dep_cidade"),
    uf: document.getElementById("az_dep_uf"),
    principal: document.getElementById("az_dep_principal"),
    bling: document.getElementById("az_dep_bling"),
    blingHint: document.getElementById("az_dep_blingHint"),
    btnCep: document.getElementById("az_dep_btnCep"),
    btnIncluir: document.getElementById("az_dep_btnIncluir"),
    btnFechar: document.getElementById("az_dep_btnFechar"),
    btnCancelar: document.getElementById("az_dep_btnCancelar"),
    btnExcluir: document.getElementById("az_dep_btnExcluir"),
  };

  if (!grid || !modal) return;

  const U = window.Util || {};
  const BASE = "/armazem/depositos";

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
    ["cep", "nome", "logradouro", "numero", "complemento", "bairro", "cidade", "uf"].forEach((k) => {
      if (el[k]) el[k].value = "";
    });
    if (el.principal) el.principal.checked = false;
    if (el.btnExcluir) el.btnExcluir.hidden = true;
    if (el.bling) el.bling.innerHTML = '<option value="">— Sem vínculo —</option>';
    if (secBling) secBling.hidden = true;
    secEnd.hidden = true;
    secFoot.hidden = true;
    titulo.textContent = "Novo depósito";
  }

  function aplicarBlingNoForm(bling, idSelecionado) {
    if (!secBling || !el.bling) return;
    if (!bling || !bling.conectado) {
      secBling.hidden = true;
      return;
    }
    const opcoes = bling.opcoes || [];
    el.bling.innerHTML =
      '<option value="">— Sem vínculo —</option>' +
      opcoes
        .map((o) => `<option value="${escapeHtml(o.id)}">${escapeHtml(o.nome || o.id)}</option>`)
        .join("");
    const sel = idSelecionado || (bling.vinculo && bling.vinculo.id_bling_deposito) || "";
    el.bling.value = sel;
    if (el.blingHint) {
      el.blingHint.textContent = bling.aviso
        ? "Lista do Bling parcial: " + bling.aviso
        : "Vincule este depósito ao depósito correspondente no Bling para liberar a importação de estoque.";
    }
    secBling.hidden = false;
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
    if (el.btnExcluir) el.btnExcluir.hidden = !d.id;
    mostrarEndereco();
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
        const vinc = d.bling_vinculo;
        const badgeBling = vinc
          ? `<span class="AzDep_CardBadge AzDep_CardBadge--bling" title="Vinculado ao Bling">Bling</span>`
          : "";
        return `
        <article class="AzDep_Card${d.principal ? " is-principal" : ""}${vinc ? " is-bling" : ""}" tabindex="0" data-id="${d.id}" title="Duplo clique para editar / vincular Bling">
          ${d.principal ? '<span class="AzDep_CardBadge">Principal</span>' : ""}
          ${badgeBling}
          <h3 class="AzDep_CardNome">${escapeHtml(d.nome)}</h3>
          <p class="AzDep_CardCep">CEP ${fmtCep(d.cep)}</p>
          <p class="AzDep_CardEndereco">${escapeHtml(end)}<br>${escapeHtml(loc)}</p>
          <p class="AzDep_CardHint">${vinc ? "Vinculado: " + escapeHtml(vinc.nome_bling || vinc.id_bling_deposito) : "Duplo clique para editar / vincular Bling"}</p>
        </article>`;
      })
      .join("");
  }

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
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
    titulo.textContent = "Editar depósito";
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
    aplicarBlingNoForm(j.bling, j.dados.id_bling_deposito);
    abrirModal();
  }

  async function abrirNovo() {
    limparForm();
    titulo.textContent = "Novo depósito";
    try {
      const r = await fetch(BASE + "/apoio", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });
      const j = await r.json();
      if (j.success) aplicarBlingNoForm(j.bling, "");
    } catch (_) {
      /* sem Bling ok */
    }
    abrirModal();
  }

  async function salvar(e) {
    e.preventDefault();
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
    if (secBling && !secBling.hidden && el.bling) {
      body.id_bling_deposito = el.bling.value || "";
      const opt = el.bling.options[el.bling.selectedIndex];
      body.nome_bling = opt && el.bling.value ? opt.textContent : null;
    }
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
    if (!el.id.value) return;
    const ok = U.confirmar
      ? await U.confirmar(
          "Remover depósito?",
          "Produtos vinculados perderão o depósito de expedição."
        )
      : window.confirm("Remover este depósito?");
    if (!ok) return;
    const r = await fetch(BASE + "/excluir", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: parseInt(el.id.value, 10) }),
    });
    const j = await r.json();
    if (!j.success) {
      alertar(j.message || "Erro ao excluir.", "error");
      return;
    }
    alertar(j.message, "success");
    fecharModal();
    carregarLista();
  }

  if (U.aplicarMascaraCEP) U.aplicarMascaraCEP(el.cep);

  el.nome.addEventListener("input", () => {
    el.nome.dataset.touched = "1";
  });

  el.btnIncluir.addEventListener("click", abrirNovo);
  el.btnCep.addEventListener("click", buscarCep);
  el.cep.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      buscarCep();
    }
  });
  el.btnFechar.addEventListener("click", fecharModal);
  el.btnCancelar.addEventListener("click", fecharModal);
  if (el.btnExcluir) el.btnExcluir.addEventListener("click", excluir);
  form.addEventListener("submit", salvar);

  modal.addEventListener("click", (ev) => {
    if (ev.target === modal) fecharModal();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !modal.hidden) fecharModal();
  });

  grid.addEventListener("dblclick", (ev) => {
    const card = ev.target.closest(".AzDep_Card");
    if (!card) return;
    abrirEdicao(card.getAttribute("data-id"));
  });

  carregarLista();
})();
