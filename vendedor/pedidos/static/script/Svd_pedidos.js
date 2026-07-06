(function () {
  const STATUS_LABEL = {
    rascunho: "Rascunho",
    aguardando_pagamento: "Aguardando pagamento",
    pago: "Pago",
    cancelado: "Cancelado",
    em_expedicao: "Em expedição",
    entregue: "Entregue",
  };

  const el = {
    tbody: document.getElementById("pd_tbody"),
    vazio: document.getElementById("pd_vazio"),
    filtro: document.getElementById("pd_filtroStatus"),
    modal: document.getElementById("pd_modal"),
    detModal: document.getElementById("pd_detModal"),
    detBody: document.getElementById("pd_detBody"),
    detFoot: document.getElementById("pd_detFoot"),
    detTitulo: document.getElementById("pd_detTitulo"),
    itens: document.getElementById("pd_itens"),
    itensVazio: document.getElementById("pd_itensVazio"),
    resultados: document.getElementById("pd_resultados"),
    msg: document.getElementById("pd_msg"),
    subtotal: document.getElementById("pd_subtotal"),
    taxa: document.getElementById("pd_taxa"),
    total: document.getElementById("pd_total"),
    linhaTaxa: document.getElementById("pd_linhaTaxa"),
    cliNome: document.getElementById("pd_cliNome"),
  };

  let idGrupo = null;
  let carrinho = [];
  let taxasPorFornecedor = {};
  let ultimosProdutos = [];
  let pollPixTimer = null;
  let pedidoPagamentoAtual = null;

  const fmt = (v) =>
    Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

  const esc = (s) =>
    String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");

  function mostrarMsg(texto, erro) {
    el.msg.textContent = texto;
    el.msg.hidden = !texto;
    el.msg.classList.toggle("is-erro", !!erro);
  }

  function badge(status) {
    return `<span class="Pd_Badge Pd_Badge--${status}">${STATUS_LABEL[status] || status}</span>`;
  }

  async function carregarLista() {
    const st = el.filtro?.value || "";
    const url = st ? `/vendedor/pedidos/dados?status=${encodeURIComponent(st)}` : "/vendedor/pedidos/dados";
    const r = await fetch(url, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    taxasPorFornecedor = j.taxas_fornecedor || {};

    const rows = j.pedidos || [];
    el.tbody.innerHTML = rows
      .map(
        (p) => `
      <tr>
        <td><strong>${esc(p.numero)}</strong>${p.numero_grupo ? `<br><small>${esc(p.numero_grupo)}</small>` : ""}</td>
        <td>${esc(p.fornecedor_nome || "")}</td>
        <td>${esc(p.cliente_nome || "")}</td>
        <td>${fmt(p.valor_total)}</td>
        <td>${badge(p.status)}</td>
        <td>${p.criado_em ? new Date(p.criado_em).toLocaleDateString("pt-BR") : "—"}</td>
        <td><button type="button" class="Pd_BtnLink" data-ver="${p.id}">Ver</button></td>
      </tr>`
      )
      .join("");

    el.vazio.hidden = rows.length > 0;
    el.tbody.querySelectorAll("[data-ver]").forEach((btn) => {
      btn.addEventListener("click", () => abrirDetalhe(+btn.dataset.ver));
    });
  }

  function atualizarResumo() {
    const sub = carrinho.reduce((s, i) => s + i.valor_drop * i.quantidade, 0);
    const fornecedores = [...new Set(carrinho.map((i) => i.id_fornecedor))];
    let taxa = 0;
    fornecedores.forEach((f) => {
      taxa += Number(taxasPorFornecedor[f] || taxasPorFornecedor[String(f)] || 0);
    });
    el.subtotal.textContent = fmt(sub);
    el.taxa.textContent = fmt(taxa);
    el.total.textContent = fmt(sub + taxa);
    el.linhaTaxa.hidden = taxa <= 0;
    el.itensVazio.hidden = carrinho.length > 0;
  }

  function renderItens() {
    el.itens.innerHTML = carrinho
      .map(
        (i, idx) => `
      <tr>
        <td>${esc(i.nome)}<br><small>${esc(i.fornecedor_nome || "")}</small></td>
        <td>${esc(i.sku)}</td>
        <td>${fmt(i.valor_drop)}</td>
        <td><input type="number" min="1" value="${i.quantidade}" data-idx="${idx}" class="Pd_QtdInput" style="width:4rem" /></td>
        <td><button type="button" class="Pd_BtnLink Pd_BtnLink--danger" data-rm="${idx}">Remover</button></td>
      </tr>`
      )
      .join("");

    el.itens.querySelectorAll("[data-rm]").forEach((b) => {
      b.addEventListener("click", () => {
        carrinho.splice(+b.dataset.rm, 1);
        renderItens();
        atualizarResumo();
      });
    });
    el.itens.querySelectorAll(".Pd_QtdInput").forEach((inp) => {
      inp.addEventListener("change", () => {
        const idx = +inp.dataset.idx;
        carrinho[idx].quantidade = Math.max(1, +inp.value || 1);
        atualizarResumo();
      });
    });
    atualizarResumo();
  }

  function abrirModal() {
    idGrupo = null;
    carrinho = [];
    taxasPorFornecedor = {};
    document.getElementById("pd_modalTitulo").textContent = "Novo pedido";
    ["pd_cliNome", "pd_cliDoc", "pd_cliEmail", "pd_cliTel", "pd_cep", "pd_logradouro",
      "pd_numero", "pd_compl", "pd_bairro", "pd_cidade", "pd_uf"].forEach((id) => {
      const f = document.getElementById(id);
      if (f) f.value = "";
    });
    renderItens();
    mostrarMsg("");
    el.modal.hidden = false;
    el.resultados.hidden = true;
  }

  function fecharModal() {
    el.modal.hidden = true;
  }

  function corpoPedido() {
    return {
      id_grupo: idGrupo,
      cliente: {
        nome: document.getElementById("pd_cliNome")?.value,
        documento: document.getElementById("pd_cliDoc")?.value,
        email: document.getElementById("pd_cliEmail")?.value,
        telefone: document.getElementById("pd_cliTel")?.value,
      },
      entrega: {
        cep: document.getElementById("pd_cep")?.value,
        logradouro: document.getElementById("pd_logradouro")?.value,
        numero: document.getElementById("pd_numero")?.value,
        complemento: document.getElementById("pd_compl")?.value,
        bairro: document.getElementById("pd_bairro")?.value,
        cidade: document.getElementById("pd_cidade")?.value,
        uf: document.getElementById("pd_uf")?.value,
      },
      itens: carrinho.map((i) => ({ id_variante: i.id_variante, quantidade: i.quantidade })),
    };
  }

  async function buscarProdutos() {
    const q = document.getElementById("pd_buscaProd")?.value || "";
    const r = await fetch(`/vendedor/pedidos/produtos?q=${encodeURIComponent(q)}`, {
      credentials: "same-origin",
    });
    const j = await r.json();
    if (!j.success) return;
    const prods = j.produtos || [];
    ultimosProdutos = prods;
    el.resultados.hidden = prods.length === 0;
    el.resultados.innerHTML = prods
      .map(
        (p, idx) => `
      <div class="Pd_ResProd" data-idx="${idx}">
        <span>${esc(p.nome)} <small>(${esc(p.sku)}) — ${esc(p.fornecedor_nome)}</small></span>
        <span>${fmt(p.valor_drop)} · est. ${p.estoque_disponivel}</span>
      </div>`
      )
      .join("");
    el.resultados.querySelectorAll(".Pd_ResProd").forEach((row) => {
      row.addEventListener("click", () => {
        const p = ultimosProdutos[+row.dataset.idx];
        if (!p) return;
        const ex = carrinho.find((x) => x.id_variante === p.id_variante);
        if (ex) ex.quantidade += 1;
        else carrinho.push({ ...p, quantidade: 1 });
        renderItens();
        el.resultados.hidden = true;
      });
    });
  }

  async function salvar(confirmar) {
    mostrarMsg("");
    const body = corpoPedido();
    const r = await fetch("/vendedor/pedidos/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.success) {
      mostrarMsg(j.message || "Erro ao salvar.", true);
      return null;
    }
    idGrupo = j.id_grupo;
    if (!confirmar) {
      mostrarMsg(j.message || "Rascunho salvo.");
      await carregarLista();
      return j;
    }
    const rc = await fetch("/vendedor/pedidos/confirmar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_grupo: j.id_grupo }),
    });
    const jc = await rc.json();
    if (!jc.success) {
      mostrarMsg(jc.message || "Erro ao confirmar.", true);
      return null;
    }
    mostrarMsg(jc.message || "Pedido confirmado.");
    await carregarLista();
    setTimeout(fecharModal, 1200);
    return jc;
  }

  async function abrirDetalhe(id) {
    const r = await fetch(`/vendedor/pedidos/${id}`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const p = j.pedido;
    pedidoPagamentoAtual = p.id;
    el.detTitulo.textContent = `Pedido ${p.numero}`;
    el.detBody.innerHTML = `
      <div class="Pd_DetGrid">
        <div><strong>Fornecedor:</strong> ${esc(p.fornecedor_nome || "")}</div>
        <div><strong>Cliente:</strong> ${esc(p.cliente_nome)}</div>
        <div><strong>Situação:</strong> ${badge(p.status)}</div>
        <div><strong>Total:</strong> ${fmt(p.valor_total)} (produtos ${fmt(p.subtotal_produtos)}${p.valor_taxa_pedido > 0 ? ` + taxa ${fmt(p.valor_taxa_pedido)}` : ""})</div>
      </div>
      <table class="Pd_Table"><thead><tr><th>Produto</th><th>Qtd</th><th>Drop</th></tr></thead>
      <tbody>${(p.itens || []).map((i) => `<tr><td>${esc(i.nome_produto)}</td><td>${i.quantidade}</td><td>${fmt(i.subtotal_drop)}</td></tr>`).join("")}</tbody></table>`;

    el.detFoot.innerHTML = "";
    if (p.status === "rascunho") {
      const bConf = document.createElement("button");
      bConf.className = "Cl_BtnSalvar";
      bConf.textContent = "Confirmar";
      bConf.onclick = async () => {
        await fetch("/vendedor/pedidos/confirmar", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id_pedido: p.id }),
        });
        el.detModal.hidden = true;
        carregarLista();
      };
      el.detFoot.appendChild(bConf);
    }
    if (p.status === "rascunho" || p.status === "aguardando_pagamento") {
      const bCan = document.createElement("button");
      bCan.className = "Cl_BtnExcluir";
      bCan.textContent = "Cancelar pedido";
      bCan.onclick = async () => {
        if (!confirm("Cancelar este pedido?")) return;
        await fetch("/vendedor/pedidos/cancelar", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id_pedido: p.id }),
        });
        el.detModal.hidden = true;
        carregarLista();
      };
      el.detFoot.appendChild(bCan);
    }
    if (p.status === "aguardando_pagamento") {
      await renderPagamento(p);
    }
    el.detModal.hidden = false;
  }

  function pararPollPix() {
    if (pollPixTimer) {
      clearInterval(pollPixTimer);
      pollPixTimer = null;
    }
  }

  function fecharPayModal() {
    pararPollPix();
    document.getElementById("pd_payModal").hidden = true;
  }

  async function pollPixStatus(idPedido) {
    const r = await fetch(`/vendedor/pedidos/${idPedido}/pagamento/status`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const stEl = document.getElementById("pd_payStatus");
    if (j.status === "pago") {
      if (stEl) stEl.textContent = "Pagamento confirmado!";
      pararPollPix();
      setTimeout(() => {
        fecharPayModal();
        el.detModal.hidden = true;
        carregarLista();
        if (window.Swal) {
          Swal.fire({ icon: "success", title: "Pago", text: "Pedido pago com sucesso.", confirmButtonColor: "#021F81" });
        }
      }, 800);
    } else if (stEl) {
      stEl.textContent = "Aguardando confirmação do PIX…";
    }
  }

  function abrirModalPix(dados) {
    const modal = document.getElementById("pd_payModal");
    const img = document.getElementById("pd_pixImg");
    const wrap = document.getElementById("pd_pixQrWrap");
    const code = document.getElementById("pd_pixCode");
    const stEl = document.getElementById("pd_payStatus");

    if (code) code.textContent = dados.qr_code || "—";
    if (dados.qr_code_base64 && img) {
      img.src = `data:image/png;base64,${dados.qr_code_base64}`;
      if (wrap) wrap.hidden = false;
    } else if (wrap) {
      wrap.hidden = true;
    }
    if (stEl) stEl.textContent = "Aguardando confirmação do PIX…";
    modal.hidden = false;

    pararPollPix();
    pollPixTimer = setInterval(() => pollPixStatus(pedidoPagamentoAtual), 5000);
    pollPixStatus(pedidoPagamentoAtual);
  }

  async function iniciarPagamento(idPedido, meio) {
    const r = await fetch("/vendedor/pedidos/pagar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_pedido: idPedido, meio }),
    });
    const j = await r.json();
    if (!j.success) {
      mostrarMsg(j.message || "Erro ao iniciar pagamento.", true);
      if (window.Swal) Swal.fire({ icon: "error", title: "Pagamento", text: j.message, confirmButtonColor: "#021F81" });
      return;
    }
    if (meio === "pix") {
      abrirModalPix(j);
      return;
    }
    if (j.checkout_url) {
      window.location.href = j.checkout_url;
    }
  }

  async function renderPagamento(p) {
    const r = await fetch(`/vendedor/pedidos/${p.id}/meios-pagamento`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      const aviso = document.createElement("p");
      aviso.className = "Pd_Hint";
      aviso.textContent = j.message || "Pagamento indisponível.";
      el.detFoot.prepend(aviso);
      return;
    }
    if (!j.conectado) {
      const aviso = document.createElement("p");
      aviso.className = "Pd_Hint";
      aviso.textContent = "Fornecedor ainda não conectou o Mercado Pago.";
      el.detFoot.prepend(aviso);
      return;
    }

    const box = document.createElement("div");
    box.className = "Pd_PayActions";
    box.innerHTML = `<span class="Pd_Hint" style="flex:1 1 100%">Pagar ${fmt(j.valor_total)} ao fornecedor:</span>`;

    if (j.pix) {
      const bPix = document.createElement("button");
      bPix.type = "button";
      bPix.className = "Pd_PayBtn Pd_PayBtn--pix";
      bPix.textContent = "Pagar com PIX";
      bPix.onclick = () => iniciarPagamento(p.id, "pix");
      box.appendChild(bPix);
    }
    if (j.cartao) {
      const bCard = document.createElement("button");
      bCard.type = "button";
      bCard.className = "Pd_PayBtn Pd_PayBtn--cartao";
      bCard.textContent = "Pagar com cartão";
      bCard.onclick = () => iniciarPagamento(p.id, "cartao");
      box.appendChild(bCard);
    }
    el.detFoot.prepend(box);
  }

  document.getElementById("pd_btnNovo")?.addEventListener("click", abrirModal);
  document.getElementById("pd_btnFechar")?.addEventListener("click", fecharModal);
  document.getElementById("pd_detFechar")?.addEventListener("click", () => {
    el.detModal.hidden = true;
  });
  document.getElementById("pd_payFechar")?.addEventListener("click", fecharPayModal);
  document.getElementById("pd_pixCopiar")?.addEventListener("click", () => {
    const code = document.getElementById("pd_pixCode")?.textContent || "";
    if (!code || code === "—") return;
    navigator.clipboard?.writeText(code).then(() => {
      const st = document.getElementById("pd_payStatus");
      if (st) st.textContent = "Código PIX copiado.";
    });
  });
  document.getElementById("pd_btnFiltrar")?.addEventListener("click", carregarLista);
  document.getElementById("pd_btnBuscaProd")?.addEventListener("click", buscarProdutos);
  document.getElementById("pd_btnSalvar")?.addEventListener("click", () => salvar(false));
  document.getElementById("pd_btnConfirmar")?.addEventListener("click", () => salvar(true));

  el.modal?.addEventListener("click", (e) => {
    if (e.target === el.modal) fecharModal();
  });

  carregarLista();

  (function tratarRetornoPagamento() {
    const params = new URLSearchParams(location.search);
    const pg = params.get("pagamento");
    const idPed = params.get("id_pedido");
    if (!pg) return;
    window.history.replaceState({}, "", location.pathname);
    const msgs = {
      success: { icon: "success", title: "Pagamento aprovado", text: "O pedido foi marcado como pago." },
      pending: { icon: "info", title: "Pagamento pendente", text: "Aguardando confirmação do Mercado Pago." },
      failure: { icon: "error", title: "Pagamento não concluído", text: "Tente novamente ou escolha outro meio." },
    };
    const m = msgs[pg] || { icon: "info", title: "Retorno", text: "Verifique o status do pedido." };
    if (window.Swal) {
      Swal.fire({ ...m, confirmButtonColor: "#021F81" }).then(() => {
        if (idPed) abrirDetalhe(+idPed);
      });
    } else if (idPed) {
      abrirDetalhe(+idPed);
    }
  })();
})();
