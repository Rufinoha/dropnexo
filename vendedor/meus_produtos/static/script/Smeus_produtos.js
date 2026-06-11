(function () {
  let paginaAtual = 1;
  let totalPaginas = 1;
  const porPagina = 20;

  const el = {
    tabs: document.querySelectorAll(".Prod_Tab"),
    painelSalvos: document.getElementById("painel_salvos"),
    painelKits: document.getElementById("painel_kits"),
    filtroBusca: document.getElementById("ob_filtroBusca"),
    btnFiltrar: document.getElementById("ob_btnFiltrar"),
    tbody: document.getElementById("ob_listaProdutos"),
    tbodyKits: document.getElementById("ob_listaKits"),
    btnNovoKit: document.getElementById("ob_btnNovoKit"),
    paginaAtual: document.getElementById("ob_paginaAtual"),
    totalPaginas: document.getElementById("ob_totalPaginas"),
    btnAnterior: document.getElementById("ob_btnAnterior"),
    btnProximo: document.getElementById("ob_btnProximo"),
  };

  function fmtMoeda(v) {
    return Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function thumb(url) {
    if (url) return `<img class="Prod_Thumb" src="${url}" alt="" loading="lazy" />`;
    return `<span class="Prod_Thumb Prod_Thumb--vazio">—</span>`;
  }

  el.tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      el.tabs.forEach((t) => t.classList.remove("Prod_Tab--ativo"));
      tab.classList.add("Prod_Tab--ativo");
      const k = tab.dataset.tab;
      el.painelSalvos.hidden = k !== "salvos";
      el.painelKits.hidden = k !== "kits";
      if (k === "kits") carregarKits();
    });
  });

  async function carregarSalvos() {
    const p = new URLSearchParams({
      pagina: paginaAtual,
      porPagina,
      busca: (el.filtroBusca?.value || "").trim(),
    });
    const r = await fetch(`/meus-produtos/dados?${p}`);
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message);
    totalPaginas = j.total_paginas || 1;
    if (el.paginaAtual) el.paginaAtual.textContent = String(paginaAtual);
    if (el.totalPaginas) el.totalPaginas.textContent = String(totalPaginas);
    if (el.btnAnterior) el.btnAnterior.disabled = paginaAtual <= 1;
    if (el.btnProximo) el.btnProximo.disabled = paginaAtual >= totalPaginas;
    const dados = j.dados || [];
    if (!dados.length) {
      el.tbody.innerHTML = "<tr><td colspan='7'>Nenhum produto salvo.</td></tr>";
      return;
    }
    el.tbody.innerHTML = dados
      .map(
        (p) => `
      <tr>
        <td class="Prod_ColImg">${thumb(p.imagem_url)}</td>
        <td>${p.fornecedor_nome}</td>
        <td>${p.sku || "—"}</td>
        <td>${p.nome}</td>
        <td>${fmtMoeda(p.preco_promocional != null && p.preco_promocional < p.preco ? p.preco_promocional : p.preco)}</td>
        <td>${p.estoque ?? 0}</td>
        <td class="Cl_TableActions">
          <button type="button" class="Cl_BtnAcao btnRemover" data-id="${p.id_variante || p.id}">Remover</button>
        </td>
      </tr>`
      )
      .join("");
  }

  async function carregarKits() {
    const r = await fetch("/meus-produtos/kits/dados");
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message);
    const kits = j.kits || [];
    if (!kits.length) {
      el.tbodyKits.innerHTML =
        "<tr><td colspan='4'>Nenhum kit. Clique em <strong>Novo kit</strong> para montar.</td></tr>";
      return;
    }
    el.tbodyKits.innerHTML = kits
      .map(
        (k) => `
      <tr>
        <td>${k.nome}</td>
        <td>${k.qtd_itens}</td>
        <td>${fmtMoeda(k.preco_venda)}</td>
        <td class="Cl_TableActions">
          <button type="button" class="Cl_BtnAcao btnEditKit" data-id="${k.id}">Editar</button>
        </td>
      </tr>`
      )
      .join("");
  }

  function abrirKit(id) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: id ? "/meus-produtos/kits/editar" : "/meus-produtos/kits/incluir",
      id: id || null,
      titulo: id ? "Editar kit" : "Novo kit",
      largura: 900,
      altura: 640,
      nivel: 1,
    });
  }

  el.btnFiltrar?.addEventListener("click", () => {
    paginaAtual = 1;
    carregarSalvos().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  el.btnAnterior?.addEventListener("click", () => {
    if (paginaAtual > 1) {
      paginaAtual -= 1;
      carregarSalvos();
    }
  });
  el.btnProximo?.addEventListener("click", () => {
    if (paginaAtual < totalPaginas) {
      paginaAtual += 1;
      carregarSalvos();
    }
  });
  el.btnNovoKit?.addEventListener("click", () => abrirKit(null));
  el.tbodyKits?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".btnEditKit");
    if (btn) abrirKit(Number(btn.dataset.id));
  });
  el.tbody?.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".btnRemover");
    if (!btn) return;
    const id = Number(btn.dataset.id);
    const r = await fetch("/meus-produtos/desfavoritar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_variante: id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) return Swal.fire("Erro", j.message, "error");
    await carregarSalvos();
  });

  window.addEventListener("message", (ev) => {
    if (ev.data?.grupo === "atualizarTabela") {
      carregarSalvos().catch(() => {});
      carregarKits().catch(() => {});
    }
  });

  carregarSalvos().catch((e) => Swal.fire("Erro", e.message, "error"));
})();
