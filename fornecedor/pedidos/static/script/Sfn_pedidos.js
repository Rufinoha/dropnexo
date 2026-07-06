(function () {
  const LABEL = {
    aguardando_pagamento: "Aguardando pagamento",
    pago: "Pago",
    cancelado: "Cancelado",
  };
  const tbody = document.getElementById("pd_fn_tbody");
  const vazio = document.getElementById("pd_fn_vazio");
  const modal = document.getElementById("pd_fn_modal");
  const body = document.getElementById("pd_fn_body");
  const titulo = document.getElementById("pd_fn_titulo");

  const fmt = (v) => Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");

  function badge(st) {
    return `<span class="PdFn_Badge PdFn_Badge--${st}">${LABEL[st] || st}</span>`;
  }

  async function carregar() {
    const st = document.getElementById("pd_fn_status")?.value || "";
    const url = st ? `/fornecedor/pedidos/dados?status=${encodeURIComponent(st)}` : "/fornecedor/pedidos/dados";
    const r = await fetch(url, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const rows = j.pedidos || [];
    tbody.innerHTML = rows
      .map(
        (p) => `
      <tr>
        <td><strong>${esc(p.numero)}</strong></td>
        <td>${esc(p.vendedor_nome || "")}</td>
        <td>${esc(p.cliente_nome || "")}</td>
        <td>${fmt(p.valor_total)}</td>
        <td>${badge(p.status)}</td>
        <td>${p.criado_em ? new Date(p.criado_em).toLocaleDateString("pt-BR") : "—"}</td>
        <td><button type="button" class="PdFn_BtnLink" data-id="${p.id}">Ver</button></td>
      </tr>`
      )
      .join("");
    vazio.hidden = rows.length > 0;
    tbody.querySelectorAll("[data-id]").forEach((b) => {
      b.addEventListener("click", () => abrir(+b.dataset.id));
    });
  }

  async function abrir(id) {
    const r = await fetch(`/fornecedor/pedidos/${id}`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const p = j.pedido;
    titulo.textContent = `Pedido ${p.numero}`;
    body.innerHTML = `
      <p><strong>Vendedor:</strong> ${esc(p.vendedor_nome || "")}</p>
      <p><strong>Cliente:</strong> ${esc(p.cliente_nome)} — ${esc(p.cliente_telefone || "")}</p>
      <p><strong>Entrega:</strong> ${esc(p.entrega_logradouro || "")} ${esc(p.entrega_numero || "")}, ${esc(p.entrega_cidade || "")}-${esc(p.entrega_uf || "")}</p>
      <p><strong>Total:</strong> ${fmt(p.valor_total)} ${p.valor_taxa_pedido > 0 ? `(incl. taxa ${fmt(p.valor_taxa_pedido)})` : ""}</p>
      <p>${badge(p.status)}</p>
      <table class="PdFn_Table" style="margin-top:1rem"><thead><tr><th>Produto</th><th>Qtd</th><th>Drop</th></tr></thead>
      <tbody>${(p.itens || []).map((i) => `<tr><td>${esc(i.nome_produto)}</td><td>${i.quantidade}</td><td>${fmt(i.subtotal_drop)}</td></tr>`).join("")}</tbody></table>`;
    modal.hidden = false;
  }

  document.getElementById("pd_fn_filtrar")?.addEventListener("click", carregar);
  document.getElementById("pd_fn_fechar")?.addEventListener("click", () => {
    modal.hidden = true;
  });
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) modal.hidden = true;
  });

  carregar();
})();
