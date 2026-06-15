/**
 * Sempresa.js — aba Minha empresa
 */
(function () {
  "use strict";

  const cfg = window.OSB_MEU_PERFIL || {};
  let dadosOriginais = null;

  function el(id) {
    return document.getElementById(id);
  }

  function soDigitos(v) {
    return String(v || "").replace(/\D/g, "");
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

  function preencher(d) {
    dadosOriginais = d;
    el("emp-nome").value = d.nome || d.nome_fantasia || "";
    el("emp-tipo-pessoa").value = d.tipo_pessoa || "J";
    el("emp-documento").value = d.documento || "";
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
    const apelido = el("emp-nome").value.trim();
    const body = {
      nome: apelido,
      nome_completo: el("emp-razao").value.trim(),
      razao_social: el("emp-razao").value.trim(),
      nome_fantasia: apelido,
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
