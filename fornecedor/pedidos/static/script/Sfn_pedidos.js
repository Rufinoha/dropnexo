(function () {
  const API = "/fornecedor/pedidos";
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
  let selecionados = new Set();
  let paginaAtual = 1;
  const porPagina = 20;
  let totalPaginas = 1;

  const PRECISA_ACAO = ["importado", "aguardando_pagamento", "aguardando_confirmacao", "pago"];
  const MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho", "agosto", "setembro", "outubro", "novembro", "dezembro"];
  const SEMANA = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"];

  function hojeDia() {
    const n = new Date();
    return new Date(n.getFullYear(), n.getMonth(), n.getDate());
  }
  function addDias(d, n) {
    return new Date(d.getFullYear(), d.getMonth(), d.getDate() + n);
  }
  function inicioMes(d) {
    return new Date(d.getFullYear(), d.getMonth(), 1);
  }
  function fimMes(d) {
    return new Date(d.getFullYear(), d.getMonth() + 1, 0);
  }
  function addMeses(d, n) {
    return new Date(d.getFullYear(), d.getMonth() + n, 1);
  }
  function mesmoDia(a, b) {
    return !!(a && b && a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate());
  }
  function cmpDia(a, b) {
    return a.getTime() - b.getTime();
  }
  function fmtDia(d) {
    const z = (n) => String(n).padStart(2, "0");
    return `${z(d.getDate())}/${z(d.getMonth() + 1)}/${d.getFullYear()}`;
  }
  function diaDePedido(iso) {
    if (!iso) return null;
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return null;
    return new Date(d.getFullYear(), d.getMonth(), d.getDate());
  }

  const PRESETS = [
    { id: "hoje", label: "Hoje", range: () => { const h = hojeDia(); return [h, h]; } },
    { id: "ontem", label: "Ontem", range: () => { const o = addDias(hojeDia(), -1); return [o, o]; } },
    { id: "7", label: "Últimos 7 dias", range: () => [addDias(hojeDia(), -6), hojeDia()] },
    { id: "30", label: "Últimos 30 dias", range: () => [addDias(hojeDia(), -29), hojeDia()] },
    { id: "mes", label: "Este mês", range: () => [inicioMes(hojeDia()), fimMes(hojeDia())] },
    { id: "mes_hoje", label: "Mês atual (até hoje)", range: () => [inicioMes(hojeDia()), hojeDia()] },
    { id: "mes_passado", label: "Mês passado", range: () => { const p = addMeses(hojeDia(), -1); return [inicioMes(p), fimMes(p)]; } },
    { id: "3m", label: "Últimos 3 meses", range: () => [inicioMes(addMeses(hojeDia(), -2)), hojeDia()] },
    { id: "ano", label: "Este ano", range: () => [new Date(hojeDia().getFullYear(), 0, 1), hojeDia()] },
  ];

  function presetInicial() {
    const p = PRESETS.find((x) => x.id === "mes_hoje");
    const [ini, fim] = p.range();
    return { ini, fim, preset: p.id };
  }

  let periodoAplicado = presetInicial();
  let rascunho = null;
  let calMes = inicioMes(hojeDia());
  let hoverDia = null;

  function presetQueCombina(ini, fim) {
    if (!ini && !fim) return "todos";
    if (!ini || !fim) return "";
    for (const p of PRESETS) {
      const [a, b] = p.range();
      if (mesmoDia(a, ini) && mesmoDia(b, fim)) return p.id;
    }
    return "";
  }

  function nomePreset(id) {
    if (id === "todos") return "Todo o período";
    if (!id) return "Personalizado";
    return PRESETS.find((p) => p.id === id)?.label || "Personalizado";
  }

  const pagEl = {
    wrap: document.getElementById("pd_fn_paginacao"),
    paginaAtual: document.getElementById("pd_fn_paginaAtual"),
    totalPaginas: document.getElementById("pd_fn_totalPaginas"),
    totalRegistros: document.getElementById("pd_fn_totalRegistros"),
    btnPrimeiro: document.getElementById("pd_fn_btnPrimeiro"),
    btnAnterior: document.getElementById("pd_fn_btnAnterior"),
    btnProximo: document.getElementById("pd_fn_btnProximo"),
    btnUltimo: document.getElementById("pd_fn_btnUltimo"),
  };

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

  function pedidosDaPagina() {
    const rows = pedidosFiltrados();
    totalPaginas = Math.max(1, Math.ceil(rows.length / porPagina));
    if (paginaAtual > totalPaginas) paginaAtual = totalPaginas;
    if (paginaAtual < 1) paginaAtual = 1;
    const ini = (paginaAtual - 1) * porPagina;
    return { todos: rows, pagina: rows.slice(ini, ini + porPagina) };
  }

  function renderPaginacao(total) {
    if (!pagEl.wrap) return;
    pagEl.wrap.hidden = total === 0;
    if (pagEl.paginaAtual) pagEl.paginaAtual.textContent = String(paginaAtual);
    if (pagEl.totalPaginas) pagEl.totalPaginas.textContent = String(totalPaginas);
    if (pagEl.totalRegistros) pagEl.totalRegistros.textContent = String(total);
    const noInicio = paginaAtual <= 1;
    const noFim = paginaAtual >= totalPaginas;
    if (pagEl.btnPrimeiro) pagEl.btnPrimeiro.disabled = noInicio;
    if (pagEl.btnAnterior) pagEl.btnAnterior.disabled = noInicio;
    if (pagEl.btnProximo) pagEl.btnProximo.disabled = noFim;
    if (pagEl.btnUltimo) pagEl.btnUltimo.disabled = noFim;
  }

  function atualizarBulkBar() {
    const bar = document.getElementById("pd_fn_bulk");
    const countEl = document.getElementById("pd_fn_bulk_count");
    const checkAll = document.getElementById("pd_fn_check_all");
    const n = selecionados.size;
    if (bar) bar.hidden = n === 0;
    if (countEl) countEl.textContent = n === 1 ? "1 selecionado" : `${n} selecionados`;
    if (checkAll) {
      const visiveis = pedidosDaPagina().pagina.map((p) => p.id);
      const todosMarcados = visiveis.length > 0 && visiveis.every((id) => selecionados.has(id));
      checkAll.checked = todosMarcados;
      checkAll.indeterminate = n > 0 && !todosMarcados;
    }
  }

  function limparSelecao() {
    selecionados.clear();
    atualizarBulkBar();
    listaEl?.querySelectorAll(".PdFn_RowCheck").forEach((c) => {
      c.checked = false;
    });
    listaEl?.querySelectorAll(".PdFn_Card").forEach((c) => c.classList.remove("is-selected"));
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

  function noPeriodo(p) {
    if (!periodoAplicado?.ini || !periodoAplicado?.fim) return true;
    const d = diaDePedido(p.criado_em);
    if (!d) return false;
    return cmpDia(d, periodoAplicado.ini) >= 0 && cmpDia(d, periodoAplicado.fim) <= 0;
  }

  function pedidosNoPeriodo() {
    return todosPedidos.filter(noPeriodo);
  }

  function pedidosFiltrados() {
    const q = (buscaEl?.value || "").trim().toLowerCase();
    return pedidosNoPeriodo().filter((p) => {
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
    atualizarStats(pedidosNoPeriodo());
    atualizarAvisoFora();
    pintarPeriodoBtn();
    const { todos, pagina } = pedidosDaPagina();
    const idsFiltrados = new Set(todos.map((p) => p.id));
    [...selecionados].forEach((id) => {
      if (!idsFiltrados.has(id)) selecionados.delete(id);
    });
    renderPaginacao(todos.length);
    if (!todos.length) {
      listaEl.innerHTML = "";
      if (vazio) {
        vazio.hidden = false;
        const forte = vazio.querySelector("strong");
        if (forte) {
          forte.textContent = periodoAplicado?.ini
            ? "Nenhum pedido neste período"
            : "Nenhum pedido neste filtro";
        }
      }
      atualizarBulkBar();
      return;
    }
    if (vazio) vazio.hidden = true;
    listaEl.innerHTML = pagina
      .map((p) => {
        const st = stV(p);
        const urgent = st === "aguardando_confirmacao";
        const ready = st === "pago";
        const on = selecionados.has(p.id);
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
          on ? "is-selected" : "",
        ]
          .filter(Boolean)
          .join(" ");
        return `
      <div class="${cardCls}" data-row-id="${p.id}">
        <label class="PdFn_RowCheckWrap" title="Selecionar">
          <input type="checkbox" class="PdFn_RowCheck" data-check-id="${p.id}" ${on ? "checked" : ""} />
        </label>
        <button type="button" class="PdFn_CardHit" data-id="${p.id}">
          ${thumbsHtml(p)}
          <div class="PdFn_CardMain">
            <div class="PdFn_CardTop">
              <span class="PdFn_CardNum">${esc(p.numero)}</span>
              ${orig ? `<span class="PdFn_Origem">${esc(orig)}</span>` : ""}
              ${badge(st)}
            </div>
            <p class="PdFn_CardMeta"><strong>${esc(p.vendedor_nome || "Vendedor")}</strong> · ${esc(p.cliente_nome || "Cliente")} · ${esc(data)}</p>
          </div>
          <div class="PdFn_CardSide">
            <span class="PdFn_CardTotal">${fmt(p.valor_total)}</span>
            <span class="PdFn_CardCta">${esc(ctaLista(st))} →</span>
          </div>
        </button>
      </div>`;
      })
      .join("");

    listaEl.querySelectorAll(".PdFn_CardHit[data-id]").forEach((b) => {
      b.addEventListener("click", () => abrir(+b.dataset.id));
    });
    listaEl.querySelectorAll(".PdFn_RowCheck").forEach((c) => {
      c.addEventListener("click", (e) => e.stopPropagation());
      c.addEventListener("change", () => {
        const id = +c.getAttribute("data-check-id");
        if (c.checked) selecionados.add(id);
        else selecionados.delete(id);
        const row = listaEl.querySelector(`[data-row-id="${id}"]`);
        row?.classList.toggle("is-selected", c.checked);
        atualizarBulkBar();
      });
    });
    atualizarBulkBar();
  }

  async function carregar() {
    const r = await fetch(`${API}/dados`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    todosPedidos = j.pedidos || [];
    renderLista();
  }

  async function loteAcao(tipo) {
    const ids = [...selecionados];
    if (!ids.length) return;

    if (tipo === "pdf_etq" || tipo === "pdf_docs") {
      const modo = tipo === "pdf_docs" ? "etiquetas_nf" : "etiquetas";
      const r = await fetch(`${API}/lote/pdf`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids, modo }),
      });
      const ct = (r.headers.get("content-type") || "").toLowerCase();
      if (!r.ok || !ct.includes("pdf")) {
        let msg = "Não foi possível gerar o PDF.";
        try {
          const j = await r.json();
          if (j.message) msg = j.message;
        } catch (_) {}
        if (window.Swal) await Swal.fire("Atenção", msg, "warning");
        else alert(msg);
        return;
      }
      const blob = await r.blob();
      const url = URL.createObjectURL(blob);
      const w = window.open(url, "_blank");
      if (!w) {
        const a = document.createElement("a");
        a.href = url;
        a.download = modo === "etiquetas_nf" ? "etiquetas_e_notas.pdf" : "etiquetas.pdf";
        a.click();
      } else {
        setTimeout(() => {
          try {
            w.focus();
            w.print();
          } catch (_) {}
        }, 600);
      }
      // Imprimiu etiqueta → Expedido automático
      try {
        const re = await fetch(`${API}/lote/expedir`, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ ids }),
        });
        const je = await re.json();
        if (window.Swal) {
          await Swal.fire(
            je.success ? "Expedido" : "Atenção",
            je.message || (je.success ? "Pedidos marcados em expedição." : "Alguns pedidos não puderam ser expedidos."),
            je.success ? "success" : "warning"
          );
        }
      } catch (_) {}
      limparSelecao();
      await carregar();
      return;
    }

    const labels = {
      expedir: {
        title: "Marcar em expedição?",
        html: "Os pedidos <strong>pagos</strong> com etiqueta e NF serão marcados como <strong>Em expedição</strong>.",
        ok: "Sim, expedir",
        url: `${API}/lote/expedir`,
      },
      entregue: {
        title: "Marcar como entregue?",
        html: "Pedidos pagos ou em expedição serão marcados como <strong>entregue</strong>.",
        ok: "Sim, entregue",
        url: `${API}/lote/entregue`,
      },
    };
    const cfg = labels[tipo];
    if (!cfg) return;

    const conf = window.Swal
      ? await Swal.fire({
          icon: "question",
          title: cfg.title,
          html: `${cfg.html}<br><br><strong>${ids.length}</strong> pedido(s) selecionado(s).`,
          showCancelButton: true,
          confirmButtonText: cfg.ok,
          cancelButtonText: "Cancelar",
          confirmButtonColor: "#021F81",
        })
      : { isConfirmed: confirm(cfg.title) };
    if (!conf.isConfirmed) return;

    const r = await fetch(cfg.url, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids }),
    });
    const j = await r.json();
    if (window.Swal) {
      await Swal.fire(
        j.success ? "Pronto" : "Atenção",
        j.message || (j.success ? "Atualizado." : "Falha."),
        j.success ? "success" : "warning"
      );
    }
    limparSelecao();
    await carregar();
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
    paginaAtual = 1;
    renderLista();
  });

  let buscaTimer = null;
  buscaEl?.addEventListener("input", () => {
    clearTimeout(buscaTimer);
    buscaTimer = setTimeout(() => {
      paginaAtual = 1;
      renderLista();
    }, 160);
  });

  pagEl.btnPrimeiro?.addEventListener("click", () => {
    paginaAtual = 1;
    renderLista();
  });
  pagEl.btnAnterior?.addEventListener("click", () => {
    if (paginaAtual > 1) {
      paginaAtual -= 1;
      renderLista();
    }
  });
  pagEl.btnProximo?.addEventListener("click", () => {
    if (paginaAtual < totalPaginas) {
      paginaAtual += 1;
      renderLista();
    }
  });
  pagEl.btnUltimo?.addEventListener("click", () => {
    paginaAtual = totalPaginas;
    renderLista();
  });

  document.getElementById("pd_fn_check_all")?.addEventListener("change", (e) => {
    const on = !!e.target.checked;
    const rows = pedidosDaPagina().pagina;
    rows.forEach((p) => {
      if (on) selecionados.add(p.id);
      else selecionados.delete(p.id);
    });
    renderLista();
  });
  document.getElementById("pd_fn_bulk_clear")?.addEventListener("click", limparSelecao);
  document.getElementById("pd_fn_bulk")?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-lote]");
    if (!btn) return;
    loteAcao(btn.getAttribute("data-lote"));
  });

  document.getElementById("pd_fn_fechar")?.addEventListener("click", () => setModalOpen(false));
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) setModalOpen(false);
  });
  function pintarPeriodoBtn() {
    const txt = document.getElementById("pd_fn_periodoTxt");
    const tag = document.getElementById("pd_fn_periodoTag");
    if (!periodoAplicado?.ini || !periodoAplicado?.fim) {
      if (txt) txt.textContent = "Todo o período";
      if (tag) tag.textContent = "Sem recorte";
      return;
    }
    if (txt) txt.textContent = `${fmtDia(periodoAplicado.ini)} – ${fmtDia(periodoAplicado.fim)}`;
    if (tag) tag.textContent = nomePreset(periodoAplicado.preset);
  }

  function atualizarAvisoFora() {
    const el = document.getElementById("pd_fn_fora");
    const txt = document.getElementById("pd_fn_foraTxt");
    if (!el || !txt) return;
    if (!periodoAplicado?.ini) {
      el.hidden = true;
      return;
    }
    const n = todosPedidos.filter((p) => !noPeriodo(p) && PRECISA_ACAO.includes(stV(p))).length;
    if (!n) {
      el.hidden = true;
      return;
    }
    txt.textContent = n === 1
      ? "1 pedido anterior a este período ainda pede ação."
      : `${n} pedidos anteriores a este período ainda pedem ação.`;
    el.hidden = false;
  }

  function textoEscolha() {
    const el = document.getElementById("pd_fn_periodoEscolha");
    if (!el || !rascunho) return;
    if (!rascunho.ini) {
      el.textContent = "Nenhum recorte — a lista mostra todos";
      return;
    }
    if (!rascunho.fim) {
      el.textContent = `${fmtDia(rascunho.ini)} – escolha o fim`;
      return;
    }
    el.textContent = `${fmtDia(rascunho.ini)} – ${fmtDia(rascunho.fim)}`;
  }

  function classeDia(dia, ini, fim, preview) {
    const cls = [];
    if (mesmoDia(dia, hojeDia())) cls.push("is-hoje");
    const fimVis = fim || preview;
    if (ini && fimVis) {
      const a = cmpDia(ini, fimVis) <= 0 ? ini : fimVis;
      const b = cmpDia(ini, fimVis) <= 0 ? fimVis : ini;
      if (cmpDia(dia, a) >= 0 && cmpDia(dia, b) <= 0) {
        if (mesmoDia(dia, a)) cls.push("is-start");
        if (mesmoDia(dia, b)) cls.push("is-end");
        cls.push(fim ? "is-in" : "is-preview");
      }
    } else if (ini && mesmoDia(dia, ini)) {
      cls.push("is-start");
    }
    return cls.join(" ");
  }

  function htmlMes(ano, mes, mostrarAnt, mostrarProx) {
    const primeiro = new Date(ano, mes, 1);
    const offset = (primeiro.getDay() + 6) % 7;
    const inicio = addDias(primeiro, -offset);
    const ini = rascunho?.ini || null;
    const fim = rascunho?.fim || null;
    const preview = !fim && ini && hoverDia ? hoverDia : null;
    let dias = "";
    for (let i = 0; i < 42; i += 1) {
      const dia = addDias(inicio, i);
      const fora = dia.getMonth() !== mes;
      const cls = `${classeDia(dia, ini, fim, preview)}${fora ? " is-out" : ""}`;
      const iso = `${dia.getFullYear()}-${dia.getMonth()}-${dia.getDate()}`;
      dias += `<div class="PdFn_Dia ${cls}"><button type="button" data-dia="${iso}">${dia.getDate()}</button></div>`;
    }
    const navAnt = mostrarAnt ? `<button type="button" class="PdFn_MesNav" data-nav="-1" aria-label="Mês anterior">‹</button>` : `<span></span>`;
    const navProx = mostrarProx ? `<button type="button" class="PdFn_MesNav" data-nav="1" aria-label="Próximo mês">›</button>` : `<span></span>`;
    const semana = SEMANA.map((s) => `<span>${s}</span>`).join("");
    return `
      <div class="PdFn_Mes">
        <div class="PdFn_MesHead">${navAnt}<span class="PdFn_MesNome">${MESES[mes]} ${ano}</span>${navProx}</div>
        <div class="PdFn_Semana">${semana}</div>
        <div class="PdFn_Dias">${dias}</div>
      </div>`;
  }

  function pintarCalendario() {
    const box = document.getElementById("pd_fn_cals");
    if (!box) return;
    const esq = calMes;
    const dir = addMeses(calMes, 1);
    box.innerHTML = htmlMes(esq.getFullYear(), esq.getMonth(), true, false) + htmlMes(dir.getFullYear(), dir.getMonth(), false, true);
    textoEscolha();
    document.querySelectorAll("#pd_fn_presets .PdFn_Preset").forEach((b) => {
      b.classList.toggle("is-on", b.getAttribute("data-preset") === (rascunho?.preset || ""));
    });
  }

  function abrirPeriodo() {
    const pop = document.getElementById("pd_fn_periodoPop");
    const btn = document.getElementById("pd_fn_periodoBtn");
    rascunho = periodoAplicado?.ini
      ? { ini: new Date(periodoAplicado.ini), fim: periodoAplicado.fim ? new Date(periodoAplicado.fim) : null, preset: periodoAplicado.preset }
      : { ini: null, fim: null, preset: "todos" };
    calMes = inicioMes(rascunho.ini || hojeDia());
    hoverDia = null;
    if (pop) pop.hidden = false;
    if (btn) btn.setAttribute("aria-expanded", "true");
    pintarCalendario();
  }

  function fecharPeriodo() {
    const pop = document.getElementById("pd_fn_periodoPop");
    const btn = document.getElementById("pd_fn_periodoBtn");
    if (pop) pop.hidden = true;
    if (btn) btn.setAttribute("aria-expanded", "false");
    hoverDia = null;
  }

  function aplicarRascunho() {
    if (!rascunho?.ini) {
      periodoAplicado = { ini: null, fim: null, preset: "todos" };
    } else {
      const fim = rascunho.fim || rascunho.ini;
      const a = cmpDia(rascunho.ini, fim) <= 0 ? rascunho.ini : fim;
      const b = cmpDia(rascunho.ini, fim) <= 0 ? fim : rascunho.ini;
      periodoAplicado = { ini: a, fim: b, preset: presetQueCombina(a, b) };
    }
    paginaAtual = 1;
    fecharPeriodo();
    renderLista();
  }

  function incluirPendentesFora() {
    let min = periodoAplicado?.ini || null;
    todosPedidos.forEach((p) => {
      if (!PRECISA_ACAO.includes(stV(p))) return;
      const d = diaDePedido(p.criado_em);
      if (d && (!min || cmpDia(d, min) < 0)) min = d;
    });
    if (!min) return;
    const fim = periodoAplicado?.fim && cmpDia(periodoAplicado.fim, min) >= 0 ? periodoAplicado.fim : hojeDia();
    periodoAplicado = { ini: min, fim, preset: presetQueCombina(min, fim) };
    paginaAtual = 1;
    renderLista();
  }

  function iniciarPeriodo() {
    const presets = document.getElementById("pd_fn_presets");
    if (presets) {
      presets.innerHTML = PRESETS.map(
        (p) => `<button type="button" class="PdFn_Preset" data-preset="${p.id}" role="option">${esc(p.label)}</button>`
      ).join("") + `<button type="button" class="PdFn_Preset" data-preset="todos" role="option">Todo o período</button>`;
    }
    pintarPeriodoBtn();

    document.getElementById("pd_fn_periodoBtn")?.addEventListener("click", (e) => {
      e.stopPropagation();
      const pop = document.getElementById("pd_fn_periodoPop");
      if (pop?.hidden) abrirPeriodo();
      else fecharPeriodo();
    });

    document.getElementById("pd_fn_periodoPop")?.addEventListener("click", (e) => {
      e.stopPropagation();
      const nav = e.target.closest("[data-nav]");
      if (nav) {
        calMes = addMeses(calMes, Number(nav.getAttribute("data-nav")));
        pintarCalendario();
        return;
      }
      const diaBtn = e.target.closest("[data-dia]");
      if (diaBtn) {
        const [y, m, d] = diaBtn.getAttribute("data-dia").split("-").map(Number);
        const dia = new Date(y, m, d);
        if (!rascunho.ini || rascunho.fim) {
          rascunho = { ini: dia, fim: null, preset: "" };
        } else {
          const a = cmpDia(rascunho.ini, dia) <= 0 ? rascunho.ini : dia;
          const b = cmpDia(rascunho.ini, dia) <= 0 ? dia : rascunho.ini;
          rascunho = { ini: a, fim: b, preset: presetQueCombina(a, b) };
        }
        hoverDia = null;
        pintarCalendario();
        return;
      }
      const pre = e.target.closest("[data-preset]");
      if (pre) {
        const id = pre.getAttribute("data-preset");
        if (id === "todos") {
          rascunho = { ini: null, fim: null, preset: "todos" };
        } else {
          const p = PRESETS.find((x) => x.id === id);
          if (!p) return;
          const [ini, fim] = p.range();
          rascunho = { ini, fim, preset: id };
          calMes = inicioMes(ini);
        }
        hoverDia = null;
        pintarCalendario();
      }
    });

    document.getElementById("pd_fn_cals")?.addEventListener("mouseover", (e) => {
      const diaBtn = e.target.closest("[data-dia]");
      if (!diaBtn || !rascunho?.ini || rascunho.fim) return;
      const [y, m, d] = diaBtn.getAttribute("data-dia").split("-").map(Number);
      const next = new Date(y, m, d);
      if (hoverDia && mesmoDia(hoverDia, next)) return;
      hoverDia = next;
      pintarCalendario();
    });

    document.getElementById("pd_fn_periodoLimpar")?.addEventListener("click", () => {
      rascunho = { ini: null, fim: null, preset: "todos" };
      hoverDia = null;
      pintarCalendario();
    });
    document.getElementById("pd_fn_periodoOk")?.addEventListener("click", aplicarRascunho);
    document.getElementById("pd_fn_fora")?.addEventListener("click", incluirPendentesFora);
    document.addEventListener("click", () => {
      const pop = document.getElementById("pd_fn_periodoPop");
      if (pop && !pop.hidden) fecharPeriodo();
    });
  }

  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    const pop = document.getElementById("pd_fn_periodoPop");
    if (pop && !pop.hidden) {
      fecharPeriodo(false);
      return;
    }
    if (modal && !modal.hidden) setModalOpen(false);
  });

  iniciarPeriodo();
  carregar();
})();
