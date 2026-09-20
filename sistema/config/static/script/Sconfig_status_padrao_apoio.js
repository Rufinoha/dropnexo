(function () {
  "use strict";

  const BASE = "/configuracoes/integracao-status-padrao";
  let nivelModal = 1;
  let idRegistro = 0;

  const el = {
    id: document.getElementById("id"),
    aplicacao: document.getElementById("aplicacao"),
    contexto: document.getElementById("contexto"),
    direcao: document.getElementById("direcao"),
    status_dn: document.getElementById("status_dn"),
    status_dn_label: document.getElementById("status_dn_label"),
    evento: document.getElementById("evento"),
    status_externo: document.getElementById("status_externo"),
    aliases: document.getElementById("aliases"),
    ordem: document.getElementById("ordem"),
    ativo: document.getElementById("ativo"),
    descricao: document.getElementById("descricao"),
    btnSalvar: document.getElementById("btnSalvar"),
    btnExcluir: document.getElementById("btnExcluir"),
    btnCancelar: document.getElementById("btnCancelar"),
    modo: document.getElementById("isp_modo"),
    titulo: document.getElementById("isp_titulo"),
  };

  function setModo(editando) {
    if (el.modo) el.modo.textContent = editando ? "Edição" : "Novo mapeamento";
    if (el.titulo) {
      el.titulo.textContent = editando ? "Editar status padrão" : "Novo status padrão";
    }
    if (el.btnExcluir) el.btnExcluir.style.display = editando ? "" : "none";
  }

  function prepararInclusao() {
    idRegistro = 0;
    if (el.id) el.id.value = "";
    if (el.aplicacao) el.aplicacao.value = "bling";
    if (el.contexto) el.contexto.value = "vendedor";
    if (el.direcao) el.direcao.value = "ambos";
    if (el.status_dn) el.status_dn.value = "";
    if (el.status_dn_label) el.status_dn_label.value = "";
    if (el.evento) el.evento.value = "";
    if (el.status_externo) el.status_externo.value = "";
    if (el.aliases) el.aliases.value = "";
    if (el.ordem) el.ordem.value = "10";
    if (el.ativo) el.ativo.checked = true;
    if (el.descricao) el.descricao.value = "";
    setModo(false);
  }

  function preencher(d) {
    idRegistro = Number(d.id) || 0;
    if (el.id) el.id.value = String(idRegistro);
    if (el.aplicacao) el.aplicacao.value = d.aplicacao || "bling";
    if (el.contexto) el.contexto.value = d.contexto || "vendedor";
    if (el.direcao) el.direcao.value = d.direcao || "ambos";
    if (el.status_dn) el.status_dn.value = d.status_dn || "";
    if (el.status_dn_label) el.status_dn_label.value = d.status_dn_label || "";
    if (el.evento) el.evento.value = d.evento || "";
    if (el.status_externo) el.status_externo.value = d.status_externo || "";
    if (el.aliases) el.aliases.value = (d.aliases || []).join(", ");
    if (el.ordem) el.ordem.value = String(d.ordem ?? 10);
    if (el.ativo) el.ativo.checked = d.ativo !== false;
    if (el.descricao) el.descricao.value = d.descricao || "";
    setModo(true);
  }

  async function carregarDadosEdicao() {
    const r = await fetch(`${BASE}/apoio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idRegistro }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar.");
    preencher(j.dados);
  }

  document.querySelector("#btnSalvar")?.addEventListener("click", async () => {
    const status_dn = (el.status_dn?.value || "").trim();
    const status_dn_label = (el.status_dn_label?.value || "").trim();
    const evento = (el.evento?.value || "").trim();
    const status_externo = (el.status_externo?.value || "").trim();
    if (!status_dn || !status_dn_label || !evento || !status_externo) {
      Swal.fire("Atenção", "Preencha DropNexo, código DN, evento e status externo.", "warning");
      return;
    }
    try {
      const body = {
        id: idRegistro > 0 ? idRegistro : null,
        aplicacao: el.aplicacao?.value,
        contexto: el.contexto?.value,
        direcao: el.direcao?.value,
        status_dn,
        status_dn_label,
        evento,
        status_externo,
        aliases: el.aliases?.value || "",
        ordem: el.ordem?.value,
        ativo: !!el.ativo?.checked,
        descricao: el.descricao?.value,
      };
      const r = await fetch(`${BASE}/salvar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
      window.parent.postMessage({ grupo: "atualizarTabela", nivel: nivelModal }, "*");
      await Swal.fire({ icon: "success", title: "Salvo", timer: 1200, showConfirmButton: false });
      window.parent.GlobalUtils?.fecharJanelaApoio(nivelModal);
    } catch (err) {
      Swal.fire("Erro", err.message, "error");
    }
  });

  document.querySelector("#btnExcluir")?.addEventListener("click", async () => {
    if (!(idRegistro > 0)) {
      Swal.fire("Atenção", "Nada para excluir.", "info");
      return;
    }
    const c = await Swal.fire({
      title: "Excluir mapeamento?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, excluir",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;
    try {
      const r = await fetch(`${BASE}/excluir`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: idRegistro }),
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Erro ao excluir.");
      window.parent.postMessage({ grupo: "atualizarTabela", nivel: nivelModal }, "*");
      await Swal.fire("Sucesso", "Removido.", "success");
      window.parent.GlobalUtils?.fecharJanelaApoio(nivelModal);
    } catch (err) {
      Swal.fire("Erro", err.message, "error");
    }
  });

  document.querySelector("#btnCancelar")?.addEventListener("click", () => {
    window.parent.GlobalUtils?.fecharJanelaApoio(nivelModal);
  });

  // Fonte da verdade (doc 04): GlobalUtils.receberDadosApoio
  if (window.GlobalUtils && typeof GlobalUtils.receberDadosApoio === "function") {
    GlobalUtils.receberDadosApoio((id, nivel) => {
      nivelModal = Number(nivel || 1) || 1;
      idRegistro = Number(id || 0) || 0;
      if (idRegistro > 0) {
        carregarDadosEdicao().catch((e) => Swal.fire("Erro", e.message, "error"));
      } else {
        prepararInclusao();
      }
    });
  } else {
    const params = new URLSearchParams(window.location.search);
    idRegistro = Number(params.get("id") || 0) || 0;
    nivelModal = Number(params.get("nivel") || 1) || 1;
    if (idRegistro > 0) carregarDadosEdicao().catch((e) => Swal.fire("Erro", e.message, "error"));
    else prepararInclusao();
  }
})();
