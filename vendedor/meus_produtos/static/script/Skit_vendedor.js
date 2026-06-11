(function () {
  let kitId = null;
  let itens = [];

  const el = {
    nome: document.getElementById("nome"),
    descricao: document.getElementById("descricao"),
    preco_venda: document.getElementById("preco_venda"),
    usar_preco_sugerido: document.getElementById("usar_preco_sugerido"),
    kit_resumo: document.getElementById("kit_resumo"),
    busca_rede: document.getElementById("busca_rede"),
    btnBuscarRede: document.getElementById("btnBuscarRede"),
    lista_rede: document.getElementById("lista_rede"),
    tbody: document.getElementById("itens_kit"),
    btnSalvar: document.getElementById("btnSalvar"),
    btnExcluir: document.getElementById("btnExcluir"),
  };

  function fmt(v) {
    return Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function atualizarResumo(meta) {
    const sug = meta?.preco_sugerido ?? itens.reduce((s, i) => s + (i.preco || 0) * i.quantidade, 0);
    const est = meta?.estoque_disponivel ?? "—";
    if (el.kit_resumo) {
      el.kit_resumo.textContent = `Preço sugerido: ${fmt(sug)} · Estoque máximo montável: ${est}`;
    }
    if (el.usar_preco_sugerido?.checked && el.preco_venda) el.preco_venda.value = Number(sug).toFixed(2);
  }

  function renderItens() {
    if (!itens.length) {
      el.tbody.innerHTML = "<tr><td colspan='3'>Nenhum item.</td></tr>";
      atualizarResumo();
      return;
    }
    el.tbody.innerHTML = itens
      .map(
        (it, idx) => `
      <tr>
        <td>${it.produto_nome || ""} — ${it.nome_exibicao || ""} <small>(${it.fornecedor_nome})</small></td>
        <td><input type="number" min="1" value="${it.quantidade}" data-idx="${idx}" class="inpQtd" style="width:70px" /></td>
        <td><button type="button" class="Cl_BtnAcao btnRem" data-idx="${idx}">Remover</button></td>
      </tr>`
      )
      .join("");
    atualizarResumo();
  }

  async function buscarRede() {
    const q = (el.busca_rede?.value || "").trim();
    const r = await fetch(`/meus-produtos/rede-opcoes?busca=${encodeURIComponent(q)}`);
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro");
    const list = j.itens || [];
    if (!list.length) {
      el.lista_rede.innerHTML = "<p>Nenhum produto encontrado.</p>";
      return;
    }
    el.lista_rede.innerHTML = list
      .map(
        (p) => `
      <div class="Prod_RedeItem">
        <span>${p.produto_nome} — ${p.nome_exibicao} · ${p.fornecedor_nome} · ${fmt(p.preco)} · est. ${p.estoque}</span>
        <button type="button" class="Cl_BtnAcao btnAdd" data-id="${p.id_variante}" data-json='${JSON.stringify(p).replace(/'/g, "&#39;")}'>+</button>
      </div>`
      )
      .join("");
  }

  el.lista_rede?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".btnAdd");
    if (!btn) return;
    try {
      const p = JSON.parse(btn.dataset.json || "{}");
      if (itens.some((x) => x.id_variante === p.id_variante)) return;
      itens.push({
        id_variante: p.id_variante,
        quantidade: 1,
        nome_exibicao: p.nome_exibicao,
        produto_nome: p.produto_nome,
        fornecedor_nome: p.fornecedor_nome,
        preco: p.preco_promocional != null && p.preco_promocional < p.preco ? p.preco_promocional : p.preco,
      });
      renderItens();
    } catch (e) {
      Swal.fire("Erro", e.message, "error");
    }
  });

  el.tbody?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".btnRem");
    if (!btn) return;
    itens.splice(Number(btn.dataset.idx), 1);
    renderItens();
  });
  el.tbody?.addEventListener("change", (ev) => {
    const inp = ev.target.closest(".inpQtd");
    if (!inp) return;
    itens[Number(inp.dataset.idx)].quantidade = Math.max(1, parseInt(inp.value, 10) || 1);
    atualizarResumo();
  });

  async function carregar(id) {
    const r = await fetch("/meus-produtos/kits/apoio", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message);
    const d = j.dados;
    el.nome.value = d.nome || "";
    el.descricao.value = d.descricao || "";
    el.preco_venda.value = d.preco_venda ?? 0;
    el.usar_preco_sugerido.checked = !!d.usar_preco_sugerido;
    itens = (d.itens || []).map((i) => ({
      id_variante: i.id_variante,
      quantidade: i.quantidade,
      nome_exibicao: i.nome_exibicao,
      produto_nome: i.produto_nome,
      fornecedor_nome: i.fornecedor_nome,
      preco: i.preco,
    }));
    renderItens();
    atualizarResumo({ preco_sugerido: d.preco_sugerido, estoque_disponivel: d.estoque_disponivel });
    if (el.btnExcluir) el.btnExcluir.style.display = "inline-block";
  }

  async function salvar() {
    const body = {
      id: kitId,
      nome: (el.nome.value || "").trim(),
      descricao: (el.descricao.value || "").trim(),
      preco_venda: el.preco_venda.value,
      usar_preco_sugerido: !!el.usar_preco_sugerido.checked,
      itens: itens.map((i) => ({ id_variante: i.id_variante, quantidade: i.quantidade })),
    };
    const r = await fetch("/meus-produtos/kits/salvar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message);
    await Swal.fire("Ok", j.message, "success");
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.GlobalUtils?.fecharJanelaApoio(1);
  }

  el.btnBuscarRede?.addEventListener("click", () => buscarRede().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnSalvar?.addEventListener("click", () => salvar().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnExcluir?.addEventListener("click", async () => {
    if (!kitId) return;
    const c = await Swal.fire({ title: "Excluir kit?", icon: "warning", showCancelButton: true });
    if (!c.isConfirmed) return;
    const r = await fetch("/meus-produtos/kits/delete", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: kitId }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message);
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.GlobalUtils?.fecharJanelaApoio(1);
  });

  if (window.GlobalUtils?.receberDadosApoio) {
    window.GlobalUtils.receberDadosApoio((id) => {
      if (id) {
        kitId = Number(id);
        carregar(kitId).catch((e) => Swal.fire("Erro", e.message, "error"));
      } else {
        buscarRede().catch(() => {});
      }
    });
  } else {
    buscarRede().catch(() => {});
  }
})();
