(function () {
  const API = "/armazem/pedidos";
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
  const headMeta = document.getElementById("pd_fn_head_meta");
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
  const int = (n) => Number(n || 0);

  function badge(st) {
    return `<span class="PdFn_Badge PdFn_Badge--${esc(st)}">${esc(LABEL[st] || st)}</span>`;
  }

  function origemLabel(origem) {
    return ORIGEM[origem] || (origem ? String(origem) : "");
  }

  function setModalOpen(open) {
    if (!modal) return;
    modal.hidden = !open;
    document.body.classList.toggle("PdFn_ModalOpen", !!open);
  }

  function thumbsHtml(p) {
    const preview = p.itens_preview || p.itens || [];
    if (!preview.length) {
      return `<div class="PdFn_Thumbs"><span class="PdFn_Thumb PdFn_Thumb--empty">—</span></div>`;
    }
    const first = preview[0];
    const extra = Math.max(0, preview.length - 1);
    const url = first.imagem_url || "";
    const img = url
      ? `<img class="PdFn_Thumb" src="${esc(url)}" alt="" loading="lazy" />`
      : `<span class="PdFn_Thumb PdFn_Thumb--empty">PROD</span>`;
    const more = extra
      ? `<span class="PdFn_Thumb PdFn_Thumb--more">+${extra}</span>`
      : "";
    return `<div class="PdFn_Thumbs">${img}${more}</div>`;
  }

  function produtoResumo(p) {
    const itens = p.itens_preview || p.itens || [];
    if (!itens.length) return "Sem itens";
    const primeiro = itens[0].nome_produto || "Produto";
    const qtd = p.qtd_itens || itens.reduce((s, i) => s + (i.quantidade || 0), 0);
    if (itens.length === 1) return `${primeiro} · ${qtd} un.`;
    return `${primeiro} +${itens.length - 1} · ${qtd} un.`;
  }

  function ctaLista(st) {
    if (st === "aguardando_confirmacao") return "Validar PIX";
    if (st === "pago") return "Separar";
    if (st === "em_expedicao") return "Acompanhar";
    return "Abrir";
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
      .map((p) => {
        const st = stV(p);
        const urgent = st === "aguardando_confirmacao";
        const ready = st === "pago";
        const data = p.criado_em
          ? new Date(p.criado_em).toLocaleDateString("pt-BR", {
              day: "2-digit",
              month: "short",
            })
          : "—";
        const orig = origemLabel(p.origem);
        const cardCls = [
          "PdFn_Card",
          urgent ? "PdFn_Card--urgent" : "",
          ready ? "PdFn_Card--ready" : "",
        ]
          .filter(Boolean)
          .join(" ");
        return `
      <button type="button" class="${cardCls}" data-id="${p.id}">
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
          <span class="PdFn_CardCta">${esc(ctaLista(st))} →</span>
        </div>
      </button>`;
      })
      .join("");

    listaEl.querySelectorAll("[data-id]").forEach((b) => {
      b.addEventListener("click", () => abrir(+b.dataset.id));
    });
  }

  async function carregar() {
    const r = await fetch(`${API}/dados`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    todosPedidos = j.pedidos || [];
    atualizarStats(todosPedidos);
    renderLista();
  }

  function docsInfo(p) {
    const anexos = p.anexos || [];
    const etq = anexos.find((a) => a.tipo === "etiqueta") || null;
    const fiscal =
      anexos.find((a) => a.tipo === "nf") ||
      anexos.find((a) => a.tipo === "declaracao") ||
      null;
    const comprovantes = anexos.filter((a) => a.tipo === "comprovante_pix");
    return {
      etq,
      fiscal,
      comprovantes,
      ok: !!(etq && fiscal),
    };
  }

  function anexoHref(a) {
    return `${API}/anexos/arquivo?caminho=${encodeURIComponent(a.caminho)}`;
  }

  function stepRail(st) {
    const payDone = !["aguardando_pagamento", "importado", "aguardando_confirmacao"].includes(st);
    const payActive = ["aguardando_pagamento", "importado", "aguardando_confirmacao"].includes(st);
    const packDone = ["em_expedicao", "entregue"].includes(st);
    const packActive = st === "pago";
    const shipDone = st === "entregue";
    const shipActive = st === "em_expedicao";

    const cls = (done, active) =>
      `PdFn_Step${done ? " is-done" : ""}${active ? " is-active" : ""}`;

    return `
      <ol class="PdFn_Rail" aria-label="Etapas do pedido">
        <li class="${cls(payDone, payActive)}"><span>1</span><em>Pagamento</em></li>
        <li class="${cls(packDone, packActive)}"><span>2</span><em>Separar</em></li>
        <li class="${cls(shipDone, shipActive)}"><span>3</span><em>Expedir</em></li>
      </ol>`;
  }

  function checkItem(ok, label, detail, href) {
    if (ok && href) {
      return `
        <a class="PdFn_Check PdFn_Check--ok" href="${href}" target="_blank" rel="noopener">
          <span class="PdFn_CheckMark" aria-hidden="true">✓</span>
          <div>
            <strong>${esc(label)}</strong>
            <p>${esc(detail || "Abrir arquivo")}</p>
          </div>
          <span class="PdFn_CheckGo">Abrir</span>
        </a>`;
    }
    if (ok) {
      return `
        <div class="PdFn_Check PdFn_Check--ok">
          <span class="PdFn_CheckMark" aria-hidden="true">✓</span>
          <div>
            <strong>${esc(label)}</strong>
            <p>${esc(detail || "Pronto")}</p>
          </div>
        </div>`;
    }
    return `
      <div class="PdFn_Check PdFn_Check--miss">
        <span class="PdFn_CheckMark" aria-hidden="true">!</span>
        <div>
          <strong>${esc(label)}</strong>
          <p>${esc(detail || "Ainda não anexado")}</p>
        </div>
      </div>`;
  }

  function docsChecklistHtml(p) {
    const { etq, fiscal, comprovantes, ok } = docsInfo(p);
    const fiscalTitulo = fiscal?.tipo === "declaracao" ? "Declaração" : "Nota fiscal";
    const st = stV(p);
    const pixNeeded = ["aguardando_confirmacao", "aguardando_pagamento", "importado"].includes(st);

    let html = `
      <div class="PdFn_Checks">
        ${checkItem(!!etq, "Etiqueta de frete", etq?.nome_original || "Aguardando etiqueta", etq ? anexoHref(etq) : null)}
        ${checkItem(!!fiscal, fiscalTitulo, fiscal?.nome_original || "Aguardando NF ou declaração", fiscal ? anexoHref(fiscal) : null)}`;

    if (comprovantes.length || pixNeeded) {
      const c = comprovantes[0];
      html += checkItem(
        !!c,
        "Comprovante PIX",
        c?.nome_original || "Sem comprovante anexado",
        c ? anexoHref(c) : null
      );
    }

    html += `</div>
      <p class="PdFn_DocsHint ${ok ? "is-ok" : ""}">${
        ok
          ? "Documentos prontos — liberado para expedição."
          : "Falta etiqueta e/ou NF. O vendedor anexa; você só precisa conferir."
      }</p>`;
    return html;
  }

  function itemLinha(i) {
    const img = i.imagem_url
      ? `<img class="PdFn_ItemImg" src="${esc(i.imagem_url)}" alt="" loading="lazy" />`
      : `<div class="PdFn_ItemImg PdFn_ItemImg--ph">SEM FOTO</div>`;
    const qtd = int(i.quantidade);
    return `
      <article class="PdFn_Item">
        <div class="PdFn_ItemQtdBig" title="Quantidade">${qtd}<small>un</small></div>
        ${img}
        <div class="PdFn_ItemInfo">
          <p class="PdFn_ItemName">${esc(i.nome_produto || "Produto")}</p>
          <p class="PdFn_ItemSku">SKU ${esc(i.sku || "—")}</p>
        </div>
        <div class="PdFn_ItemRight">
          <span class="PdFn_ItemVal">${fmt(i.subtotal_drop)}</span>
        </div>
      </article>`;
  }

  function enderecoTexto(p) {
    return [
      p.entrega_logradouro,
      p.entrega_numero,
      p.entrega_complemento,
      p.entrega_bairro,
      p.entrega_cidade && p.entrega_uf ? `${p.entrega_cidade}/${p.entrega_uf}` : p.entrega_cidade || p.entrega_uf,
      p.entrega_cep ? `CEP ${p.entrega_cep}` : "",
    ]
      .filter(Boolean)
      .join(", ");
  }

  async function copiarTexto(texto, btn) {
    try {
      await navigator.clipboard.writeText(texto);
      if (btn) {
        const prev = btn.textContent;
        btn.textContent = "Copiado!";
        btn.classList.add("is-copied");
        setTimeout(() => {
          btn.textContent = prev;
          btn.classList.remove("is-copied");
        }, 1400);
      }
    } catch (_) {
      if (window.Swal) Swal.fire("Atenção", "Não foi possível copiar.", "info");
    }
  }

  function renderAcoes(p) {
    if (!foot) return;
    foot.innerHTML = "";
    const { comprovantes, ok: docsOk } = docsInfo(p);
    const temComprovante = comprovantes.length > 0;
    const st = stV(p);
    const meio = String(p.meio_pagamento || "").toLowerCase();
    const ehPixManual =
      meio === "pix_manual" ||
      !!(p.pix_manual_txid || "").trim() ||
      String(p.status_pagamento || "").toLowerCase() === "comprovante_enviado";
    const podeConfirmarPix =
      ehPixManual &&
      ["aguardando_pagamento", "importado", "aguardando_confirmacao"].includes(st);

    if (podeConfirmarPix) {
      const links = comprovantes
        .map(
          (a) =>
            `<li><a href="${anexoHref(a)}" target="_blank" rel="noopener">${esc(a.nome_original)}</a></li>`
        )
        .join("");
      const avisoSemComp = temComprovante
        ? ""
        : `<p class="PdFn_PayValidHint">Sem comprovante anexado — você pode confirmar se já viu o crédito no banco.</p>`;
      const btnRejeitar = temComprovante
        ? `<button type="button" class="Cl_BtnExcluir" id="pd_fn_btn_rej_pix">Rejeitar comprovante</button>`
        : "";
      foot.innerHTML = `
        <div class="PdFn_PayValid">
          <div class="PdFn_PayValidHead">
            <span class="PdFn_PayValidMark" aria-hidden="true">PIX</span>
            <div>
              <strong>Validar pagamento</strong>
              <p>Confirme só depois de verificar o crédito na sua conta.</p>
            </div>
          </div>
          <ul class="PdFn_PayValidList">${links || "<li>Nenhum comprovante anexado pelo vendedor</li>"}</ul>
          ${avisoSemComp}
          <div class="PdFn_PayValidBtns">
            <button type="button" class="Cl_botaoprimario" id="pd_fn_btn_conf_pix">Confirmar pagamento</button>
            ${btnRejeitar}
          </div>
        </div>`;
      document
        .getElementById("pd_fn_btn_conf_pix")
        ?.addEventListener("click", () => confirmarPix(p.id, temComprovante));
      document.getElementById("pd_fn_btn_rej_pix")?.addEventListener("click", () => rejeitarPix(p.id));
      return;
    }

    if (st === "pago") {
      foot.innerHTML = `
        <div class="PdFn_ShipBar">
          <div class="PdFn_ShipFields">
            <label>
              <span>Rastreio <em>(opcional)</em></span>
              <input type="text" id="pd_fn_rastreio" placeholder="Código de rastreio" autocomplete="off" value="${esc(p.codigo_rastreio || "")}" />
            </label>
            <label>
              <span>Transportadora <em>(opcional)</em></span>
              <input type="text" id="pd_fn_transp" placeholder="Ex.: Correios, Jadlog…" autocomplete="off" value="${esc(p.transportadora || "")}" />
            </label>
          </div>
          <div class="PdFn_ShipActions">
            <p class="PdFn_ShipHint">${
              docsOk
                ? "Documentos ok. Ao expedir, o estoque é baixado."
                : "Ainda faltam documentos — a expedição só libera com etiqueta + NF."
            }</p>
            <button type="button" class="Cl_botaoprimario" id="pd_fn_btn_expedir" ${docsOk ? "" : "disabled"}>Marcar em expedição</button>
          </div>
        </div>`;
      document.getElementById("pd_fn_btn_expedir")?.addEventListener("click", () => expedir(p.id));
      return;
    }

    if (st === "em_expedicao") {
      foot.innerHTML = `
        <div class="PdFn_PayValid is-ok PdFn_ShipDone">
          <div>
            <strong>Em expedição</strong>
            <p>${
              p.codigo_rastreio
                ? `Rastreio: <strong>${esc(p.codigo_rastreio)}</strong>`
                : "Pedido separado e estoque baixado."
            }</p>
          </div>
          <button type="button" class="Cl_botaoprimario" id="pd_fn_btn_entregue">Marcar entregue</button>
        </div>`;
      document.getElementById("pd_fn_btn_entregue")?.addEventListener("click", () => marcarEntregue(p.id));
      return;
    }

    if (st === "entregue") {
      foot.innerHTML = `
        <div class="PdFn_PayValid is-ok">
          <strong>Pedido entregue</strong>
          <p>Fluxo concluído neste pedido.</p>
        </div>`;
    }
  }

  async function confirmarPix(id, temComprovante) {
    const extra = temComprovante
      ? ""
      : "<br><br>O vendedor <strong>não anexou comprovante</strong>. Confirme apenas se o PIX já apareceu na sua conta.";
    const conf = window.Swal
      ? await Swal.fire({
          icon: "question",
          title: "Confirmar pagamento?",
          html:
            "Só confirme se o PIX já caiu na sua conta. Isso libera o pedido como <strong>Pagamento confirmado</strong>." +
            extra,
          showCancelButton: true,
          confirmButtonText: "Sim, confirmar",
          cancelButtonText: "Cancelar",
          confirmButtonColor: "#021F81",
        })
      : { isConfirmed: confirm("Confirmar pagamento?") };
    if (!conf.isConfirmed) return;

    const r = await fetch(`${API}/${id}/pagamento/confirmar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const j = await r.json();
    if (window.Swal) await Swal.fire(j.success ? "Pago" : "Erro", j.message, j.success ? "success" : "error");
    if (j.success) {
      await carregar();
      await abrir(id);
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

    const resp = await fetch(`${API}/${id}/pagamento/rejeitar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ motivo }),
    });
    const j = await resp.json();
    if (window.Swal) await Swal.fire(j.success ? "Rejeitado" : "Erro", j.message, j.success ? "info" : "error");
    if (j.success) abrir(id);
  }

  async function expedir(id) {
    const rastreio = (document.getElementById("pd_fn_rastreio")?.value || "").trim();
    const transp = (document.getElementById("pd_fn_transp")?.value || "").trim();
    const conf = window.Swal
      ? await Swal.fire({
          icon: "question",
          title: "Marcar em expedição?",
          html: "Isso <strong>baixa o estoque</strong> e avança o pedido para <strong>Em expedição</strong>.",
          showCancelButton: true,
          confirmButtonText: "Sim, expedir",
          cancelButtonText: "Cancelar",
          confirmButtonColor: "#021F81",
        })
      : { isConfirmed: confirm("Marcar em expedição? Estoque será baixado.") };
    if (!conf.isConfirmed) return;

    const r = await fetch(`${API}/${id}/expedir`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        codigo_rastreio: rastreio || null,
        transportadora: transp || null,
      }),
    });
    const j = await r.json();
    if (window.Swal) await Swal.fire(j.success ? "Expedido" : "Erro", j.message, j.success ? "success" : "error");
    if (j.success) {
      await carregar();
      await abrir(id);
    }
  }

  async function marcarEntregue(id) {
    const conf = window.Swal
      ? await Swal.fire({
          icon: "question",
          title: "Marcar como entregue?",
          showCancelButton: true,
          confirmButtonText: "Sim, entregue",
          cancelButtonText: "Cancelar",
          confirmButtonColor: "#021F81",
        })
      : { isConfirmed: confirm("Marcar como entregue?") };
    if (!conf.isConfirmed) return;

    const r = await fetch(`${API}/${id}/entregue`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const j = await r.json();
    if (window.Swal) await Swal.fire(j.success ? "Entregue" : "Erro", j.message, j.success ? "success" : "error");
    if (j.success) {
      await carregar();
      await abrir(id);
    }
  }

  async function abrir(id) {
    const r = await fetch(`${API}/${id}`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const p = j.pedido;
    pedidoAtual = p;
    const st = stV(p);
    const orig = origemLabel(p.origem);

    if (titulo) titulo.textContent = p.numero || `Pedido #${id}`;
    if (kicker) kicker.textContent = orig ? `Pedido · ${orig}` : "Pedido recebido";
    if (headMeta) {
      headMeta.innerHTML = `${badge(st)} <span class="PdFn_HeadTotal">${fmt(p.valor_total)}</span>`;
    }

    const end = enderecoTexto(p);
    const tel = p.cliente_telefone ? String(p.cliente_telefone) : "";

    body.innerHTML = `
      ${stepRail(st)}
      <div class="PdFn_Ops">
        <section class="PdFn_OpsMain">
          <div class="PdFn_Block">
            <div class="PdFn_BlockHead">
              <p class="PdFn_PanelTitle">Separar</p>
              <span class="PdFn_BlockCount">${int(p.qtd_itens || (p.itens || []).reduce((s, i) => s + int(i.quantidade), 0))} un.</span>
            </div>
            <div class="PdFn_Itens">${(p.itens || []).map(itemLinha).join("") || '<p class="PdFn_Hint">Sem itens.</p>'}</div>
          </div>

          <div class="PdFn_Block">
            <div class="PdFn_BlockHead">
              <p class="PdFn_PanelTitle">Entrega</p>
              <button type="button" class="PdFn_CopyBtn" id="pd_fn_copy_end" ${end ? "" : "disabled"}>Copiar endereço</button>
            </div>
            <div class="PdFn_Addr">
              <p class="PdFn_AddrName">${esc(p.cliente_nome || "Cliente")}${
                tel ? ` · <a href="tel:${esc(tel.replace(/\s/g, ""))}">${esc(tel)}</a>` : ""
              }</p>
              <p class="PdFn_AddrLine">${esc(end || "Endereço não informado")}</p>
              ${
                p.codigo_rastreio
                  ? `<p class="PdFn_AddrTrack"><strong>Rastreio</strong> ${esc(p.codigo_rastreio)}</p>`
                  : ""
              }
            </div>
          </div>
        </section>

        <aside class="PdFn_OpsSide">
          <div class="PdFn_Block">
            <p class="PdFn_PanelTitle">Rede</p>
            <dl class="PdFn_Meta">
              <div><dt>Vendedor</dt><dd>${esc(p.vendedor_nome || "—")}</dd></div>
              <div><dt>Total</dt><dd>${fmt(p.valor_total)}${
                p.valor_taxa_pedido > 0
                  ? ` <span class="PdFn_Hint">(taxa ${fmt(p.valor_taxa_pedido)})</span>`
                  : ""
              }</dd></div>
            </dl>
          </div>
          <div class="PdFn_Block">
            <p class="PdFn_PanelTitle">Documentos</p>
            ${docsChecklistHtml(p)}
          </div>
        </aside>
      </div>`;

    document.getElementById("pd_fn_copy_end")?.addEventListener("click", (e) => {
      copiarTexto(end, e.currentTarget);
    });

    renderAcoes(p);
    setModalOpen(true);
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

  document.getElementById("pd_fn_fechar")?.addEventListener("click", () => setModalOpen(false));
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) setModalOpen(false);
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && !modal.hidden) setModalOpen(false);
  });

  carregar();
})();
