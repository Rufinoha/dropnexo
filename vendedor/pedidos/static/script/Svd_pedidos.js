(function () {
  const STATUS_LABEL_VENDEDOR = {
    rascunho: "Rascunho",
    importado: "Importado",
    aguardando_pagamento: "Aguardando pagamento",
    pago: "Pago",
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
  let pedidoFocoAnexo = null;
  let tipoAnexoFoco = null;
  /** @type {Record<string, string>} */
  let meioPagamentoPorFornecedor = {};
  /** @type {Record<number, {opcoes?: Array, escolhido?: object, valor?: number, nome?: string}>} */
  let fretePorPedido = {};
  /** @type {Record<number, 'me'|'manual'>} */
  let freteModoPorPedido = {};
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
        <td><strong>${esc(p.numero)}</strong>${p.numero_grupo ? `<br><small>${esc(p.numero_grupo)}</small>` : ""}</td>
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

  function inferirModoFrete(ped) {
    if (freteModoPorPedido[ped.id]) return freteModoPorPedido[ped.id];
    if (ped.frete_modo === "manual" || ped.me_etiqueta_status === "manual") return "manual";
    if (ped.me_service_id) return "me";
    const temEtiqueta = (ped.anexos || []).some((a) => a.tipo === "etiqueta");
    if (temEtiqueta) return "manual";
    return meFreteConectado ? "me" : "manual";
  }

  function sincronizarModoFreteDoGrupo() {
    (pedidosGrupo || []).forEach((p) => {
      freteModoPorPedido[p.id] = inferirModoFrete(p);
    });
  }

  function sincronizarFreteDoGrupo() {
    fretePorPedido = {};
    (pedidosGrupo || []).forEach((p) => {
      if (p.valor_frete > 0 || p.me_service_id || p.frete_modo === "manual" || p.me_etiqueta_status === "manual") {
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
    if (id === "anexos") renderAnexos();
  }

  function aplicarEstadoWizard(grupo) {
    editavelCampos = grupo ? !!grupo.editavel : true;
    const bloqueadoIntegracao = pedidosGrupo.some((p) => (p.origem || "manual") !== "manual");
    const bloqueadoPago = pedidosGrupo.some((p) =>
      ["pago", "em_expedicao", "entregue"].includes(stV(p))
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
    sincronizarFreteDoGrupo();
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

  async function carregarContextoPedido(idPed) {
    const r = await fetch(`/vendedor/pedidos/${idPed}/contexto`, { credentials: "same-origin" });
    const j = await parseJsonResp(r);
    if (!j.success) throw new Error(j.message || "Erro ao carregar pedido.");
    return j.grupo;
  }

  async function abrirModalEdicao(opts = {}) {
    const { idGrupo: gid, idPedido: idPed, painelInicial = "produto", idPedidoFoco = null, tipoAnexo = null } = opts;
    if (!gid && !idPed) return;

    mostrarMsg("");
    pedidoFocoAnexo = idPedidoFoco || idPed || null;
    tipoAnexoFoco = tipoAnexo;

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
    const st = stV(ped);
    const podeEnviar =
      st !== "cancelado" &&
      !["pago", "em_expedicao", "entregue"].includes(st) &&
      ((ped.origem || "manual") === "manual" || ["importado", "aguardando_pagamento"].includes(st));
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
            <br><small>${esc(p.fornecedor_nome || "")} · ${badge(stV(p))} · Comprador: ${badge(stC(p), "comprador")}</small>
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
      if (painelAtivo === "frete") renderFretePainel();
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
      return j;
    } catch {
      meFreteConectado = false;
      return { conectado: false };
    }
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

  async function cotarFretePedido(idPed) {
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
      const card = elFreteConteudo?.querySelector(`[data-frete-ped="${idPed}"]`);
      const box = card?.querySelector(".Pd_FreteOpcoes");
      const ped = pedidosGrupo.find((p) => p.id === idPed);
      if (box && ped) {
        box.innerHTML = renderFreteOpcoes(ped, j.opcoes);
        bindFreteOpcoes();
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
      elFreteConteudo?.querySelectorAll(`[data-frete-ped="${idPed}"] .Pd_FreteOpcao`).forEach((lbl) => {
        lbl.classList.toggle("is-selected", +lbl.querySelector("input")?.value === serviceId);
      });
      atualizarResumo();
    } catch (e) {
      mostrarFreteAviso(e.message || "Erro ao salvar frete.", true);
    }
  }

  function etiquetaStatusHtml(ped) {
    const modo = inferirModoFrete(ped);
    if (modo === "manual") {
      const etiquetas = (ped.anexos || []).filter((a) => a.tipo === "etiqueta");
      if (!etiquetas.length) return "";
      const rastreio = ped.codigo_rastreio || "";
      return `<p class="Pd_EtiquetaStatus Pd_EtiquetaStatus--gerada">Etiqueta anexada (envio próprio)${rastreio ? ` — rastreio <strong>${esc(rastreio)}</strong>` : ""}</p>`;
    }
    if (!ped.me_service_id) return "";
    const st = (ped.me_etiqueta_status || "").toLowerCase();
    const rastreio = ped.codigo_rastreio || "";
    const proto = ped.me_protocol || "";
    let txt = "";
    if (st === "gerada") {
      txt = `Etiqueta gerada${rastreio ? ` — rastreio <strong>${esc(rastreio)}</strong>` : ""}${proto ? ` <small>(${esc(proto)})</small>` : ""}`;
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
    const r = await fetch(`/vendedor/pedidos/${idPed}/frete/modo`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ modo: modo === "manual" ? "manual" : "melhor_envio" }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao alterar modo de frete.");
    freteModoPorPedido[idPed] = modo;
    const ped = pedidosGrupo.find((p) => p.id === idPed);
    if (ped) {
      ped.frete_modo = modo === "manual" ? "manual" : "melhor_envio";
      ped.me_etiqueta_status = modo === "manual" ? "manual" : "";
      if (modo !== "manual") {
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
    const dis = editavelCampos ? "" : "disabled";
    const meHint = meFreteConectado ? "" : ' title="Conecte o Melhor Envio em Integrações → Frete"';
    return `
      <div class="Pd_FreteModo" role="tablist" aria-label="Forma de envio">
        <button type="button" class="Pd_FreteModoBtn${modo === "me" ? " is-active" : ""}" data-frete-modo="me" data-ped="${ped.id}" ${dis}${meHint}>Melhor Envio</button>
        <button type="button" class="Pd_FreteModoBtn${modo === "manual" ? " is-active" : ""}" data-frete-modo="manual" data-ped="${ped.id}" ${dis}>Minha etiqueta</button>
      </div>`;
  }

  function renderFreteManual(ped) {
    const etiquetas = (ped.anexos || []).filter((a) => a.tipo === "etiqueta");
    const inpId = `pd_frete_etq_inp_${ped.id}`;
    const pode = editavelCampos && stV(ped) === "rascunho";
    const valorRef = Number(ped.valor_frete || fretePorPedido[ped.id]?.valor || 0);
    return `
      <div class="Pd_FreteManual">
        <p class="Pd_Hint">Anexe a etiqueta em PDF de outra transportadora (Correios, Jadlog, etc.). O fornecedor verá o arquivo nos anexos do pedido.</p>
        <div class="Pd_AnexoUpload">
          <input type="file" id="${inpId}" class="Pd_AnexoInput" hidden accept=".pdf,.png,.jpg,.jpeg,.webp" data-frete-upload="${ped.id}" ${pode ? "" : "disabled"} />
          ${pode ? `<label for="${inpId}" class="Cl_botaoFiltro Pd_AnexoBtn">Escolher PDF ou imagem</label>` : ""}
          <span class="Pd_Hint">Máx. 5 MB</span>
        </div>
        <ul class="Pd_AnexoItens Pd_FreteEtqLista">
          ${etiquetas.length
            ? etiquetas
                .map(
                  (a) => `
            <li>
              <a href="/vendedor/pedidos/anexos/arquivo?caminho=${encodeURIComponent(a.caminho)}" target="_blank" rel="noopener">${esc(a.nome_original)}</a>
              ${pode ? `<button type="button" class="Pd_BtnLink Pd_BtnLink--danger" data-del-anexo="${a.id}">Remover</button>` : ""}
            </li>`
                )
                .join("")
            : '<li class="Pd_Hint">Nenhuma etiqueta anexada ainda.</li>'}
        </ul>
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

  function renderFreteMe(ped, frete, escolhido, opcoesHtml) {
    if (!meFreteConectado) {
      return `<p class="Pd_Hint">Conecte o <strong>Melhor Envio</strong> em Integrações → Frete para cotar e comprar etiquetas automaticamente.</p>`;
    }
    return `
      <div class="Pd_FreteMeHead">
        <button type="button" class="Cl_botaoFiltro" data-cotar="${ped.id}" ${editavelCampos ? "" : "disabled"}>Cotar</button>
      </div>
      <div class="Pd_FreteOpcoes">${opcoesHtml}</div>`;
  }

  async function enviarEtiquetaFrete(input) {
    const idPed = +input.dataset.freteUpload;
    const file = input.files?.[0];
    if (!idPed || !file) return;
    const fd = new FormData();
    fd.append("tipo", "etiqueta");
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
      await setFreteModo(idPed, "manual");
      const ped = pedidosGrupo.find((p) => p.id === idPed);
      if (ped) {
        ped.anexos = ped.anexos || [];
        ped.anexos.push(j.anexo);
      }
      await renderFretePainel();
      atualizarNavAnexos();
      if (window.Swal) {
        Swal.fire({ icon: "success", title: "Etiqueta anexada", timer: 1600, showConfirmButton: false });
      }
    } catch (e) {
      if (window.Swal) Swal.fire({ icon: "error", title: "Etiqueta", text: e.message, confirmButtonColor: "#021F81" });
    } finally {
      input.value = "";
      input.disabled = false;
    }
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
            : '<p class="Pd_Hint">Clique em Cotar para ver as opções do Melhor Envio.</p>';
        const etiquetaHtml = etiquetaStatusHtml(ped);
        const corpo =
          modo === "manual"
            ? renderFreteManual(ped)
            : renderFreteMe(ped, frete, escolhido, opcoesHtml);
        return `
        <article class="Pd_FreteCard" data-frete-ped="${ped.id}" data-frete-modo-atual="${modo}">
          <div class="Pd_FreteCardHead">
            <div>
              <h5>${esc(ped.fornecedor_nome || "Fornecedor")}</h5>
              <small class="Pd_Hint">Pedido ${esc(ped.numero || "")}</small>
            </div>
          </div>
          ${renderFreteModoTabs(ped, modo)}
          ${etiquetaHtml}
          <div class="Pd_FreteCorpo">${corpo}</div>
        </article>`;
      })
      .join("");

    elFreteConteudo.querySelectorAll("[data-frete-modo]").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const idPed = +btn.dataset.ped;
        const modo = btn.dataset.freteModo;
        if (inferirModoFrete(pedidosGrupo.find((p) => p.id === idPed) || {}) === modo) return;
        btn.disabled = true;
        try {
          await setFreteModo(idPed, modo);
          await renderFretePainel();
          if (modo === "me" && meFreteConectado && editavelCampos) {
            await cotarFretePedido(idPed);
          }
        } catch (e) {
          Swal.fire({ icon: "error", title: "Frete", text: e.message, confirmButtonColor: "#021F81" });
        } finally {
          btn.disabled = false;
        }
      });
    });

    elFreteConteudo.querySelectorAll("[data-cotar]").forEach((btn) => {
      btn.addEventListener("click", () => cotarFretePedido(+btn.dataset.cotar));
    });
    elFreteConteudo.querySelectorAll("[data-frete-upload]").forEach((inp) => {
      inp.addEventListener("change", () => enviarEtiquetaFrete(inp));
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
            await renderFretePainel();
            if (painelAtivo === "anexos") renderAnexos();
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
    if (pedidosGrupo.length && meFreteConectado && editavelCampos) {
      for (const ped of pedidosGrupo) {
        if (inferirModoFrete(ped) !== "me") continue;
        if (!fretePorPedido[ped.id]?.opcoes?.length && !fretePorPedido[ped.id]?.escolhido) {
          await cotarFretePedido(ped.id);
        }
      }
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
      btn.addEventListener("click", () =>
        pagarCard(+btn.dataset.pagar, btn.dataset.integ, +btn.dataset.ped)
      );
    });

    elPayIntegracoes.querySelectorAll("[data-upload-comprovante]").forEach((inp) => {
      inp.addEventListener("change", () => enviarComprovantePix(inp));
    });

    cards.forEach(({ ped }) => {
      if (ped?.pix_manual_payload && document.getElementById(`pd_pixm_${ped.id}`)) {
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
    const pedidoPago = ped && ["pago", "em_expedicao", "entregue"].includes(stV(ped));
    const aguardando = stV(ped) === "aguardando_pagamento";
    const importado = stV(ped) === "importado";
    const rascunho = stV(ped) === "rascunho";
    const comprovanteEnviado = ped?.status_pagamento === "comprovante_enviado";
    const pixManualAtivo = ped?.meio_pagamento === "pix_manual" || ped?.pix_manual_payload;

    let statusHtml = "";
    if (pedidoPago) {
      const quando = ped.pago_em ? new Date(ped.pago_em).toLocaleString("pt-BR") : "";
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pago">${badge("pago")} Pagamento confirmado${quando ? ` · ${esc(quando)}` : ""}</div>`;
    } else if (comprovanteEnviado && isPixManual) {
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pendente">Comprovante enviado — aguardando validação do fornecedor</div>`;
    } else if (importado) {
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pendente">${badge("importado")} Cliente já pagou no canal — prepare frete e pague o fornecedor · ${fmt(ped.valor_total)}</div>`;
    } else if (aguardando) {
    } else if (rascunho) {
      statusHtml = `<div class="Pd_PayStatus Pd_PayStatus--pendente">${badge("rascunho")} Confirme o pedido para pagar</div>`;
    }

    const logoHtml = icone
      ? `<img class="Pd_PayCardLogo" src="${esc(icone)}" alt="" />`
      : `<span class="Pd_PayCardLogo Pd_PayCardLogo--txt" style="background:#32BCAD;color:#fff">PX</span>`;

    const opcoes = [];
    if (isPixManual) {
      opcoes.push(`
        <label class="Pd_PayOpcao Pd_PayOpcao--pix${pref === "pix_manual" || !pref ? " is-selected" : ""}">
          <input type="radio" name="pd_meio_${k}" value="pix_manual"${pref === "pix_manual" || !pref ? " checked" : ""} />
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

    const podePagar = (aguardando || importado) && !pedidoPago && !comprovanteEnviado;
    const idPed = ped?.id || 0;
    const payRow = `
      <div class="Pd_PayRow">
        ${statusHtml || ""}
        ${podePagar ? `<button type="button" class="Cl_BtnSalvar Pd_BtnPagar" data-pagar="${idForn}" data-integ="${esc(integracao)}" data-ped="${idPed}">Pagar agora</button>` : ""}
      </div>`;

    const pixBox = isPixManual && ped && (pixManualAtivo || podePagar)
      ? `<div class="Pd_PixInline" id="pd_pixm_${ped.id}" ${pixManualAtivo ? "" : "hidden"}></div>
         ${pixManualAtivo && !pedidoPago && !comprovanteEnviado ? `
         <div class="Pd_ComprovanteUpload">
           <label class="Pd_Hint">Após pagar, anexe o comprovante:</label>
           <input type="file" class="Pd_AnexoInput" accept=".pdf,.png,.jpg,.jpeg,.webp" data-upload-comprovante="${ped.id}" />
         </div>` : ""}`
      : isPixManual
        ? ""
        : podePagar
          ? `<div class="Pd_PixInline" id="pd_pix_${idPed}" hidden></div>`
          : "";

    return `
      <div class="Pd_PayCard" data-forn="${idForn}" data-pay-key="${esc(k)}" data-integ="${esc(integracao)}">
        <div class="Pd_PayCardHead">
          ${logoHtml}
          <div>
            <div class="Pd_PayCardNome">${esc(nomeInteg)}</div>
            <div class="Pd_PayCardForn">${esc(fornNome)}${ped?.numero ? ` · ${esc(ped.numero)}` : ""}</div>
          </div>
        </div>
        ${(aguardando || rascunho || !ped) && opcoes.length ? `<div class="Pd_PayOpcoes">${opcoes.join("")}</div>` : ""}
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
      <p class="Pd_Hint">Pague o valor exato e anexe o comprovante abaixo. O fornecedor validará manualmente.</p>`;

    const canvas = document.getElementById(`pd_pixm_qr_${idPed}`);
    if (canvas && window.QRCode) {
      window.QRCode.toCanvas(canvas, dados.payload, { width: 180, margin: 1 }, () => {});
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
      if (ped) ped.status_pagamento = "comprovante_enviado";
      if (window.Swal) {
        Swal.fire({ icon: "success", title: "Comprovante enviado", text: "Aguardando validação do fornecedor.", confirmButtonColor: "#021F81" });
      }
      renderPayIntegracoes();
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

  async function pagarCard(idForn, integracao, idPed) {
    const ped = pedidosGrupo.find((p) => p.id === idPed);
    if (!ped || !["importado", "aguardando_pagamento"].includes(stV(ped))) return;

    const k = payKey(idForn, integracao);
    const meio = meioPagamentoPorFornecedor[k] || (integracao === "pix-manual" ? "pix_manual" : "pix");
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
        mostrarPixManualInline(idPed, j);
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

  function atualizarResumo() {
    const sub = carrinho.reduce((s, i) => s + i.valor_drop * i.quantidade, 0);
    const fornecedores = [...new Set(carrinho.map((i) => i.id_fornecedor))];
    let taxa = 0;
    fornecedores.forEach((f) => {
      taxa += Number(taxasPorFornecedor[f] || taxasPorFornecedor[String(f)] || 0);
    });
    const frete = Object.values(fretePorPedido).reduce((s, f) => s + Number(f.valor || 0), 0);
    el.subtotal.textContent = fmt(sub);
    if (elSubtotalMini) elSubtotalMini.textContent = fmt(sub);
    el.taxa.textContent = fmt(taxa);
    el.total.textContent = fmt(sub + taxa);
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
      mostrarMsg(j.message || "Erro ao salvar.", true);
      if (elBtnSalvar) elBtnSalvar.disabled = false;
      if (elBtnConfirmar) elBtnConfirmar.disabled = false;
      return null;
    }
    idGrupo = j.id_grupo;
    try {
      const grupo = await carregarGrupo(idGrupo);
      pedidosGrupo = grupo.pedidos || [];
      sincronizarFreteDoGrupo();
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
        (stV(p) === "rascunho" || stV(p) === "aguardando_pagamento") &&
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

  document.getElementById("pd_btnNovo")?.addEventListener("click", abrirModal);
  document.getElementById("pd_btnFechar")?.addEventListener("click", fecharModal);
  elBtnCancelar?.addEventListener("click", cancelarPedidoGrupo);

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
    if (acao === "nf") {
      abrirModalEdicao({
        idGrupo: idG || null,
        idPedido: idG ? null : idPed,
        painelInicial: "anexos",
        idPedidoFoco: idPed,
        tipoAnexo: "nf",
      });
      return;
    }
    if (acao === "etiqueta") {
      abrirModalEdicao({
        idGrupo: idG || null,
        idPedido: idG ? null : idPed,
        painelInicial: "anexos",
        idPedidoFoco: idPed,
        tipoAnexo: "etiqueta",
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
