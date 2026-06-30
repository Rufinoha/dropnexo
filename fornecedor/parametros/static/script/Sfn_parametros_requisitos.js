/**
 * Parâmetros — Requisitos para vendedores
 */
(function () {
  "use strict";

  const API_DADOS = "/fornecedor/parametros/requisitos-vendedor/dados";
  const API_SALVAR = "/fornecedor/parametros/requisitos-vendedor/salvar";

  const el = {
    exige_cnpj: document.getElementById("req_exige_cnpj"),
    exige_nf: document.getElementById("req_exige_nf"),
    cobra_vinculo: document.getElementById("req_cobra_vinculo"),
    valor_vinculo: document.getElementById("req_valor_vinculo"),
    cobra_mensal: document.getElementById("req_cobra_mensal"),
    valor_mensal: document.getElementById("req_valor_mensal"),
    cobra_pedido: document.getElementById("req_cobra_pedido"),
    valor_pedido: document.getElementById("req_valor_pedido"),
    texto: document.getElementById("req_texto_adicional"),
    mostrar_contato: document.getElementById("req_mostrar_contato"),
    form: document.getElementById("formRequisitosVendedor"),
  };

  if (!el.form) return;

  const paresTaxa = [
    [el.cobra_vinculo, el.valor_vinculo],
    [el.cobra_mensal, el.valor_mensal],
    [el.cobra_pedido, el.valor_pedido],
  ];

  function syncValor(sw, inp) {
    if (!inp) return;
    const on = !!sw?.checked;
    inp.disabled = !on;
    inp.closest(".mp-req-taxa")?.classList.toggle("is-ativo", on);
  }

  function syncTodosValores() {
    paresTaxa.forEach(([sw, inp]) => syncValor(sw, inp));
  }

  paresTaxa.forEach(([sw, inp]) => {
    sw?.addEventListener("change", () => syncValor(sw, inp));
  });

  function preencher(r) {
    if (!r) return;
    if (el.exige_cnpj) el.exige_cnpj.checked = !!r.exige_cnpj;
    if (el.exige_nf) el.exige_nf.checked = !!r.exige_nf;
    if (el.cobra_vinculo) el.cobra_vinculo.checked = !!r.cobra_taxa_vinculo;
    if (el.valor_vinculo) el.valor_vinculo.value = r.valor_taxa_vinculo ?? "";
    if (el.cobra_mensal) el.cobra_mensal.checked = !!r.cobra_taxa_mensal;
    if (el.valor_mensal) el.valor_mensal.value = r.valor_taxa_mensal ?? "";
    if (el.cobra_pedido) el.cobra_pedido.checked = !!r.cobra_taxa_pedido;
    if (el.valor_pedido) el.valor_pedido.value = r.valor_taxa_pedido ?? "";
    if (el.texto) el.texto.value = r.texto_adicional || "";
    if (el.mostrar_contato) el.mostrar_contato.checked = r.mostrar_contato_vendedor !== false;
    syncTodosValores();
  }

  async function carregar() {
    const r = await fetch(API_DADOS, { credentials: "same-origin" });
    const j = await r.json();
    if (j.success) preencher(j.requisitos);
  }

  el.form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = {
      exige_cnpj: !!el.exige_cnpj?.checked,
      exige_nf: !!el.exige_nf?.checked,
      cobra_taxa_vinculo: !!el.cobra_vinculo?.checked,
      valor_taxa_vinculo: parseFloat(el.valor_vinculo?.value || "0") || 0,
      cobra_taxa_mensal: !!el.cobra_mensal?.checked,
      valor_taxa_mensal: parseFloat(el.valor_mensal?.value || "0") || 0,
      cobra_taxa_pedido: !!el.cobra_pedido?.checked,
      valor_taxa_pedido: parseFloat(el.valor_pedido?.value || "0") || 0,
      mostrar_contato_vendedor: !!el.mostrar_contato?.checked,
      texto_adicional: (el.texto?.value || "").trim(),
    };
    const r = await fetch(API_SALVAR, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (window.Util?.alertar) Util.alertar(j.message || (j.success ? "Salvo" : "Erro"), j.success ? "success" : "error");
    else if (window.Swal) Swal.fire(j.success ? "Salvo" : "Erro", j.message, j.success ? "success" : "error");
    else alert(j.message || (j.success ? "Salvo" : "Erro"));
    if (j.success && j.requisitos) preencher(j.requisitos);
  });

  syncTodosValores();
  carregar();
})();
