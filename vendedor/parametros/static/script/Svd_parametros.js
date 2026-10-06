(function () {
  "use strict";

  function el(id) {
    return document.getElementById(id);
  }

  function nfBase() {
    const n = document.querySelector("[data-nf-base]");
    return ((n && n.getAttribute("data-nf-base")) || "/vendedor").replace(/\/$/, "");
  }

  function preencher(j) {
    const set = (id, val) => {
      const n = el(id);
      if (n && val != null) n.value = val;
    };
    set("nf_ambiente", j.ambiente || "homologacao");
    set("nf_ambiente_val", el("nf_ambiente")?.value || j.ambiente || "homologacao");
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
    if (!j.token_configurado) partes.push("Falta o token do hub de NF-e no servidor. Sem ele a nota não é enviada.");
    else if (j.tem_certificado && !j.focus_empresa_id) partes.push("A empresa sincroniza ao salvar o certificado.");
    if (j.tabela_ok === false) partes.push("Rode o SQL da nota fiscal neste banco.");
    pintarCert(j.certificado);
    const nomeArq = el("nf_cert_nome");
    const escolhido = el("nf_cert")?.files?.[0]?.name;
    if (nomeArq) {
      nomeArq.textContent = escolhido
        || (j.tem_certificado ? (j.certificado_nome || "Certificado enviado") : "Nenhum arquivo escolhido");
    }
    const st = el("nf_par_status");
    if (st) {
      if (!partes.length) {
        st.hidden = true;
        st.textContent = "";
      } else {
        const pendente = !j.token_configurado || j.tabela_ok === false;
        st.hidden = false;
        st.className = pendente ? "Fin_Aviso" : "Nf_Ok";
        st.textContent = partes.join(" ");
      }
    }
  }

  function pintarCert(c) {
    const box = el("nf_cert_box");
    const titulo = el("nf_cert_titulo");
    const corpo = el("nf_cert_corpo");
    if (!box || !titulo || !corpo) return;
    box.hidden = false;
    box.className = "Nf_CertOk";
    corpo.replaceChildren();
    const linha = (texto) => {
      const p = document.createElement("p");
      p.textContent = texto;
      corpo.appendChild(p);
    };
    const info = c || {};
    if (!info.instalado && info.situacao !== "arquivo") {
      box.classList.add("is-off");
      titulo.textContent = "Nenhum certificado instalado";
      linha("Envie o arquivo .pfx e a senha, depois salve.");
      return;
    }
    if (info.situacao === "arquivo") {
      box.classList.add("is-vence");
      titulo.textContent = "Arquivo não encontrado";
      linha("O certificado foi registrado, mas o arquivo não está mais no servidor. Envie de novo.");
      return;
    }
    if (info.situacao === "ilegivel" || info.situacao === "sem_senha") {
      box.classList.add("is-vence");
      titulo.textContent = "Certificado salvo";
      linha("Não foi possível ler a validade. Confira a senha e salve de novo.");
      return;
    }
    if (info.situacao === "vencido") box.classList.add("is-vencido");
    else if (info.situacao === "vence") box.classList.add("is-vence");
    titulo.textContent = info.situacao === "vencido" ? "Certificado vencido" : "Certificado instalado";
    if (info.titular) linha(`Titular: ${info.titular}`);
    if (info.valido_de && info.valido_ate) linha(`Válido de ${info.valido_de} até ${info.valido_ate}.`);
    if (info.dias != null) {
      if (info.dias < 0) linha(`Vencido há ${Math.abs(info.dias)} dias.`);
      else if (info.dias === 0) linha("Vence hoje.");
      else linha(`Faltam ${info.dias} dias.`);
    }
    if (info.emissor) linha(`Emissor: ${info.emissor}`);
  }

  async function carregar() {
    const r = await fetch(`${nfBase()}/parametros/fiscal`, { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar.");
    preencher(j);
  }

  el("nf_cert")?.addEventListener("change", () => {
    const nome = el("nf_cert")?.files?.[0]?.name;
    const alvo = el("nf_cert_nome");
    if (alvo) alvo.textContent = nome || "Nenhum arquivo escolhido";
  });

  el("nf_aba_parametros")?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const fd = new FormData(ev.target);
    if (window.Swal) Swal.fire({ title: "Salvando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
      const r = await fetch(`${nfBase()}/parametros/fiscal`, {
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

  if (!el("nf_tbody")) {
    el("nf_par_shell")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-nf-tab]");
      const root = el("nf_par_shell");
      if (!btn || !root || !root.contains(btn)) return;
      const nome = btn.dataset.nfTab;
      root.querySelectorAll("[data-nf-tab]").forEach((b) => b.classList.toggle("is-active", b === btn));
      root.querySelectorAll("[data-nf-pane]").forEach((p) => {
        p.hidden = p.dataset.nfPane !== nome;
      });
    });
  }

  carregar().catch((e) => {
    if (window.Swal) Swal.fire("Erro", e.message || "Falha ao carregar.", "error");
  });
})();
