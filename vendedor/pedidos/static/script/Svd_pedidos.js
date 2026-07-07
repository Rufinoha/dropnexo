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
    itens: document.getElementById("pd_itens"),
    itensVazio: document.getElementById("pd_itensVazio"),
    msg: document.getElementById("pd_msg"),
    subtotal: document.getElementById("pd_subtotal"),
    taxa: document.getElementById("pd_taxa"),
    total: document.getElementById("pd_total"),
    linhaTaxa: document.getElementById("pd_linhaTaxa"),
  };

  let idGrupo = null;
  let carrinho = [];
  let taxasPorFornecedor = {};
  let comboProd = null;
  let pollPixTimer = null;
  let pedidoPagamentoAtual = null;
  let painelAtivo = "produto";
  let bloqueadoTotal = false;
  let editavelCampos = true;
  let somenteLeitura = false;
  /** @type {Array<{id:number,numero:string,status:string,fornecedor_nome:string,anexos?:Array}>} */
  let pedidosGrupo = [];
  let pedidoFocoAnexo = null;
  let tipoAnexoFoco = null;
  /** @type {Record<number, string>} */
  let meioPagamentoPorFornecedor = {};

  const util = () => window.Util || {};

  const icoBtn = (nome, title, cls, attrs = "") => {
    const html = util().gerarIconeTech?.(nome) || "";
    return `<button type="button" class="Cl_BtnAcao ${cls}" title="${esc(title)}" ${attrs}>${html}</button>`;
  };

  let cfg = { mp_icone: "/static/api/mercadopago/imge/icone_mercadopago.png" };
  try {
    cfg = JSON.parse(document.getElementById("pd_cfg")?.textContent || "{}");
  } catch {
    /* defaults */
  }

  const elPayIntegracoes = document.getElementById("pd_payIntegracoes");
  const elSubtotalMini = document.getElementById("pd_subtotalMini");
  const elFrete = document.getElementById("pd_frete");
  const elNavProduto = document.getElementById("pd_navProduto");
  const elNavCliente = document.getElementById("pd_navCliente");
  const elNavEndereco = document.getElementById("pd_navEndereco");
  const elNavValores = document.getElementById("pd_navValores");
  const elNavAnexos = document.getElementById("pd_navAnexos");
  const elAnexosLista = document.getElementById("pd_anexosLista");
  const elAnexosAviso = document.getElementById("pd_anexosAviso");
  const elWizMain = document.querySelector(".Pd_WizMain");
  const elBtnSalvar = document.getElementById("pd_btnSalvar");
  const elBtnConfirmar = document.getElementById("pd_btnConfirmar");
  const elBtnCancelar = document.getElementById("pd_btnCancelar");

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
        <td class="Cl_TableActions Pd_Acoes">
          ${icoBtn("editar", p.status === "rascunho" ? "Editar pedido" : "Ver pedido", "Pd_BtnEdit", `data-acao="editar" data-id="${p.id}" data-grupo="${p.id_grupo || ""}" data-status="${esc(p.status)}"`)}
          ${icoBtn("nf_hub", "Incluir NF", "Pd_BtnNf", `data-acao="nf" data-id="${p.id}" data-grupo="${p.id_grupo || ""}"`)}
          ${icoBtn("etiqueta", "Incluir etiqueta", "Pd_BtnEtq", `data-acao="etiqueta" data-id="${p.id}" data-grupo="${p.id_grupo || ""}"`)}
        </td>
      </tr>`
      )
      .join("");

    el.vazio.hidden = rows.length > 0;
    window.lucide?.createIcons?.();
  }

  function irPainel(id) {
    painelAtivo = id;
    document.querySelectorAll(".Pd_WizNavItem").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.painel === id);
    });
    document.querySelectorAll(".Pd_WizPane").forEach((pane) => {
      const on = pane.dataset.painel === id;
      pane.hidden = !on;
      pane.classList.toggle("is-active", on);
    });
    window.lucide?.createIcons?.();
    if (id === "valores") renderPayIntegracoes();
    if (id === "anexos") renderAnexos();
  }

  function aplicarEstadoWizard(grupo) {
    editavelCampos = grupo ? !!grupo.editavel : true;
    const bloqueadoIntegracao = pedidosGrupo.some((p) => (p.origem || "manual") !== "manual");
    const bloqueadoPago = pedidosGrupo.some((p) =>
      ["pago", "em_expedicao", "entregue"].includes(p.status)
    );

    bloqueadoTotal = bloqueadoIntegracao;
    somenteLeitura = bloqueadoIntegracao;

    elWizMain?.classList.toggle("is-readonly", bloqueadoIntegracao);
    elWizMain?.classList.toggle(
      "is-campos-readonly",
      !editavelCampos || bloqueadoPago || bloqueadoIntegracao
    );

    if (elBtnSalvar) elBtnSalvar.hidden = !editavelCampos;
    if (elBtnConfirmar) elBtnConfirmar.hidden = !editavelCampos;

    const podeCancelar =
      pedidosGrupo.some(
        (p) =>
          (p.status === "rascunho" || p.status === "aguardando_pagamento") &&
          (p.origem || "manual") === "manual"
      ) && !bloqueadoIntegracao;
    if (elBtnCancelar) elBtnCancelar.hidden = !podeCancelar;
  }

  function preencherFormulario(grupo) {
    const c = grupo.cliente || {};
    const e = grupo.entrega || {};
    const set = (id, val) => {
      const f = document.getElementById(id);
      if (f) f.value = val || "";
    };
    set("pd_cliNome", c.nome);
    set("pd_cliDoc", c.documento);
    set("pd_cliEmail", c.email);
    set("pd_cliTel", c.telefone);
    set("pd_cep", e.cep);
    set("pd_logradouro", e.logradouro);
    set("pd_numero", e.numero);
    set("pd_compl", e.complemento);
    set("pd_bairro", e.bairro);
    set("pd_cidade", e.cidade);
    set("pd_uf", e.uf);
    carrinho = (grupo.itens || []).map((i) => ({
      id_variante: i.id_variante,
      id_fornecedor: i.id_fornecedor,
      nome: i.nome,
      sku: i.sku,
      valor_drop: i.valor_drop,
      fornecedor_nome: i.fornecedor_nome,
      quantidade: i.quantidade,
    }));
    pedidosGrupo = grupo.pedidos || [];
    renderItens();
    atualizarNavResumos();
    atualizarNavAnexos();
  }

  function atualizarNavAnexos() {
    if (!elNavAnexos) return;
    const qtd = pedidosGrupo.reduce((s, p) => s + (p.anexos?.length || 0), 0);
    elNavAnexos.textContent = qtd ? `${qtd} arquivo(s)` : "NF e etiqueta";
  }

  async function carregarGrupo(idG) {
    const r = await fetch(`/vendedor/pedidos/grupo/${idG}`, { credentials: "same-origin" });
    const j = await parseJsonResp(r);
    if (!j.success) throw new Error(j.message || "Erro ao carregar pedido.");
    return j.grupo;
  }

  async function abrirModalEdicao(opts = {}) {
    const { idGrupo: gid, painelInicial = "produto", idPedidoFoco = null, tipoAnexo = null } = opts;
    if (!gid) return;

    mostrarMsg("");
    pedidoFocoAnexo = idPedidoFoco;
    tipoAnexoFoco = tipoAnexo;

    let grupo;
    try {
      grupo = await carregarGrupo(gid);
    } catch (e) {
      if (window.Swal) {
        Swal.fire({ icon: "error", title: "Pedido", text: e.message, confirmButtonColor: "#021F81" });
      } else {
        mostrarMsg(e.message, true);
      }
      return;
    }

    idGrupo = grupo.id_grupo;
    meioPagamentoPorFornecedor = {};
    preencherFormulario(grupo);
    aplicarEstadoWizard(grupo);

    const titulo = grupo.editavel
      ? `Editar pedido ${grupo.numero_grupo || ""}`.trim()
      : `Pedido ${grupo.numero_grupo || ""}`.trim();
    document.getElementById("pd_modalTitulo").textContent = titulo;

    if (!comboProd) initComboProduto();
    limparComboProduto();
    el.modal.hidden = false;
    irPainel(painelInicial);

    if (painelInicial === "anexos" && pedidoFocoAnexo) {
      requestAnimationFrame(() => {
        document.getElementById(`pd_anexo_card_${pedidoFocoAnexo}`)?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    }
  }

  function renderBlocoAnexo(ped, tipo, rotulo) {
    const lista = (ped.anexos || []).filter((a) => a.tipo === tipo);
    const inpId = `pd_anexo_inp_${ped.id}_${tipo}`;
    const podeEnviar =
      (ped.origem || "manual") === "manual" && ped.status !== "cancelado" && !bloqueadoTotal;
    return `
      <div class="Pd_AnexoBloco" id="pd_anexo_${ped.id}_${tipo}">
        <h5>${esc(rotulo)}</h5>
        <div class="Pd_AnexoUpload">
          <input type="file" id="${inpId}" class="Pd_AnexoInput" hidden accept=".pdf,.xml,.png,.jpg,.jpeg,.webp" data-upload-anexo="${ped.id}" data-tipo="${tipo}" ${podeEnviar ? "" : "disabled"} />
          ${podeEnviar ? `<label for="${inpId}" class="Cl_botaoFiltro Pd_AnexoBtn">Escolher arquivo</label>` : ""}
          <span class="Pd_AnexoFileName" data-anexo-label="${ped.id}_${tipo}">Nenhum arquivo escolhido</span>
          <span class="Pd_Hint">PDF, XML ou imagem — máx. 5 MB</span>
        </div>
        <ul class="Pd_AnexoItens">
          ${lista.length
            ? lista
                .map(
                  (a) => `
            <li>
              <a href="/vendedor/pedidos/anexos/arquivo?caminho=${encodeURIComponent(a.caminho)}" target="_blank" rel="noopener">${esc(a.nome_original)}</a>
              <button type="button" class="Pd_BtnLink Pd_BtnLink--danger" data-del-anexo="${a.id}">Remover</button>
            </li>`
                )
                .join("")
            : '<li class="Pd_Hint">Nenhum arquivo.</li>'}
        </ul>
      </div>`;
  }

  function renderAnexos() {
    if (!elAnexosLista) return;
    if (!pedidosGrupo.length) {
      elAnexosLista.innerHTML =
        '<p class="Pd_Hint">Confirme o pedido ou abra um pedido existente para anexar NF e etiqueta.</p>';
      if (elAnexosAviso) {
        elAnexosAviso.hidden = false;
        elAnexosAviso.textContent =
          "Anexos ficam vinculados a cada pedido do fornecedor após o primeiro salvamento.";
      }
      return;
    }
    if (elAnexosAviso) elAnexosAviso.hidden = true;
    elAnexosLista.innerHTML = pedidosGrupo
      .map(
        (p) => `
      <article class="Pd_AnexoCard" id="pd_anexo_card_${p.id}">
        <div class="Pd_AnexoCardHead">
          <div>
            <strong>${esc(p.numero)}</strong>
            <br><small>${esc(p.fornecedor_nome || "")} · ${badge(p.status)}</small>
          </div>
        </div>
        ${renderBlocoAnexo(p, "nf", "Nota fiscal")}
        ${renderBlocoAnexo(p, "etiqueta", "Etiqueta de envio")}
      </article>`
      )
      .join("");

    elAnexosLista.querySelectorAll("[data-upload-anexo]").forEach((inp) => {
      inp.addEventListener("change", () => enviarAnexo(inp));
    });
    elAnexosLista.querySelectorAll("[data-del-anexo]").forEach((btn) => {
      btn.addEventListener("click", () => excluirAnexo(+btn.dataset.delAnexo));
    });

    if (tipoAnexoFoco && pedidoFocoAnexo) {
      document.getElementById(`pd_anexo_${pedidoFocoAnexo}_${tipoAnexoFoco}`)?.classList.add("is-focus");
    }
    window.lucide?.createIcons?.();
  }

  async function enviarAnexo(input) {
    const idPed = +input.dataset.uploadAnexo;
    const tipo = input.dataset.tipo;
    const file = input.files?.[0];
    if (!idPed || !tipo || !file) return;
    const labelEl = document.querySelector(`[data-anexo-label="${idPed}_${tipo}"]`);
    if (labelEl) labelEl.textContent = file.name;
    const fd = new FormData();
    fd.append("tipo", tipo);
    fd.append("arquivo", file);
    input.disabled = true;
    try {
      const r = await fetch(`/vendedor/pedidos/${idPed}/anexos`, {
        method: "POST",
        credentials: "same-origin",
        body: fd,
      });
      const j = await parseJsonResp(r);
      if (!j.success) throw new Error(j.message || "Erro ao enviar.");
      const ped = pedidosGrupo.find((p) => p.id === idPed);
      if (ped) {
        ped.anexos = ped.anexos || [];
        ped.anexos.push(j.anexo);
      }
      renderAnexos();
      atualizarNavAnexos();
      if (window.Swal) {
        Swal.fire({ icon: "success", title: "Anexo", text: j.message, timer: 1800, showConfirmButton: false });
      }
    } catch (e) {
      if (labelEl) labelEl.textContent = "Nenhum arquivo escolhido";
      if (window.Swal) {
        Swal.fire({ icon: "error", title: "Anexo", text: e.message, confirmButtonColor: "#021F81" });
      } else {
        mostrarMsg(e.message, true);
      }
    } finally {
      input.value = "";
      input.disabled = false;
    }
  }

  async function excluirAnexo(idAnexo) {
    if (!confirm("Remover este anexo?")) return;
    try {
      const r = await fetch(`/vendedor/pedidos/anexos/${idAnexo}`, {
        method: "DELETE",
        credentials: "same-origin",
      });
      const j = await parseJsonResp(r);
      if (!j.success) throw new Error(j.message || "Erro ao remover.");
      pedidosGrupo.forEach((p) => {
        p.anexos = (p.anexos || []).filter((a) => a.id !== idAnexo);
      });
      renderAnexos();
      atualizarNavAnexos();
    } catch (e) {
      if (window.Swal) {
        Swal.fire({ icon: "error", title: "Anexo", text: e.message, confirmButtonColor: "#021F81" });
      }
    }
  }

  function atualizarNavResumos() {
    const qtd = carrinho.length;
    const sub = carrinho.reduce((s, i) => s + i.valor_drop * i.quantidade, 0);
    if (elNavProduto) {
      elNavProduto.textContent = qtd
        ? `${qtd} item(ns) · ${fmt(sub)}`
        : "Nenhum item";
    }

    const nome = document.getElementById("pd_cliNome")?.value?.trim() || "";
    if (elNavCliente) {
      elNavCliente.textContent = nome || "Dados do comprador";
    }

    const cidade = document.getElementById("pd_cidade")?.value?.trim() || "";
    const uf = document.getElementById("pd_uf")?.value?.trim() || "";
    if (elNavEndereco) {
      elNavEndereco.textContent =
        cidade || uf ? [cidade, uf].filter(Boolean).join(" / ") : "Destino da mercadoria";
    }

    const fornecedores = [...new Set(carrinho.map((i) => i.id_fornecedor))];
    let taxa = 0;
    fornecedores.forEach((f) => {
      taxa += Number(taxasPorFornecedor[f] || taxasPorFornecedor[String(f)] || 0);
    });
    if (elNavValores) {
      elNavValores.textContent = qtd ? `Total ${fmt(sub + taxa)}` : "Resumo e pagamento";
    }
  }

  async function renderPayIntegracoes() {
    if (!elPayIntegracoes) return;
    pararPollPix();

    const idsFornCarrinho = [...new Set(carrinho.map((i) => i.id_fornecedor))];
    if (!idsFornCarrinho.length && !pedidosGrupo.length) {
      elPayIntegracoes.innerHTML =
        '<p class="Pd_Hint">Adicione produtos para ver as opções de pagamento.</p>';
      return;
    }

    elPayIntegracoes.innerHTML = '<p class="Pd_Hint">Carregando integrações…</p>';

    /** @type {Array<{ped?: object, preview?: object, meios?: object}>} */
    const cards = [];

    if (pedidosGrupo.length) {
      for (const ped of pedidosGrupo) {
        let meios = { conectado: false, pix: false, cartao: false };
        if (ped.status === "aguardando_pagamento") {
          const r = await fetch(`/vendedor/pedidos/${ped.id}/meios-pagamento`, {
            credentials: "same-origin",
          });
          const j = await r.json();
          if (j.success) meios = j;
        }
        cards.push({ ped, meios });
      }
    } else {
      const r = await fetch(
        `/vendedor/pedidos/meios-pagamento/preview?fornecedores=${idsFornCarrinho.join(",")}`,
        { credentials: "same-origin" }
      );
      const j = await r.json();
      if (!j.success || !j.fornecedores?.length) {
        elPayIntegracoes.innerHTML =
          '<p class="Pd_Hint">Não foi possível carregar as formas de pagamento.</p>';
        return;
      }
      j.fornecedores.forEach((f) => cards.push({ preview: f, meios: f }));
    }

    elPayIntegracoes.innerHTML = cards.map((c) => renderPayCard(c)).join("");

    elPayIntegracoes.querySelectorAll('input[type="radio"]').forEach((inp) => {
      inp.addEventListener("change", () => {
        const card = inp.closest(".Pd_PayCard");
        const idForn = +card?.dataset.forn;
        if (idForn) meioPagamentoPorFornecedor[idForn] = inp.value;
        card?.querySelectorAll(".Pd_PayOpcao").forEach((lbl) => {
          lbl.classList.toggle("is-selected", lbl.querySelector("input")?.checked);
        });
      });
      if (inp.checked) {
        const card = inp.closest(".Pd_PayCard");
        const idForn = +card?.dataset.forn;
        if (idForn) meioPagamentoPorFornecedor[idForn] = inp.value;
      }
    });

    elPayIntegracoes.querySelectorAll("[data-pagar-forn]").forEach((btn) => {
      btn.addEventListener("click", () => pagarFornecedor(+btn.dataset.pagarForn));
    });
  }

  function renderPayCard({ ped, preview, meios }) {
    const idForn = ped?.id_fornecedor ?? preview?.id_fornecedor;
    const fornNome = ped?.fornecedor_nome ?? preview?.fornecedor_nome ?? "";
    const icone = preview?.icone_url || meios?.icone_url || cfg.mp_icone;
    const conectado = meios?.conectado ?? preview?.conectado;
    const pix = meios?.pix ?? preview?.pix;
    const cartao = meios?.cartao ?? preview?.cartao;
    const pref = meioPagamentoPorFornecedor[idForn] || "";
    const pedidoPago = ped && ["pago", "em_expedicao", "entregue"].includes(ped.status);
    const aguardando = ped?.status === "aguardando_pagamento";
    const rascunho = ped?.status === "rascunho";

    let statusHtml = "";
    if (pedidoPago) {
      const quando = ped.pago_em
        ? new Date(ped.pago_em).toLocaleString("pt-BR")
        : "";
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pago">${badge("pago")} Pagamento confirmado${quando ? ` · ${esc(quando)}` : ""}</div>`;
    } else if (aguardando) {
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pendente">${badge(ped.status)} Aguardando pagamento · ${fmt(ped.valor_total)}</div>`;
    } else if (rascunho) {
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pendente">${badge("rascunho")} Confirme o pedido para pagar</div>`;
    }

    if (!conectado) {
      return `
        <div class="Pd_PayCard" data-forn="${idForn}">
          <div class="Pd_PayCardHead">
            <img class="Pd_PayCardLogo" src="${esc(icone)}" alt="" />
            <div>
              <div class="Pd_PayCardNome">${esc(meios?.integracao_nome || preview?.integracao_nome || "Mercado Pago")}</div>
              <div class="Pd_PayCardForn">${esc(fornNome)}${ped?.numero ? ` · ${esc(ped.numero)}` : ""}</div>
            </div>
          </div>
          ${statusHtml ? `<div class="Pd_PayRow">${statusHtml}</div>` : ""}
          <p class="Pd_PayCardOff">Fornecedor ainda não conectou o Mercado Pago.</p>
        </div>`;
    }

    const opcoes = [];
    if (pix) {
      opcoes.push(`
        <label class="Pd_PayOpcao Pd_PayOpcao--pix${pref === "pix" ? " is-selected" : ""}">
          <input type="radio" name="pd_meio_${idForn}" value="pix"${pref === "pix" || (!pref && !cartao) ? " checked" : ""} ${aguardando || rascunho || !ped ? "" : "disabled"} />
          PIX
        </label>`);
    }
    if (cartao) {
      opcoes.push(`
        <label class="Pd_PayOpcao Pd_PayOpcao--cartao${pref === "cartao" ? " is-selected" : ""}">
          <input type="radio" name="pd_meio_${idForn}" value="cartao"${pref === "cartao" || (!pref && cartao && !pix) ? " checked" : ""} ${aguardando || rascunho || !ped ? "" : "disabled"} />
          Cartão de crédito
        </label>`);
    }

    const podePagar = aguardando && !bloqueadoTotal && !pedidoPago;
    const payRow = `
      <div class="Pd_PayRow">
        ${statusHtml || ""}
        ${podePagar ? `<button type="button" class="Cl_BtnSalvar Pd_BtnPagar" data-pagar-forn="${idForn}">Pagar agora</button>` : ""}
      </div>
      ${podePagar ? `<div class="Pd_PixInline" id="pd_pix_${ped.id}" hidden></div>` : ""}`;

    return `
      <div class="Pd_PayCard" data-forn="${idForn}">
        <div class="Pd_PayCardHead">
          <img class="Pd_PayCardLogo" src="${esc(icone)}" alt="" />
          <div>
            <div class="Pd_PayCardNome">${esc(meios?.integracao_nome || preview?.integracao_nome || "Mercado Pago")}</div>
            <div class="Pd_PayCardForn">${esc(fornNome)}${ped?.numero ? ` · ${esc(ped.numero)}` : ""}</div>
          </div>
        </div>
        ${(aguardando || rascunho || !ped) && opcoes.length ? `<div class="Pd_PayOpcoes">${opcoes.join("")}</div>` : ""}
        ${payRow}
      </div>`;
  }

  function mostrarPixInline(idPed, dados) {
    const box = document.getElementById(`pd_pix_${idPed}`);
    if (!box) return;
    box.hidden = false;
    box.innerHTML = `
      <p class="Pd_Hint">Escaneie o QR Code ou copie o código PIX</p>
      ${dados.qr_code_base64 ? `<img src="data:image/png;base64,${dados.qr_code_base64}" alt="QR PIX" />` : ""}
      <code>${esc(dados.qr_code || "—")}</code>
      <button type="button" class="Cl_botaoFiltro" data-copiar-pix="${idPed}">Copiar PIX</button>
      <p class="Pd_Hint" id="pd_pixSt_${idPed}">Aguardando confirmação do PIX…</p>`;
    box.querySelector("[data-copiar-pix]")?.addEventListener("click", () => {
      const code = dados.qr_code || "";
      if (!code) return;
      navigator.clipboard?.writeText(code).then(() => {
        const st = document.getElementById(`pd_pixSt_${idPed}`);
        if (st) st.textContent = "Código PIX copiado.";
      });
    });
  }

  async function pollPixInline(idPed) {
    const r = await fetch(`/vendedor/pedidos/${idPed}/pagamento/status`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const stEl = document.getElementById(`pd_pixSt_${idPed}`);
    if (j.status === "pago") {
      if (stEl) stEl.textContent = "Pagamento confirmado!";
      pararPollPix();
      await atualizarGrupoAposPagamento(idPed);
      if (window.Swal) {
        Swal.fire({ icon: "success", title: "Pago", text: "Pagamento confirmado.", timer: 2000, showConfirmButton: false });
      }
    } else if (stEl) {
      stEl.textContent = "Aguardando confirmação do PIX…";
    }
  }

  async function atualizarGrupoAposPagamento(idPed) {
    const ped = pedidosGrupo.find((p) => p.id === idPed);
    if (ped) {
      ped.status = "pago";
      ped.status_pagamento = "pago";
    }
    await carregarLista();
    if (idGrupo) {
      try {
        const grupo = await carregarGrupo(idGrupo);
        pedidosGrupo = grupo.pedidos || [];
        aplicarEstadoWizard(grupo);
      } catch {
        /* ok */
      }
    }
    if (painelAtivo === "valores") renderPayIntegracoes();
  }

  async function pagarFornecedor(idForn) {
    const ped = pedidosGrupo.find((p) => p.id_fornecedor === idForn);
    if (!ped || ped.status !== "aguardando_pagamento") return;

    const meio = meioPagamentoPorFornecedor[idForn] || "pix";
    const btn = elPayIntegracoes?.querySelector(`[data-pagar-forn="${idForn}"]`);
    if (btn) btn.disabled = true;

    try {
      const r = await fetch("/vendedor/pedidos/pagar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_pedido: ped.id, meio }),
      });
      const j = await parseJsonResp(r);
      if (!j.success) throw new Error(j.message || "Erro ao iniciar pagamento.");

      if (meio === "pix") {
        pedidoPagamentoAtual = ped.id;
        mostrarPixInline(ped.id, j);
        pararPollPix();
        pollPixTimer = setInterval(() => pollPixInline(ped.id), 5000);
        pollPixInline(ped.id);
        return;
      }
      if (j.checkout_url) {
        window.location.href = j.checkout_url;
      }
    } catch (e) {
      if (window.Swal) {
        Swal.fire({ icon: "error", title: "Pagamento", text: e.message, confirmButtonColor: "#021F81" });
      } else {
        mostrarMsg(e.message, true);
      }
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  function atualizarResumo() {
    const sub = carrinho.reduce((s, i) => s + i.valor_drop * i.quantidade, 0);
    const fornecedores = [...new Set(carrinho.map((i) => i.id_fornecedor))];
    let taxa = 0;
    fornecedores.forEach((f) => {
      taxa += Number(taxasPorFornecedor[f] || taxasPorFornecedor[String(f)] || 0);
    });
    const frete = 0;
    el.subtotal.textContent = fmt(sub);
    if (elSubtotalMini) elSubtotalMini.textContent = fmt(sub);
    el.taxa.textContent = fmt(taxa);
    el.total.textContent = fmt(sub + taxa + frete);
    if (elFrete) elFrete.textContent = fmt(frete);
    el.linhaTaxa.hidden = taxa <= 0;
    el.itensVazio.hidden = carrinho.length > 0;
    atualizarNavResumos();
    if (painelAtivo === "valores") renderPayIntegracoes();
  }

  function limparComboProduto() {
    const display = document.querySelector("#pd_combo_produto .Cl_SelectDisplay");
    const hidden = document.getElementById("pd_produto_id");
    if (display) display.value = "";
    if (hidden) hidden.value = "";
  }

  function adicionarProdutoCombo(item) {
    if (!item?.id_variante) return;
    const ex = carrinho.find((x) => x.id_variante === item.id_variante);
    if (ex) ex.quantidade += 1;
    else {
      carrinho.push({
        id_variante: item.id_variante,
        id_fornecedor: item.id_fornecedor,
        nome: item.nome,
        sku: item.sku,
        valor_drop: item.valor_drop,
        fornecedor_nome: item.fornecedor_nome,
        quantidade: 1,
      });
    }
    renderItens();
    limparComboProduto();
  }

  function initComboProduto() {
    if (!window.Util?.combobox_personalisado) {
      console.warn("[Pedidos] Util.combobox_personalisado ainda não carregou (global_utils.js).");
      return null;
    }
    if (comboProd) return comboProd;
    try {
      comboProd = Util.combobox_personalisado({
        seletor: "#pd_combo_produto",
        caracteres: 3,
        rota: "/vendedor/pedidos/produtos/combobox",
        limite: 20,
        campoOcultoId: "pd_produto_id",
        col_l1: ["nome", false],
        col_l2: ["variacao", "Variação"],
        col_l3: ["sku", "SKU"],
        col_l4: ["preco_venda_label", "Preço de venda"],
        onSelect: adicionarProdutoCombo,
      });
    } catch (e) {
      console.error("[Pedidos] Falha ao iniciar ComboBusca:", e);
      return null;
    }
    return comboProd;
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
    pedidosGrupo = [];
    pedidoFocoAnexo = null;
    tipoAnexoFoco = null;
    meioPagamentoPorFornecedor = {};
    bloqueadoTotal = false;
    editavelCampos = true;
    aplicarEstadoWizard(null);
    document.getElementById("pd_modalTitulo").textContent = "Novo pedido";
    ["pd_cliNome", "pd_cliDoc", "pd_cliEmail", "pd_cliTel", "pd_cep", "pd_logradouro",
      "pd_numero", "pd_compl", "pd_bairro", "pd_cidade", "pd_uf"].forEach((id) => {
      const f = document.getElementById(id);
      if (f) f.value = "";
    });
    renderItens();
    limparComboProduto();
    mostrarMsg("");
    if (!comboProd) initComboProduto();
    el.modal.hidden = false;
    irPainel("produto");
    window.lucide?.createIcons?.();
  }

  function fecharModal() {
    pararPollPix();
    el.modal.hidden = true;
  }

  function soDigitos(v) {
    return String(v || "").replace(/\D/g, "");
  }

  async function buscarCep() {
    const cepEl = document.getElementById("pd_cep");
    const cep = soDigitos(cepEl?.value);
    if (cep.length !== 8) {
      if (window.Swal) {
        Swal.fire({ icon: "warning", title: "CEP", text: "Informe um CEP com 8 dígitos.", confirmButtonColor: "#021F81" });
      } else {
        mostrarMsg("Informe um CEP com 8 dígitos.", true);
      }
      return;
    }
    const btn = document.getElementById("pd_btnCep");
    if (btn) btn.disabled = true;
    try {
      const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
      const j = await r.json();
      if (j.erro) throw new Error("CEP não encontrado.");
      const set = (id, val) => {
        const f = document.getElementById(id);
        if (f) f.value = val || "";
      };
      set("pd_logradouro", j.logradouro);
      set("pd_bairro", j.bairro);
      set("pd_cidade", j.localidade);
      set("pd_uf", j.uf);
      if (j.complemento) set("pd_compl", j.complemento);
      atualizarNavResumos();
      document.getElementById("pd_numero")?.focus();
    } catch (e) {
      const msg = e.message || "Não foi possível buscar o CEP.";
      if (window.Swal) {
        Swal.fire({ icon: "error", title: "CEP", text: msg, confirmButtonColor: "#021F81" });
      } else {
        mostrarMsg(msg, true);
      }
    } finally {
      if (btn) btn.disabled = false;
    }
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

  async function parseJsonResp(r) {
    const txt = await r.text();
    try {
      return JSON.parse(txt);
    } catch {
      throw new Error(r.status >= 500 ? "Erro interno no servidor. Tente novamente." : "Resposta inválida do servidor.");
    }
  }

  async function salvar(confirmar) {
    mostrarMsg("");
    if (bloqueadoTotal || !editavelCampos) return null;
    const body = corpoPedido();
    if (elBtnSalvar) elBtnSalvar.disabled = true;
    if (elBtnConfirmar) elBtnConfirmar.disabled = true;
    let j;
    try {
      const r = await fetch("/vendedor/pedidos/salvar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      j = await parseJsonResp(r);
    } catch (e) {
      mostrarMsg(e.message || "Erro ao salvar.", true);
      if (elBtnSalvar) elBtnSalvar.disabled = false;
      if (elBtnConfirmar) elBtnConfirmar.disabled = false;
      return null;
    }
    if (!j.success) {
      mostrarMsg(j.message || "Erro ao salvar.", true);
      if (elBtnSalvar) elBtnSalvar.disabled = false;
      if (elBtnConfirmar) elBtnConfirmar.disabled = false;
      return null;
    }
    idGrupo = j.id_grupo;
    try {
      const grupo = await carregarGrupo(idGrupo);
      pedidosGrupo = grupo.pedidos || [];
      atualizarNavAnexos();
    } catch {
      /* anexos opcionais */
    }
    if (!confirmar) {
      mostrarMsg(j.message || "Rascunho salvo.");
      await carregarLista();
      if (elBtnSalvar) elBtnSalvar.disabled = false;
      if (elBtnConfirmar) elBtnConfirmar.disabled = false;
      return j;
    }
    let jc;
    try {
      const rc = await fetch("/vendedor/pedidos/confirmar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_grupo: j.id_grupo }),
      });
      jc = await parseJsonResp(rc);
    } catch (e) {
      mostrarMsg(e.message || "Erro ao confirmar.", true);
      if (elBtnSalvar) elBtnSalvar.disabled = false;
      if (elBtnConfirmar) elBtnConfirmar.disabled = false;
      return null;
    }
    if (!jc.success) {
      mostrarMsg(jc.message || "Erro ao confirmar.", true);
      if (window.Swal) {
        Swal.fire({ icon: "error", title: "Confirmar", text: jc.message, confirmButtonColor: "#021F81" });
      }
      if (elBtnSalvar) elBtnSalvar.disabled = false;
      if (elBtnConfirmar) elBtnConfirmar.disabled = false;
      return null;
    }
    mostrarMsg(jc.message || "Pedido confirmado.");
    if (window.Swal) {
      Swal.fire({ icon: "success", title: "Confirmado", text: jc.message, timer: 1800, showConfirmButton: false });
    }
    try {
      const grupo = await carregarGrupo(idGrupo);
      pedidosGrupo = grupo.pedidos || [];
      aplicarEstadoWizard(grupo);
    } catch {
      /* ok */
    }
    await carregarLista();
    irPainel("valores");
    if (elBtnSalvar) elBtnSalvar.disabled = false;
    if (elBtnConfirmar) elBtnConfirmar.disabled = false;
    return jc;
  }

  async function cancelarPedidoGrupo() {
    const cancelaveis = pedidosGrupo.filter(
      (p) =>
        (p.status === "rascunho" || p.status === "aguardando_pagamento") &&
        (p.origem || "manual") === "manual"
    );
    if (!cancelaveis.length) return;
    if (!confirm("Cancelar este(s) pedido(s)?")) return;
    try {
      for (const p of cancelaveis) {
        const r = await fetch("/vendedor/pedidos/cancelar", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id_pedido: p.id }),
        });
        const j = await parseJsonResp(r);
        if (!j.success) throw new Error(j.message || "Erro ao cancelar.");
      }
      fecharModal();
      await carregarLista();
    } catch (e) {
      if (window.Swal) {
        Swal.fire({ icon: "error", title: "Cancelar", text: e.message, confirmButtonColor: "#021F81" });
      }
    }
  }

  async function abrirAposRetornoPagamento(idPed) {
    try {
      const r = await fetch(`/vendedor/pedidos/${idPed}`, { credentials: "same-origin" });
      const j = await parseJsonResp(r);
      if (j.success && j.pedido?.id_grupo) {
        await abrirModalEdicao({ idGrupo: j.pedido.id_grupo, painelInicial: "valores" });
      }
    } catch {
      /* ok */
    }
  }

  function pararPollPix() {
    if (pollPixTimer) {
      clearInterval(pollPixTimer);
      pollPixTimer = null;
    }
  }

  document.getElementById("pd_btnNovo")?.addEventListener("click", abrirModal);
  document.getElementById("pd_btnFechar")?.addEventListener("click", fecharModal);
  elBtnCancelar?.addEventListener("click", cancelarPedidoGrupo);

  document.querySelectorAll(".Pd_WizNavItem").forEach((btn) => {
    btn.addEventListener("click", () => irPainel(btn.dataset.painel));
  });

  ["pd_cliNome", "pd_cliDoc", "pd_cliEmail", "pd_cliTel", "pd_cep", "pd_logradouro",
    "pd_numero", "pd_compl", "pd_bairro", "pd_cidade", "pd_uf"].forEach((id) => {
    document.getElementById(id)?.addEventListener("input", atualizarNavResumos);
  });
  document.getElementById("pd_btnFiltrar")?.addEventListener("click", carregarLista);
  document.getElementById("pd_btnCep")?.addEventListener("click", buscarCep);
  document.getElementById("pd_cep")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      buscarCep();
    }
  });
  document.getElementById("pd_btnSalvar")?.addEventListener("click", () => salvar(false));
  document.getElementById("pd_btnConfirmar")?.addEventListener("click", () => salvar(true));

  el.tbody?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("button[data-acao]");
    if (!btn) return;
    const acao = btn.dataset.acao;
    const idPed = +btn.dataset.id;
    const idG = +btn.dataset.grupo;
    if (!idG) {
      if (window.Swal) {
        Swal.fire({ icon: "info", title: "Pedido", text: "Grupo do pedido indisponível.", confirmButtonColor: "#021F81" });
      }
      return;
    }
    if (acao === "editar") {
      const st = btn.dataset.status || "";
      const painel = st === "aguardando_pagamento" || st === "pago" ? "valores" : "produto";
      abrirModalEdicao({ idGrupo: idG, painelInicial: painel, idPedidoFoco: idPed });
      return;
    }
    if (acao === "nf") {
      abrirModalEdicao({ idGrupo: idG, painelInicial: "anexos", idPedidoFoco: idPed, tipoAnexo: "nf" });
      return;
    }
    if (acao === "etiqueta") {
      abrirModalEdicao({ idGrupo: idG, painelInicial: "anexos", idPedidoFoco: idPed, tipoAnexo: "etiqueta" });
    }
  });

  function bootPedidos() {
    initComboProduto();
    carregarLista();
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
        if (idPed) abrirAposRetornoPagamento(+idPed);
      });
    } else if (idPed) {
      abrirAposRetornoPagamento(+idPed);
    }
  }

  function agendarBootPedidos() {
    let tentativas = 0;
    const tentar = () => {
      if (!window.Util?.combobox_personalisado) {
        if (++tentativas < 50) {
          setTimeout(tentar, 40);
        } else {
          console.error("[Pedidos] global_utils.js não carregou — combobox indisponível.");
        }
        return;
      }
      bootPedidos();
    };
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", tentar, { once: true });
    } else {
      tentar();
    }
  }

  agendarBootPedidos();
})();
