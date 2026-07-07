(function () {
  const LABEL = {
    aguardando_pagamento: "Aguardando pagamento",
    pago: "Pago",
    em_expedicao: "Em expedição",
    entregue: "Entregue",
    cancelado: "Cancelado",
  };
  const tbody = document.getElementById("pd_fn_tbody");
  const vazio = document.getElementById("pd_fn_vazio");
  const modal = document.getElementById("pd_fn_modal");
  const body = document.getElementById("pd_fn_body");
  const titulo = document.getElementById("pd_fn_titulo");
  const foot = document.getElementById("pd_fn_foot");
  let pedidoAtual = null;

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
        <td><strong>${esc(p.numero)}</strong>${p.origem === "bling" ? ' <small>(Bling)</small>' : ""}</td>
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

  function renderAcoes(p) {
    if (!foot) return;
    foot.innerHTML = "";
    const comprovantes = (p.anexos || []).filter((a) => a.tipo === "comprovante_pix");
    if (
      p.status === "aguardando_pagamento" &&
      p.meio_pagamento === "pix_manual" &&
      (p.status_pagamento === "comprovante_enviado" || comprovantes.length)
    ) {
      const links = comprovantes
        .map(
          (a) =>
            `<li><a href="/vendedor/pedidos/anexos/arquivo?caminho=${encodeURIComponent(a.caminho)}" target="_blank">${a.nome_original}</a></li>`
        )
        .join("");
      foot.innerHTML = `
        <div class="PdFn_PayValid">
          <p><strong>PIX manual</strong> — valide o comprovante:</p>
          <ul>${links || "<li>Comprovante pendente de anexo</li>"}</ul>
          <div class="PdFn_PayValidBtns">
            <button type="button" class="Cl_botaoprimario" id="pd_fn_btn_conf_pix">Confirmar pagamento</button>
            <button type="button" class="Cl_BtnExcluir" id="pd_fn_btn_rej_pix">Rejeitar comprovante</button>
          </div>
        </div>`;
      document.getElementById("pd_fn_btn_conf_pix")?.addEventListener("click", () => confirmarPix(p.id));
      document.getElementById("pd_fn_btn_rej_pix")?.addEventListener("click", () => rejeitarPix(p.id));
      return;
    }
    if (p.status === "pago") {
      foot.innerHTML = `
        <div class="PdFn_ExpForm">
          <label>Transportadora <input type="text" id="pd_fn_transportadora" placeholder="Opcional" /></label>
          <label>Código rastreio <input type="text" id="pd_fn_rastreio" placeholder="Opcional" /></label>
          <button type="button" class="Cl_botaoprimario" id="pd_fn_btn_expedir">Marcar em expedição</button>
        </div>`;
      document.getElementById("pd_fn_btn_expedir")?.addEventListener("click", () => expedir(p.id));
    } else if (p.status === "em_expedicao") {
      foot.innerHTML = `<button type="button" class="Cl_botaoprimario" id="pd_fn_btn_entregue">Marcar entregue</button>`;
      document.getElementById("pd_fn_btn_entregue")?.addEventListener("click", () => entregue(p.id));
    }
  }

  async function expedir(id) {
    const rastreio = document.getElementById("pd_fn_rastreio")?.value || "";
    const transp = document.getElementById("pd_fn_transportadora")?.value || "";
    const r = await fetch(`/fornecedor/pedidos/${id}/expedir`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ codigo_rastreio: rastreio, transportadora: transp }),
    });
    const j = await r.json();
    if (window.Swal) await Swal.fire(j.success ? "Sucesso" : "Erro", j.message, j.success ? "success" : "error");
    if (j.success) {
      modal.hidden = true;
      carregar();
    }
  }

  async function entregue(id) {
    const r = await fetch(`/fornecedor/pedidos/${id}/entregue`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const j = await r.json();
    if (window.Swal) await Swal.fire(j.success ? "Sucesso" : "Erro", j.message, j.success ? "success" : "error");
    if (j.success) {
      modal.hidden = true;
      carregar();
    }
  }

  async function confirmarPix(id) {
    const r = await fetch(`/fornecedor/pedidos/${id}/pagamento/confirmar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const j = await r.json();
    if (window.Swal) await Swal.fire(j.success ? "Pago" : "Erro", j.message, j.success ? "success" : "error");
    if (j.success) {
      modal.hidden = true;
      carregar();
    }
  }

  async function rejeitarPix(id) {
    const motivo = prompt("Motivo da rejeição (opcional):") || "";
    const r = await fetch(`/fornecedor/pedidos/${id}/pagamento/rejeitar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motivo }),
    });
    const j = await r.json();
    if (window.Swal) await Swal.fire(j.success ? "Rejeitado" : "Erro", j.message, j.success ? "info" : "error");
    if (j.success) abrir(id);
  }

  async function abrir(id) {
    const r = await fetch(`/fornecedor/pedidos/${id}`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const p = j.pedido;
    pedidoAtual = p;
    titulo.textContent = `Pedido ${p.numero}`;
    body.innerHTML = `
      <p><strong>Vendedor:</strong> ${esc(p.vendedor_nome || "")}</p>
      <p><strong>Cliente:</strong> ${esc(p.cliente_nome)} — ${esc(p.cliente_telefone || "")}</p>
      <p><strong>Entrega:</strong> ${esc(p.entrega_logradouro || "")} ${esc(p.entrega_numero || "")}, ${esc(p.entrega_cidade || "")}-${esc(p.entrega_uf || "")}</p>
      <p><strong>Total:</strong> ${fmt(p.valor_total)} ${p.valor_taxa_pedido > 0 ? `(incl. taxa ${fmt(p.valor_taxa_pedido)})` : ""}</p>
      <p>${badge(p.status)}</p>
      ${p.codigo_rastreio ? `<p><strong>Rastreio:</strong> ${esc(p.codigo_rastreio)}</p>` : ""}
      <table class="PdFn_Table" style="margin-top:1rem"><thead><tr><th>Produto</th><th>Qtd</th><th>Drop</th></tr></thead>
      <tbody>${(p.itens || []).map((i) => `<tr><td>${esc(i.nome_produto)}</td><td>${i.quantidade}</td><td>${fmt(i.subtotal_drop)}</td></tr>`).join("")}</tbody></table>`;
    renderAcoes(p);
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
