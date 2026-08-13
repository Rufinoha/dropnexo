(function () {
  const LABEL = {
    importado: "Aguardando pagamento",
    aguardando_pagamento: "Aguardando pagamento",
    aguardando_confirmacao: "Aguardando aprovação",
    pago: "Pagamento confirmado",
    cancelado: "Cancelado",
    em_expedicao: "Em expedição",
    entregue: "Entregue",
  };
  const stV = (p) => p?.status_vendedor || p?.status || "";
  const tbody = document.getElementById("pd_fn_tbody");
  const vazio = document.getElementById("pd_fn_vazio");
  const modal = document.getElementById("pd_fn_modal");
  const body = document.getElementById("pd_fn_body");
  const titulo = document.getElementById("pd_fn_titulo");
  const foot = document.getElementById("pd_fn_foot");
  let pedidoAtual = null;

  const fmt = (v) => Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const esc = (s) => String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/"/g, "&quot;");

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
        <td><strong>${esc(p.numero)}</strong>${p.origem === "bling" ? ' <small>(Bling)</small>' : p.origem === "mercado_livre" ? ' <small>(Mercado Livre)</small>' : p.origem === "tiktok" ? ' <small>(TikTok)</small>' : p.origem === "amazon" ? ' <small>(Amazon)</small>' : ""}</td>
        <td>${esc(p.vendedor_nome || "")}</td>
        <td>${esc(p.cliente_nome || "")}</td>
        <td>${fmt(p.valor_total)}</td>
        <td>${badge(stV(p))}</td>
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
    const aguardaConf =
      stV(p) === "aguardando_confirmacao" ||
      (stV(p) === "aguardando_pagamento" &&
        p.meio_pagamento === "pix_manual" &&
        (p.status_pagamento === "comprovante_enviado" || comprovantes.length));

    if (aguardaConf && p.meio_pagamento === "pix_manual") {
      const links = comprovantes
        .map(
          (a) =>
            `<li><a href="/fornecedor/pedidos/anexos/arquivo?caminho=${encodeURIComponent(a.caminho)}" target="_blank" rel="noopener">${esc(a.nome_original)}</a></li>`
        )
        .join("");
      foot.innerHTML = `
        <div class="PdFn_PayValid">
          <div class="PdFn_PayValidHead">
            <span class="PdFn_PayValidMark" aria-hidden="true">PIX</span>
            <div>
              <strong>Validar pagamento</strong>
              <p>O vendedor enviou o comprovante. Confirme só depois de verificar o crédito na sua conta.</p>
            </div>
          </div>
          <ul class="PdFn_PayValidList">${links || "<li>Comprovante pendente de anexo</li>"}</ul>
          <div class="PdFn_PayValidBtns">
            <button type="button" class="Cl_botaoprimario" id="pd_fn_btn_conf_pix">Confirmar pagamento</button>
            <button type="button" class="Cl_BtnExcluir" id="pd_fn_btn_rej_pix">Rejeitar comprovante</button>
          </div>
        </div>`;
      document.getElementById("pd_fn_btn_conf_pix")?.addEventListener("click", () => confirmarPix(p.id));
      document.getElementById("pd_fn_btn_rej_pix")?.addEventListener("click", () => rejeitarPix(p.id));
      return;
    }

    if (stV(p) === "pago") {
      foot.innerHTML = `
        <div class="PdFn_PayValid is-ok">
          <strong>Pagamento confirmado</strong>
          <p>Este pedido está liberado. Anexe etiqueta/NF pelo fluxo do vendedor quando necessário.</p>
        </div>`;
    } else if (stV(p) === "aguardando_pagamento") {
      foot.innerHTML = `
        <div class="PdFn_PayValid is-wait">
          <strong>Aguardando pagamento</strong>
          <p>O vendedor ainda não enviou o comprovante PIX.</p>
        </div>`;
    }
  }

  async function confirmarPix(id) {
    const conf = window.Swal
      ? await Swal.fire({
          icon: "question",
          title: "Confirmar pagamento?",
          html: "Só confirme se o PIX já caiu na sua conta. Isso libera o pedido como <strong>Pagamento confirmado</strong>.",
          showCancelButton: true,
          confirmButtonText: "Sim, confirmar",
          cancelButtonText: "Cancelar",
          confirmButtonColor: "#021F81",
        })
      : { isConfirmed: confirm("Confirmar pagamento?") };
    if (!conf.isConfirmed) return;

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
    let motivo = "";
    if (window.Swal) {
      const r = await Swal.fire({
        title: "Rejeitar comprovante",
        width: 520,
        html: `
          <div class="PdFn_RejeitaSwal">
            <div class="PdFn_RejeitaSwal__info">
              <p class="PdFn_RejeitaSwal__lead">O que acontece</p>
              <ul>
                <li>O pedido volta para <strong>Aguardando pagamento</strong>.</li>
                <li>O vendedor recebe o motivo e pode enviar outro comprovante.</li>
                <li>Nada é marcado como pago até você confirmar.</li>
              </ul>
            </div>
            <label class="PdFn_RejeitaSwal__label" for="pd_fn_motivo_rej">Motivo da rejeição <span>*</span></label>
            <textarea id="pd_fn_motivo_rej" class="PdFn_RejeitaSwal__textarea" rows="4" placeholder="Ex.: valor divergente, comprovante ilegível, PIX não identificado…"></textarea>
          </div>`,
        icon: "warning",
        showCancelButton: true,
        confirmButtonText: "Rejeitar comprovante",
        cancelButtonText: "Voltar",
        confirmButtonColor: "#b91c1c",
        cancelButtonColor: "#94a3b8",
        focusConfirm: false,
        customClass: {
          popup: "PdFn_RejeitaPopup",
          title: "PdFn_RejeitaTitle",
          htmlContainer: "PdFn_RejeitaHtml",
          actions: "PdFn_RejeitaActions",
        },
        preConfirm: () => {
          const txt = (document.getElementById("pd_fn_motivo_rej")?.value || "").trim();
          if (txt.length < 5) {
            Swal.showValidationMessage("Informe o motivo com pelo menos 5 caracteres.");
            return false;
          }
          return txt;
        },
      });
      if (!r.isConfirmed) return;
      motivo = r.value;
    } else {
      motivo = (prompt("Motivo da rejeição (obrigatório):") || "").trim();
      if (motivo.length < 5) {
        alert("Informe o motivo com pelo menos 5 caracteres.");
        return;
      }
    }

    const resp = await fetch(`/fornecedor/pedidos/${id}/pagamento/rejeitar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motivo }),
    });
    const j = await resp.json();
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
    const docs = (p.anexos || []).filter((a) => ["etiqueta", "nf", "declaracao"].includes(a.tipo));
    const docsHtml = docs.length
      ? `<ul style="margin:0.35rem 0 0;padding-left:1.1rem">${docs
          .map(
            (a) =>
              `<li><a href="/fornecedor/pedidos/anexos/arquivo?caminho=${encodeURIComponent(a.caminho)}" target="_blank" rel="noopener">${esc(a.tipo)} — ${esc(a.nome_original)}</a></li>`
          )
          .join("")}</ul>`
      : `<p class="PdFn_Hint">Sem etiqueta/NF/declaração anexadas.</p>`;
    body.innerHTML = `
      <p><strong>Vendedor:</strong> ${esc(p.vendedor_nome || "")}</p>
      <p><strong>Cliente:</strong> ${esc(p.cliente_nome)} — ${esc(p.cliente_telefone || "")}</p>
      <p><strong>Entrega:</strong> ${esc(p.entrega_logradouro || "")} ${esc(p.entrega_numero || "")}, ${esc(p.entrega_cidade || "")}-${esc(p.entrega_uf || "")}</p>
      <p><strong>Total:</strong> ${fmt(p.valor_total)} ${p.valor_taxa_pedido > 0 ? `(incl. taxa ${fmt(p.valor_taxa_pedido)})` : ""}</p>
      <p>${badge(stV(p))}</p>
      ${p.codigo_rastreio ? `<p><strong>Rastreio:</strong> ${esc(p.codigo_rastreio)}</p>` : ""}
      <div style="margin-top:0.85rem"><strong>Documentos de frete</strong>${docsHtml}</div>
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
