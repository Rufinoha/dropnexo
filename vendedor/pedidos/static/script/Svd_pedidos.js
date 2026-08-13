(function () {
  const STATUS_LABEL_VENDEDOR = {
    rascunho: "Rascunho",
    importado: "Importado",
    aguardando_pagamento: "Aguardando pagamento",
    aguardando_confirmacao: "Aguardando aprovação",
    pago: "Pago (fornecedor aprovou)",
    cancelado: "Cancelado",
    em_expedicao: "Em expedição",
    entregue: "Entregue",
  };

  const STATUS_LABEL_COMPRADOR = {
    pendente: "Pendente",
    pago: "Pago",
    cancelado: "Cancelado",
  };

  const stV = (p) => (typeof p === "string" ? p : p?.status_vendedor || p?.status || "");
  const stC = (p) => (typeof p === "string" ? p : p?.status_comprador || "pendente");
  const freteEditavelPedido = (ped) =>
    ["rascunho", "importado", "aguardando_pagamento", "aguardando_confirmacao"].includes(stV(ped));

  const STATUS_LABEL = STATUS_LABEL_VENDEDOR;

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
  let pedidoFocoFrete = null;
  /** @type {Record<string, string>} */
  let meioPagamentoPorFornecedor = {};
  /** @type {Record<number, {opcoes?: Array, escolhido?: object, valor?: number, nome?: string}>} */
  let fretePorPedido = {};
  /** @type {Record<number, 'me'|'manual'>} */
  let freteModoPorPedido = {};
  /** @type {Array<{id:string,nome:string,conectado:boolean}>} */
  let freteIntegracoesDn = [];
  /** @type {Record<number, string>} provider id selecionado no DropNexo */
  let freteProviderPorPedido = {};
  /** @type {Record<number, 'nf'|'declaracao'>} tipo fiscal no Manual/DropNexo */
  let fiscalTipoPorPedido = {};
  let meFreteConectado = false;
  let freteDirty = false;

  const elFreteConteudo = document.getElementById("pd_freteConteudo");
  const elFreteAviso = document.getElementById("pd_freteAviso");

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
  const elNavFrete = document.getElementById("pd_navFrete");
  const elWizMain = document.querySelector(".Pd_WizMain");
  const elBtnSalvar = document.getElementById("pd_btnSalvar");
  const elBtnConfirmar = document.getElementById("pd_btnConfirmar");
  const elBtnCancelar = document.getElementById("pd_btnCancelar");
  const elBtnEmailTeste = document.getElementById("pd_btnEmailTeste");
  const ehDev = !!(window.OSB_SHELL && window.OSB_SHELL.ehDesenvolvedor);

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

  function badge(status, tipo = "vendedor") {
    const labels = tipo === "comprador" ? STATUS_LABEL_COMPRADOR : STATUS_LABEL_VENDEDOR;
    const cls = tipo === "comprador" ? `Pd_Badge Pd_Badge--c_${status}` : `Pd_Badge Pd_Badge--${status}`;
    return `<span class="${cls}">${labels[status] || status}</span>`;
  }

  function badgesPedido(p) {
    return `<span class="Pd_StatusPair">${badge(stC(p), "comprador")}${badge(stV(p), "vendedor")}</span>`;
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
        <td><strong>${esc(p.numero)}</strong></td>
        <td>${esc(p.fornecedor_nome || "")}</td>
        <td>${esc(p.cliente_nome || "")}</td>
        <td>${fmt(p.valor_total)}</td>
        <td>${badge(stC(p), "comprador")}</td>
        <td>${badge(stV(p), "vendedor")}</td>
        <td>${p.criado_em ? new Date(p.criado_em).toLocaleDateString("pt-BR") : "—"}</td>
        <td class="Cl_TableActions Pd_Acoes">
          ${icoBtn("editar", stV(p) === "rascunho" ? "Editar pedido" : "Ver pedido", "Pd_BtnEdit", `data-acao="editar" data-id="${p.id}" data-grupo="${p.id_grupo || ""}" data-status="${esc(stV(p))}"`)}
          ${icoBtn("nf_hub", "Incluir NF", "Pd_BtnNf", `data-acao="nf" data-id="${p.id}" data-grupo="${p.id_grupo || ""}"`)}
          ${icoBtn("etiqueta", "Incluir etiqueta", "Pd_BtnEtq", `data-acao="etiqueta" data-id="${p.id}" data-grupo="${p.id_grupo || ""}"`)}
        </td>
      </tr>`
      )
      .join("");

    el.vazio.hidden = rows.length > 0;
    window.lucide?.createIcons?.();
  }

  function limparFreteLocal() {
    fretePorPedido = {};
    freteModoPorPedido = {};
    freteDirty = true;
    atualizarResumo();
  }

  function origemTemIntegracaoFrete(ped) {
    const o = (ped.origem || "").toLowerCase();
    return o === "mercado_livre" || o === "tiktok" || o === "amazon" || o === "bling";
  }

  function normalizarModoFreteUi(modo) {
    const m = String(modo || "").toLowerCase();
    if (m === "me" || m === "melhor_envio" || m === "dropnexo") return "dropnexo";
    if (m === "ml" || m === "tiktok" || m === "amazon" || m === "integracao" || m === "mercado_livre") {
      return "integracao";
    }
    if (m === "manual") return "manual";
    return "";
  }

  function inferirModoFrete(ped) {
    if (freteModoPorPedido[ped.id]) return normalizarModoFreteUi(freteModoPorPedido[ped.id]) || freteModoPorPedido[ped.id];
    const salvo = normalizarModoFreteUi(ped.frete_modo);
    if (salvo) return salvo;
    if (ped.me_etiqueta_status === "manual") return "manual";
    if (ped.me_service_id) return "dropnexo";
    if (origemTemIntegracaoFrete(ped)) return "integracao";
    const temEtiqueta = (ped.anexos || []).some((a) => a.tipo === "etiqueta");
    if (temEtiqueta) return "manual";
    return meFreteConectado ? "dropnexo" : "manual";
  }

  function freteDocsStatus(ped) {
    const tipos = new Set((ped.anexos || []).map((a) => a.tipo));
    const temEtiqueta = tipos.has("etiqueta");
    const temFiscal = tipos.has("nf") || tipos.has("declaracao");
    const faltando = [];
    if (!temEtiqueta) faltando.push("etiqueta");
    if (!temFiscal) faltando.push("NF ou declaração");
    return {
      ok: temEtiqueta && temFiscal,
      temEtiqueta,
      temFiscal,
      temNf: tipos.has("nf"),
      temDeclaracao: tipos.has("declaracao"),
      faltando,
    };
  }

  function anexoHref(a) {
    return `/vendedor/pedidos/anexos/arquivo?caminho=${encodeURIComponent(a.caminho)}`;
  }

  function renderDocChip(a) {
    const nome = a.nome_original || "documento";
    const isXml = /\.xml$/i.test(nome) || /\.xml$/i.test(a.caminho || "");
    return `
      <a class="Pd_DocChip" href="${anexoHref(a)}" target="_blank" rel="noopener" title="${esc(nome)}">
        <i data-lucide="${isXml ? "file-code" : "file-text"}" aria-hidden="true"></i>
        <span>${esc(nome)}</span>
      </a>`;
  }

  function renderDocStatusCard(opts) {
    const { ok, titulo, sub, anexos, emptyHint } = opts;
    const lista = (anexos || []).filter(Boolean);
    return `
      <article class="Pd_DocCard ${ok ? "is-ok" : "is-pendente"}">
        <div class="Pd_DocCardTop">
          <span class="Pd_DocCardBadge" aria-hidden="true">
            <i data-lucide="${ok ? "check" : "clock"}"></i>
          </span>
          <div class="Pd_DocCardTxt">
            <strong>${esc(titulo)}</strong>
            <small>${esc(sub)}</small>
          </div>
        </div>
        ${
          lista.length
            ? `<div class="Pd_DocChips">${lista.map(renderDocChip).join("")}</div>`
            : `<p class="Pd_DocCardEmpty">${esc(emptyHint || "Aguardando…")}</p>`
        }
      </article>`;
  }

  function renderFreteDocsDuo(ped, { emptyEtq, emptyNf } = {}) {
    const d = freteDocsStatus(ped);
    const etqs = (ped.anexos || []).filter((a) => a.tipo === "etiqueta");
    const fiscais = (ped.anexos || []).filter((a) => a.tipo === "nf" || a.tipo === "declaracao");
    const tituloNf = d.temDeclaracao && !d.temNf ? "Declaração" : "Nota fiscal";
    return `
      <div class="Pd_DocDuo ${d.ok ? "is-completo" : ""}">
        ${renderDocStatusCard({
          ok: d.temEtiqueta,
          titulo: "Etiqueta",
          sub: d.temEtiqueta ? "Pronta para o fornecedor" : "Ainda não anexada",
          anexos: etqs,
          emptyHint: emptyEtq || "Sem etiqueta ainda",
        })}
        ${renderDocStatusCard({
          ok: d.temFiscal,
          titulo: tituloNf,
          sub: d.temFiscal ? "Pronta para o fornecedor" : "Ainda não anexada",
          anexos: fiscais,
          emptyHint: emptyNf || "Sem NF ou declaração ainda",
        })}
      </div>`;
  }

  function renderFreteDocsChecklist(ped) {
    return renderFreteDocsDuo(ped);
  }

  function sincronizarModoFreteDoGrupo() {
    (pedidosGrupo || []).forEach((p) => {
      freteModoPorPedido[p.id] = inferirModoFrete(p);
    });
  }

  function sincronizarFreteDoGrupo() {
    fretePorPedido = {};
    (pedidosGrupo || []).forEach((p) => {
      if (
        p.valor_frete > 0 ||
        p.me_service_id ||
        normalizarModoFreteUi(p.frete_modo) === "manual" ||
        p.me_etiqueta_status === "manual"
      ) {
        fretePorPedido[p.id] = {
          valor: Number(p.valor_frete || p.me_preco_cotado || 0),
          escolhido: { id: p.me_service_id, nome: p.frete_nome || "" },
          nome: p.frete_nome || "",
          transportadora: p.transportadora || "",
          prazo: p.me_prazo_dias,
        };
      }
    });
    freteDirty = false;
    sincronizarModoFreteDoGrupo();
    atualizarResumo();
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
    if (id === "frete") prepararFrete();
    if (id === "valores") renderPayIntegracoes();
  }

  function aplicarEstadoWizard(grupo) {
    editavelCampos = grupo ? !!grupo.editavel : true;
    const bloqueadoIntegracao = pedidosGrupo.some((p) => (p.origem || "manual") !== "manual");
    const bloqueadoPago = pedidosGrupo.some((p) =>
      ["pago", "aguardando_confirmacao", "em_expedicao", "entregue"].includes(stV(p))
    );

    bloqueadoTotal = false;
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
          (stV(p) === "rascunho" || stV(p) === "aguardando_pagamento") &&
          (p.origem || "manual") === "manual"
      ) && !bloqueadoIntegracao;
    if (elBtnCancelar) elBtnCancelar.hidden = !podeCancelar;

    if (elBtnEmailTeste) {
      elBtnEmailTeste.hidden = !(ehDev && pedidosGrupo.some((p) => p.id));
    }
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
      preco_venda: i.preco_venda,
      fornecedor_nome: i.fornecedor_nome,
      quantidade: i.quantidade,
    }));
    pedidosGrupo = grupo.pedidos || [];
    sincronizarFreteDoGrupo();
    renderItens();
    atualizarNavResumos();
    atualizarNavFrete();
  }

  function atualizarNavFrete() {
    if (!elNavFrete) return;
    if (!pedidosGrupo.length) {
      elNavFrete.textContent = "Etiqueta e nota fiscal";
      return;
    }
    const ok = pedidosGrupo.every((p) => freteDocsStatus(p).ok);
    const qtd = pedidosGrupo.reduce(
      (s, p) => s + (p.anexos || []).filter((a) => ["etiqueta", "nf", "declaracao"].includes(a.tipo)).length,
      0
    );
    elNavFrete.textContent = ok
      ? "Pronto para expedir"
      : qtd
        ? `${qtd} doc(s) · falta completar`
        : "Etiqueta e nota fiscal";
  }

  async function carregarGrupo(idG) {
    const r = await fetch(`/vendedor/pedidos/grupo/${idG}`, { credentials: "same-origin" });
    const j = await parseJsonResp(r);
    if (!j.success) throw new Error(j.message || "Erro ao carregar pedido.");
    return j.grupo;
  }

  async function carregarContextoPedido(idPed) {
    const r = await fetch(`/vendedor/pedidos/${idPed}/contexto`, { credentials: "same-origin" });
    const j = await parseJsonResp(r);
    if (!j.success) throw new Error(j.message || "Erro ao carregar pedido.");
    return j.grupo;
  }

  async function abrirModalEdicao(opts = {}) {
    const { idGrupo: gid, idPedido: idPed, painelInicial = "produto", idPedidoFoco = null } = opts;
    if (!gid && !idPed) return;

    mostrarMsg("");
    pedidoFocoFrete = idPedidoFoco || idPed || null;

    let grupo;
    try {
      grupo = gid ? await carregarGrupo(gid) : await carregarContextoPedido(idPed);
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

    const nums = (grupo.pedidos || []).map((p) => p.numero).filter(Boolean);
    const refNum = nums.length === 1 ? nums[0] : nums.join(", ");
    const titulo = grupo.editavel
      ? `Editar pedido ${refNum || ""}`.trim()
      : `Pedido ${refNum || ""}`.trim();
    document.getElementById("pd_modalTitulo").textContent = titulo;

    if (!comboProd) initComboProduto();
    limparComboProduto();
    el.modal.hidden = false;
    const painel = painelInicial === "anexos" ? "frete" : painelInicial;
    irPainel(painel);

    if (painel === "frete" && pedidoFocoFrete) {
      requestAnimationFrame(() => {
        document
          .querySelector(`[data-frete-ped="${pedidoFocoFrete}"]`)
          ?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
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
      const idPed = j.id_pedido || pedidosGrupo.find((p) =>
        (p.anexos || []).some((a) => a.id === idAnexo)
      )?.id;
      pedidosGrupo.forEach((p) => {
        p.anexos = (p.anexos || []).filter((a) => a.id !== idAnexo);
      });
      if (j.tipo === "comprovante_pix" && idPed) {
        const ped = pedidosGrupo.find((p) => p.id === idPed);
        if (ped) {
          if (j.pedido) Object.assign(ped, j.pedido);
          else {
            ped.status_vendedor = "aguardando_pagamento";
            ped.status = "aguardando_pagamento";
            ped.status_pagamento = "pendente";
            ped.pago_em = null;
          }
        }
        if (painelAtivo === "valores") await renderPayIntegracoes();
      }
      atualizarNavFrete();
      if (painelAtivo === "frete") await renderFretePainel();
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

  function payKey(idForn, integracao) {
    return `${idForn}:${integracao}`;
  }

  async function carregarStatusMeFrete() {
    try {
      const r = await fetch("/vendedor/pedidos/frete/melhor-envio/status", { credentials: "same-origin" });
      const j = await r.json();
      meFreteConectado = !!(j.success && j.conectado);
      freteIntegracoesDn = [
        {
          id: "melhor_envio",
          nome: "Melhor Envio",
          conectado: meFreteConectado,
        },
        // Futuras integrações internas entram aqui (Correios, Jadlog API, etc.)
      ];
      return j;
    } catch {
      meFreteConectado = false;
      freteIntegracoesDn = [{ id: "melhor_envio", nome: "Melhor Envio", conectado: false }];
      return { conectado: false };
    }
  }

  function integracoesDropnexoConectadas() {
    return (freteIntegracoesDn || []).filter((i) => i.conectado);
  }

  function providerDropnexoPedido(ped) {
    const conectadas = integracoesDropnexoConectadas();
    if (!conectadas.length) return "";
    const atual = freteProviderPorPedido[ped.id];
    if (atual && conectadas.some((i) => i.id === atual)) return atual;
    // Se já cotou ME, assume Melhor Envio
    if (ped.me_service_id || fretePorPedido[ped.id]?.opcoes?.length) {
      freteProviderPorPedido[ped.id] = "melhor_envio";
      return "melhor_envio";
    }
    freteProviderPorPedido[ped.id] = conectadas[0].id;
    return conectadas[0].id;
  }

  function melhorPrecoOpcoes(opcoes) {
    if (!opcoes?.length) return null;
    let min = null;
    for (const o of opcoes) {
      const p = Number(o.preco);
      if (!Number.isFinite(p)) continue;
      if (min == null || p < min) min = p;
    }
    return min;
  }

  function inferirTipoFiscal(ped) {
    if (fiscalTipoPorPedido[ped.id] === "nf" || fiscalTipoPorPedido[ped.id] === "declaracao") {
      return fiscalTipoPorPedido[ped.id];
    }
    const tipos = new Set((ped.anexos || []).map((a) => a.tipo));
    if (tipos.has("nf")) {
      fiscalTipoPorPedido[ped.id] = "nf";
      return "nf";
    }
    if (tipos.has("declaracao")) {
      fiscalTipoPorPedido[ped.id] = "declaracao";
      return "declaracao";
    }
    return "";
  }

  function renderEscolhaFiscal(ped, { obrigatorioEscolher = true } = {}) {
    const tipo = inferirTipoFiscal(ped);
    const dis = "";
    return `
      <div class="Pd_FreteFiscalEscolha">
        <p class="Pd_Hint">Documento fiscal: escolha <strong>uma</strong> opção (NF ou declaração — nunca as duas).</p>
        <div class="Pd_FreteFiscalTabs" role="tablist">
          <button type="button" class="Pd_FreteFiscalBtn${tipo === "nf" ? " is-active" : ""}" data-fiscal-tipo="nf" data-ped="${ped.id}" ${dis}>Nota fiscal</button>
          <button type="button" class="Pd_FreteFiscalBtn${tipo === "declaracao" ? " is-active" : ""}" data-fiscal-tipo="declaracao" data-ped="${ped.id}" ${dis}>Declaração de conteúdo</button>
        </div>
        ${
          tipo === "nf"
            ? renderUploadPdfFrete(ped, "nf", "Nota fiscal (PDF)")
            : tipo === "declaracao"
              ? renderUploadPdfFrete(ped, "declaracao", "Declaração de conteúdo (PDF)")
              : obrigatorioEscolher
                ? `<p class="Pd_Hint Pd_FreteFiscalAviso">Selecione Nota fiscal ou Declaração para anexar o PDF.</p>`
                : ""
        }
      </div>`;
  }

  async function removerAnexosTipo(idPed, tipo) {
    const ped = pedidosGrupo.find((p) => p.id === idPed);
    if (!ped) return;
    const lista = (ped.anexos || []).filter((a) => a.tipo === tipo);
    for (const a of lista) {
      try {
        await fetch(`/vendedor/pedidos/anexos/${a.id}`, { method: "DELETE", credentials: "same-origin" });
      } catch {
        /* best-effort */
      }
    }
    ped.anexos = (ped.anexos || []).filter((a) => a.tipo !== tipo);
  }

  function mostrarFreteAviso(msg, isErro) {
    if (!elFreteAviso) return;
    if (!msg) {
      elFreteAviso.hidden = true;
      elFreteAviso.textContent = "";
      return;
    }
    elFreteAviso.hidden = false;
    elFreteAviso.textContent = msg;
    elFreteAviso.classList.toggle("Pd_Msg--erro", !!isErro);
  }

  function renderFreteOpcoes(ped, opcoes) {
    const sel = fretePorPedido[ped.id]?.escolhido?.id;
    return (opcoes || [])
      .map((o) => {
        const checked = sel === o.id ? "checked" : "";
        const prazo = o.prazo_dias != null ? `${o.prazo_dias} dia(s)` : "Prazo sob consulta";
        const transp = o.transportadora ? `${o.transportadora} · ` : "";
        return `
        <label class="Pd_FreteOpcao${checked ? " is-selected" : ""}">
          <input type="radio" name="frete_${ped.id}" value="${o.id}" data-ped="${ped.id}" ${checked} />
          <span class="Pd_FreteOpcaoInfo">
            <strong>${esc(o.nome)}</strong>
            <small>${esc(transp)}${esc(prazo)}</small>
          </span>
          <span class="Pd_FreteOpcaoPreco">${fmt(o.preco)}</span>
        </label>`;
      })
      .join("");
  }

  function bindFreteOpcoes() {
    elFreteConteudo?.querySelectorAll('input[type="radio"][data-ped]').forEach((inp) => {
      inp.addEventListener("change", () => escolherFrete(+inp.dataset.ped, +inp.value));
    });
  }

  async function cotarFretePedido(idPed, { rerender = true } = {}) {
    const btn = elFreteConteudo?.querySelector(`[data-cotar="${idPed}"]`);
    if (btn) btn.disabled = true;
    mostrarFreteAviso("");
    try {
      const r = await fetch(`/vendedor/pedidos/${idPed}/frete/cotar`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
      });
      const j = await parseJsonResp(r);
      if (!j.success) throw new Error(j.message || "Erro ao cotar frete.");
      fretePorPedido[idPed] = { ...(fretePorPedido[idPed] || {}), opcoes: j.opcoes || [] };
      freteProviderPorPedido[idPed] = freteProviderPorPedido[idPed] || "melhor_envio";
      if (j.aviso) mostrarFreteAviso(j.aviso, false);
      if (rerender) {
        await renderFretePainel();
      } else {
        const card = elFreteConteudo?.querySelector(`[data-frete-ped="${idPed}"]`);
        const box = card?.querySelector(".Pd_FreteOpcoes");
        const ped = pedidosGrupo.find((p) => p.id === idPed);
        if (box && ped) {
          box.innerHTML = renderFreteOpcoes(ped, j.opcoes);
          bindFreteOpcoes();
        }
      }
    } catch (e) {
      mostrarFreteAviso(e.message || "Erro ao cotar frete.", true);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function escolherFrete(idPed, serviceId) {
    const opcoes = fretePorPedido[idPed]?.opcoes || [];
    const opcao = opcoes.find((o) => o.id === serviceId);
    mostrarFreteAviso("");
    try {
      const r = await fetch(`/vendedor/pedidos/${idPed}/frete/escolher`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ service_id: serviceId, opcao: opcao?.raw }),
      });
      const j = await parseJsonResp(r);
      if (!j.success) throw new Error(j.message || "Erro ao salvar frete.");
      fretePorPedido[idPed] = {
        ...(fretePorPedido[idPed] || {}),
        valor: Number(j.valor_frete || 0),
        escolhido: { id: serviceId, nome: j.nome || "" },
        nome: j.nome || "",
        prazo: j.me_prazo_dias,
      };
      const ped = pedidosGrupo.find((p) => p.id === idPed);
      if (ped) {
        ped.valor_frete = fretePorPedido[idPed].valor;
        ped.me_service_id = serviceId;
      }
      atualizarResumo();
      await renderFretePainel();
    } catch (e) {
      mostrarFreteAviso(e.message || "Erro ao salvar frete.", true);
    }
  }

  function etiquetaStatusHtml(ped) {
    const modo = inferirModoFrete(ped);
    if (modo === "manual" || modo === "integracao") {
      const etiquetas = (ped.anexos || []).filter((a) => a.tipo === "etiqueta");
      if (!etiquetas.length) return "";
      const rastreio = ped.codigo_rastreio || "";
      const rotulo = modo === "integracao" ? "Etiqueta da integração" : "Etiqueta anexada (manual)";
      return `<p class="Pd_EtiquetaStatus Pd_EtiquetaStatus--gerada">${rotulo}${rastreio ? ` — rastreio <strong>${esc(rastreio)}</strong>` : ""}</p>`;
    }
    if (!ped.me_service_id) return "";
    const st = (ped.me_etiqueta_status || "").toLowerCase();
    const rastreio = ped.codigo_rastreio || "";
    const proto = ped.me_protocol || "";
    let txt = "";
    if (st === "gerada") {
      txt = `Etiqueta DropNexo gerada${rastreio ? ` — rastreio <strong>${esc(rastreio)}</strong>` : ""}${proto ? ` <small>(${esc(proto)})</small>` : ""}`;
    } else if (st === "erro") {
      txt = "Falha ao gerar etiqueta no Melhor Envio.";
    } else if (st === "pendente" && stV(ped) === "pago") {
      txt = "Gerando etiqueta no Melhor Envio…";
    } else if (st === "pendente") {
      txt = "Etiqueta será gerada após o pagamento.";
    }
    if (!txt) return "";
    const retry =
      st === "erro" && ["pago", "em_expedicao"].includes(stV(ped))
        ? `<button type="button" class="Cl_botaoFiltro Pd_BtnEtiquetaRetry" data-etiqueta-retry="${ped.id}">Tentar novamente</button>`
        : "";
    return `<p class="Pd_EtiquetaStatus Pd_EtiquetaStatus--${esc(st || "pendente")}">${txt}${retry}</p>`;
  }

  async function contratarEtiquetaPedido(idPed, forcar = false) {
    const r = await fetch(`/vendedor/pedidos/${idPed}/frete/contratar-etiqueta`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ forcar }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao gerar etiqueta.");
    return j;
  }

  async function setFreteModo(idPed, modo) {
    const modoApi = normalizarModoFreteUi(modo) || modo;
    const r = await fetch(`/vendedor/pedidos/${idPed}/frete/modo`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ modo: modoApi }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao alterar modo de frete.");
    freteModoPorPedido[idPed] = modoApi;
    const ped = pedidosGrupo.find((p) => p.id === idPed);
    if (ped) {
      ped.frete_modo = j.frete_modo || modoApi;
      ped.me_etiqueta_status = modoApi === "manual" ? "manual" : "";
      if (modoApi !== "dropnexo") {
        ped.me_service_id = null;
        fretePorPedido[idPed] = {};
      }
    }
    return j;
  }

  async function salvarFreteManualCampos(idPed) {
    const valor = document.getElementById(`pd_frete_valor_${idPed}`)?.value;
    const rastreio = document.getElementById(`pd_frete_rastreio_${idPed}`)?.value?.trim();
    const transp = document.getElementById(`pd_frete_transp_${idPed}`)?.value?.trim();
    const body = {};
    if (valor !== undefined && valor !== "") body.valor_frete = parseFloat(String(valor).replace(",", ".")) || 0;
    if (rastreio) body.codigo_rastreio = rastreio;
    if (transp) body.transportadora = transp;
    const r = await fetch(`/vendedor/pedidos/${idPed}/frete/manual`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar frete.");
    const ped = pedidosGrupo.find((p) => p.id === idPed);
    if (ped) {
      if (body.valor_frete !== undefined) ped.valor_frete = j.valor_frete;
      if (rastreio) ped.codigo_rastreio = rastreio;
      if (transp) ped.transportadora = transp;
      fretePorPedido[idPed] = { ...(fretePorPedido[idPed] || {}), valor: Number(j.valor_frete || 0) };
    }
    atualizarResumo();
    return j;
  }

  function renderFreteModoTabs(ped, modo) {
    const dis = freteEditavelPedido(ped) ? "" : "disabled";
    const temCanal = origemTemIntegracaoFrete(ped);
    const meHint = meFreteConectado ? "" : ' title="Conecte o Melhor Envio em Integrações → Frete"';
    const intDis = !temCanal ? "disabled" : dis;
    const intHint = !temCanal ? ' title="Disponível só para pedidos de marketplace"' : "";
    return `
      <div class="Pd_FreteModo" role="tablist" aria-label="Forma de envio">
        <button type="button" class="Pd_FreteModoBtn${modo === "integracao" ? " is-active" : ""}" data-frete-modo="integracao" data-ped="${ped.id}" ${intDis}${intHint}>Integração</button>
        <button type="button" class="Pd_FreteModoBtn${modo === "dropnexo" ? " is-active" : ""}" data-frete-modo="dropnexo" data-ped="${ped.id}" ${dis}${meHint}>DropNexo</button>
        <button type="button" class="Pd_FreteModoBtn${modo === "manual" ? " is-active" : ""}" data-frete-modo="manual" data-ped="${ped.id}" ${dis}>Manual</button>
      </div>`;
  }

  function renderListaAnexosTipo(ped, tipo, vazioMsg, podeRemover) {
    const lista = (ped.anexos || []).filter((a) => a.tipo === tipo);
    if (!lista.length) return `<li class="Pd_Hint">${esc(vazioMsg)}</li>`;
    return lista
      .map(
        (a) => `
      <li class="Pd_AnexoLinha">
        ${renderDocChip(a)}
        ${podeRemover ? `<button type="button" class="Pd_BtnLink Pd_BtnLink--danger" data-del-anexo="${a.id}">Remover</button>` : ""}
      </li>`
      )
      .join("");
  }

  function renderUploadPdfFrete(ped, tipo, rotulo) {
    const inpId = `pd_frete_up_${ped.id}_${tipo}`;
    const pode = freteEditavelPedido(ped) || ["pago", "aguardando_pagamento", "importado"].includes(stV(ped));
    const st = stV(ped);
    const bloqueado = st === "cancelado" || st === "entregue" || st === "em_expedicao";
    const ok = pode && !bloqueado;
    const aceitaXml = tipo === "nf" || tipo === "declaracao";
    const accept = aceitaXml ? ".pdf,.xml,application/pdf,text/xml,application/xml" : ".pdf,application/pdf";
    const hintFmt = aceitaXml ? "PDF ou XML · máx. 5 MB" : "Somente PDF · máx. 5 MB";
    const btnTxt = aceitaXml ? "Anexar PDF/XML" : "Anexar PDF";
    return `
      <div class="Pd_FreteUploadBloco">
        <h6>${esc(rotulo)}</h6>
        <div class="Pd_AnexoUpload">
          <input type="file" id="${inpId}" class="Pd_AnexoInput" hidden accept="${accept}" data-frete-doc-upload="${ped.id}" data-tipo="${tipo}" ${ok ? "" : "disabled"} />
          ${ok ? `<label for="${inpId}" class="Cl_botaoFiltro Pd_AnexoBtn">${btnTxt}</label>` : ""}
          <span class="Pd_Hint">${hintFmt}</span>
        </div>
        <ul class="Pd_AnexoItens Pd_FreteEtqLista">
          ${renderListaAnexosTipo(ped, tipo, "Nenhum arquivo.", ok)}
        </ul>
      </div>`;
  }

  function renderAnexosSomenteLeitura(ped, tipo, titulo) {
    const lista = (ped.anexos || []).filter((a) => a.tipo === tipo);
    if (!lista.length) return "";
    return `
      <div class="Pd_FreteUploadBloco">
        <h6>${esc(titulo)}</h6>
        <ul class="Pd_AnexoItens Pd_FreteEtqLista">
          ${renderListaAnexosTipo(ped, tipo, "", false)}
        </ul>
      </div>`;
  }

  function renderFreteIntegracao(ped) {
    const origem = (ped.origem || "").toLowerCase();
    const isTt = origem === "tiktok";
    const isAmz = origem === "amazon";
    const isBling = origem === "bling";
    const isMl = origem === "mercado_livre";
    const canal = isAmz
      ? "Amazon"
      : isTt
        ? "TikTok Shop"
        : isBling
          ? "Bling"
          : "Mercado Livre";
    if (isAmz) {
      return `
      <div class="Pd_FreteIntegracao">
        <p class="Pd_Hint">Pedido da <strong>Amazon</strong>. A etiqueta fica no Seller Central — anexe em PDF abaixo (ou use o modo Manual).</p>
        ${renderFreteDocsChecklist(ped)}
        ${renderUploadPdfFrete(ped, "etiqueta", "Etiqueta de frete")}
        ${renderEscolhaFiscal(ped)}
      </div>`;
    }
    if (isBling) {
      return `
      <div class="Pd_FreteIntegracao">
        <p class="Pd_Hint">Pedido do <strong>Bling</strong>. Puxamos a DANFE em PDF (sem XML). A etiqueta de frete deve ser anexada manualmente.</p>
        <button type="button" class="Cl_botaoprimario" data-puxar-integracao="${ped.id}">Puxar DANFE (Bling)</button>
        ${renderFreteDocsChecklist(ped)}
        ${renderUploadPdfFrete(ped, "etiqueta", "Etiqueta de frete")}
        ${renderEscolhaFiscal(ped, { obrigatorioEscolher: false })}
      </div>`;
    }
    if (isMl || isTt) {
      const docs = freteDocsStatus(ped);
      const canalCurto = isTt ? "TikTok" : "Mercado Livre";
      const btnTxt = docs.ok
        ? `Atualizar documentos (${canalCurto})`
        : docs.temEtiqueta || docs.temFiscal
          ? `Completar documentos (${canalCurto})`
          : `Buscar etiqueta e NF (${canalCurto})`;
      const heroSub = docs.ok
        ? "Tudo certo — o fornecedor já pode despachar com estes arquivos."
        : isTt
          ? "Buscamos etiqueta e nota direto no TikTok Shop. Se faltar algo, tente de novo ou use Manual."
          : "Buscamos etiqueta e nota (PDF ou XML) direto no Mercado Livre.";
      return `
      <div class="Pd_FreteIntegracao Pd_FreteIntegracao--canal">
        <div class="Pd_FreteHero">
          <div class="Pd_FreteHeroTxt">
            <span class="Pd_FreteHeroTag">${esc(canalCurto)}</span>
            <strong>${docs.ok ? "Documentos prontos" : "Documentos do canal"}</strong>
            <p>${heroSub}</p>
          </div>
          <button type="button" class="Cl_botaoprimario Pd_FreteHeroBtn" data-puxar-integracao="${ped.id}">
            <i data-lucide="download" aria-hidden="true"></i>
            ${btnTxt}
          </button>
        </div>
        ${renderFreteDocsDuo(ped, {
          emptyEtq: `Clique em buscar para puxar do ${canalCurto}`,
          emptyNf: isMl
            ? "Após emitir no ML, busque de novo — importamos PDF ou XML"
            : `Clique em buscar para puxar do ${canalCurto}`,
        })}
        <p class="Pd_FreteFootHint">Precisa anexar à mão? Use a aba <strong>Manual</strong>.</p>
      </div>`;
    }
    return `
      <div class="Pd_FreteIntegracao">
        <p class="Pd_Hint">Pedido de ${esc(canal)}. Use o botão para puxar documentos da integração.</p>
        <button type="button" class="Cl_botaoprimario" data-puxar-integracao="${ped.id}">Puxar da integração (${esc(canal)})</button>
        ${renderFreteDocsChecklist(ped)}
      </div>`;
  }

  async function baixarEtiquetaMl(idPed) {
    const r = await fetch(`/vendedor/pedidos/${idPed}/ml/etiqueta`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const j = await parseJsonResp(r);
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao baixar etiqueta ML.");
    const ped = pedidosGrupo.find((p) => p.id === idPed);
    if (ped && j.anexo && !j.ja_existia) {
      ped.anexos = ped.anexos || [];
      ped.anexos.push(j.anexo);
    }
    if (ped && j.id_ml_shipment) ped.id_ml_shipment = j.id_ml_shipment;
    return j;
  }

  async function baixarEtiquetaTiktok(idPed) {
    const r = await fetch(`/vendedor/pedidos/${idPed}/tiktok/etiqueta`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const j = await parseJsonResp(r);
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao baixar etiqueta TikTok.");
    const ped = pedidosGrupo.find((p) => p.id === idPed);
    if (ped && j.anexo && !j.ja_existia) {
      ped.anexos = ped.anexos || [];
      ped.anexos.push(j.anexo);
    }
    return j;
  }

  function renderFreteManual(ped) {
    const pode = freteEditavelPedido(ped);
    const valorRef = Number(ped.valor_frete || fretePorPedido[ped.id]?.valor || 0);
    return `
      <div class="Pd_FreteManual">
        <p class="Pd_Hint">Envio próprio: anexe a <strong>etiqueta</strong> e escolha <strong>NF ou declaração</strong> (PDF).</p>
        ${renderFreteDocsChecklist(ped)}
        ${renderUploadPdfFrete(ped, "etiqueta", "Etiqueta de frete")}
        ${renderEscolhaFiscal(ped)}
        <div class="Pd_FreteManualCampos">
          <label class="Pd_FieldMini">
            <span>Valor do frete (referência)</span>
            <input type="text" id="pd_frete_valor_${ped.id}" inputmode="decimal" placeholder="0,00" value="${valorRef > 0 ? valorRef.toFixed(2).replace(".", ",") : ""}" ${pode ? "" : "readonly"} />
          </label>
          <label class="Pd_FieldMini">
            <span>Código de rastreio</span>
            <input type="text" id="pd_frete_rastreio_${ped.id}" placeholder="Opcional" value="${esc(ped.codigo_rastreio || "")}" ${pode ? "" : "readonly"} />
          </label>
          <label class="Pd_FieldMini">
            <span>Transportadora</span>
            <input type="text" id="pd_frete_transp_${ped.id}" placeholder="Ex.: Correios" value="${esc(ped.transportadora || "")}" ${pode ? "" : "readonly"} />
          </label>
        </div>
        ${pode ? `<button type="button" class="Cl_botaoFiltro" data-salvar-manual="${ped.id}">Salvar dados do frete</button>` : ""}
      </div>`;
  }

  function renderCardsIntegracaoDropnexo(ped) {
    const conectadas = integracoesDropnexoConectadas();
    if (!conectadas.length) {
      return `
        <div class="Pd_FreteDnVazio">
          <p class="Pd_Hint">Nenhuma integração de frete conectada.</p>
          <p class="Pd_Hint">Conecte o <strong>Melhor Envio</strong> em <strong>Integrações → Frete</strong> para cotar e comprar etiquetas pelo DropNexo.</p>
        </div>`;
    }
    const sel = providerDropnexoPedido(ped);
    const cards = conectadas
      .map((integ) => {
        const ativo = sel === integ.id;
        let simHtml = '<span class="Pd_FreteDnSim">Simulação sob demanda</span>';
        if (integ.id === "melhor_envio") {
          const min = melhorPrecoOpcoes(fretePorPedido[ped.id]?.opcoes);
          const escolhido = fretePorPedido[ped.id]?.escolhido;
          if (escolhido?.id && fretePorPedido[ped.id]?.valor != null) {
            simHtml = `<span class="Pd_FreteDnSim is-ok">Selecionado: ${fmt(fretePorPedido[ped.id].valor)}</span>`;
          } else if (min != null) {
            simHtml = `<span class="Pd_FreteDnSim is-ok">A partir de ${fmt(min)}</span>`;
          } else if (ativo) {
            simHtml = '<span class="Pd_FreteDnSim">Cotando…</span>';
          }
        }
        return `
          <button type="button" class="Pd_FreteDnCard${ativo ? " is-active" : ""}" data-dn-provider="${esc(integ.id)}" data-ped="${ped.id}">
            <strong>${esc(integ.nome)}</strong>
            <small>Integração DropNexo</small>
            ${simHtml}
          </button>`;
      })
      .join("");
    return `<div class="Pd_FreteDnCards">${cards}</div>`;
  }

  function renderFreteDropnexo(ped, frete, escolhido, opcoesHtml) {
    const conectadas = integracoesDropnexoConectadas();
    const provider = providerDropnexoPedido(ped);
    let corpoProvider = "";
    if (conectadas.length && provider === "melhor_envio") {
      corpoProvider = `
        <div class="Pd_FreteMeHead">
          <button type="button" class="Cl_botaoFiltro" data-cotar="${ped.id}" ${freteEditavelPedido(ped) ? "" : "disabled"}>Atualizar cotação</button>
        </div>
        <div class="Pd_FreteOpcoes">${opcoesHtml}</div>
        ${etiquetaStatusHtml(ped)}`;
    } else if (conectadas.length && provider) {
      corpoProvider = `<p class="Pd_Hint">Integração <strong>${esc(provider)}</strong> em breve neste fluxo.</p>`;
    }
    return `
      <div class="Pd_FreteDropnexo">
        <p class="Pd_Hint">Escolha a integração para cotar e comprar o frete. A etiqueta é gerada após o pagamento.</p>
        ${renderCardsIntegracaoDropnexo(ped)}
        ${corpoProvider}
        ${conectadas.length ? renderFreteDocsChecklist(ped) : ""}
        ${conectadas.length ? renderEscolhaFiscal(ped) : ""}
      </div>`;
  }

  async function enviarDocFrete(input) {
    const idPed = +input.dataset.freteDocUpload;
    const tipo = input.dataset.tipo || "etiqueta";
    const file = input.files?.[0];
    if (!idPed || !file) return;
    const nome = file.name || "";
    const okPdf = /\.pdf$/i.test(nome);
    const okXml = (tipo === "nf" || tipo === "declaracao") && /\.xml$/i.test(nome);
    if (!okPdf && !okXml) {
      if (window.Swal) {
        Swal.fire({
          icon: "warning",
          title: "Arquivo",
          text:
            tipo === "nf" || tipo === "declaracao"
              ? "Envie a nota em PDF ou XML."
              : "Envie somente arquivo PDF.",
          confirmButtonColor: "#021F81",
        });
      }
      input.value = "";
      return;
    }
    const fd = new FormData();
    fd.append("tipo", tipo);
    fd.append("arquivo", file);
    input.disabled = true;
    try {
      // NF e declaração são exclusivos
      if (tipo === "nf") await removerAnexosTipo(idPed, "declaracao");
      if (tipo === "declaracao") await removerAnexosTipo(idPed, "nf");

      const r = await fetch(`/vendedor/pedidos/${idPed}/anexos`, {
        method: "POST",
        credentials: "same-origin",
        body: fd,
      });
      const j = await parseJsonResp(r);
      if (!j.success) throw new Error(j.message || "Erro ao enviar.");
      const ped = pedidosGrupo.find((p) => p.id === idPed);
      const modoAtual = ped ? inferirModoFrete(ped) : "";
      if (modoAtual === "manual" || (tipo === "etiqueta" && modoAtual !== "integracao" && modoAtual !== "dropnexo")) {
        try {
          await setFreteModo(idPed, modoAtual === "integracao" ? "integracao" : "manual");
        } catch (_) {
          /* ignore se status não editável */
        }
      }
      if (ped) {
        ped.anexos = ped.anexos || [];
        ped.anexos.push(j.anexo);
      }
      if (tipo === "nf" || tipo === "declaracao") fiscalTipoPorPedido[idPed] = tipo;
      await renderFretePainel();
      atualizarNavFrete();
      if (window.Swal) {
        Swal.fire({ icon: "success", title: "Arquivo anexado", timer: 1600, showConfirmButton: false });
      }
    } catch (e) {
      if (window.Swal) Swal.fire({ icon: "error", title: "Anexo", text: e.message, confirmButtonColor: "#021F81" });
    } finally {
      input.value = "";
      input.disabled = false;
    }
  }

  async function puxarIntegracaoPedido(idPed) {
    const r = await fetch(`/vendedor/pedidos/${idPed}/frete/integracao/puxar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    });
    const j = await parseJsonResp(r);
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao puxar da integração.");
    const ped = pedidosGrupo.find((p) => p.id === idPed);
    if (ped) {
      ped.frete_modo = "integracao";
      freteModoPorPedido[idPed] = "integracao";
      if (Array.isArray(j.anexos)) ped.anexos = j.anexos;
      else {
        ped.anexos = ped.anexos || [];
        if (j.etiqueta?.anexo && !j.etiqueta.ja_existia) ped.anexos.push(j.etiqueta.anexo);
        if (j.fiscal?.anexo && !j.fiscal.ja_existia) ped.anexos.push(j.fiscal.anexo);
      }
    }
    return j;
  }

  async function renderFretePainel() {
    if (!elFreteConteudo) return;
    if (!carrinho.length) {
      elFreteConteudo.innerHTML = '<p class="Pd_Hint">Adicione produtos ao pedido.</p>';
      return;
    }
    if (!pedidosGrupo.length) {
      elFreteConteudo.innerHTML =
        '<p class="Pd_Hint">Salve o rascunho para gerar os pedidos por fornecedor e definir o envio.</p>';
      return;
    }
    const cep = soDigitos(document.getElementById("pd_cep")?.value);
    if (cep.length !== 8) {
      elFreteConteudo.innerHTML =
        '<p class="Pd_Hint">Informe o CEP de entrega no passo <strong>Endereço</strong>.</p>';
      return;
    }

    sincronizarModoFreteDoGrupo();

    elFreteConteudo.innerHTML = pedidosGrupo
      .map((ped) => {
        const modo = inferirModoFrete(ped);
        const frete = fretePorPedido[ped.id];
        const escolhido = frete?.escolhido;
        const opcoesHtml = frete?.opcoes?.length
          ? renderFreteOpcoes(ped, frete.opcoes)
          : escolhido
            ? `<p class="Pd_Hint">Frete selecionado: <strong>${esc(escolhido.nome || frete.nome || "")}</strong> — ${fmt(frete.valor || 0)}</p>`
            : '<p class="Pd_Hint">Clique em Cotar frete para ver as opções do Melhor Envio.</p>';
        const origem = (ped.origem || "").toLowerCase();
        const canalLabel =
          origem === "amazon"
            ? " · Amazon"
            : origem === "tiktok"
              ? " · TikTok Shop"
              : origem === "bling"
                ? " · Bling"
                : origem === "mercado_livre"
                  ? " · Mercado Livre"
                  : "";
        const corpo =
          modo === "integracao"
            ? renderFreteIntegracao(ped)
            : modo === "manual"
              ? renderFreteManual(ped)
              : renderFreteDropnexo(ped, frete, escolhido, opcoesHtml);
        return `
        <article class="Pd_FreteCard" data-frete-ped="${ped.id}" data-frete-modo-atual="${modo}">
          <div class="Pd_FreteCardHead">
            <div>
              <h5>${esc(ped.fornecedor_nome || "Fornecedor")}</h5>
              <small class="Pd_Hint">Pedido ${esc(ped.numero || "")}${canalLabel}</small>
            </div>
          </div>
          ${renderFreteModoTabs(ped, modo)}
          <div class="Pd_FreteCorpo">${corpo}</div>
        </article>`;
      })
      .join("");

    elFreteConteudo.querySelectorAll("[data-puxar-integracao]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        const temSwal = !!window.Swal;
        if (temSwal) {
          Swal.fire({
            title: "Buscando documentos…",
            html: "<p style='margin:0;color:#64748b'>Consultando etiqueta e nota na integração.</p>",
            allowOutsideClick: false,
            allowEscapeKey: false,
            showConfirmButton: false,
            didOpen: () => Swal.showLoading(),
          });
        }
        try {
          const j = await puxarIntegracaoPedido(+btn.dataset.puxarIntegracao);
          if (j?.fiscal_debug) {
            try {
              console.info("[DropNexo] fiscal_debug ML", j.fiscal_debug);
            } catch (_) {}
          }
          await renderFretePainel();
          atualizarNavFrete();
          const etqOk = !!j.etiqueta;
          const nfOk = !!j.fiscal;
          const etqMotivo = j.etiqueta_motivo || (!etqOk ? "Ainda não liberada no Mercado Livre." : "");
          const nfMotivo = j.fiscal_motivo || (!nfOk ? "Ainda não liberada no Mercado Livre." : "");
          const icon = etqOk && nfOk ? "success" : etqOk || nfOk ? "info" : "warning";
          const title =
            etqOk && nfOk
              ? "Documentos baixados"
              : etqOk || nfOk
                ? "Parcialmente disponível"
                : "Ainda não disponível";
          const nfDetail = nfOk
            ? j.fiscal?.gerado_local
              ? "PDF gerado com a chave e dados oficiais do ML."
              : j.fiscal?.formato === "xml"
                ? "XML da nota anexado ao pedido."
                : "Arquivo anexado ao pedido."
            : nfMotivo;
          const card = (ok, nome, detail) => `
            <div style="padding:0.7rem 0.8rem;border-radius:10px;border:1px solid ${
              ok ? "#bbf7d0" : "#fde68a"
            };background:${ok ? "#f0fdf4" : "#fffbeb"};margin:0.4rem 0">
              <div style="font-weight:800;color:${ok ? "#166534" : "#92400e"}">${nome}: ${
                ok ? "pronta" : "pendente"
              }</div>
              <div style="margin-top:0.25rem;font-size:0.88rem;line-height:1.4;color:${
                ok ? "#15803d" : "#78350f"
              }">${esc(detail || "")}</div>
            </div>`;
          if (temSwal) {
            await Swal.fire({
              icon,
              title,
              html: `<div style="text-align:left">
                <p style="margin:0 0 0.55rem;color:#475569">${esc(
                  j.message || "Consultamos a integração."
                )}</p>
                ${card(etqOk, "Etiqueta", etqOk ? "Arquivo anexado ao pedido." : etqMotivo)}
                ${card(nfOk, "Nota fiscal", nfDetail)}
                ${
                  etqOk && nfOk
                    ? ""
                    : `<p style="margin:0.75rem 0 0;font-size:0.85rem;color:#64748b;line-height:1.4">
                  Pode tentar de novo quando o canal liberar. Para anexar PDF agora, use a aba <strong>Manual</strong>.
                </p>`
                }
              </div>`,
              confirmButtonText: "Entendi",
              confirmButtonColor: "#021F81",
            });
          }
        } catch (e) {
          if (temSwal) {
            await Swal.fire({
              icon: "warning",
              title: "Não foi possível buscar",
              html: `<div style="text-align:left">
                <p style="margin:0;line-height:1.45;color:#334155">${esc(e.message)}</p>
                <p style="margin:0.75rem 0 0;color:#64748b;font-size:0.9rem;line-height:1.4">
                  Tente novamente em alguns minutos ou anexe o PDF na aba <strong>Manual</strong>.
                </p>
              </div>`,
              confirmButtonText: "Entendi",
              confirmButtonColor: "#021F81",
            });
          }
        } finally {
          btn.disabled = false;
        }
      });
    });

    elFreteConteudo.querySelectorAll("[data-frete-modo]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const idPed = +btn.dataset.ped;
        const modo = normalizarModoFreteUi(btn.dataset.freteModo) || btn.dataset.freteModo;
        if (inferirModoFrete(pedidosGrupo.find((p) => p.id === idPed) || {}) === modo) return;
        btn.disabled = true;
        try {
          await setFreteModo(idPed, modo);
          await renderFretePainel();
          const ped = pedidosGrupo.find((p) => p.id === idPed) || {};
          if (
            modo === "dropnexo" &&
            providerDropnexoPedido(ped) === "melhor_envio" &&
            meFreteConectado &&
            freteEditavelPedido(ped)
          ) {
            await cotarFretePedido(idPed);
            await renderFretePainel();
          }
          if (modo === "integracao" && origemTemIntegracaoFrete(ped) && (ped.origem || "") !== "amazon") {
            try {
              await puxarIntegracaoPedido(idPed);
              await renderFretePainel();
            } catch (_) {
              /* deixa o usuário tentar pelo botão */
            }
          }
        } catch (e) {
          Swal.fire({ icon: "error", title: "Frete", text: e.message, confirmButtonColor: "#021F81" });
        } finally {
          btn.disabled = false;
        }
      });
    });

    elFreteConteudo.querySelectorAll("[data-dn-provider]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const idPed = +btn.dataset.ped;
        const provider = btn.dataset.dnProvider;
        if (!idPed || !provider) return;
        freteProviderPorPedido[idPed] = provider;
        await renderFretePainel();
        const ped = pedidosGrupo.find((p) => p.id === idPed) || {};
        if (
          provider === "melhor_envio" &&
          meFreteConectado &&
          freteEditavelPedido(ped) &&
          !fretePorPedido[idPed]?.opcoes?.length
        ) {
          await cotarFretePedido(idPed);
          await renderFretePainel();
        }
      });
    });

    elFreteConteudo.querySelectorAll("[data-fiscal-tipo]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const idPed = +btn.dataset.ped;
        const tipo = btn.dataset.fiscalTipo;
        if (!idPed || (tipo !== "nf" && tipo !== "declaracao")) return;
        const ped = pedidosGrupo.find((p) => p.id === idPed);
        const atual = inferirTipoFiscal(ped || {});
        if (atual === tipo) return;
        // Trocar tipo: remove o outro se existir
        if (tipo === "nf") await removerAnexosTipo(idPed, "declaracao");
        if (tipo === "declaracao") await removerAnexosTipo(idPed, "nf");
        fiscalTipoPorPedido[idPed] = tipo;
        await renderFretePainel();
        atualizarNavFrete();
      });
    });

    elFreteConteudo.querySelectorAll("[data-cotar]").forEach((btn) => {
      btn.addEventListener("click", () => cotarFretePedido(+btn.dataset.cotar));
    });
    elFreteConteudo.querySelectorAll("[data-frete-doc-upload]").forEach((inp) => {
      inp.addEventListener("change", () => enviarDocFrete(inp));
    });
    elFreteConteudo.querySelectorAll("[data-salvar-manual]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          await salvarFreteManualCampos(+btn.dataset.salvarManual);
          Swal.fire({ icon: "success", title: "Salvo", timer: 1200, showConfirmButton: false });
        } catch (e) {
          Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
        } finally {
          btn.disabled = false;
        }
      });
    });
    elFreteConteudo.querySelectorAll("[data-del-anexo]").forEach((btn) => {
      btn.addEventListener("click", () => excluirAnexo(+btn.dataset.delAnexo));
    });
    elFreteConteudo.querySelectorAll("[data-etiqueta-retry]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        btn.disabled = true;
        try {
          const j = await contratarEtiquetaPedido(+btn.dataset.etiquetaRetry, true);
          await Swal.fire({
            icon: "success",
            title: "Etiqueta",
            text: j.message || "Etiqueta gerada.",
            confirmButtonColor: "#021F81",
          });
          if (idGrupo) {
            const grupo = await carregarGrupo(idGrupo);
            pedidosGrupo = grupo.pedidos || [];
            sincronizarFreteDoGrupo();
            atualizarNavFrete();
            await renderFretePainel();
          } else {
            await renderFretePainel();
          }
        } catch (e) {
          Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
        } finally {
          btn.disabled = false;
        }
      });
    });
    bindFreteOpcoes();
    window.lucide?.createIcons?.();
  }

  async function prepararFrete() {
    mostrarFreteAviso("");
    if (!carrinho.length) {
      if (elFreteConteudo) {
        elFreteConteudo.innerHTML = '<p class="Pd_Hint">Adicione produtos ao pedido.</p>';
      }
      return;
    }
    if (editavelCampos && (!idGrupo || freteDirty)) {
      const salvo = await salvar(false);
      if (!salvo) return;
    }
    await carregarStatusMeFrete();
    await renderFretePainel();
    for (const ped of pedidosGrupo) {
      const modo = inferirModoFrete(ped);
      if (
        modo === "dropnexo" &&
        providerDropnexoPedido(ped) === "melhor_envio" &&
        meFreteConectado &&
        freteEditavelPedido(ped)
      ) {
        if (!fretePorPedido[ped.id]?.opcoes?.length && !fretePorPedido[ped.id]?.escolhido) {
          await cotarFretePedido(ped.id, { rerender: false });
        }
      }
      if (
        modo === "integracao" &&
        origemTemIntegracaoFrete(ped) &&
        (ped.origem || "") !== "amazon" &&
        !(ped.anexos || []).some((a) => a.tipo === "etiqueta")
      ) {
        try {
          await puxarIntegracaoPedido(ped.id);
        } catch (_) {
          /* silencioso — botão manual permanece */
        }
      }
    }
    await renderFretePainel();
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

    const idsForn = pedidosGrupo.length
      ? [...new Set(pedidosGrupo.map((p) => p.id_fornecedor))]
      : idsFornCarrinho;

    const r = await fetch(
      `/vendedor/pedidos/meios-pagamento/preview?fornecedores=${idsForn.join(",")}`,
      { credentials: "same-origin" }
    );
    const j = await r.json();
    if (!j.success) {
      elPayIntegracoes.innerHTML = '<p class="Pd_Hint">Não foi possível carregar as formas de pagamento.</p>';
      return;
    }

    const mapaForn = {};
    (j.fornecedores || []).forEach((f) => {
      mapaForn[f.id_fornecedor] = f;
    });

    /** @type {Array<{ped?: object, integ: object, forn?: object}>} */
    const cards = [];

    if (pedidosGrupo.length) {
      for (const ped of pedidosGrupo) {
        const forn = mapaForn[ped.id_fornecedor];
        (forn?.integracoes || []).forEach((integ) => cards.push({ ped, integ, forn }));
      }
    } else {
      (j.fornecedores || []).forEach((forn) => {
        (forn.integracoes || []).forEach((integ) => cards.push({ integ, forn }));
      });
    }

    if (!cards.length) {
      elPayIntegracoes.innerHTML =
        '<p class="Pd_Hint">Nenhuma forma de pagamento disponível. O fornecedor precisa conectar Mercado Pago ou configurar PIX manual.</p>';
      return;
    }

    elPayIntegracoes.innerHTML = cards.map((c) => renderPayCard(c)).join("");

    elPayIntegracoes.querySelectorAll('input[type="radio"]').forEach((inp) => {
      inp.addEventListener("change", () => {
        const card = inp.closest(".Pd_PayCard");
        const k = card?.dataset.payKey;
        if (k) meioPagamentoPorFornecedor[k] = inp.value;
        card?.querySelectorAll(".Pd_PayOpcao").forEach((lbl) => {
          lbl.classList.toggle("is-selected", lbl.querySelector("input")?.checked);
        });
      });
      if (inp.checked) {
        const card = inp.closest(".Pd_PayCard");
        const k = card?.dataset.payKey;
        if (k) meioPagamentoPorFornecedor[k] = inp.value;
      }
    });

    elPayIntegracoes.querySelectorAll("[data-pagar]").forEach((btn) => {
      const go = () => pagarCard(+btn.dataset.pagar, btn.dataset.integ, +btn.dataset.ped);
      btn.addEventListener("click", go);
      btn.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") {
          ev.preventDefault();
          go();
        }
      });
    });

    elPayIntegracoes.querySelectorAll("[data-reabrir-pix]").forEach((btn) => {
      btn.addEventListener("click", () => reabrirPixManual(+btn.dataset.reabrirPix));
    });

    elPayIntegracoes.querySelectorAll("[data-upload-comprovante]").forEach((inp) => {
      inp.addEventListener("change", () => enviarComprovantePix(inp));
    });

    elPayIntegracoes.querySelectorAll("[data-del-anexo]").forEach((btn) => {
      btn.addEventListener("click", () => excluirAnexo(+btn.dataset.delAnexo));
    });

    cards.forEach(({ ped }) => {
      const temComp = (ped?.anexos || []).some((a) => a.tipo === "comprovante_pix");
      if (
        ped?.pix_manual_payload &&
        !temComp &&
        freteDocsStatus(ped).ok &&
        document.getElementById(`pd_pixm_${ped.id}`)
      ) {
        mostrarPixManualInline(ped.id, {
          payload: ped.pix_manual_payload,
          txid: ped.pix_manual_txid,
          numero_pedido: ped.numero,
        });
      }
    });
  }

  function renderPayCard({ ped, integ, forn }) {
    const idForn = ped?.id_fornecedor ?? forn?.id_fornecedor;
    const fornNome = ped?.fornecedor_nome ?? forn?.fornecedor_nome ?? "";
    const integracao = integ.integracao || "mercado-pago";
    const nomeInteg = integ.integracao_nome || "Pagamento";
    const icone = integ.icone_url || (integracao === "mercado-pago" ? cfg.mp_icone : "");
    const isPixManual = integracao === "pix-manual";
    const k = payKey(idForn, integracao);
    const pref = meioPagamentoPorFornecedor[k] || "";
    const stPag = (ped?.status_pagamento || "").toLowerCase();
    const comprovantes = (ped?.anexos || []).filter((a) => a.tipo === "comprovante_pix");
    const temComprovante = comprovantes.length > 0;
    const pagoConfirmadoForn =
      ped &&
      ["pago", "em_expedicao", "entregue"].includes(stV(ped)) &&
      (stPag === "pago" || !!ped.pago_em) &&
      temComprovante;
    const aguardando = stV(ped) === "aguardando_pagamento";
    const aguardandoConf = temComprovante || stV(ped) === "aguardando_confirmacao";
    const importado = stV(ped) === "importado";
    const rascunho = stV(ped) === "rascunho";
    const pixManualAtivo = !!(ped?.meio_pagamento === "pix_manual" || ped?.pix_manual_payload);
    const st = stV(ped);
    const idPed = ped?.id || 0;
    const docsFreteOk = ped ? freteDocsStatus(ped).ok : false;
    const docsFreteFaltando = ped ? freteDocsStatus(ped).faltando : [];
    // Botão liberado até ter comprovante (cancela/entregue não)
    const podeGerarPixManual =
      isPixManual && !!idPed && !temComprovante && !["cancelado", "entregue"].includes(st);

    let statusHtml = "";
    if (pagoConfirmadoForn) {
      const quando = ped.pago_em ? new Date(ped.pago_em).toLocaleString("pt-BR") : "";
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pago">Pagamento aprovado pelo fornecedor${quando ? ` · ${esc(quando)}` : ""}</div>`;
    } else if (temComprovante && isPixManual) {
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pendente">Comprovante enviado — aguardando o fornecedor confirmar</div>`;
    } else if (isPixManual && ped && !docsFreteOk) {
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pendente">Antes de gerar o PIX, anexe em <strong>Frete e NF</strong>: ${esc(docsFreteFaltando.join(", "))}</div>`;
    } else if (isPixManual && ped) {
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pendente">Clique em <strong>Gerar PIX</strong> para ver o QR e o copia e cola · ${fmt(totalFornecedorPedido(ped))}</div>`;
    } else if (importado || aguardando) {
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pendente">Pague o fornecedor · ${fmt(totalFornecedorPedido(ped))}</div>`;
    } else if (rascunho) {
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pendente">Confirme o pedido para pagar</div>`;
    }

    const logoHtml = icone
      ? `<img class="Pd_PayCardLogo" src="${esc(icone)}" alt="" />`
      : `<span class="Pd_PayCardLogo Pd_PayCardLogo--txt" style="background:#32BCAD;color:#fff">PX</span>`;

    const opcoes = [];
    if (isPixManual) {
      opcoes.push(`
        <label class="Pd_PayOpcao Pd_PayOpcao--pix is-selected">
          <input type="radio" name="pd_meio_${k}" value="pix_manual" checked />
          PIX Manual
        </label>`);
    } else {
      if (integ.pix) {
        opcoes.push(`
          <label class="Pd_PayOpcao Pd_PayOpcao--pix${pref === "pix" ? " is-selected" : ""}">
            <input type="radio" name="pd_meio_${k}" value="pix"${pref === "pix" || (!pref && !integ.cartao) ? " checked" : ""} />
            PIX
          </label>`);
      }
      if (integ.cartao) {
        opcoes.push(`
          <label class="Pd_PayOpcao Pd_PayOpcao--cartao${pref === "cartao" ? " is-selected" : ""}">
            <input type="radio" name="pd_meio_${k}" value="cartao"${pref === "cartao" || (!pref && integ.cartao && !integ.pix) ? " checked" : ""} />
            Cartão de crédito
          </label>`);
      }
    }

    const podePagarMp =
      !isPixManual && (aguardando || importado) && !pagoConfirmadoForn && !aguardandoConf;
    const passosPix =
      isPixManual && ped && podeGerarPixManual && docsFreteOk
        ? `<ol class="Pd_PixPassos">
          <li>Gere o PIX (QR / copia e cola)</li>
          <li>Anexe o comprovante</li>
          <li>Fornecedor confirma o pagamento</li>
        </ol>`
        : isPixManual && ped && podeGerarPixManual && !docsFreteOk
          ? `<ol class="Pd_PixPassos">
          <li>Anexe etiqueta + NF/declaração em Frete e NF</li>
          <li>Gere o PIX e pague</li>
          <li>Anexe o comprovante</li>
        </ol>`
          : "";
    const labelGerar = !docsFreteOk
      ? "Gerar PIX"
      : pixManualAtivo
        ? "Gerar PIX novamente"
        : "Gerar PIX";
    const payRow = `
      <div class="Pd_PayRow">
        ${statusHtml || ""}
        ${
          podeGerarPixManual
            ? `<button type="button" class="Cl_BtnSalvar Pd_BtnPagar Pd_BtnPagar--destaque" data-pagar="${idForn}" data-integ="${esc(integracao)}" data-ped="${idPed}">${labelGerar}</button>`
            : ""
        }
        ${
          podePagarMp
            ? `<button type="button" class="Cl_BtnSalvar Pd_BtnPagar" data-pagar="${idForn}" data-integ="${esc(integracao)}" data-ped="${idPed}">Gerar PIX</button>`
            : ""
        }
      </div>`;

    const listaComprovantes = temComprovante
      ? `<div class="Pd_ComprovanteLista">
          ${comprovantes
            .map(
              (a) => `
            <div class="Pd_ComprovanteItem">
              <a href="${anexoHref(a)}" target="_blank" rel="noopener">${esc(a.nome_original || "Comprovante")}</a>
              ${
                !pagoConfirmadoForn && st !== "entregue" && st !== "cancelado"
                  ? `<button type="button" class="Pd_BtnLink Pd_BtnLink--danger" data-del-anexo="${a.id}">Excluir comprovante</button>`
                  : ""
              }
            </div>`
            )
            .join("")}
        </div>`
      : "";
    const mostrarUploadComprovante =
      isPixManual &&
      ped &&
      !pagoConfirmadoForn &&
      !temComprovante &&
      pixManualAtivo &&
      docsFreteOk;
    const mostrarQr = pixManualAtivo && !temComprovante && docsFreteOk;
    const pixBox = isPixManual && ped
      ? `<div class="Pd_PixInline" id="pd_pixm_${ped.id}" ${mostrarQr ? "" : "hidden"}></div>
         ${listaComprovantes}
         ${
           mostrarUploadComprovante
             ? `<div class="Pd_ComprovanteUpload">
           <label class="Pd_Hint">Após pagar, anexe o comprovante:</label>
           <input type="file" class="Pd_AnexoInput" accept=".pdf,.png,.jpg,.jpeg,.webp" data-upload-comprovante="${ped.id}" />
         </div>`
             : ""
         }`
      : isPixManual
        ? ""
        : podePagarMp
          ? `<div class="Pd_PixInline" id="pd_pix_${idPed}" hidden></div>`
          : "";

    return `
      <div class="Pd_PayCard${isPixManual ? " Pd_PayCard--pixManual" : ""}" data-forn="${idForn}" data-pay-key="${esc(k)}" data-integ="${esc(integracao)}">
        <div class="Pd_PayCardHead"${
          podeGerarPixManual
            ? ` role="button" tabindex="0" data-pagar="${idForn}" data-integ="${esc(integracao)}" data-ped="${idPed}" title="Clique para gerar o PIX"`
            : ""
        }>
          ${logoHtml}
          <div>
            <div class="Pd_PayCardNome">${esc(nomeInteg)}</div>
            <div class="Pd_PayCardForn">${esc(fornNome)}${ped?.numero ? ` · ${esc(ped.numero)}` : ""}</div>
          </div>
        </div>
        ${opcoes.length ? `<div class="Pd_PayOpcoes">${opcoes.join("")}</div>` : ""}
        ${passosPix}
        ${payRow}
        ${pixBox}
      </div>`;
  }

  function mostrarPixManualInline(idPed, dados) {
    const box = document.getElementById(`pd_pixm_${idPed}`);
    if (!box || !dados?.payload) return;
    box.hidden = false;
    const ref = dados.txid || dados.numero_pedido || "";
    box.innerHTML = `
      <p class="Pd_Hint">Referência no PIX: <strong>${esc(ref)}</strong></p>
      <div class="Pd_PixDual">
        <div class="Pd_PixDualCol">
          <strong>1 — QR Code</strong>
          <canvas id="pd_pixm_qr_${idPed}"></canvas>
        </div>
        <div class="Pd_PixDualCol">
          <strong>2 — Copia e cola</strong>
          <code id="pd_pixm_code_${idPed}">${esc(dados.payload)}</code>
          <button type="button" class="Cl_botaoFiltro" data-copiar-pixm="${idPed}">Copiar código</button>
        </div>
      </div>
      <p class="Pd_Hint">Pague o valor exato, anexe o comprovante abaixo e aguarde o fornecedor aprovar. Só depois o pedido fica pago.</p>`;

    const canvas = document.getElementById(`pd_pixm_qr_${idPed}`);
    const colQr = canvas?.closest(".Pd_PixDualCol");
    function falhaQr(msg) {
      if (!colQr) return;
      colQr.innerHTML =
        `<strong>1 — QR Code</strong>` +
        `<p class="Pd_Hint">${esc(msg || "Não foi possível gerar o QR. Use o copia e cola.")}</p>`;
    }
    if (!canvas) {
      falhaQr("Área do QR indisponível.");
    } else if (!window.QRCode?.toCanvas) {
      falhaQr("Biblioteca de QR Code não carregou. Use o copia e cola.");
    } else {
      window.QRCode.toCanvas(
        canvas,
        dados.payload,
        { width: 180, margin: 1, errorCorrectionLevel: "M" },
        (err) => {
          if (err) falhaQr("Falha ao desenhar o QR Code. Use o copia e cola.");
        }
      );
    }

    box.querySelector("[data-copiar-pixm]")?.addEventListener("click", () => {
      navigator.clipboard?.writeText(dados.payload || "");
      if (window.Swal) Swal.fire({ icon: "success", title: "Copiado", timer: 1200, showConfirmButton: false });
    });
  }

  async function enviarComprovantePix(input) {
    const idPed = +input.dataset.uploadComprovante;
    const file = input.files?.[0];
    if (!idPed || !file) return;
    const fd = new FormData();
    fd.append("tipo", "comprovante_pix");
    fd.append("arquivo", file);
    input.disabled = true;
    try {
      const r = await fetch(`/vendedor/pedidos/${idPed}/anexos`, {
        method: "POST",
        credentials: "same-origin",
        body: fd,
      });
      const j = await parseJsonResp(r);
      if (!j.success) throw new Error(j.message || "Erro ao enviar comprovante.");
      const ped = pedidosGrupo.find((p) => p.id === idPed);
      if (ped) {
        ped.status_pagamento = "comprovante_enviado";
        ped.status_vendedor = "aguardando_confirmacao";
        ped.status = "aguardando_confirmacao";
        ped.anexos = ped.anexos || [];
        if (j.anexo) ped.anexos.push(j.anexo);
      }
      if (window.Swal) {
        Swal.fire({
          icon: "success",
          title: "Comprovante enviado",
          text: "Aguardando o fornecedor confirmar o pagamento.",
          confirmButtonColor: "#021F81",
        });
      }
      await renderPayIntegracoes();
    } catch (e) {
      if (window.Swal) Swal.fire({ icon: "error", title: "Comprovante", text: e.message, confirmButtonColor: "#021F81" });
    } finally {
      input.value = "";
      input.disabled = false;
    }
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
      ped.status_vendedor = "pago";
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

  async function reabrirPixManual(idPed) {
    const ped = pedidosGrupo.find((p) => p.id === idPed);
    if (!ped) return;
    if (!freteDocsStatus(ped).ok) {
      await avisarDocsFreteObrigatorios(ped);
      return;
    }
    const ok = window.Swal
      ? (
          await Swal.fire({
            icon: "question",
            title: "Gerar PIX novamente?",
            html: `<p style="text-align:left;margin:0;color:#334155;line-height:1.45">
              Vamos reabrir a cobrança. O pedido só fica <strong>pago</strong> depois que você
              anexar o comprovante e o <strong>fornecedor aprovar</strong>.
            </p>`,
            showCancelButton: true,
            confirmButtonText: "Gerar PIX",
            cancelButtonText: "Cancelar",
            confirmButtonColor: "#021F81",
          })
        ).isConfirmed
      : true;
    if (!ok) return;
    try {
      const r = await fetch(`/vendedor/pedidos/${idPed}/pix-manual/reabrir`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const j = await parseJsonResp(r);
      if (!r.ok || !j.success) throw new Error(j.message || "Não foi possível reabrir o PIX.");
      if (j.pedido) {
        Object.assign(ped, j.pedido);
      } else {
        ped.status_vendedor = "aguardando_pagamento";
        ped.status = "aguardando_pagamento";
        ped.status_pagamento = "pendente";
        ped.pago_em = null;
        ped.meio_pagamento = "pix_manual";
        ped.pix_manual_payload = j.payload;
        ped.pix_manual_txid = j.txid;
      }
      await renderPayIntegracoes();
      if (j.payload) mostrarPixManualInline(idPed, j);
      if (window.Swal) {
        Swal.fire({
          icon: "success",
          title: "PIX gerado",
          text: "Pague, anexe o comprovante e aguarde o fornecedor aprovar.",
          confirmButtonColor: "#021F81",
        });
      }
    } catch (e) {
      if (window.Swal) {
        Swal.fire({ icon: "error", title: "PIX", text: e.message, confirmButtonColor: "#021F81" });
      }
    }
  }

  async function avisarDocsFreteObrigatorios(ped) {
    const docs = freteDocsStatus(ped);
    const lista = (docs.faltando || []).map((f) => `<li>${esc(f)}</li>`).join("");
    if (window.Swal) {
      const r = await Swal.fire({
        icon: "warning",
        title: "Documentos pendentes",
        html: `<p style="text-align:left;margin:0 0 0.6rem;color:#334155;line-height:1.45">
          Para gerar o PIX, anexe em <strong>Frete e NF</strong>:
        </p>
        <ul style="text-align:left;margin:0;padding-left:1.2rem;color:#334155">${lista}</ul>`,
        confirmButtonText: "Ir para Frete e NF",
        showCancelButton: true,
        cancelButtonText: "Fechar",
        confirmButtonColor: "#021F81",
      });
      if (r.isConfirmed && typeof irPainel === "function") {
        pedidoFocoFrete = ped.id;
        irPainel("frete");
      }
    } else {
      alert(`Antes de gerar o PIX, anexe: ${(docs.faltando || []).join(", ")}`);
    }
  }

  async function pagarCard(idForn, integracao, idPed) {
    const ped = pedidosGrupo.find((p) => p.id === idPed);
    if (!ped) return;
    const st = stV(ped);
    const isPixManual = integracao === "pix-manual";
    const okStatusMp = ["importado", "aguardando_pagamento"].includes(st);
    const temComp = (ped.anexos || []).some((a) => a.tipo === "comprovante_pix");
    const okStatusPixManual =
      isPixManual && !temComp && !["entregue", "cancelado"].includes(st);
    if (!okStatusMp && !okStatusPixManual) {
      if (isPixManual && temComp && window.Swal) {
        Swal.fire({
          icon: "info",
          title: "Comprovante já anexado",
          text: "Exclua o comprovante se quiser gerar o PIX de novo.",
          confirmButtonColor: "#021F81",
        });
      }
      return;
    }

    if (isPixManual && !freteDocsStatus(ped).ok) {
      await avisarDocsFreteObrigatorios(ped);
      return;
    }

    const k = payKey(idForn, integracao);
    const meio = meioPagamentoPorFornecedor[k] || (isPixManual ? "pix_manual" : "pix");
    const btn = elPayIntegracoes?.querySelector(`[data-pagar="${idForn}"][data-integ="${integracao}"]`);
    if (btn) btn.disabled = true;

    try {
      const r = await fetch("/vendedor/pedidos/pagar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_pedido: idPed, meio }),
      });
      const j = await parseJsonResp(r);
      if (!j.success) throw new Error(j.message || "Erro ao iniciar pagamento.");

      if (meio === "pix_manual") {
        ped.meio_pagamento = "pix_manual";
        ped.pix_manual_payload = j.payload;
        ped.pix_manual_txid = j.txid;
        if (j.reaberto || j.status_vendedor) {
          ped.status_vendedor = j.status_vendedor || "aguardando_pagamento";
          ped.status = ped.status_vendedor;
          ped.status_pagamento = "pendente";
          ped.pago_em = null;
        }
        await renderPayIntegracoes();
        if (freteDocsStatus(ped).ok) mostrarPixManualInline(idPed, j);
        if (window.Swal) {
          Swal.fire({
            icon: "success",
            title: "PIX gerado",
            text: "Pague, anexe o comprovante e aguarde o fornecedor aprovar.",
            confirmButtonColor: "#021F81",
          });
        }
        return;
      }
      if (meio === "pix") {
        pedidoPagamentoAtual = idPed;
        mostrarPixInline(idPed, j);
        pararPollPix();
        pollPixTimer = setInterval(() => pollPixInline(idPed), 5000);
        pollPixInline(idPed);
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

  function totalFornecedorPedido(ped) {
    if (!ped) return 0;
    const idForn = Number(ped.id_fornecedor);
    const sub = carrinho
      .filter((i) => Number(i.id_fornecedor) === idForn)
      .reduce((s, i) => s + Number(i.valor_drop || 0) * Number(i.quantidade || 0), 0);
    const taxa = Number(taxasPorFornecedor[idForn] || taxasPorFornecedor[String(idForn)] || 0);
    return sub + taxa;
  }

  function freteReferenciaValor() {
    let frete = Object.values(fretePorPedido).reduce((s, f) => s + Number(f.valor || 0), 0);
    if (frete <= 0 && pedidosGrupo?.length) {
      frete = pedidosGrupo.reduce((s, p) => s + Number(p.valor_frete || 0), 0);
    }
    return frete;
  }

  function atualizarResumo() {
    const sub = carrinho.reduce((s, i) => s + i.valor_drop * i.quantidade, 0);
    const fornecedores = [...new Set(carrinho.map((i) => i.id_fornecedor))];
    let taxa = 0;
    fornecedores.forEach((f) => {
      taxa += Number(taxasPorFornecedor[f] || taxasPorFornecedor[String(f)] || 0);
    });
    const freteRef = freteReferenciaValor();
    const totalFornecedor = sub + taxa;
    el.subtotal.textContent = fmt(sub);
    if (elSubtotalMini) elSubtotalMini.textContent = fmt(sub);
    el.taxa.textContent = fmt(taxa);
    el.total.textContent = fmt(totalFornecedor);
    if (elFrete) elFrete.textContent = fmt(freteRef);
    el.linhaTaxa.hidden = taxa <= 0;
    el.itensVazio.hidden = carrinho.length > 0;
    atualizarNavResumos();
    if (painelAtivo === "valores") {
      renderPayIntegracoes();
      window.lucide?.createIcons?.();
    }
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
        preco_venda: item.preco_venda,
        fornecedor_nome: item.fornecedor_nome,
        quantidade: 1,
      });
    }
    renderItens();
    limparFreteLocal();
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

  function margemItem(i) {
    const venda = Number(i.preco_venda || 0);
    const drop = Number(i.valor_drop || 0);
    if (venda <= 0 && drop <= 0) return "—";
    const m = venda - drop;
    const cls = m >= 0 ? "Pd_Margem--ok" : "Pd_Margem--neg";
    return `<span class="Pd_Margem ${cls}">${fmt(m)}</span>`;
  }

  function renderItens() {
    const somenteVer = somenteLeitura || !editavelCampos;
    el.itens.innerHTML = carrinho
      .map(
        (i, idx) => `
      <tr>
        <td>${esc(i.nome)}<br><small>${esc(i.fornecedor_nome || "")}</small></td>
        <td>${esc(i.sku)}</td>
        <td>${fmt(i.valor_drop)}</td>
        <td>${fmt(i.preco_venda)}</td>
        <td>${margemItem(i)}</td>
        <td><input type="number" min="1" value="${i.quantidade}" data-idx="${idx}" class="Pd_QtdInput" style="width:4rem" ${somenteVer ? "readonly" : ""} /></td>
        <td>${somenteVer ? "" : `<button type="button" class="Pd_BtnLink Pd_BtnLink--danger" data-rm="${idx}">Remover</button>`}</td>
      </tr>`
      )
      .join("");

    el.itens.querySelectorAll("[data-rm]").forEach((b) => {
      b.addEventListener("click", () => {
        carrinho.splice(+b.dataset.rm, 1);
        limparFreteLocal();
        renderItens();
      });
    });
    el.itens.querySelectorAll(".Pd_QtdInput").forEach((inp) => {
      inp.addEventListener("change", () => {
        const idx = +inp.dataset.idx;
        carrinho[idx].quantidade = Math.max(1, +inp.value || 1);
        limparFreteLocal();
        atualizarResumo();
      });
    });
    atualizarResumo();
  }

  function abrirModal() {
    idGrupo = null;
    carrinho = [];
    pedidosGrupo = [];
    fretePorPedido = {};
    freteDirty = false;
    pedidoFocoFrete = null;
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
      limparFreteLocal();
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
      const msgErro = j.message || "Erro ao salvar.";
      mostrarMsg(msgErro, true);
      if (window.Swal) {
        Swal.fire({ icon: "error", title: "Salvar pedido", text: msgErro, confirmButtonColor: "#021F81" });
      }
      if (elBtnSalvar) elBtnSalvar.disabled = false;
      if (elBtnConfirmar) elBtnConfirmar.disabled = false;
      return null;
    }
    idGrupo = j.id_grupo;
    try {
      const grupo = await carregarGrupo(idGrupo);
      pedidosGrupo = grupo.pedidos || [];
      sincronizarFreteDoGrupo();
      atualizarNavFrete();
    } catch {
      /* frete/docs opcionais após salvar */
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
        (stV(p) === "rascunho" ||
          stV(p) === "aguardando_pagamento" ||
          stV(p) === "aguardando_confirmacao") &&
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
      if (j.success) {
        const idG = j.pedido?.id_grupo;
        if (idG) {
          await abrirModalEdicao({ idGrupo: idG, painelInicial: "valores" });
        } else {
          await abrirModalEdicao({ idPedido: idPed, painelInicial: "valores" });
        }
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

  async function enviarEmailTesteLayout() {
    const idPed = (pedidoFocoFrete || pedidosGrupo.find((p) => p.id)?.id) || null;
    if (!idPed) {
      mostrarMsg("Abra um pedido salvo para testar o e-mail.", true);
      return;
    }
    elBtnEmailTeste.disabled = true;
    try {
      const r = await fetch(`/vendedor/pedidos/${idPed}/email-teste`, {
        method: "POST",
        headers: { Accept: "application/json" },
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) {
        throw new Error(j.message || "Falha ao enviar e-mail de teste.");
      }
      if (window.Swal) {
        Swal.fire({
          icon: "success",
          title: "E-mail teste",
          text: j.message || "Enviado para hazael@h74.com.br",
          confirmButtonColor: "#021F81",
        });
      } else {
        mostrarMsg(j.message || "E-mail de teste enviado.", false);
      }
    } catch (e) {
      if (window.Swal) {
        Swal.fire({
          icon: "error",
          title: "E-mail teste",
          text: e.message || "Erro",
          confirmButtonColor: "#021F81",
        });
      } else {
        mostrarMsg(e.message || "Erro", true);
      }
    } finally {
      elBtnEmailTeste.disabled = false;
    }
  }

  document.getElementById("pd_btnNovo")?.addEventListener("click", abrirModal);
  document.getElementById("pd_btnFechar")?.addEventListener("click", fecharModal);
  elBtnCancelar?.addEventListener("click", cancelarPedidoGrupo);
  elBtnEmailTeste?.addEventListener("click", enviarEmailTesteLayout);

  document.querySelectorAll(".Pd_WizNavItem").forEach((btn) => {
    btn.addEventListener("click", () => irPainel(btn.dataset.painel));
  });

  ["pd_cliNome", "pd_cliDoc", "pd_cliEmail", "pd_cliTel", "pd_cep", "pd_logradouro",
    "pd_numero", "pd_compl", "pd_bairro", "pd_cidade", "pd_uf"].forEach((id) => {
    document.getElementById(id)?.addEventListener("input", () => {
      if (["pd_cep", "pd_logradouro", "pd_numero", "pd_compl", "pd_bairro", "pd_cidade", "pd_uf"].includes(id)) {
        limparFreteLocal();
      }
      atualizarNavResumos();
    });
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
    if (!idG && !idPed) {
      if (window.Swal) {
        Swal.fire({ icon: "info", title: "Pedido", text: "Pedido indisponível.", confirmButtonColor: "#021F81" });
      }
      return;
    }
    if (acao === "editar") {
      const st = btn.dataset.status || "";
      const painel = ["importado", "aguardando_pagamento", "pago"].includes(st) ? "valores" : "produto";
      abrirModalEdicao({
        idGrupo: idG || null,
        idPedido: idG ? null : idPed,
        painelInicial: painel,
        idPedidoFoco: idPed,
      });
      return;
    }
    if (acao === "nf" || acao === "etiqueta") {
      abrirModalEdicao({
        idGrupo: idG || null,
        idPedido: idG ? null : idPed,
        painelInicial: "frete",
        idPedidoFoco: idPed,
      });
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
