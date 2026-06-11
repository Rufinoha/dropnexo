(function () {
  let idFornecedor = null;
  let regrasCache = [];
  let depositosCache = [];

  const el = {
    id: document.getElementById("id"),
    documento: document.getElementById("documento"),
    razao_social: document.getElementById("razao_social"),
    nome_fantasia: document.getElementById("nome_fantasia"),
    nome: document.getElementById("nome"),
    situacao_cadastral: document.getElementById("situacao_cadastral"),
    cnae_principal: document.getElementById("cnae_principal"),
    inscricao_estadual: document.getElementById("inscricao_estadual"),
    telefone_comercial: document.getElementById("telefone_comercial"),
    email_comercial: document.getElementById("email_comercial"),
    ativo: document.getElementById("ativo"),
    btnBuscarCnpj: document.getElementById("btnBuscarCnpj"),
    btnSalvar: document.getElementById("btnSalvar"),
    tabBtnDepositos: document.getElementById("tabBtnDepositos"),
    tabBtnRegras: document.getElementById("tabBtnRegras"),
    lista_depositos: document.getElementById("lista_depositos"),
    lista_regras: document.getElementById("lista_regras"),
    dep_id: document.getElementById("dep_id"),
    dep_cep: document.getElementById("dep_cep"),
    dep_nome: document.getElementById("dep_nome"),
    dep_logradouro: document.getElementById("dep_logradouro"),
    dep_numero: document.getElementById("dep_numero"),
    dep_complemento: document.getElementById("dep_complemento"),
    dep_bairro: document.getElementById("dep_bairro"),
    dep_cidade: document.getElementById("dep_cidade"),
    dep_uf: document.getElementById("dep_uf"),
    dep_remetente_nome: document.getElementById("dep_remetente_nome"),
    dep_remetente_documento: document.getElementById("dep_remetente_documento"),
    dep_principal: document.getElementById("dep_principal"),
    btnBuscarCepDep: document.getElementById("btnBuscarCepDep"),
    btnSalvarDeposito: document.getElementById("btnSalvarDeposito"),
  };
  if (!el.documento) return;

  const BASE = window.DN_GESTAO_BASE || "/configuracoes/fornecedores-plataforma";
  const U = window.Util || {};

  function util() {
    return window.Util || { gerarIconeTech: () => "…" };
  }

  function soDigitos(v) {
    return (v || "").replace(/\D/g, "");
  }

  const TAB_ORDER = ["pj", "depositos", "regras"];

  function atualizarFooterHint(cod) {
    const hint = document.getElementById("forn_footer_hint");
    if (!hint) return;
    if (!idFornecedor) {
      hint.textContent = "Salve os dados da empresa para liberar depósitos e regras comerciais.";
      return;
    }
    if (cod === "depositos") hint.textContent = "Cadastre ao menos um depósito com CEP único para expedição.";
    else if (cod === "regras") hint.textContent = "Defina as regras visíveis aos vendedores da rede DropNexo.";
    else hint.textContent = "Revise os dados e avance pelas etapas ou salve o fornecedor.";
  }

  function habilitarAbasExtras() {
    const ok = !!idFornecedor;
    if (el.tabBtnDepositos) el.tabBtnDepositos.disabled = !ok;
    if (el.tabBtnRegras) el.tabBtnRegras.disabled = !ok;
    document.querySelectorAll(".Forn_Step").forEach((s) => {
      if (s.dataset.tab !== "pj") s.classList.toggle("is-done", ok && TAB_ORDER.indexOf(s.dataset.tab) < TAB_ORDER.indexOf(getTabAtiva()));
    });
    atualizarFooterHint(getTabAtiva());
  }

  function getTabAtiva() {
    const active = document.querySelector(".Forn_Step.is-active");
    return active?.dataset.tab || "pj";
  }

  function ativarTab(cod) {
    const idx = TAB_ORDER.indexOf(cod);
    document.querySelectorAll(".Forn_Step").forEach((s) => {
      const si = TAB_ORDER.indexOf(s.dataset.tab);
      s.classList.toggle("is-active", s.dataset.tab === cod);
      s.classList.toggle("is-done", idFornecedor && si >= 0 && si < idx);
    });
    document.querySelectorAll(".Forn_TabPanel").forEach((p) => {
      const on = p.dataset.panel === cod;
      p.classList.toggle("is-active", on);
      p.hidden = !on;
    });
    atualizarFooterHint(cod);
  }

  document.querySelectorAll(".Forn_Step").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (btn.disabled) return;
      ativarTab(btn.dataset.tab);
    });
  });

  U.aplicarMascaraCNPJ?.(el.documento);
  U.aplicarMascaraCEP?.(el.dep_cep);

  function limparFormDeposito() {
    if (el.dep_id) el.dep_id.value = "";
    ["dep_cep", "dep_nome", "dep_logradouro", "dep_numero", "dep_complemento", "dep_bairro", "dep_cidade", "dep_uf", "dep_remetente_nome", "dep_remetente_documento"].forEach((k) => {
      if (el[k]) el[k].value = "";
    });
    if (el.dep_principal) el.dep_principal.checked = false;
  }

  function preencherDep(d) {
    if (el.dep_id) el.dep_id.value = d.id ? String(d.id) : "";
    if (el.dep_cep) el.dep_cep.value = U.formatarCEP ? U.formatarCEP(d.cep) : d.cep;
    if (el.dep_nome) el.dep_nome.value = d.nome || "";
    if (el.dep_logradouro) el.dep_logradouro.value = d.logradouro || "";
    if (el.dep_numero) el.dep_numero.value = d.numero || "";
    if (el.dep_complemento) el.dep_complemento.value = d.complemento || "";
    if (el.dep_bairro) el.dep_bairro.value = d.bairro || "";
    if (el.dep_cidade) el.dep_cidade.value = d.cidade || "";
    if (el.dep_uf) el.dep_uf.value = d.uf || "";
    if (el.dep_remetente_nome) el.dep_remetente_nome.value = d.remetente_nome || el.nome?.value || "";
    if (el.dep_remetente_documento) el.dep_remetente_documento.value = d.remetente_documento || soDigitos(el.documento.value);
    if (el.dep_principal) el.dep_principal.checked = !!d.principal;
  }

  function renderDepositos() {
    const u = util();
    if (!depositosCache.length) {
      el.lista_depositos.innerHTML =
        '<tr><td colspan="5" class="Forn_DepEmpty">Nenhum depósito cadastrado. Use o formulário ao lado.</td></tr>';
      return;
    }
    el.lista_depositos.innerHTML = depositosCache
      .map(
        (d) => `<tr>
        <td>${d.nome}</td>
        <td>${U.formatarCEP ? U.formatarCEP(d.cep) : d.cep}</td>
        <td>${d.cidade}/${d.uf}</td>
        <td>${d.principal ? "Sim" : "—"}</td>
        <td class="Cl_TableActions">
          <button type="button" class="Cl_BtnAcao btnEditDep" data-id="${d.id}">${u.gerarIconeTech("editar")}</button>
          <button type="button" class="Cl_BtnAcao btnDelDep" data-id="${d.id}">${u.gerarIconeTech("excluir")}</button>
        </td>
      </tr>`
      )
      .join("");
    window.lucide?.createIcons?.();
  }

  function renderRegras() {
    el.lista_regras.innerHTML = regrasCache
      .map((r) => {
        let campo = "";
        if (r.codigo === "aceita_devolucao") {
          campo = `<label class="Forn_Switch"><input type="checkbox" data-cod="${r.codigo}" class="reg-bool" ${r.valor_booleano ? "checked" : ""}/><span class="Forn_SwitchTrack"></span></label>`;
        } else if (r.codigo === "frete_retorno") {
          campo = `<select data-cod="${r.codigo}" class="reg-txt" style="max-width:220px;">
            <option value="fornecedor" ${r.valor_texto === "fornecedor" ? "selected" : ""}>Fornecedor</option>
            <option value="vendedor" ${r.valor_texto === "vendedor" ? "selected" : ""}>Vendedor</option>
            <option value="negociado" ${r.valor_texto === "negociado" ? "selected" : ""}>Negociado</option>
          </select>`;
        } else if (r.codigo === "politica_troca") {
          campo = `<textarea data-cod="${r.codigo}" class="reg-area" rows="3" style="width:100%;max-width:420px;">${r.valor_texto || ""}</textarea>`;
        } else if (r.codigo === "valor_pedido_minimo") {
          campo = `<input type="number" step="0.01" min="0" data-cod="${r.codigo}" class="reg-txt" value="${r.valor_texto || "0"}" style="max-width:120px"/>`;
        } else {
          campo = `<input type="number" min="0" data-cod="${r.codigo}" class="reg-int" value="${r.valor_inteiro ?? ""}" style="max-width:80px"/>`;
        }
        return `<div class="Forn_RegraCard">
          <div><h4>${r.titulo}</h4><p>${r.descricao || ""}</p></div>
          <div>${campo}</div>
        </div>`;
      })
      .join("");
  }

  function coletarRegras() {
    return regrasCache.map((r) => {
      const cod = r.codigo;
      const out = { codigo: cod, ativo: true };
      if (cod === "aceita_devolucao") {
        const cb = document.querySelector(`.reg-bool[data-cod="${cod}"]`);
        out.valor_booleano = !!cb?.checked;
      } else if (cod === "frete_retorno") {
        const sel = document.querySelector(`.reg-txt[data-cod="${cod}"]`);
        out.valor_texto = sel?.value || "fornecedor";
      } else if (cod === "politica_troca") {
        const area = document.querySelector(`.reg-area[data-cod="${cod}"]`);
        out.valor_texto = (area?.value || "").trim();
      } else if (cod === "valor_pedido_minimo") {
        const inp = document.querySelector(`.reg-txt[data-cod="${cod}"]`);
        out.valor_texto = String(inp?.value || "0");
      } else {
        const inp = document.querySelector(`.reg-int[data-cod="${cod}"]`);
        out.valor_inteiro = inp?.value === "" ? null : parseInt(inp.value, 10);
      }
      return out;
    });
  }

  async function buscarCnpj() {
    const doc = soDigitos(el.documento.value);
    if (doc.length !== 14) throw new Error("Informe o CNPJ completo.");
    const r = await fetch(`${BASE}/cnpj/${doc}`);
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro na consulta.");
    const d = j.dados;
    el.razao_social.value = d.razao_social || "";
    el.nome_fantasia.value = d.nome_fantasia || "";
    if (!el.nome.value) el.nome.value = d.nome_fantasia || d.razao_social || "";
    el.situacao_cadastral.value = d.situacao_cadastral || "";
    el.cnae_principal.value = d.cnae_principal || "";
    await Swal.fire({ title: "CNPJ consultado", text: "Dados oficiais carregados com sucesso.", icon: "success", confirmButtonColor: "#021f81" });
  }

  async function buscarCepDep() {
    const cep = soDigitos(el.dep_cep.value);
    if (cep.length !== 8) throw new Error("CEP inválido.");
    const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
    const j = await r.json();
    if (j.erro) throw new Error("CEP não encontrado.");
    el.dep_logradouro.value = j.logradouro || "";
    el.dep_bairro.value = j.bairro || "";
    el.dep_cidade.value = j.localidade || "";
    el.dep_uf.value = j.uf || "";
  }

  async function carregarApoio(id) {
    const r = await fetch(`${BASE}/apoio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    const d = j.dados;
    idFornecedor = d.id;
    if (el.id) el.id.value = String(d.id);
    const titulo = document.getElementById("forn_titulo_pagina");
    if (titulo) titulo.textContent = "Editar fornecedor";
    el.documento.value = U.formatarCNPJ ? U.formatarCNPJ(d.documento) : d.documento;
    el.razao_social.value = d.razao_social || "";
    el.nome_fantasia.value = d.nome_fantasia || "";
    el.nome.value = d.nome || "";
    el.situacao_cadastral.value = d.situacao_cadastral || "";
    el.cnae_principal.value = d.cnae_principal || "";
    el.inscricao_estadual.value = d.inscricao_estadual || "";
    el.telefone_comercial.value = d.telefone_comercial || "";
    el.email_comercial.value = d.email_comercial || "";
    el.ativo.checked = !!d.ativo;
    depositosCache = d.depositos || [];
    regrasCache = d.regras || [];
    renderDepositos();
    renderRegras();
    habilitarAbasExtras();
  }

  async function salvarFornecedor() {
    const body = {
      id: idFornecedor,
      documento: soDigitos(el.documento.value),
      razao_social: (el.razao_social.value || "").trim(),
      nome_fantasia: (el.nome_fantasia.value || "").trim(),
      nome: (el.nome.value || "").trim(),
      inscricao_estadual: (el.inscricao_estadual.value || "").trim(),
      situacao_cadastral: (el.situacao_cadastral.value || "").trim(),
      cnae_principal: (el.cnae_principal.value || "").trim(),
      telefone_comercial: (el.telefone_comercial.value || "").trim(),
      email_comercial: (el.email_comercial.value || "").trim(),
      ativo: el.ativo.checked,
      regras: idFornecedor ? coletarRegras() : [],
    };
    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    if (!idFornecedor && j.id) {
      idFornecedor = j.id;
      if (el.id) el.id.value = String(j.id);
      habilitarAbasExtras();
      await carregarApoio(j.id);
    }
    await Swal.fire("Salvo", j.message, "success");
  }

  async function salvarDeposito() {
    if (!idFornecedor) throw new Error("Salve o fornecedor antes do depósito.");
    const body = {
      id: el.dep_id?.value || null,
      id_tenant: idFornecedor,
      cep: soDigitos(el.dep_cep.value),
      nome: (el.dep_nome.value || "Depósito").trim(),
      logradouro: (el.dep_logradouro.value || "").trim(),
      numero: (el.dep_numero.value || "S/N").trim(),
      complemento: (el.dep_complemento.value || "").trim(),
      bairro: (el.dep_bairro.value || "").trim(),
      cidade: (el.dep_cidade.value || "").trim(),
      uf: (el.dep_uf.value || "").trim(),
      remetente_nome: (el.dep_remetente_nome.value || "").trim(),
      remetente_documento: soDigitos(el.dep_remetente_documento.value),
      principal: el.dep_principal?.checked,
      ativo: true,
    };
    const r = await fetch(`${BASE}/deposito/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    limparFormDeposito();
    await carregarApoio(idFornecedor);
    await Swal.fire("Depósito", j.message, "success");
  }

  async function excluirDeposito(depId) {
    const c = await Swal.fire({ title: "Excluir depósito?", icon: "warning", showCancelButton: true });
    if (!c.isConfirmed) return;
    const r = await fetch(`${BASE}/deposito/excluir`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: depId, id_tenant: idFornecedor }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await carregarApoio(idFornecedor);
  }

  el.btnBuscarCnpj?.addEventListener("click", () => buscarCnpj().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnBuscarCepDep?.addEventListener("click", () => buscarCepDep().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnSalvar?.addEventListener("click", () => salvarFornecedor().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnSalvarDeposito?.addEventListener("click", () => salvarDeposito().catch((e) => Swal.fire("Erro", e.message, "error")));

  el.lista_depositos?.addEventListener("click", (ev) => {
    const edit = ev.target.closest(".btnEditDep");
    const del = ev.target.closest(".btnDelDep");
    if (edit) {
      const d = depositosCache.find((x) => x.id === Number(edit.dataset.id));
      if (d) preencherDep(d);
      ativarTab("depositos");
      return;
    }
    if (del) excluirDeposito(Number(del.dataset.id)).catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  el.nome_fantasia?.addEventListener("blur", () => {
    if (!el.nome.value && el.nome_fantasia.value) el.nome.value = el.nome_fantasia.value;
  });

  async function aplicarId(id) {
    idFornecedor = id ? Number(id) : null;
    habilitarAbasExtras();
    if (idFornecedor) await carregarApoio(idFornecedor);
    else {
      if (el.dep_remetente_documento) el.dep_remetente_documento.value = "";
      renderRegras();
    }
  }

  if (window.GlobalUtils?.receberDadosApoio) {
    window.GlobalUtils.receberDadosApoio((id) => aplicarId(id));
  }

  habilitarAbasExtras();
  atualizarFooterHint("pj");
})();
