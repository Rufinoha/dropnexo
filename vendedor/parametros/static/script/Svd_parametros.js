(function () {
  "use strict";

  function el(id) {
    return document.getElementById(id);
  }

  function preencher(j) {
    const set = (id, val) => {
      const n = el(id);
      if (n && val != null) n.value = val;
    };
    set("nf_ambiente", j.ambiente || "homologacao");
    set("nf_serie", j.serie ?? 1);
    set("nf_numero", j.proximo_numero ?? 1);
    set("nf_natureza", j.natureza_operacao || "Venda de mercadoria");
    set("nf_cfop_int", j.cfop_interno || "5102");
    set("nf_cfop_ie", j.cfop_interestadual || "6102");
    set("nf_cfop_cf", j.cfop_consumidor_interestadual || "6108");
    set("nf_icms", j.icms_situacao || "102");
    set("nf_aliq", j.icms_aliquota ?? "");
    set("nf_pis", j.pis_situacao || "49");
    set("nf_cofins", j.cofins_situacao || "49");
    const partes = [];
    partes.push(j.tem_certificado ? `Certificado: ${j.certificado_nome || "enviado"}.` : "Certificado ainda não enviado.");
    partes.push(j.token_configurado ? "Token da Focus NFe configurado." : "Falta FOCUS_NFE_TOKEN no servidor.");
    partes.push(j.focus_empresa_id ? "Empresa sincronizada com a Focus." : "A empresa sincroniza ao salvar o certificado.");
    if (j.tabela_ok === false) partes.push("Rode o SQL da nota fiscal neste banco.");
    const st = el("nf_par_status");
    if (st) st.textContent = partes.join(" ");
  }

  async function carregar() {
    const r = await fetch("/vendedor/parametros/fiscal", { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar.");
    preencher(j);
  }

  el("nf_par_form")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    if (window.Swal) Swal.fire({ title: "Salvando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
      const r = await fetch("/vendedor/parametros/fiscal", {
        method: "POST",
        credentials: "same-origin",
        body: fd,
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao salvar.");
      preencher(j);
      const texto = j.aviso ? `Salvo. A sincronização avisou: ${j.aviso}` : "Parâmetros fiscais salvos.";
      if (window.Swal) Swal.fire(j.aviso ? "Atenção" : "Salvo", texto, j.aviso ? "warning" : "success");
    } catch (e) {
      if (window.Swal) Swal.fire("Erro", e.message || "Falha ao salvar.", "error");
    }
  });

  carregar().catch((e) => {
    if (window.Swal) Swal.fire("Erro", e.message || "Falha ao carregar.", "error");
  });
})();
