(function () {
  const LABEL = {
    pago: "Pago",
    em_expedicao: "Em expedição",
    entregue: "Entregue",
  };
  const tbody = document.getElementById("ex_pd_tbody");
  const vazio = document.getElementById("ex_pd_vazio");
  const modal = document.getElementById("ex_pd_modal");
  const body = document.getElementById("ex_pd_body");
  const titulo = document.getElementById("ex_pd_titulo");

  const fmt = (v) => Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const esc = (s) => String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;");

  function badge(st) {
    return `<span class="ExPd_Badge ExPd_Badge--${st}">${LABEL[st] || st}</span>`;
  }

  async function carregar() {
    const st = document.getElementById("ex_pd_status")?.value || "";
    const url = st ? `/vendedor/expedicao/dados?status=${encodeURIComponent(st)}` : "/vendedor/expedicao/dados";
    const r = await fetch(url, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const rows = j.pedidos || [];
    tbody.innerHTML = rows
      .map(
        (p) => `
      <tr>
        <td><strong>${esc(p.numero)}</strong></td>
        <td>${esc(p.fornecedor_nome || "")}</td>
        <td>${esc(p.cliente_nome || "")}</td>
        <td>${fmt(p.valor_total)}</td>
        <td>${badge(p.status)}</td>
        <td>${esc(p.codigo_rastreio || "—")}</td>
        <td><button type="button" class="ExPd_BtnLink" data-id="${p.id}">Ver</button></td>
      </tr>`
      )
      .join("");
    vazio.hidden = rows.length > 0;
    tbody.querySelectorAll("[data-id]").forEach((b) => {
      b.addEventListener("click", () => abrir(+b.dataset.id));
    });
  }

  async function abrir(id) {
    const r = await fetch(`/vendedor/pedidos/${id}`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const p = j.pedido;
    titulo.textContent = `Pedido ${p.numero}`;
    body.innerHTML = `
      <p><strong>Fornecedor:</strong> ${esc(p.fornecedor_nome || "")}</p>
      <p><strong>Cliente:</strong> ${esc(p.cliente_nome)}</p>
      <p><strong>Entrega:</strong> ${esc(p.entrega_logradouro || "")} ${esc(p.entrega_numero || "")}, ${esc(p.entrega_cidade || "")}-${esc(p.entrega_uf || "")}</p>
      <p>${badge(p.status)}</p>
      ${p.transportadora ? `<p><strong>Transportadora:</strong> ${esc(p.transportadora)}</p>` : ""}
      ${p.codigo_rastreio ? `<p><strong>Rastreio:</strong> ${esc(p.codigo_rastreio)}</p>` : ""}
      ${p.expedido_em ? `<p><strong>Expedido em:</strong> ${new Date(p.expedido_em).toLocaleString("pt-BR")}</p>` : ""}
      ${p.entregue_em ? `<p><strong>Entregue em:</strong> ${new Date(p.entregue_em).toLocaleString("pt-BR")}</p>` : ""}
      <table class="ExPd_Table" style="margin-top:1rem"><thead><tr><th>Produto</th><th>Qtd</th></tr></thead>
      <tbody>${(p.itens || []).map((i) => `<tr><td>${esc(i.nome_produto)}</td><td>${i.quantidade}</td></tr>`).join("")}</tbody></table>`;
    modal.hidden = false;
  }

  document.getElementById("ex_pd_filtrar")?.addEventListener("click", carregar);
  document.getElementById("ex_pd_fechar")?.addEventListener("click", () => {
    modal.hidden = true;
  });
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) modal.hidden = true;
  });

  carregar();
})();
