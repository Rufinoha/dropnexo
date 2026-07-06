(function () {
  const params = new URLSearchParams(window.location.search);
  let idVariante = Number(params.get("id_variante") || 0);
  let idProduto = Number(params.get("id_produto") || 0);
  let nivelModal = 2;
  let dadosPai = null;
  let atributosCache = {};
  let galeriaPai = [];
  let imagensVariante = [];
  let imgDragCtx = null;
  let integradoBling = false;
  let estoqueDepositos = [];

  let descricaoPropria = "";
  let valorDropManual = false;

  const el = {
    id_variante: document.getElementById("id_variante"),
    id_produto: document.getElementById("id_produto"),
    titulo: document.getElementById("titulo_variante"),
    herda_pai: document.getElementById("herda_pai"),
    hint_herda: document.getElementById("hint_herda"),
    painel_imagens_herda: document.getElementById("painel_imagens_herda"),
    painel_imagens_split: document.getElementById("painel_imagens_split"),
    hint_imagem_variante: document.getElementById("hint_imagem_variante"),
    galeria_variante_sel: document.getElementById("galeria_variante_sel"),
    galeria_pai_fonte: document.getElementById("galeria_pai_fonte"),
    nome_exibicao: document.getElementById("nome_exibicao"),
    sku: document.getElementById("sku"),
    descricao: document.getElementById("descricao"),
    wrap_descricao: document.getElementById("wrapDescricaoVariante"),
    hint_descricao_herda: document.getElementById("hint_descricao_herda"),
    hint_atributos: document.getElementById("hint_atributos"),
    ativo: document.getElementById("ativo"),
    preco: document.getElementById("preco"),
    valor_drop: document.getElementById("valor_drop"),
    preco_promocional: document.getElementById("preco_promocional"),
    promocao_validade: document.getElementById("promocao_validade"),
    promocao_ate_zerar_estoque: document.getElementById("promocao_ate_zerar_estoque"),
    campoPromoData: document.getElementById("campoPromoData"),
    hintPromoStatus: document.getElementById("hintPromoStatus"),
    hintValorDropVar: document.getElementById("hintValorDropVar"),
    peso_liquido_kg: document.getElementById("peso_liquido_kg"),
    peso_bruto_kg: document.getElementById("peso_bruto_kg"),
    altura_cm: document.getElementById("altura_cm"),
    largura_cm: document.getElementById("largura_cm"),
    profundidade_cm: document.getElementById("profundidade_cm"),
    gtin: document.getElementById("gtin"),
    ncm: document.getElementById("ncm"),
    quantidade: document.getElementById("quantidade"),
    tblEstoqueDepositosVar: document.getElementById("gridEstoqueDepositosVar"),
    btnSalvar: document.getElementById("btnSalvar"),
    btnExcluir: document.getElementById("btnExcluir"),
  };
  if (!el.nome_exibicao) return;

  const BASE = window.CAT_APOIO_BASE || "/catalogos";
  const isVendedor = (window.CAT_APOIO_MODO || "fornecedor") === "vendedor";
  let integrado = false;

  function apiBase() {
    if (isVendedor && !integrado) return "/catalogos";
    return BASE;
  }
  let pausadoVitrine = false;
  let pausadoMsg = "";
  const camposHerdaveis = document.querySelectorAll(
    "#preco, #valor_drop, #preco_promocional, #promocao_validade, #peso_liquido_kg, #peso_bruto_kg, #altura_cm, #largura_cm, #profundidade_cm, #gtin, #ncm"
  );

  function syncModoVendedorUi() {
    if (!isVendedor) return;
    if (el.herda_pai) el.herda_pai.disabled = integrado;
    const bloquear = integrado
      ? ["sku", "valor_drop", "preco_promocional", "promocao_validade", "peso_liquido_kg", "peso_bruto_kg", "altura_cm", "largura_cm", "profundidade_cm", "gtin", "ncm"]
      : [];
    const map = {
      sku: el.sku,
      valor_drop: el.valor_drop,
      preco_promocional: el.preco_promocional,
      promocao_validade: el.promocao_validade,
      peso_liquido_kg: el.peso_liquido_kg,
      peso_bruto_kg: el.peso_bruto_kg,
      altura_cm: el.altura_cm,
      largura_cm: el.largura_cm,
      profundidade_cm: el.profundidade_cm,
      gtin: el.gtin,
      ncm: el.ncm,
    };
    Object.entries(map).forEach(([k, inp]) => {
      if (!inp) return;
      const ro = bloquear.includes(k);
      inp.readOnly = ro;
      inp.classList.toggle("Cat_CampoHerdado", ro);
    });
    if (el.promocao_ate_zerar_estoque) el.promocao_ate_zerar_estoque.disabled = integrado || !!el.herda_pai?.checked;
    if (el.btnExcluir) el.btnExcluir.hidden = integrado;
    if (el.quantidade) el.quantidade.readOnly = true;
    if (integrado && el.hint_herda) {
      el.hint_herda.textContent = el.herda_pai?.checked
        ? "Cadastro do fornecedor: esta variação usa preço, peso, GTIN, descrição e imagens do produto pai."
        : "Cadastro do fornecedor: esta variação tem valores e imagens próprios no catálogo do fornecedor.";
    }
    syncHerdaUi();
  }

  function ativarTab(cod) {
    document.querySelectorAll(".Cat_Tab").forEach((t) => t.classList.toggle("is-active", t.dataset.tab === cod));
    document.querySelectorAll(".Cat_TabPanel").forEach((p) => {
      const on = p.dataset.panel === cod;
      p.classList.toggle("is-active", on);
      p.hidden = !on;
    });
  }

  document.querySelectorAll(".Cat_Tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      ativarTab(btn.dataset.tab);
      if (btn.dataset.tab === "estoque") carregarEstoqueDepositos().catch(() => {});
    });
  });

  function fmtData(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("pt-BR");
    } catch {
      return iso;
    }
  }

  function escHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function localDeposito(d) {
    const cidade = (d.cidade || "").trim();
    const uf = (d.uf || "").trim();
    if (cidade && uf) return `${cidade} · ${uf}`;
    return cidade || uf || "—";
  }

  function cardDepositoHtml(d) {
    const badges = [
      d.principal ? '<span class="Cat_EstoqueDepCardBadge">Principal</span>' : "",
      d.vinculado_bling ? '<span class="Cat_EstoqueTag">Bling</span>' : "",
    ]
      .filter(Boolean)
      .join("");
    const qtd = Number(d.quantidade) || 0;
    return `<article class="Cat_EstoqueDepCard${qtd > 0 ? " has-stock" : ""}" data-dep="${d.id_deposito}" title="Duplo clique para detalhes">
      <div class="Cat_EstoqueDepCardHead">
        <h4 class="Cat_EstoqueDepCardNome">${escHtml(d.nome)}</h4>
        ${badges ? `<div class="Cat_EstoqueDepCardBadges">${badges}</div>` : ""}
      </div>
      <p class="Cat_EstoqueDepCardLoc">${escHtml(localDeposito(d))}</p>
      <div class="Cat_EstoqueDepCardSaldo">
        <span class="Cat_EstoqueDepCardSaldoLbl">Saldo em estoque</span>
        <strong class="Cat_EstoqueDepCardSaldoVal">${qtd}</strong>
      </div>
      <footer class="Cat_EstoqueDepCardFoot">Atualizado ${fmtData(d.atualizado_em)}</footer>
    </article>`;
  }

  function renderEstoqueCards() {
    if (!el.tblEstoqueDepositosVar) return;
    if (!estoqueDepositos.length) {
      el.tblEstoqueDepositosVar.innerHTML = isVendedor
        ? '<p class="Cat_EstoqueDepEmpty">Nenhum depósito do fornecedor com saldo para esta variação.</p>'
        : '<p class="Cat_EstoqueDepEmpty">Nenhum depósito cadastrado. Cadastre em Fornecedor → Depósitos.</p>';
      return;
    }
    el.tblEstoqueDepositosVar.innerHTML = estoqueDepositos.map(cardDepositoHtml).join("");
  }

  async function carregarEstoqueDepositos() {
    if (!idVariante || !el.tblEstoqueDepositosVar) return;
    const r = await fetch(
      `${apiBase()}/estoque/depositos?id_produto=${idProduto}&id_variante=${idVariante}`,
      { credentials: "include" }
    );
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar estoque.");
    integradoBling = !!j.integrado_bling;
    estoqueDepositos = j.depositos || [];
    if (isVendedor && j.pausado) pausadoVitrine = true;
    renderEstoqueCards();
    const total = estoqueDepositos.reduce((s, d) => s + (d.quantidade || 0), 0);
    if (el.quantidade) el.quantidade.value = String(total);
  }

  async function editarSaldoDeposito(idDeposito, saldoAtual) {
    const dep = estoqueDepositos.find((d) => d.id_deposito === idDeposito);
    let sincronizarBling = false;
    if (integradoBling) {
      const c = await Swal.fire({
        icon: "warning",
        title: "Produto integrado ao Bling",
        html: `Alterar o saldo desta variação pode atualizar o estoque no Bling.`,
        showCancelButton: true,
        confirmButtonText: "Continuar",
        cancelButtonText: "Cancelar",
      });
      if (!c.isConfirmed) return;
      if (dep?.vinculado_bling) {
        const s = await Swal.fire({
          icon: "question",
          title: "Sincronizar com o Bling?",
          showCancelButton: true,
          confirmButtonText: "Sim, sincronizar",
          cancelButtonText: "Só no DropNexo",
        });
        sincronizarBling = s.isConfirmed;
      }
    }
    const badges = [
      dep?.principal ? '<span class="Cat_EstoqueDepCardBadge">Principal</span>' : "",
      dep?.vinculado_bling ? '<span class="Cat_EstoqueTag">Bling</span>' : "",
    ]
      .filter(Boolean)
      .join(" ");
    const r = await Swal.fire({
      title: dep?.nome || "Depósito",
      html: `<div class="Cat_EstoqueModal">
        <p class="Cat_EstoqueModalLoc">${escHtml(localDeposito(dep || {}))}</p>
        ${badges ? `<p style="margin:0 0 8px">${badges}</p>` : ""}
        <p class="Cat_EstoqueModalHint">Saldo atual: <strong>${saldoAtual}</strong> · ${fmtData(dep?.atualizado_em)}</p>
      </div>`,
      input: "number",
      inputLabel: "Novo saldo",
      inputValue: saldoAtual,
      inputAttributes: { min: 0, step: 1 },
      showCancelButton: true,
      confirmButtonText: "Salvar",
      cancelButtonText: "Cancelar",
    });
    if (!r.isConfirmed || r.value === undefined || r.value === "") return;
    const qtd = Math.max(0, parseInt(r.value, 10) || 0);
    const resp = await fetch(`${apiBase()}/estoque/depositos/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        id_produto: idProduto,
        id_variante: idVariante,
        id_deposito: idDeposito,
        quantidade: qtd,
        sincronizar_bling: sincronizarBling,
      }),
    });
    const j = await resp.json();
    if (!resp.ok || !j.success) throw new Error(j.message || "Erro ao salvar saldo.");
    if (j.dados?.promocao_encerrada) {
      el.preco_promocional.value = "";
      if (el.promocao_validade) el.promocao_validade.value = "";
      if (el.promocao_ate_zerar_estoque) el.promocao_ate_zerar_estoque.checked = false;
      syncPromoUi();
      await Swal.fire({
        icon: "info",
        title: "Promoção encerrada",
        text: "O estoque zerou ou foi reposto — a promoção desta variante foi removida.",
        timer: 3200,
        showConfirmButton: false,
      });
    } else {
      await Swal.fire({ icon: "success", title: "Salvo", text: j.message, timer: 2200, showConfirmButton: false });
    }
    await carregarEstoqueDepositos();
  }

  el.tblEstoqueDepositosVar?.addEventListener("dblclick", (ev) => {
    if (isVendedor && integrado) return;
    const card = ev.target.closest(".Cat_EstoqueDepCard");
    if (!card || !idVariante) return;
    const idDep = parseInt(card.dataset.dep || "0", 10);
    if (!idDep) return;
    const dep = estoqueDepositos.find((d) => d.id_deposito === idDep);
    editarSaldoDeposito(idDep, dep?.quantidade ?? 0).catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  function rotuloOrdem(idx) {
    if (idx === 0) return "PRINCIPAL";
    return `${idx + 1}ª`;
  }

  function idsVarianteSet() {
    return new Set(imagensVariante.map((i) => Number(i.id)));
  }

  function imagensPaiDisponiveis() {
    const usados = idsVarianteSet();
    return galeriaPai.filter((i) => i.id && !usados.has(Number(i.id)));
  }

  function abrirModalImagem(img, idx) {
    if (!img?.url) return;
    const titulo = idx !== undefined && idx !== null ? rotuloOrdem(idx) : "Imagem";
    Swal.fire({
      title: titulo,
      imageUrl: img.url,
      imageAlt: "Imagem do produto",
      showConfirmButton: false,
      showCloseButton: true,
      width: "auto",
      padding: "1rem",
      background: "#fff",
    });
  }

  function cardImagemHtml(img, idx, lado) {
    const ordem =
      lado === "variante" && idx !== null && idx !== undefined
        ? `<span class="Cat_GaleriaSplitOrdem${idx === 0 ? " is-principal" : ""}">${rotuloOrdem(idx)}</span>`
        : "";
    return `<div class="Cat_GaleriaSplitItem" draggable="true" data-lado="${lado}" data-id="${img.id}" data-idx="${idx ?? ""}">
      ${ordem}
      <img src="${img.url || ""}" alt="" loading="lazy" draggable="false" />
    </div>`;
  }

  function reordenarVariante(from, to) {
    if (from === to || from < 0 || to < 0) return;
    const arr = imagensVariante.slice();
    const [moved] = arr.splice(from, 1);
    if (!moved) return;
    arr.splice(to, 0, moved);
    imagensVariante = arr;
    renderSplitImagens();
  }

  function adicionarImagemVariante(idImg, toIdx) {
    const id = Number(idImg);
    if (!id || idsVarianteSet().has(id)) return;
    const img = galeriaPai.find((i) => Number(i.id) === id);
    if (!img) return;
    const arr = imagensVariante.slice();
    const pos = Math.min(Math.max(0, toIdx ?? arr.length), arr.length);
    arr.splice(pos, 0, img);
    imagensVariante = arr;
    renderSplitImagens();
  }

  function removerImagemVariante(idImg) {
    const id = Number(idImg);
    imagensVariante = imagensVariante.filter((i) => Number(i.id) !== id);
    renderSplitImagens();
  }

  function wirePainelDrag(panel, lado) {
    if (!panel) return;
    panel.addEventListener("dragover", (ev) => {
      ev.preventDefault();
      ev.dataTransfer.dropEffect = "move";
    });
    panel.addEventListener("drop", (ev) => {
      if (ev.target.closest(".Cat_GaleriaSplitItem")) return;
      ev.preventDefault();
      const ctx = imgDragCtx || {
        lado: ev.dataTransfer.getData("lado"),
        id: Number(ev.dataTransfer.getData("id")),
        idx: Number(ev.dataTransfer.getData("idx")),
      };
      if (lado === "variante" && ctx.lado === "pai" && ctx.id) {
        adicionarImagemVariante(ctx.id, imagensVariante.length);
      } else if (lado === "pai" && ctx.lado === "variante" && ctx.id) {
        removerImagemVariante(ctx.id);
      }
    });
  }

  function wireItensDrag(container) {
    if (!container) return;
    container.querySelectorAll(".Cat_GaleriaSplitItem").forEach((item) => {
      item.addEventListener("dragstart", (ev) => {
        imgDragCtx = {
          lado: item.dataset.lado,
          id: Number(item.dataset.id),
          idx: Number(item.dataset.idx),
        };
        item.classList.add("is-dragging");
        ev.dataTransfer.effectAllowed = "move";
        try {
          ev.dataTransfer.setData("lado", imgDragCtx.lado);
          ev.dataTransfer.setData("id", String(imgDragCtx.id));
          ev.dataTransfer.setData("idx", String(imgDragCtx.idx));
        } catch {
          /* ignore */
        }
      });
      item.addEventListener("dragend", () => {
        item.classList.remove("is-dragging");
        imgDragCtx = null;
        document.querySelectorAll(".Cat_GaleriaSplitItem").forEach((n) => n.classList.remove("is-dragover"));
      });
      item.addEventListener("dragover", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        ev.dataTransfer.dropEffect = "move";
        item.classList.add("is-dragover");
      });
      item.addEventListener("dragleave", () => item.classList.remove("is-dragover"));
      item.addEventListener("drop", (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        item.classList.remove("is-dragover");
        const ctx = imgDragCtx || {
          lado: ev.dataTransfer.getData("lado"),
          id: Number(ev.dataTransfer.getData("id")),
          idx: Number(ev.dataTransfer.getData("idx")),
        };
        const toIdx = Number(item.dataset.idx);
        const toLado = item.dataset.lado;
        if (toLado === "variante") {
          if (ctx.lado === "pai") adicionarImagemVariante(ctx.id, toIdx);
          else if (ctx.lado === "variante" && !Number.isNaN(ctx.idx)) reordenarVariante(ctx.idx, toIdx);
        } else if (toLado === "pai" && ctx.lado === "variante") {
          removerImagemVariante(ctx.id);
        }
      });
      item.addEventListener("dblclick", () => {
        const lado = item.dataset.lado;
        const id = Number(item.dataset.id);
        if (lado === "variante") {
          const idx = Number(item.dataset.idx);
          const img = imagensVariante[idx];
          abrirModalImagem(img, idx);
        } else {
          const img = galeriaPai.find((i) => Number(i.id) === id);
          abrirModalImagem(img);
        }
      });
    });
  }

  function renderSplitImagens() {
    if (!el.galeria_variante_sel || !el.galeria_pai_fonte) return;
    if (!galeriaPai.length) {
      el.galeria_variante_sel.innerHTML = "";
      el.galeria_pai_fonte.innerHTML =
        '<p class="Cat_ImagemHint" style="grid-column:1/-1">Nenhuma imagem na galeria do pai.</p>';
      el.galeria_variante_sel.classList.add("is-empty");
      el.galeria_pai_fonte.classList.remove("is-empty");
      return;
    }
    el.galeria_variante_sel.classList.toggle("is-empty", !imagensVariante.length);
    el.galeria_variante_sel.innerHTML = imagensVariante
      .map((img, idx) => cardImagemHtml(img, idx, "variante"))
      .join("");
    const disp = imagensPaiDisponiveis();
    el.galeria_pai_fonte.classList.toggle("is-empty", !disp.length);
    el.galeria_pai_fonte.innerHTML = disp.map((img) => cardImagemHtml(img, null, "pai")).join("");
    wireItensDrag(el.galeria_variante_sel);
    wireItensDrag(el.galeria_pai_fonte);
  }

  wirePainelDrag(el.galeria_variante_sel, "variante");
  wirePainelDrag(el.galeria_pai_fonte, "pai");

  function syncValorDropUi() {
    if (!el.valor_drop) return;
    el.valor_drop.classList.toggle("is-manual", valorDropManual);
    if (el.hintValorDropVar) {
      el.hintValorDropVar.textContent = valorDropManual
        ? "Valor ajustado manualmente. Ao aplicar a precificação novamente, será recalculado pelas regras."
        : "Calculado em Parâmetros → Precificação. Duplo clique para ajustar.";
    }
  }

  async function editarValorDrop() {
    if (!idVariante) {
      await Swal.fire("Atenção", "Salve a variante antes de alterar o valor Drop.", "warning");
      return;
    }
    if (el.herda_pai?.checked) {
      await Swal.fire("Atenção", "Desmarque «Utilizar informações do produto pai» para editar o valor Drop desta variante.", "warning");
      return;
    }
    const atual = parseFloat(el.valor_drop?.value || "0") || 0;
    const aviso = await Swal.fire({
      icon: "info",
      title: "Valor Drop manual",
      html:
        "Este valor é oferecido aos vendedores na rede.<br><br>" +
        "<strong>Atenção:</strong> ao aplicar a precificação novamente em Parâmetros, " +
        "este valor pode ser substituído pelo cálculo das regras.",
      showCancelButton: true,
      confirmButtonText: "Continuar",
      cancelButtonText: "Cancelar",
    });
    if (!aviso.isConfirmed) return;
    const r = await Swal.fire({
      title: "Valor Drop (R$)",
      input: "number",
      inputValue: atual,
      inputAttributes: { min: 0, step: 0.01 },
      showCancelButton: true,
      confirmButtonText: "Salvar",
    });
    if (!r.isConfirmed || r.value === undefined || r.value === "") return;
    const vd = Math.max(0, parseFloat(r.value) || 0);
    const resp = await fetch(`${apiBase()}/variantes/valor-drop/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ id_variante: idVariante, valor_drop: vd }),
    });
    const j = await resp.json();
    if (!resp.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    el.valor_drop.value = j.valor_drop ?? vd;
    valorDropManual = true;
    syncValorDropUi();
    await Swal.fire({ icon: "success", title: "Salvo", text: j.message, timer: 2000, showConfirmButton: false });
  }

  function syncPromoUi() {
    const ateZerar = !!el.promocao_ate_zerar_estoque?.checked;
    if (el.campoPromoData) el.campoPromoData.hidden = ateZerar;
    if (el.promocao_validade) {
      el.promocao_validade.disabled = ateZerar || !!el.herda_pai?.checked;
      if (ateZerar) el.promocao_validade.value = "";
    }
    const temPromo = (parseFloat(el.preco_promocional?.value || "0") || 0) > 0;
    if (!el.hintPromoStatus) return;
    if (!temPromo) {
      el.hintPromoStatus.hidden = true;
      return;
    }
    el.hintPromoStatus.hidden = false;
    if (ateZerar) {
      const est = parseInt(el.quantidade?.value || "0", 10) || 0;
      el.hintPromoStatus.textContent =
        est > 0
          ? `Promoção ativa enquanto houver estoque (${est} un.).`
          : "Promoção inativa — estoque zerado.";
      el.hintPromoStatus.className = est > 0 ? "Cat_ImagemHint is-ativa" : "Cat_ImagemHint is-inativa";
    } else if (el.promocao_validade?.value) {
      el.hintPromoStatus.textContent = `Promoção válida até ${el.promocao_validade.value.split("-").reverse().join("/")}.`;
      el.hintPromoStatus.className = "Cat_ImagemHint is-ativa";
    } else {
      el.hintPromoStatus.textContent = "Informe a data de vencimento ou marque «Até zerar o estoque».";
      el.hintPromoStatus.className = "Cat_ImagemHint is-inativa";
    }
  }

  function getDescricaoValue() {
    return window.CatDescricaoEditor
      ? CatDescricaoEditor.getValue()
      : (el.descricao?.value || "").trim();
  }

  function setDescricaoValue(v) {
    if (window.CatDescricaoEditor) CatDescricaoEditor.setValue(v);
    else if (el.descricao) el.descricao.value = v;
  }

  function syncDescricaoUi(h) {
    if (!el.descricao && !document.getElementById("descricaoEditor")) return;
    const paiDesc = (dadosPai?.descricao || "").trim();
    const wrap = el.wrap_descricao || document.querySelector(".Cat_DescricaoCampo");
    if (h) {
      const atual = getDescricaoValue();
      if (!descricaoPropria && atual && atual !== paiDesc) {
        descricaoPropria = atual;
      }
      setDescricaoValue(paiDesc || atual || "");
      window.CatDescricaoEditor?.setReadOnly?.(true);
      wrap?.classList.add("Cat_CampoHerdado");
      if (el.hint_descricao_herda) el.hint_descricao_herda.hidden = false;
    } else {
      window.CatDescricaoEditor?.setReadOnly?.(false);
      wrap?.classList.remove("Cat_CampoHerdado");
      if (!getDescricaoValue()) {
        setDescricaoValue(descricaoPropria || paiDesc);
      }
      if (el.hint_descricao_herda) el.hint_descricao_herda.hidden = true;
    }
  }

  function syncHerdaUi() {
    const h = !!el.herda_pai?.checked;
    camposHerdaveis.forEach((inp) => {
      const vitrineField = isVendedor && (inp.id === "preco" || inp.id === "valor_drop");
      if (vitrineField) return;
      inp.disabled = h;
      inp.classList.toggle("Cat_CampoHerdado", h);
    });
    if (isVendedor) {
      if (el.nome_exibicao) {
        el.nome_exibicao.disabled = false;
        el.nome_exibicao.classList.remove("Cat_CampoHerdado");
      }
      if (el.preco) {
        el.preco.disabled = false;
        el.preco.classList.remove("Cat_CampoHerdado");
      }
      if (el.ativo) el.ativo.disabled = false;
      window.CatDescricaoEditor?.setReadOnly?.(false);
      if (el.wrap_descricao) el.wrap_descricao.classList.remove("Cat_CampoHerdado");
      if (el.hint_descricao_herda) el.hint_descricao_herda.hidden = !h;
    } else {
      syncDescricaoUi(h);
    }
    syncValorDropUi();
    syncPromoUi();
    if (el.hint_herda) {
      el.hint_herda.textContent = h
        ? "Valor, valor Drop, promoção, peso, GTIN, descrição e imagens seguem o cadastro do pai."
        : "Esta variante usa valores, descrição e imagens próprios.";
    }
    if (el.painel_imagens_herda) el.painel_imagens_herda.hidden = isVendedor ? true : !h;
    if (el.painel_imagens_split) el.painel_imagens_split.hidden = isVendedor ? false : h;
    if (el.promocao_ate_zerar_estoque) el.promocao_ate_zerar_estoque.disabled = h || (isVendedor && integrado);
    if (isVendedor || !h) renderSplitImagens();
  }

  function rotuloAttr(atributos) {
    if (!atributos || typeof atributos !== "object") return "";
    return Object.entries(atributos)
      .map(([k, v]) => `${k}: ${v}`)
      .join(" · ");
  }

  async function carregarGaleriaPai() {
    if (!idProduto) return;
    const r = await fetch(`${apiBase()}/imagens/lista?id_produto=${idProduto}`);
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar galeria.");
    galeriaPai = j.imagens || [];
  }

  function preencher(d, pai) {
    dadosPai = pai;
    idVariante = d.id;
    idProduto = d.id_produto;
    if (el.id_variante) el.id_variante.value = String(idVariante);
    if (el.id_produto) el.id_produto.value = String(idProduto);
    if (el.titulo) el.titulo.textContent = d.nome_exibicao || "Variante";
    el.herda_pai.checked = d.herda_pai !== false;
    el.nome_exibicao.value = d.nome_exibicao || "";
    el.sku.value = d.sku || "";
    atributosCache = d.atributos || {};
    descricaoPropria = (d.descricao_propria || "").trim();
    setDescricaoValue((d.descricao || pai?.descricao || "").trim());
    if (el.hint_atributos) {
      const attrTxt = rotuloAttr(d.atributos);
      el.hint_atributos.textContent = attrTxt ? `Variação: ${attrTxt}` : "";
      el.hint_atributos.hidden = !attrTxt;
    }
    el.ativo.checked = !!d.ativo;
    el.preco.value = d.preco ?? "";
    if (el.valor_drop) el.valor_drop.value = d.valor_drop ?? "";
    valorDropManual = !!d.valor_drop_manual;
    el.preco_promocional.value = d.preco_promocional ?? "";
    if (el.promocao_validade) el.promocao_validade.value = d.promocao_validade || "";
    if (el.promocao_ate_zerar_estoque) el.promocao_ate_zerar_estoque.checked = !!d.promocao_ate_zerar_estoque;
    el.peso_liquido_kg.value = d.peso_liquido_kg ?? "";
    el.peso_bruto_kg.value = d.peso_bruto_kg ?? "";
    el.altura_cm.value = d.altura_cm ?? "";
    el.largura_cm.value = d.largura_cm ?? "";
    el.profundidade_cm.value = d.profundidade_cm ?? "";
    el.gtin.value = d.gtin || "";
    el.ncm.value = d.ncm || "";
    el.quantidade.value = d.estoque ?? 0;
    if (Array.isArray(d.imagens_pai) && d.imagens_pai.length) {
      galeriaPai = d.imagens_pai;
    }
    imagensVariante = Array.isArray(d.imagens_selecionadas) ? d.imagens_selecionadas.slice() : [];
    integrado = !!d.integrado;
    pausadoVitrine = !!d.pausado;
    pausadoMsg = d.pausado_msg || "";
    syncHerdaUi();
    syncModoVendedorUi();
  }

  async function carregar() {
    if (!idVariante) throw new Error("Variante não informada.");
    const r = await fetch(`${BASE}/variante/apoio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idVariante }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar.");
    if (!j.dados?.imagens_pai?.length) await carregarGaleriaPai().catch(() => {});
    else galeriaPai = j.dados.imagens_pai;
    preencher(j.dados, j.pai);
    await carregarEstoqueDepositos().catch(() => {});
    syncPromoUi();
  }

  function notificarPersistenciaVariante() {
    window.parent.postMessage({ grupo: "atualizarVariantes", id_produto: idProduto }, "*");
    const destinoLista =
      window.parent.parent && window.parent.parent !== window.parent
        ? window.parent.parent
        : window.parent;
    destinoLista.postMessage({ grupo: "atualizarTabela" }, "*");
  }

  async function salvar() {
    if (isVendedor && integrado) {
      const imgSel = imagensVariante[0] || galeriaPai[0];
      const body = {
        id_variante: idVariante,
        nome_exibicao: (el.nome_exibicao.value || "").trim(),
        descricao: getDescricaoValue(),
        preco: el.preco.value,
        imagem_url: imgSel?.caminho || imgSel?.url || "",
        ativo: !!el.ativo.checked,
      };
      const r = await fetch(`${BASE}/variante/salvar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
      await Swal.fire("Sucesso", j.message, "success");
      notificarPersistenciaVariante();
      window.GlobalUtils?.fecharJanelaApoio(nivelModal);
      return;
    }
    const body = {
      id: idVariante,
      id_produto: idProduto,
      nome_exibicao: (el.nome_exibicao.value || "").trim(),
      sku: (el.sku.value || "").trim(),
      descricao: el.herda_pai?.checked
        ? ""
        : getDescricaoValue() || (dadosPai?.descricao || "").trim(),
      ativo: !!el.ativo.checked,
      herda_pai: !!el.herda_pai.checked,
      preco: el.preco.value,
      preco_promocional: el.preco_promocional.value,
      promocao_validade: el.promocao_ate_zerar_estoque?.checked ? "" : el.promocao_validade?.value || "",
      promocao_ate_zerar_estoque: !!el.promocao_ate_zerar_estoque?.checked,
      peso_liquido_kg: el.peso_liquido_kg.value,
      peso_bruto_kg: el.peso_bruto_kg.value,
      altura_cm: el.altura_cm.value,
      largura_cm: el.largura_cm.value,
      profundidade_cm: el.profundidade_cm.value,
      gtin: (el.gtin.value || "").trim(),
      ncm: (el.ncm.value || "").trim(),
      quantidade: el.quantidade.value,
      ids_imagens: el.herda_pai?.checked ? [] : imagensVariante.map((i) => i.id).filter(Boolean),
      id_imagem_principal: el.herda_pai?.checked ? null : imagensVariante[0]?.id || null,
      atributos: atributosCache,
    };
    const r = await fetch(`${apiBase()}/variantes/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    await Swal.fire("Sucesso", j.message, "success");
    notificarPersistenciaVariante();
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  async function excluir() {
    const c = await Swal.fire({
      title: "Excluir variante?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, excluir",
    });
    if (!c.isConfirmed) return;
    const r = await fetch(`${apiBase()}/variantes/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idVariante }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await Swal.fire("Sucesso", j.message, "success");
    notificarPersistenciaVariante();
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  el.herda_pai?.addEventListener("change", syncHerdaUi);
  el.promocao_ate_zerar_estoque?.addEventListener("change", syncPromoUi);
  el.preco_promocional?.addEventListener("input", syncPromoUi);
  el.promocao_validade?.addEventListener("change", syncPromoUi);
  el.valor_drop?.addEventListener("dblclick", () => {
    editarValorDrop().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  el.btnSalvar?.addEventListener("click", () => salvar().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnExcluir?.addEventListener("click", () => excluir().catch((e) => Swal.fire("Erro", e.message, "error")));

  if (window.GlobalUtils?.receberDadosApoio) {
    window.GlobalUtils.receberDadosApoio((id, nivel) => {
      if (id) idVariante = Number(id);
      nivelModal = nivel || 2;
    });
  }

  carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
})();
