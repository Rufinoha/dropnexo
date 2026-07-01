/**
 * Sempresa.js — aba Minha empresa
 */
(function () {
  "use strict";

  const cfg = window.OSB_MEU_PERFIL || {};
  let dadosOriginais = null;
  let exigeNichos = false;
  let conversaoPjAtiva = false;

  function el(id) {
    return document.getElementById(id);
  }

  function soDigitos(v) {
    return String(v || "").replace(/\D/g, "");
  }

  function mascaraCpf(v) {
    const d = soDigitos(v).slice(0, 11);
    return d
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  }

  function mascaraCnpj(v) {
    const d = soDigitos(v).slice(0, 14);
    return d
      .replace(/^(\d{2})(\d)/, "$1.$2")
      .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1/$2")
      .replace(/(\d{4})(\d)/, "$1-$2");
  }

  function formatarDocumento(doc, tipo) {
    const d = soDigitos(doc);
    if (!d) return "";
    return (tipo || "").toUpperCase() === "J" ? mascaraCnpj(d) : mascaraCpf(d);
  }

  function tipoOriginal() {
    return (dadosOriginais?.tipo_pessoa || "F").toUpperCase();
  }

  function aplicarUiTipoPessoa() {
    const sel = el("emp-tipo-pessoa");
    const doc = el("emp-documento");
    const lblDoc = el("emp-lbl-documento");
    const btnCnpj = el("emp-btn-cnpj");
    const hint = el("emp-tipo-hint");
    if (!sel || !doc) return;

    const orig = tipoOriginal();
    const tipo = (sel.value || "F").toUpperCase();

    if (orig === "J") {
      sel.value = "J";
      sel.disabled = true;
      sel.classList.add("mp-readonly");
      if (hint) hint.hidden = false;
      if (lblDoc) lblDoc.textContent = "CNPJ";
      doc.readOnly = true;
      doc.classList.add("mp-readonly");
      if (btnCnpj) btnCnpj.hidden = true;
      doc.value = formatarDocumento(dadosOriginais?.documento || doc.value, "J");
      return;
    }

    sel.disabled = false;
    sel.classList.remove("mp-readonly");
    if (hint) hint.hidden = true;

    if (tipo === "J" && conversaoPjAtiva) {
      if (lblDoc) lblDoc.textContent = "CNPJ";
      doc.readOnly = false;
      doc.classList.remove("mp-readonly");
      if (btnCnpj) btnCnpj.hidden = false;
      doc.value = mascaraCnpj(doc.value);
    } else {
      sel.value = "F";
      conversaoPjAtiva = false;
      if (lblDoc) lblDoc.textContent = "CPF";
      doc.readOnly = true;
      doc.classList.add("mp-readonly");
      if (btnCnpj) btnCnpj.hidden = true;
      doc.value = formatarDocumento(dadosOriginais?.documento || "", "F");
    }
  }

  async function onTipoPessoaChange() {
    const sel = el("emp-tipo-pessoa");
    if (!sel || tipoOriginal() !== "F") return;

    if (sel.value === "J") {
      if (typeof Swal !== "undefined") {
        const r = await Swal.fire({
          icon: "warning",
          title: "Alterar para Pessoa Jurídica?",
          html:
            "<p>Esta alteração <strong>não poderá ser desfeita</strong>.</p>" +
            "<p>Informe o CNPJ da empresa e revise a razão social antes de salvar.</p>",
          showCancelButton: true,
          confirmButtonText: "Sim, alterar",
          cancelButtonText: "Cancelar",
          confirmButtonColor: "#021f81",
        });
        if (!r.isConfirmed) {
          sel.value = "F";
          conversaoPjAtiva = false;
          aplicarUiTipoPessoa();
          return;
        }
      }
      conversaoPjAtiva = true;
      el("emp-documento").value = "";
      aplicarUiTipoPessoa();
      el("emp-documento")?.focus();
      return;
    }

    conversaoPjAtiva = false;
    aplicarUiTipoPessoa();
  }

  function linhaSt(uf, ie) {
    const row = document.createElement("div");
    row.className = "mp-st-row";
    row.innerHTML =
      '<div class="filter-group"><label>UF</label><input type="text" class="emp-st-uf mp-input-uf" maxlength="2" value="' +
      (uf || "") +
      '" /></div>' +
      '<div class="filter-group"><label>Inscrição estadual</label><input type="text" class="emp-st-ie" maxlength="20" value="' +
      (ie || "") +
      '" /></div>' +
      '<button type="button" class="mp-st-del" title="Remover" aria-label="Remover">✕</button>';
    row.querySelector(".mp-st-del").addEventListener("click", function () {
      row.remove();
    });
    return row;
  }

  function renderSt(lista) {
    const box = el("emp-st-lista");
    if (!box) return;
    box.innerHTML = "";
    (lista || []).forEach(function (i) {
      box.appendChild(linhaSt(i.uf, i.inscricao_estadual));
    });
  }

  function coletarSt() {
    const out = [];
    document.querySelectorAll("#emp-st-lista .mp-st-row").forEach(function (row) {
      const uf = (row.querySelector(".emp-st-uf")?.value || "").trim().toUpperCase();
      const ie = (row.querySelector(".emp-st-ie")?.value || "").trim();
      if (uf && ie) out.push({ uf: uf, inscricao_estadual: ie });
    });
    return out;
  }

  function renderSegmentosNichos(d) {
    const sec = el("emp-sec-nichos");
    const box = el("emp-segmentos-nichos");
    if (!sec || !box || !window.SegNichos) return;
    const tipo = (d.tipo_negocio || "").toLowerCase();
    exigeNichos = tipo === "fornecedor" || tipo === "hibrido";
    sec.hidden = !exigeNichos;
    if (!exigeNichos) return;
    const segs = d.segmentos_nichos || [];
    const ids = d.ids_segmentos_nichos || [];
    SegNichos.render(box, segs, ids, d.ids_segmentos_com_categorias || []);
    SegNichos.bind(box);
  }

  function preencher(d) {
    dadosOriginais = d;
    conversaoPjAtiva = false;
    el("emp-nome").value = d.nome || d.nome_fantasia || "";
    el("emp-tipo-pessoa").value = d.tipo_pessoa || "J";
    el("emp-documento").value = formatarDocumento(d.documento || "", d.tipo_pessoa || "F");
    el("emp-razao").value = d.nome_completo || d.razao_social || "";
    el("emp-ie").value = d.inscricao_estadual || "";
    el("emp-ie-isento").checked = !!d.ie_isento;
    el("emp-im").value = d.inscricao_municipal || "";
    el("emp-cnae").value = d.cnae_principal || "";
    el("emp-atividade").value = d.atividade_principal || "";
    el("emp-regime").value = d.codigo_regime_tributario || "";
    el("emp-porte").value = d.tamanho_empresa || "";
    el("emp-seg-comercio").checked = !!d.segmento_comercio;
    el("emp-seg-ecommerce").checked = !!d.segmento_ecommerce;
    el("emp-seg-industria").checked = !!d.segmento_industria;
    el("emp-seg-servicos").checked = !!d.segmento_servicos;
    el("emp-faturamento").value = d.faturamento_ultimo_ano || "";
    el("emp-funcionarios").value = d.quantidade_funcionarios || "";
    el("emp-cep").value = d.cep || "";
    el("emp-uf").value = d.uf || "";
    el("emp-cidade").value = d.cidade || "";
    el("emp-bairro").value = d.bairro || "";
    el("emp-logradouro").value = d.logradouro || "";
    el("emp-numero").value = d.numero || "";
    el("emp-complemento").value = d.complemento || "";
    el("emp-contato").value = d.pessoas_contato || "";
    el("emp-telefone").value = d.telefone_comercial || "";
    el("emp-celular").value = d.celular_comercial || "";
    el("emp-email").value = d.email_comercial || "";
    el("emp-site").value = d.site || "";
    renderSt(d.inscricoes_st || []);
    const img = el("emp-logo");
    const ph = el("emp-logo-placeholder");
    if (d.logo_url && img) {
      const bust = d.logo_url.indexOf("?") >= 0 ? "&" : "?";
      img.src = d.logo_url + bust + "t=" + Date.now();
      img.hidden = false;
      if (ph) ph.hidden = true;
    } else if (img && ph) {
      img.hidden = true;
      ph.hidden = false;
    }
    renderSegmentosNichos(d);
    aplicarUiTipoPessoa();
  }

  async function buscarCnpj() {
    const doc = soDigitos(el("emp-documento")?.value);
    if (doc.length !== 14) {
      if (typeof Swal !== "undefined") {
        Swal.fire("Atenção", "Informe o CNPJ completo com 14 dígitos.", "warning");
      }
      return;
    }
    const btn = el("emp-btn-cnpj");
    if (btn) btn.disabled = true;
    try {
      const r = await fetch(`${cfg.apiCnpj}?cnpj=${encodeURIComponent(doc)}`, {
        headers: { Accept: "application/json" },
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Erro na consulta do CNPJ.");
      const dados = j.dados || {};
      if (dados.razao_social) el("emp-razao").value = dados.razao_social;
      if (dados.nome_fantasia) el("emp-nome").value = dados.nome_fantasia;
      if (dados.cep) el("emp-cep").value = dados.cep;
      if (dados.logradouro) el("emp-logradouro").value = dados.logradouro;
      if (dados.numero) el("emp-numero").value = dados.numero;
      if (dados.complemento) el("emp-complemento").value = dados.complemento;
      if (dados.bairro) el("emp-bairro").value = dados.bairro;
      if (dados.cidade) el("emp-cidade").value = dados.cidade;
      if (dados.uf) el("emp-uf").value = dados.uf;
    } catch (err) {
      if (typeof Swal !== "undefined") Swal.fire("Consulta CNPJ", err.message || "Falha na consulta.", "warning");
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function carregar() {
    if (!cfg.apiEmpresa) return;
    try {
      const r = await fetch(cfg.apiEmpresa, { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (j.success && j.dados) preencher(j.dados);
    } catch (e) {
      console.error(e);
    }
  }

  async function buscarCep() {
    const cep = soDigitos(el("emp-cep")?.value);
    if (cep.length !== 8) return;
    try {
      const r = await fetch(cfg.apiCepBase + cep, { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.success) return;
      const e = j.endereco || {};
      if (e.logradouro) el("emp-logradouro").value = e.logradouro;
      if (e.bairro) el("emp-bairro").value = e.bairro;
      if (e.cidade) el("emp-cidade").value = e.cidade;
      if (e.uf) el("emp-uf").value = e.uf;
    } catch (err) {
      console.error(err);
    }
  }

  async function salvar(ev) {
    ev.preventDefault();
    const boxSeg = el("emp-segmentos-nichos");
    if (exigeNichos && boxSeg && window.SegNichos) {
      const err = el("emp-seg-erro");
      if (!SegNichos.validarMinimo(boxSeg, "Selecione ao menos um segmento (nicho) em que sua empresa atua.")) {
        if (err) err.hidden = false;
        return;
      }
    }
    const apelido = el("emp-nome").value.trim();
    const tipoSel = (el("emp-tipo-pessoa")?.value || tipoOriginal()).toUpperCase();
    const body = {
      nome: apelido,
      nome_completo: el("emp-razao").value.trim(),
      razao_social: el("emp-razao").value.trim(),
      nome_fantasia: apelido,
      tipo_pessoa: tipoSel,
      inscricao_estadual: el("emp-ie").value.trim(),
      inscricao_municipal: el("emp-im").value.trim(),
      ie_isento: el("emp-ie-isento").checked,
      cnae_principal: el("emp-cnae").value.trim(),
      atividade_principal: el("emp-atividade").value,
      codigo_regime_tributario: el("emp-regime").value,
      tamanho_empresa: el("emp-porte").value,
      segmento_comercio: el("emp-seg-comercio").checked,
      segmento_ecommerce: el("emp-seg-ecommerce").checked,
      segmento_industria: el("emp-seg-industria").checked,
      segmento_servicos: el("emp-seg-servicos").checked,
      faturamento_ultimo_ano: el("emp-faturamento").value,
      quantidade_funcionarios: el("emp-funcionarios").value,
      cep: soDigitos(el("emp-cep").value),
      uf: el("emp-uf").value.trim().toUpperCase(),
      cidade: el("emp-cidade").value.trim(),
      bairro: el("emp-bairro").value.trim(),
      logradouro: el("emp-logradouro").value.trim(),
      numero: el("emp-numero").value.trim(),
      complemento: el("emp-complemento").value.trim(),
      pessoas_contato: el("emp-contato").value.trim(),
      telefone_comercial: soDigitos(el("emp-telefone").value),
      celular_comercial: soDigitos(el("emp-celular").value),
      email_comercial: el("emp-email").value.trim(),
      site: el("emp-site").value.trim(),
      inscricoes_st: coletarSt(),
    };
    if (tipoOriginal() === "F" && tipoSel === "J") {
      const doc = soDigitos(el("emp-documento")?.value);
      if (doc.length !== 14) {
        if (typeof Swal !== "undefined") {
          Swal.fire("Atenção", "Informe um CNPJ válido com 14 dígitos.", "warning");
        }
        return;
      }
      body.documento = doc;
    }
    if (exigeNichos && boxSeg && window.SegNichos) {
      body.ids_segmentos_nichos = SegNichos.idsSelecionados(boxSeg);
    }
    try {
      const r = await fetch(cfg.apiEmpresaSalvar, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (typeof Swal !== "undefined") {
        Swal.fire(j.success ? "Salvo" : "Erro", j.message || "", j.success ? "success" : "error");
      }
      if (j.success) carregar();
    } catch (err) {
      if (typeof Swal !== "undefined") Swal.fire("Erro", err.message, "error");
    }
  }

  async function uploadLogo(file) {
    if (!file) return;
    const fd = new FormData();
    fd.append("arquivo", file);
    try {
      const r = await fetch(cfg.apiEmpresaLogo, { method: "POST", body: fd });
      const j = await r.json();
      if (j.success && j.logo_url) {
        const img = el("emp-logo");
        const ph = el("emp-logo-placeholder");
        img.src = j.logo_url;
        img.hidden = false;
        if (ph) ph.hidden = true;
      }
      if (typeof Swal !== "undefined") Swal.fire(j.success ? "OK" : "Erro", j.message || "", j.success ? "success" : "error");
    } catch (e) {
      console.error(e);
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!el("form-empresa")) return;
    el("form-empresa")?.addEventListener("submit", salvar);
    el("emp-tipo-pessoa")?.addEventListener("change", onTipoPessoaChange);
    el("emp-documento")?.addEventListener("input", function () {
      if (conversaoPjAtiva) this.value = mascaraCnpj(this.value);
    });
    el("emp-btn-cnpj")?.addEventListener("click", buscarCnpj);
    el("emp-btn-cep")?.addEventListener("click", buscarCep);
    el("emp-st-add")?.addEventListener("click", function () {
      el("emp-st-lista")?.appendChild(linhaSt("", ""));
    });
    el("emp-btn-cancelar")?.addEventListener("click", function () {
      if (dadosOriginais) preencher(dadosOriginais);
    });
    el("emp-logo-input")?.addEventListener("change", function () {
      const f = this.files && this.files[0];
      if (f) uploadLogo(f);
      this.value = "";
    });
    window.addEventListener("mp-tab-change", function (ev) {
      if (ev.detail.aba === "empresa") carregar();
    });
    if ((cfg.abaInicial || "perfil") === "empresa") carregar();
  });
})();
