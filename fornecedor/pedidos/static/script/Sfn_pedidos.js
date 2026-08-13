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
  const ORIGEM = {
    mercado_livre: "Mercado Livre",
    bling: "Bling",
    tiktok: "TikTok",
    amazon: "Amazon",
    manual: "Manual",
  };

  const stV = (p) => p?.status_vendedor || p?.status || "";
  const listaEl = document.getElementById("pd_fn_lista");
  const vazio = document.getElementById("pd_fn_vazio");
  const modal = document.getElementById("pd_fn_modal");
  const body = document.getElementById("pd_fn_body");
  const titulo = document.getElementById("pd_fn_titulo");
  const kicker = document.getElementById("pd_fn_kicker");
  const foot = document.getElementById("pd_fn_foot");
  const buscaEl = document.getElementById("pd_fn_busca");

  let todosPedidos = [];
  let filtroStatus = "";
  let pedidoAtual = null;

  const fmt = (v) =>
    Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const esc = (s) =>
    String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");

  function badge(st) {
    return `<span class="PdFn_Badge PdFn_Badge--${esc(st)}">${esc(LABEL[st] || st)}</span>`;
  }

  function origemLabel(origem) {
    return ORIGEM[origem] || (origem ? String(origem) : "");
  }

  function thumbsHtml(p) {
    const preview = p.itens_preview || p.itens || [];
    if (!preview.length) {
      return `<div class="PdFn_Thumbs"><span class="PdFn_Thumb PdFn_Thumb--empty">SEM FOTO</span></div>`;
    }
    const shown = preview.slice(0, 3);
    const extra = Math.max(0, (p.itens_preview || p.itens || []).length - shown.length);
    const imgs = shown
      .map((i, idx) => {
        const url = i.imagem_url || "";
        if (url) {
          return `<img class="PdFn_Thumb" src="${esc(url)}" alt="" loading="lazy" style="z-index:${3 - idx}" />`;
        }
        return `<span class="PdFn_Thumb PdFn_Thumb--empty" style="z-index:${3 - idx}">PROD</span>`;
      })
      .join("");
    const more = extra
      ? `<span class="PdFn_Thumb PdFn_Thumb--more" style="z-index:0">+${extra}</span>`
      : "";
    return `<div class="PdFn_Thumbs">${imgs}${more}</div>`;
  }

  function produtoResumo(p) {
    const itens = p.itens_preview || p.itens || [];
    if (!itens.length) return "Sem itens";
    const primeiro = itens[0].nome_produto || "Produto";
    const qtd = p.qtd_itens || itens.reduce((s, i) => s + (i.quantidade || 0), 0);
    if (itens.length === 1) return `${primeiro} · ${qtd} un.`;
    return `${primeiro} +${itens.length - 1} · ${qtd} un.`;
  }

  function atualizarStats(rows) {
    const counts = {
      aguardando_pagamento: 0,
      aguardando_confirmacao: 0,
      pago: 0,
    };
    rows.forEach((p) => {
      const st = stV(p);
      if (st === "importado" || st === "aguardando_pagamento") counts.aguardando_pagamento += 1;
      else if (st === "aguardando_confirmacao") counts.aguardando_confirmacao += 1;
      else if (st === "pago") counts.pago += 1;
    });
    document.querySelectorAll("[data-stat]").forEach((el) => {
      const key = el.getAttribute("data-stat");
      const val = el.querySelector(".PdFn_StatVal");
      if (val && key in counts) val.textContent = String(counts[key]);
    });
  }

  function pedidosFiltrados() {
    const q = (buscaEl?.value || "").trim().toLowerCase();
    return todosPedidos.filter((p) => {
      const st = stV(p);
      if (filtroStatus) {
        if (filtroStatus === "aguardando_pagamento") {
          if (!["aguardando_pagamento", "importado"].includes(st)) return false;
        } else if (st !== filtroStatus) return false;
      }
      if (!q) return true;
      const blob = [
        p.numero,
        p.vendedor_nome,
        p.cliente_nome,
        ...(p.itens_preview || []).map((i) => i.nome_produto),
        ...(p.itens_preview || []).map((i) => i.sku),
      ]
        .join(" ")
        .toLowerCase();
      return blob.includes(q);
    });
  }

  function renderLista() {
    if (!listaEl) return;
    const rows = pedidosFiltrados();
    if (!rows.length) {
      listaEl.innerHTML = "";
      if (vazio) vazio.hidden = false;
      return;
    }
    if (vazio) vazio.hidden = true;
    listaEl.innerHTML = rows
      .map((p, idx) => {
        const st = stV(p);
        const urgent = st === "aguardando_confirmacao";
        const data = p.criado_em
          ? new Date(p.criado_em).toLocaleDateString("pt-BR", {
              day: "2-digit",
              month: "short",
            })
          : "—";
        const orig = origemLabel(p.origem);
        return `
      <button type="button" class="PdFn_Card${urgent ? " PdFn_Card--urgent" : ""}" data-id="${p.id}" style="animation-delay:${Math.min(idx, 8) * 0.04}s">
        ${thumbsHtml(p)}
        <div class="PdFn_CardMain">
          <div class="PdFn_CardTop">
            <span class="PdFn_CardNum">${esc(p.numero)}</span>
            ${orig ? `<span class="PdFn_Origem">${esc(orig)}</span>` : ""}
            ${badge(st)}
          </div>
          <p class="PdFn_CardMeta"><strong>${esc(p.vendedor_nome || "Vendedor")}</strong> · ${esc(p.cliente_nome || "Cliente")} · ${esc(data)}</p>
          <p class="PdFn_CardProd">${esc(produtoResumo(p))}</p>
        </div>
        <div class="PdFn_CardSide">
          <span class="PdFn_CardTotal">${fmt(p.valor_total)}</span>
          <span class="PdFn_CardCta">${urgent ? "Validar PIX →" : "Abrir →"}</span>
        </div>
      </button>`;
      })
      .join("");

    listaEl.querySelectorAll("[data-id]").forEach((b) => {
      b.addEventListener("click", () => abrir(+b.dataset.id));
    });
  }

  async function carregar() {
    const r = await fetch("/fornecedor/pedidos/dados", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    todosPedidos = j.pedidos || [];
    atualizarStats(todosPedidos);
    renderLista();
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
              <p>Confirme só depois de verificar o crédito na sua conta.</p>
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
          <p>Pedido liberado. Pronto para seguir com a expedição quando os documentos estiverem ok.</p>
        </div>`;
    } else if (["aguardando_pagamento", "importado"].includes(stV(p))) {
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

  function itemLinha(i) {
    const img = i.imagem_url
      ? `<img class="PdFn_ItemImg" src="${esc(i.imagem_url)}" alt="" loading="lazy" />`
      : `<div class="PdFn_ItemImg PdFn_ItemImg--ph">SEM FOTO</div>`;
    return `
      <article class="PdFn_Item">
        ${img}
        <div>
          <p class="PdFn_ItemName">${esc(i.nome_produto || "Produto")}</p>
          <p class="PdFn_ItemSku">${esc(i.sku || "—")}</p>
        </div>
        <div class="PdFn_ItemRight">
          <span class="PdFn_ItemQtd">${int(i.quantidade)} un.</span>
          <span class="PdFn_ItemVal">${fmt(i.subtotal_drop)}</span>
        </div>
      </article>`;
  }

  function int(n) {
    return Number(n || 0);
  }

  async function abrir(id) {
    const r = await fetch(`/fornecedor/pedidos/${id}`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const p = j.pedido;
    pedidoAtual = p;
    if (titulo) titulo.textContent = p.numero || `Pedido #${id}`;
    if (kicker) {
      const orig = origemLabel(p.origem);
      kicker.textContent = orig ? `Pedido · ${orig}` : "Pedido";
    }

    const docs = (p.anexos || []).filter((a) =>
      ["etiqueta", "nf", "declaracao"].includes(a.tipo)
    );
    const docsHtml = docs.length
      ? `<ul class="PdFn_Docs">${docs
          .map(
            (a) =>
              `<li><a href="/fornecedor/pedidos/anexos/arquivo?caminho=${encodeURIComponent(a.caminho)}" target="_blank" rel="noopener">${esc(a.tipo)} — ${esc(a.nome_original)}</a></li>`
          )
          .join("")}</ul>`
      : `<p class="PdFn_Hint">Sem etiqueta / NF / declaração anexadas.</p>`;

    const end = [
      p.entrega_logradouro,
      p.entrega_numero,
      p.entrega_bairro,
      p.entrega_cidade && p.entrega_uf ? `${p.entrega_cidade}/${p.entrega_uf}` : p.entrega_cidade || p.entrega_uf,
      p.entrega_cep,
    ]
      .filter(Boolean)
      .join(", ");

    body.innerHTML = `
      <div class="PdFn_Grid">
        <div class="PdFn_Panel">
          <p class="PdFn_PanelTitle">Situação</p>
          <p>${badge(stV(p))}</p>
          <p style="margin-top:0.55rem"><strong>Total</strong> ${fmt(p.valor_total)}${
            p.valor_taxa_pedido > 0 ? ` <span class="PdFn_Hint">(taxa ${fmt(p.valor_taxa_pedido)})</span>` : ""
          }</p>
        </div>
        <div class="PdFn_Panel">
          <p class="PdFn_PanelTitle">Rede</p>
          <p><strong>Vendedor</strong><br>${esc(p.vendedor_nome || "—")}</p>
          <p style="margin-top:0.45rem"><strong>Cliente</strong><br>${esc(p.cliente_nome || "—")}${
            p.cliente_telefone ? ` · ${esc(p.cliente_telefone)}` : ""
          }</p>
        </div>
        <div class="PdFn_Panel PdFn_Panel--wide">
          <p class="PdFn_PanelTitle">Entrega</p>
          <p>${esc(end || "Endereço não informado")}</p>
          ${p.codigo_rastreio ? `<p style="margin-top:0.4rem"><strong>Rastreio:</strong> ${esc(p.codigo_rastreio)}</p>` : ""}
        </div>
        <div class="PdFn_Panel PdFn_Panel--wide">
          <p class="PdFn_PanelTitle">Produtos</p>
          <div class="PdFn_Itens">${(p.itens || []).map(itemLinha).join("") || '<p class="PdFn_Hint">Sem itens.</p>'}</div>
        </div>
        <div class="PdFn_Panel PdFn_Panel--wide">
          <p class="PdFn_PanelTitle">Documentos de frete</p>
          ${docsHtml}
        </div>
      </div>`;
    renderAcoes(p);
    modal.hidden = false;
  }

  document.getElementById("pd_fn_chips")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-status]");
    if (!btn) return;
    filtroStatus = btn.getAttribute("data-status") || "";
    document.querySelectorAll("#pd_fn_chips .PdFn_Chip").forEach((c) => {
      const on = c === btn;
      c.classList.toggle("is-active", on);
      c.setAttribute("aria-selected", on ? "true" : "false");
    });
    renderLista();
  });

  let buscaTimer = null;
  buscaEl?.addEventListener("input", () => {
    clearTimeout(buscaTimer);
    buscaTimer = setTimeout(renderLista, 160);
  });

  document.getElementById("pd_fn_fechar")?.addEventListener("click", () => {
    modal.hidden = true;
  });
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) modal.hidden = true;
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && !modal.hidden) modal.hidden = true;
  });

  carregar();
})();
