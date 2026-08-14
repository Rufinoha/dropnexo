(function () {
  const BASE = "/armazem/produtos";
  const grid = document.getElementById("az_prod_grid");
  const vazio = document.getElementById("az_prod_vazio");
  const modal = document.getElementById("az_prod_modal");
  const form = document.getElementById("az_prod_form");
  const busca = document.getElementById("az_prod_busca");
  const filtroForn = document.getElementById("az_prod_filtro_forn");
  const estoqueList = document.getElementById("az_prod_estoque_list");
  let depositos = [];
  let fornecedores = [];

  const el = {
    id: document.getElementById("az_prod_id"),
    forn: document.getElementById("az_prod_forn"),
    nome: document.getElementById("az_prod_nome"),
    sku: document.getElementById("az_prod_sku"),
    preco: document.getElementById("az_prod_preco"),
    dep: document.getElementById("az_prod_dep"),
    pub: document.getElementById("az_prod_pub"),
    btnExcluir: document.getElementById("az_prod_btnExcluir"),
    titulo: document.getElementById("az_prod_titulo"),
  };

  if (!grid) return;

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmt(v) {
    return Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function renderEstoque(rows) {
    const map = {};
    (rows || []).forEach((r) => {
      map[r.id_deposito] = r.quantidade;
    });
    estoqueList.innerHTML = depositos
      .map(
        (d) => `
      <label class="AzProd_EstoqueRow">
        <span>${esc(d.nome)}</span>
        <input type="number" min="0" step="1" data-dep="${d.id}" value="${map[d.id] ?? 0}" />
      </label>`
      )
      .join("") || "<p class='AzProd_Hint'>Cadastre um depósito antes de informar estoque.</p>";
  }

  function abrir(dados) {
    el.id.value = dados?.id || "";
    el.nome.value = dados?.nome || "";
    el.sku.value = dados?.sku || "";
    el.preco.value = dados?.preco ?? "";
    el.pub.checked = dados ? !!dados.publicado : true;
    el.forn.value = dados?.id_armazem_fornecedor || "";
    el.dep.value = dados?.id_deposito_expedicao || "";
    el.titulo.textContent = dados?.id ? "Editar produto" : "Novo produto";
    el.btnExcluir.hidden = !dados?.id;
    renderEstoque(dados?.estoques || []);
    modal.hidden = false;
  }

  function fechar() {
    modal.hidden = true;
  }

  async function combos() {
    const r = await fetch(`${BASE}/combos`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    fornecedores = j.fornecedores || [];
    depositos = j.depositos || [];
    el.forn.innerHTML =
      '<option value="">Selecione…</option>' +
      fornecedores.map((f) => `<option value="${f.id}">${esc(f.nome)}</option>`).join("");
    el.dep.innerHTML =
      '<option value="">—</option>' +
      depositos.map((d) => `<option value="${d.id}">${esc(d.nome)}</option>`).join("");
    filtroForn.innerHTML =
      '<option value="">Todos os fornecedores</option>' +
      fornecedores.map((f) => `<option value="${f.id}">${esc(f.nome)}</option>`).join("");
  }

  async function carregar() {
    const q = (busca.value || "").trim();
    const fid = filtroForn.value || "";
    const params = new URLSearchParams();
    if (q) params.set("busca", q);
    if (fid) params.set("id_fornecedor", fid);
    const r = await fetch(`${BASE}/dados?${params}`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const lista = j.dados || [];
    if (!lista.length) {
      grid.innerHTML = "";
      vazio.hidden = false;
      return;
    }
    vazio.hidden = true;
    grid.innerHTML = lista
      .map(
        (p) => `
      <article class="AzProd_Card" data-id="${p.id}">
        <strong>${esc(p.nome)}</strong>
        <span>${esc(p.fornecedor_nome || "Sem fornecedor")}</span>
        <span class="AzProd_Meta">${esc(p.sku || "s/ SKU")} · ${fmt(p.preco)} · est. ${p.estoque}</span>
        <span class="AzProd_Badge ${p.publicado ? "is-on" : ""}">${p.publicado ? "Publicado" : "Oculto"}</span>
      </article>`
      )
      .join("");
  }

  document.getElementById("az_prod_btnIncluir")?.addEventListener("click", () => {
    if (!fornecedores.length) {
      (window.Util?.alertar || alert)("Cadastre ao menos um fornecedor antes.");
      return;
    }
    abrir(null);
  });
  document.getElementById("az_prod_btnFechar")?.addEventListener("click", fechar);
  document.getElementById("az_prod_btnCancelar")?.addEventListener("click", fechar);

  grid.addEventListener("dblclick", async (e) => {
    const card = e.target.closest("[data-id]");
    if (!card) return;
    const r = await fetch(`${BASE}/apoio`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: Number(card.dataset.id) }),
    });
    const j = await r.json();
    if (j.success) abrir(j.dados);
  });

  form?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const estoques = [...estoqueList.querySelectorAll("input[data-dep]")].map((inp) => ({
      id_deposito: Number(inp.dataset.dep),
      quantidade: Number(inp.value || 0),
    }));
    const body = {
      id: el.id.value ? Number(el.id.value) : null,
      nome: el.nome.value,
      sku: el.sku.value,
      preco: el.preco.value,
      publicado: !!el.pub.checked,
      id_armazem_fornecedor: Number(el.forn.value),
      id_deposito_expedicao: el.dep.value ? Number(el.dep.value) : null,
      estoques,
    };
    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (window.Util?.alertar) Util.alertar(j.message || (j.success ? "Salvo" : "Erro"), j.success ? "success" : "error");
    else if (window.Swal) Swal.fire(j.success ? "Salvo" : "Erro", j.message, j.success ? "success" : "error");
    if (j.success) {
      fechar();
      carregar();
    }
  });

  el.btnExcluir?.addEventListener("click", async () => {
    if (!el.id.value) return;
    const r = await fetch(`${BASE}/excluir`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: Number(el.id.value) }),
    });
    const j = await r.json();
    if (j.success) {
      fechar();
      carregar();
    }
  });

  let t = null;
  busca?.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(carregar, 280);
  });
  filtroForn?.addEventListener("change", carregar);

  combos().then(carregar);
})();
