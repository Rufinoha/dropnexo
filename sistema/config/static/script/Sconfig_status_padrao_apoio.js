(function () {
  "use strict";

  const BASE = "/configuracoes/integracao-status-padrao";
  let idRow = null;
  let nivelModal = 1;

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
  };

  function limpar() {
    idRow = null;
    if (el.id) el.id.value = "";
    if (el.aplicacao) el.aplicacao.value = "bling";
    if (el.contexto) el.contexto.value = "vendedor";
    if (el.direcao) el.direcao.value = "ambos";
    if (el.status_dn) el.status_dn.value = "";
    if (el.status_dn_label) el.status_dn_label.value = "";
    if (el.evento) el.evento.value = "";
    if (el.status_externo) el.status_externo.value = "";
    if (el.aliases) el.aliases.value = "";
    if (el.ordem) el.ordem.value = "0";
    if (el.ativo) el.ativo.checked = true;
    if (el.descricao) el.descricao.value = "";
  }

  function preencher(d) {
    idRow = d.id;
    if (el.id) el.id.value = String(d.id);
    if (el.aplicacao) el.aplicacao.value = d.aplicacao || "bling";
    if (el.contexto) el.contexto.value = d.contexto || "vendedor";
    if (el.direcao) el.direcao.value = d.direcao || "ambos";
    if (el.status_dn) el.status_dn.value = d.status_dn || "";
    if (el.status_dn_label) el.status_dn_label.value = d.status_dn_label || "";
    if (el.evento) el.evento.value = d.evento || "";
    if (el.status_externo) el.status_externo.value = d.status_externo || "";
    if (el.aliases) el.aliases.value = (d.aliases || []).join(", ");
    if (el.ordem) el.ordem.value = String(d.ordem ?? 0);
    if (el.ativo) el.ativo.checked = d.ativo !== false;
    if (el.descricao) el.descricao.value = d.descricao || "";
  }

  async function carregarApoio(id) {
    const r = await fetch(`${BASE}/apoio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar.");
    preencher(j.dados);
  }

  async function salvar() {
    const body = {
      id: idRow || null,
      aplicacao: el.aplicacao?.value,
      contexto: el.contexto?.value,
      direcao: el.direcao?.value,
      status_dn: el.status_dn?.value,
      status_dn_label: el.status_dn_label?.value,
      evento: el.evento?.value,
      status_externo: el.status_externo?.value,
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
    const q = await Swal.fire({
      title: "Salvo!",
      text: "Deseja cadastrar outro?",
      icon: "success",
      showCancelButton: true,
      confirmButtonText: "Sim",
      cancelButtonText: "Não",
    });
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    if (q.isConfirmed) {
      limpar();
      return;
    }
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  async function excluir() {
    if (!idRow) {
      await Swal.fire("Atenção", "Nada para excluir.", "info");
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
    const r = await fetch(`${BASE}/excluir`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idRow }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao excluir.");
    await Swal.fire("Sucesso", "Removido.", "success");
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  el.btnSalvar?.addEventListener("click", () =>
    salvar().catch((e) => Swal.fire("Erro", e.message, "error"))
  );
  el.btnExcluir?.addEventListener("click", () =>
    excluir().catch((e) => Swal.fire("Erro", e.message, "error"))
  );

  window.addEventListener("message", (ev) => {
    const d = ev?.data;
    if (!d || d.grupo !== "receberDadosModal") return;
    nivelModal = d.nivel || 1;
    const id = d.id != null && d.id !== "" ? Number(d.id) : null;
    if (!id) {
      limpar();
      return;
    }
    carregarApoio(id).catch((e) => Swal.fire("Erro", e.message, "error"));
  });
})();
