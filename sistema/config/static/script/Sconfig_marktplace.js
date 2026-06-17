(function () {
  const BASE = "/configuracoes/marktplace-produtos";
  const lista = document.getElementById("cfg_mk_lista");
  if (!lista) return;

  const fld = {
    id: document.getElementById("cfg_mk_id"),
    titulo: document.getElementById("cfg_mk_titulo"),
    slug: document.getElementById("cfg_mk_slug"),
    ordem: document.getElementById("cfg_mk_ordem"),
    resumo: document.getElementById("cfg_mk_resumo"),
    valor: document.getElementById("cfg_mk_valor"),
    tipo_pagamento: document.getElementById("cfg_mk_tipo_pagamento"),
    publico: document.getElementById("cfg_mk_publico"),
    categoria: document.getElementById("cfg_mk_categoria"),
    tipo_acao: document.getElementById("cfg_mk_tipo_acao"),
    icone: document.getElementById("cfg_mk_icone"),
    cor: document.getElementById("cfg_mk_cor"),
    meta: document.getElementById("cfg_mk_meta"),
    ativo: document.getElementById("cfg_mk_ativo"),
  };
  const formTitulo = document.getElementById("cfg_mk_formTitulo");
  const btnExcluir = document.getElementById("cfg_mk_btnExcluir");

  let produtos = [];
  let selecionado = null;

  const PUBLICO_LABEL = { ambos: "Ambos", fornecedor: "Fornecedor", vendedor: "Vendedor" };
  const PAG_LABEL = { unico: "Único", mensal: "Mensal" };

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  function centavosParaReais(c) {
    const v = (Number(c) || 0) / 100;
    return v.toFixed(2).replace(".", ",");
  }

  function reaisParaCentavos(txt) {
    const n = parseFloat(String(txt || "0").replace(/\./g, "").replace(",", "."));
    return Number.isFinite(n) ? n : 0;
  }

  function limpar() {
    selecionado = null;
    fld.id.value = "";
    fld.titulo.value = "";
    fld.slug.value = "";
    fld.ordem.value = "0";
    fld.resumo.value = "";
    fld.valor.value = "";
    fld.tipo_pagamento.value = "unico";
    fld.publico.value = "ambos";
    fld.categoria.value = "geral";
    fld.tipo_acao.value = "";
    fld.icone.value = "shopping-bag";
    fld.cor.value = "#5b57f5";
    fld.meta.value = "{}";
    fld.ativo.checked = true;
    window.CatDescricaoEditor?.setValue?.("");
    formTitulo.textContent = "Novo produto";
    btnExcluir.hidden = true;
    lista.querySelectorAll(".CfgMk_Item").forEach((el) => el.classList.remove("is-selected"));
  }

  function preencher(p) {
    selecionado = p.id;
    fld.id.value = String(p.id);
    fld.titulo.value = p.titulo || "";
    fld.slug.value = p.slug || "";
    fld.ordem.value = String(p.ordem ?? 0);
    fld.resumo.value = p.resumo || "";
    fld.valor.value = centavosParaReais(p.valor_centavos);
    fld.tipo_pagamento.value = p.tipo_pagamento || "unico";
    fld.publico.value = p.publico || "ambos";
    fld.categoria.value = p.categoria || "geral";
    fld.tipo_acao.value = p.tipo_acao || "";
    fld.icone.value = p.icone || "shopping-bag";
    fld.cor.value = p.cor_topo || "#5b57f5";
    fld.meta.value = JSON.stringify(p.meta || {}, null, 0);
    fld.ativo.checked = !!p.ativo;
    window.CatDescricaoEditor?.setValue?.(p.descricao || "");
    formTitulo.textContent = "Editar produto";
    btnExcluir.hidden = false;
    lista.querySelectorAll(".CfgMk_Item").forEach((el) => {
      el.classList.toggle("is-selected", Number(el.dataset.id) === p.id);
    });
  }

  function renderLista() {
    lista.innerHTML = produtos
      .map(
        (p) => `
      <article class="CfgMk_Item${p.ativo ? "" : " is-off"}${selecionado === p.id ? " is-selected" : ""}" data-id="${p.id}">
        <strong>${esc(p.titulo)}</strong>
        <p class="CfgMk_ItemMeta">${esc(PUBLICO_LABEL[p.publico] || p.publico)} · ${esc(PAG_LABEL[p.tipo_pagamento] || p.tipo_pagamento)} · R$ ${centavosParaReais(p.valor_centavos)}${p.ativo ? "" : " · inativo"}</p>
      </article>`
      )
      .join("");
  }

  async function carregar() {
    const r = await fetch(BASE + "/dados", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    produtos = j.produtos || [];
    renderLista();
  }

  async function salvar() {
    const titulo = fld.titulo.value.trim();
    if (!titulo) {
      window.Swal?.fire?.({ icon: "warning", title: "Informe o título", confirmButtonColor: "#5b57f5" });
      return;
    }
    let meta = {};
    try {
      meta = JSON.parse(fld.meta.value.trim() || "{}");
    } catch {
      window.Swal?.fire?.({ icon: "error", title: "Meta JSON inválido", confirmButtonColor: "#5b57f5" });
      return;
    }
    const body = {
      id: fld.id.value ? Number(fld.id.value) : null,
      titulo,
      slug: fld.slug.value.trim(),
      ordem: Number(fld.ordem.value || 0),
      resumo: fld.resumo.value.trim(),
      valor_reais: reaisParaCentavos(fld.valor.value),
      tipo_pagamento: fld.tipo_pagamento.value,
      publico: fld.publico.value,
      categoria: fld.categoria.value,
      tipo_acao: fld.tipo_acao.value,
      icone: fld.icone.value.trim(),
      cor_topo: fld.cor.value,
      meta,
      ativo: fld.ativo.checked,
      descricao: window.CatDescricaoEditor?.getValue?.() || "",
    };
    const r = await fetch(BASE + "/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.success) {
      window.Swal?.fire?.({ icon: "error", title: j.message || "Erro ao salvar", confirmButtonColor: "#5b57f5" });
      return;
    }
    window.Swal?.fire?.({ icon: "success", title: "Salvo", timer: 1400, showConfirmButton: false });
    await carregar();
    if (j.produto) preencher(j.produto);
  }

  async function excluir() {
    const id = Number(fld.id.value);
    if (!id) return;
    const ok = await window.Swal?.fire?.({
      icon: "warning",
      title: "Excluir produto?",
      text: "Esta ação não pode ser desfeita.",
      showCancelButton: true,
      confirmButtonColor: "#dc2626",
      cancelButtonColor: "#94a3b8",
      confirmButtonText: "Excluir",
      cancelButtonText: "Cancelar",
    });
    if (ok && !ok.isConfirmed) return;
    if (!window.Swal && !confirm("Excluir produto?")) return;
    const r = await fetch(BASE + "/excluir", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!j.success) {
      window.Swal?.fire?.({ icon: "error", title: j.message || "Erro", confirmButtonColor: "#5b57f5" });
      return;
    }
    limpar();
    await carregar();
  }

  lista.addEventListener("click", (e) => {
    const item = e.target.closest(".CfgMk_Item");
    if (!item) return;
    const p = produtos.find((x) => x.id === Number(item.dataset.id));
    if (p) preencher(p);
  });

  document.getElementById("cfg_mk_btnNovo")?.addEventListener("click", limpar);
  document.getElementById("cfg_mk_btnSalvar")?.addEventListener("click", salvar);
  document.getElementById("cfg_mk_btnExcluir")?.addEventListener("click", excluir);

  fld.titulo?.addEventListener("blur", () => {
    if (!fld.slug.value.trim() && fld.titulo.value.trim()) {
      fld.slug.value = fld.titulo.value
        .normalize("NFD")
        .replace(/[\u0300-\u036f]/g, "")
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, "-")
        .replace(/^-|-$/g, "")
        .slice(0, 56);
    }
  });

  carregar();
})();
