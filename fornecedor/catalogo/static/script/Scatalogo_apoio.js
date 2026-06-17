(function () {
  const MAX_IMAGENS = 10;
  let idProduto = null;
  let nivelModal = 1;
  let atributosProduto = [];
  let galeriaImagens = [];
  let imgDragIdx = null;
  let tipoGaleria = null;
  let regrasAtributo = [];

  const el = {
    id: document.getElementById("id"),
    nome: document.getElementById("nome"),
    sku: document.getElementById("sku"),
    formato: document.getElementById("formato"),
    preco: document.getElementById("preco"),
    valor_drop: document.getElementById("valor_drop"),
    preco_custo: document.getElementById("preco_custo"),
    unidade: document.getElementById("unidade"),
    lista_unidades: document.getElementById("lista_unidades"),
    condicao: document.getElementById("condicao"),
    ativo: document.getElementById("ativo"),
    publicado: document.getElementById("publicado"),
    descricao: document.getElementById("descricao"),
    marca: document.getElementById("marca"),
    peso_liquido_kg: document.getElementById("peso_liquido_kg"),
    peso_bruto_kg: document.getElementById("peso_bruto_kg"),
    largura_cm: document.getElementById("largura_cm"),
    altura_cm: document.getElementById("altura_cm"),
    profundidade_cm: document.getElementById("profundidade_cm"),
    itens_por_caixa: document.getElementById("itens_por_caixa"),
    gtin: document.getElementById("gtin"),
    ncm: document.getElementById("ncm"),
    cest: document.getElementById("cest"),
    origem_fiscal: document.getElementById("origem_fiscal"),
    volumes: document.getElementById("volumes"),
    producao: document.getElementById("producao"),
    frete_gratis: document.getElementById("frete_gratis"),
    id_categoria: document.getElementById("id_categoria"),
    quantidade: document.getElementById("quantidade"),
    painelEstoqueSimples: document.getElementById("painelEstoqueSimples"),
    avisoEstoqueVariacao: document.getElementById("avisoEstoqueVariacao"),
    img_link_url: document.getElementById("img_link_url"),
    arquivo_imagem: document.getElementById("arquivo_imagem"),
    btnImgLink: document.getElementById("btnImgLink"),
    btnImgUpload: document.getElementById("btnImgUpload"),
    painelImgLink: document.getElementById("painelImgLink"),
    painelImgUpload: document.getElementById("painelImgUpload"),
    galeria_imagens: document.getElementById("galeria_imagens"),
    imgContador: document.getElementById("imgContador"),
    avisoImgSalvar: document.getElementById("avisoImgSalvar"),
    avisoImgOrdem: document.getElementById("avisoImgOrdem"),
    painelImgAtributo: document.getElementById("painelImgAtributo"),
    img_attr_nome: document.getElementById("img_attr_nome"),
    img_attr_valor: document.getElementById("img_attr_valor"),
    img_attr_imagem: document.getElementById("img_attr_imagem"),
    btnImgAtributo: document.getElementById("btnImgAtributo"),
    lista_img_atributo: document.getElementById("lista_img_atributo"),
    imagem_caminho: document.getElementById("imagem_caminho"),
    imagem_url: document.getElementById("imagem_url"),
    tabVariacoes: document.getElementById("tabVariacoes"),
    painel_variantes: document.getElementById("painel_variantes"),
    lista_variantes: document.getElementById("lista_variantes"),
    btnNovaVariante: document.getElementById("btnNovaVariante"),
    btnAdicionarVariacao: document.getElementById("btnAdicionarVariacao"),
    btnAplicarPreset: document.getElementById("btnAplicarPreset"),
    preset_variacao: document.getElementById("preset_variacao"),
    attr_nome: document.getElementById("attr_nome"),
    attr_valores: document.getElementById("attr_valores"),
    lista_atributos: document.getElementById("lista_atributos"),
    avisoVariacoes: document.getElementById("avisoVariacoes"),
    painelEstoqueDepositos: document.getElementById("painelEstoqueDepositos"),
    tblEstoqueDepositos: document.getElementById("tblEstoqueDepositos"),
    avisoEstoqueCadastro: document.getElementById("avisoEstoqueCadastro"),
    avisoEstoqueDeposito: document.getElementById("avisoEstoqueDeposito"),
    btnSalvar: document.getElementById("btnSalvar"),
    btnExcluir: document.getElementById("btnExcluir"),
  };

  if (!el.nome) return;

  const BASE = "/catalogos";
  const CONDICOES = new Set(["", "NOVO", "USADO", "RECONDICIONADO"]);

  function util() {
    return window.Util || { gerarIconeTech: () => "…" };
  }

  function formatoAtual() {
    return el.formato?.value === "E" ? "E" : "S";
  }

  const BASE = "/catalogos";
  const CONDICOES = new Set(["", "NOVO", "USADO", "RECONDICIONADO"]);
  let integradoBling = false;
  let estoqueDepositos = [];
  let valorDropManual = false;

  function syncValorDropUi() {
    const hint = document.getElementById("hintValorDrop");
    if (!el.valor_drop) return;
    el.valor_drop.classList.toggle("is-manual", valorDropManual);
    if (hint) {
      hint.textContent = valorDropManual
        ? "Valor ajustado manualmente. Ao aplicar a precificação novamente, será recalculado pelas regras."
        : "Calculado em Parâmetros → Precificação. Duplo clique para ajustar.";
    }
  }

  async function editarValorDrop() {
    if (!idProduto) {
      await Swal.fire("Atenção", "Salve o produto antes de alterar o valor Drop.", "warning");
      return;
    }
    const atual = parseFloat(el.valor_drop?.value || "0") || 0;
    const aviso = await Swal.fire({
      icon: "info",
      title: "Valor Drop manual",
      html:
        "Este valor é oferecido aos vendedores na rede.<br><br>" +
        "<strong>Atenção:</strong> se você aplicar a precificação novamente " +
        "(Parâmetros → Precificação → <em>Aplicar agora</em>), este valor será " +
        "substituído pelo cálculo das regras.",
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
    const resp = await fetch(`${BASE}/valor-drop/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ id_produto: idProduto, valor_drop: vd }),
    });
    const j = await resp.json();
    if (!resp.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    el.valor_drop.value = j.valor_drop ?? vd;
    valorDropManual = true;
    syncValorDropUi();
    await Swal.fire({ icon: "success", title: "Salvo", text: j.message, timer: 2000, showConfirmButton: false });
  }

  el.valor_drop?.addEventListener("dblclick", () => {
    editarValorDrop().catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  function fmtData(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("pt-BR");
    } catch {
      return iso;
    }
  }

  function syncEstoqueUi() {
    const comVariacao = formatoAtual() === "E";
    const semProduto = !idProduto;
    if (el.avisoEstoqueVariacao) el.avisoEstoqueVariacao.hidden = !comVariacao;
    if (el.avisoEstoqueCadastro) el.avisoEstoqueCadastro.hidden = !semProduto || comVariacao;
    if (el.painelEstoqueDepositos) el.painelEstoqueDepositos.hidden = semProduto || comVariacao;
    if (el.avisoEstoqueDeposito) el.avisoEstoqueDeposito.hidden = comVariacao || semProduto;
    if (!comVariacao && idProduto) carregarEstoqueDepositos().catch(() => {});
  }

  async function carregarEstoqueDepositos() {
    if (!idProduto || !el.tblEstoqueDepositos) return;
    const r = await fetch(`${BASE}/estoque/depositos?id_produto=${idProduto}`, { credentials: "include" });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar estoque.");
    integradoBling = !!j.integrado_bling;
    estoqueDepositos = j.depositos || [];
    if (!estoqueDepositos.length) {
      el.tblEstoqueDepositos.innerHTML =
        `<tr><td colspan="3">Nenhum depósito cadastrado. Cadastre em Fornecedor → Depósitos.</td></tr>`;
      return;
    }
    el.tblEstoqueDepositos.innerHTML = estoqueDepositos
      .map(
        (d) => `<tr data-dep="${d.id_deposito}">
          <td>${d.nome}${d.vinculado_bling ? ' <span class="Cat_EstoqueTag">Bling</span>' : ""}</td>
          <td class="Cat_EstoqueSaldo" title="Duplo clique para editar">${d.quantidade}</td>
          <td>${fmtData(d.atualizado_em)}</td>
        </tr>`
      )
      .join("");
  }

  async function editarSaldoDeposito(idDeposito, saldoAtual) {
    const dep = estoqueDepositos.find((d) => d.id_deposito === idDeposito);
  let sincronizarBling = false;
    if (integradoBling) {
      const c = await Swal.fire({
        icon: "warning",
        title: "Produto integrado ao Bling",
        html: `Alterar o saldo também pode atualizar o estoque no Bling${dep?.vinculado_bling ? "" : " (depósito sem vínculo — só DropNexo)"}.`,
        showCancelButton: true,
        confirmButtonText: "Continuar",
        cancelButtonText: "Cancelar",
      });
      if (!c.isConfirmed) return;
      if (dep?.vinculado_bling) {
        const s = await Swal.fire({
          icon: "question",
          title: "Sincronizar com o Bling?",
          text: "O saldo será enviado ao depósito vinculado no Bling.",
          showCancelButton: true,
          confirmButtonText: "Sim, sincronizar",
          cancelButtonText: "Só no DropNexo",
        });
        sincronizarBling = s.isConfirmed;
      }
    }
    const r = await Swal.fire({
      title: `Saldo — ${dep?.nome || "Depósito"}`,
      input: "number",
      inputValue: saldoAtual,
      inputAttributes: { min: 0, step: 1 },
      showCancelButton: true,
      confirmButtonText: "Salvar",
    });
    if (!r.isConfirmed || r.value === undefined || r.value === "") return;
    const qtd = Math.max(0, parseInt(r.value, 10) || 0);
    const resp = await fetch(`${BASE}/estoque/depositos/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({
        id_produto: idProduto,
        id_deposito: idDeposito,
        quantidade: qtd,
        sincronizar_bling: sincronizarBling,
      }),
    });
    const j = await resp.json();
    if (!resp.ok || !j.success) throw new Error(j.message || "Erro ao salvar saldo.");
    await Swal.fire({ icon: "success", title: "Salvo", text: j.message, timer: 2200, showConfirmButton: false });
    await carregarEstoqueDepositos();
    if (el.quantidade) {
      const total = estoqueDepositos.reduce((s, d) => s + (d.quantidade || 0), 0);
      el.quantidade.value = String(total);
    }
  }

  el.tblEstoqueDepositos?.addEventListener("dblclick", (ev) => {
    const cell = ev.target.closest(".Cat_EstoqueSaldo");
    if (!cell || !idProduto) return;
    const row = cell.closest("tr");
    const idDep = parseInt(row?.dataset?.dep || "0", 10);
    if (!idDep) return;
    const atual = parseInt(cell.textContent || "0", 10) || 0;
    editarSaldoDeposito(idDep, atual).catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  function syncFormatoUi() {
    const comVariacao = formatoAtual() === "E";
    if (el.tabVariacoes) el.tabVariacoes.hidden = !comVariacao;
    if (el.avisoEstoqueVariacao) el.avisoEstoqueVariacao.hidden = !comVariacao;
    syncEstoqueUi();
    if (el.painel_variantes) el.painel_variantes.style.display = comVariacao && idProduto ? "block" : "none";
    if (el.avisoVariacoes) el.avisoVariacoes.style.display = comVariacao && !idProduto ? "block" : "none";
    if (!comVariacao) {
      const tabVar = document.querySelector('.Cat_Tab[data-tab="variacoes"]');
      if (tabVar?.classList.contains("is-active")) ativarTab("caracteristicas");
    }
    if (comVariacao && idProduto) {
      carregarVariantes().catch(() => {});
      carregarPresets().catch(() => {});
    }
  }

  async function carregarPresets() {
    if (!el.preset_variacao) return;
    const r = await fetch(`${BASE}/variantes/presets`);
    const j = await r.json();
    if (!r.ok || !j.success) return;
    const v = el.preset_variacao.value;
    el.preset_variacao.innerHTML = '<option value="">(selecione um modelo)</option>';
    (j.presets || []).forEach((p) => {
      const o = document.createElement("option");
      o.value = String(p.id);
      o.textContent = p.nome;
      el.preset_variacao.appendChild(o);
    });
    el.preset_variacao.value = v;
  }

  function ativarTab(cod) {
    document.querySelectorAll(".Cat_Tab").forEach((t) => {
      if (t.hidden) return;
      t.classList.toggle("is-active", t.dataset.tab === cod);
    });
    document.querySelectorAll(".Cat_TabPanel").forEach((p) => {
      const on = p.dataset.panel === cod;
      p.classList.toggle("is-active", on);
      p.hidden = !on;
    });
  }

  document.querySelectorAll(".Cat_Tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (!btn.hidden) {
        ativarTab(btn.dataset.tab);
        if (btn.dataset.tab === "estoque") syncEstoqueUi();
      }
    });
  });

  el.formato?.addEventListener("change", syncFormatoUi);

  function tipoDaImagem(img) {
    return img?.tipo || ((img?.caminho || img?.url || "").startsWith("http") ? "link" : "upload");
  }

  function rotuloOrdemImagem(idx) {
    if (idx === 0) return "Principal";
    return `${idx + 1}ª`;
  }

  function syncModoImagem() {
    const locked = galeriaImagens.length > 0;
    const tipo = tipoGaleria || (locked ? tipoDaImagem(galeriaImagens[0]) : null);
    document.querySelectorAll('input[name="img_modo"]').forEach((r) => {
      const opt = r.closest(".Cat_ImgModoOpt");
      r.disabled = locked;
      if (opt) opt.classList.toggle("is-locked", locked);
      if (locked && tipo && r.value === tipo) r.checked = true;
    });
    const modo = document.querySelector('input[name="img_modo"]:checked')?.value || "link";
    if (el.painelImgLink) el.painelImgLink.hidden = modo !== "link";
    if (el.painelImgUpload) el.painelImgUpload.hidden = modo !== "upload";
  }

  document.querySelectorAll('input[name="img_modo"]').forEach((r) => {
    r.addEventListener("change", () => {
      if (galeriaImagens.length) return;
      syncModoImagem();
    });
  });
  syncModoImagem();

  function formatarTamanho(bytes) {
    if (bytes == null || bytes === "") return "—";
    const n = Number(bytes);
    if (!Number.isFinite(n) || n <= 0) return "—";
    if (n < 1024) return `${n} B`;
    if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
    return `${(n / (1024 * 1024)).toFixed(2)} MB`;
  }

  function imagemPrincipal() {
    return galeriaImagens.find((i) => i.principal) || galeriaImagens[0] || null;
  }

  function syncImagemHidden() {
    const princ = imagemPrincipal();
    if (el.imagem_caminho) {
      el.imagem_caminho.value = princ && !princ.url?.startsWith("http") ? princ.caminho || "" : "";
    }
    if (el.imagem_url) {
      el.imagem_url.value =
        princ && (princ.caminho || "").startsWith("http") ? princ.caminho : princ?.url?.startsWith("http") ? princ.url : "";
    }
  }

  function podeReordenarImagens() {
    return galeriaImagens.length > 1 && galeriaImagens.every((i) => i.id);
  }

  function rotuloOrigem(origem) {
    const map = {
      bling_interna: "Bling",
      bling_externa: "Link ext.",
      manual_url: "URL",
      manual_upload: "Upload",
    };
    return map[origem] || "";
  }

  function renderRegrasAtributo() {
    if (!el.painelImgAtributo) return;
    const comVar = formatoAtual() === "E" && idProduto && galeriaImagens.length > 0;
    el.painelImgAtributo.hidden = !comVar;
    if (!comVar) return;

    if (el.img_attr_nome) {
      const nomes = [...new Set(atributosProduto.map((a) => a.nome).filter(Boolean))];
      el.img_attr_nome.innerHTML = nomes.map((n) => `<option value="${n}">${n}</option>`).join("");
    }
    if (el.img_attr_imagem) {
      el.img_attr_imagem.innerHTML = galeriaImagens
        .filter((i) => i.id)
        .map(
          (img, idx) =>
            `<option value="${img.id}">Imagem ${idx + 1}${img.principal ? " (principal)" : ""}</option>`
        )
        .join("");
    }
    if (el.lista_img_atributo) {
      if (!regrasAtributo.length) {
        el.lista_img_atributo.innerHTML = '<li class="Cat_ImagemHint">Nenhuma regra cadastrada.</li>';
        return;
      }
      el.lista_img_atributo.innerHTML = regrasAtributo
        .map(
          (r) =>
            `<li><img src="${r.url || ""}" alt="" /><span><strong>${r.nome_atributo}</strong> = ${r.valor}</span></li>`
        )
        .join("");
    }
  }

  function renderGaleria() {
    if (!el.galeria_imagens) return;
    if (el.imgContador) el.imgContador.textContent = `${galeriaImagens.length} / ${MAX_IMAGENS} imagens`;
    syncImagemHidden();
    syncModoImagem();
    if (!galeriaImagens.length) {
      el.galeria_imagens.innerHTML = '<p class="Cat_ImagemHint">Nenhuma imagem cadastrada.</p>';
      syncAvisoImagens();
      return;
    }
    const drag = podeReordenarImagens();
    el.galeria_imagens.innerHTML = galeriaImagens
      .map(
        (img, idx) => `<div class="Cat_GaleriaItem${drag ? " is-draggable" : ""}" data-idx="${idx}" ${drag ? 'draggable="true"' : ""}>
        <span class="Cat_GaleriaOrdem">${rotuloOrdemImagem(idx)}</span>
        <button type="button" class="Cat_GaleriaRm" data-id="${img.id ?? ""}" data-idx="${idx}" title="Remover">×</button>
        <img src="${img.url || ""}" alt="" loading="lazy" draggable="false" />
        <div class="Cat_GaleriaMeta">
          <div><strong>${(img.extensao || "—").toUpperCase()}</strong>${rotuloOrigem(img.origem) ? ` · ${rotuloOrigem(img.origem)}` : ""}</div>
          <div>${formatarTamanho(img.tamanho_bytes)}</div>
        </div>
      </div>`
      )
      .join("");
    if (el.avisoImgOrdem) el.avisoImgOrdem.hidden = !drag;
    if (drag) {
      el.galeria_imagens.querySelectorAll(".Cat_GaleriaItem.is-draggable").forEach((item) => {
        item.addEventListener("dragstart", (ev) => {
          imgDragIdx = Number(item.dataset.idx);
          item.classList.add("is-dragging");
          ev.dataTransfer.effectAllowed = "move";
        });
        item.addEventListener("dragend", () => {
          item.classList.remove("is-dragging");
          imgDragIdx = null;
          el.galeria_imagens.querySelectorAll(".Cat_GaleriaItem").forEach((n) => n.classList.remove("is-dragover"));
        });
        item.addEventListener("dragover", (ev) => {
          ev.preventDefault();
          ev.dataTransfer.dropEffect = "move";
          item.classList.add("is-dragover");
        });
        item.addEventListener("dragleave", () => item.classList.remove("is-dragover"));
        item.addEventListener("drop", (ev) => {
          ev.preventDefault();
          item.classList.remove("is-dragover");
          const toIdx = Number(item.dataset.idx);
          if (imgDragIdx == null || imgDragIdx === toIdx) return;
          reordenarImagensLocal(imgDragIdx, toIdx);
        });
      });
    }
    syncAvisoImagens();
    renderRegrasAtributo();
  }

  async function reordenarImagensLocal(from, to) {
    const arr = galeriaImagens.slice();
    const [moved] = arr.splice(from, 1);
    arr.splice(to, 0, moved);
    galeriaImagens = arr;
    renderGaleria();
    const ids = galeriaImagens.map((i) => i.id).filter(Boolean);
    if (!ids.length) return;
    const r = await fetch(`${BASE}/imagens/ordenar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_produto: idProduto, ids }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao ordenar.");
    await carregarImagens();
  }

  async function carregarImagens() {
    if (!idProduto) {
      galeriaImagens = [];
      tipoGaleria = null;
      renderGaleria();
      return;
    }
    const r = await fetch(`${BASE}/imagens/lista?id_produto=${idProduto}`);
    const j = await r.json();
    if (!r.ok || !j.success) return;
    galeriaImagens = j.imagens || [];
    tipoGaleria = j.imagem_modo || j.tipo_galeria || null;
    regrasAtributo = j.regras_atributo || [];
    if (tipoGaleria) {
      const radio = document.querySelector(`input[name="img_modo"][value="${tipoGaleria}"]`);
      if (radio) radio.checked = true;
    }
    renderGaleria();
  }

  async function associarImagemAtributo() {
    if (!idProduto) throw new Error("Salve o produto antes.");
    const nome = (el.img_attr_nome?.value || "").trim();
    const valor = (el.img_attr_valor?.value || "").trim();
    const idImagem = Number(el.img_attr_imagem?.value || 0);
    if (!nome || !valor || !idImagem) throw new Error("Preencha atributo, valor e imagem.");
    const r = await fetch(`${BASE}/imagens/atributo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_produto: idProduto,
        nome_atributo: nome,
        valor,
        id_imagem: idImagem,
      }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    regrasAtributo = j.regras || [];
    if (el.img_attr_valor) el.img_attr_valor.value = "";
    renderRegrasAtributo();
    await Swal.fire("Sucesso", j.message, "success");
  }

  function syncAvisoImagens() {
    if (!el.avisoImgSalvar) return;
    el.avisoImgSalvar.style.display = idProduto ? "none" : "block";
    const modo = document.querySelector('input[name="img_modo"]:checked')?.value || "link";
    const cheio = galeriaImagens.length >= MAX_IMAGENS;
    const desabilitado = !idProduto || cheio;
    if (el.btnImgLink) el.btnImgLink.disabled = desabilitado || modo !== "link";
    if (el.btnImgUpload) el.btnImgUpload.disabled = desabilitado || modo !== "upload";
  }

  async function incluirLink() {
    if (!idProduto) throw new Error("Salve o produto antes de incluir imagens.");
    const url = (el.img_link_url?.value || "").trim();
    if (!url) throw new Error("Informe a URL da imagem.");
    const r = await fetch(`${BASE}/imagens/link`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_produto: idProduto, url }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    if (el.img_link_url) el.img_link_url.value = "";
    await carregarImagens();
  }

  async function enviarUpload() {
    if (!idProduto) throw new Error("Salve o produto antes de enviar imagens.");
    const f = el.arquivo_imagem?.files?.[0];
    if (!f) throw new Error("Selecione um arquivo.");
    const fd = new FormData();
    fd.append("id_produto", String(idProduto));
    fd.append("arquivo", f);
    const r = await fetch(`${BASE}/imagens/upload`, { method: "POST", body: fd });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao enviar.");
    if (el.arquivo_imagem) el.arquivo_imagem.value = "";
    await carregarImagens();
  }

  async function removerImagem(idImg, idx) {
    if (!idProduto) return;
    const payload = { id_produto: idProduto };
    if (idImg) payload.id_imagem = idImg;
    else payload.limpar_principal = true;
    const r = await fetch(`${BASE}/imagens/remover`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await carregarImagens();
  }

  async function carregarCombos() {
    const r = await fetch(`${BASE}/combos`);
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro nos combos.");
    if (el.lista_unidades) {
      el.lista_unidades.innerHTML = "";
      (j.unidades || ["UN"]).forEach((u) => {
        const o = document.createElement("option");
        o.value = u;
        el.lista_unidades.appendChild(o);
      });
    }
    if (!el.unidade.value) el.unidade.value = "UN";
    el.id_categoria.innerHTML = '<option value="">(sem categoria)</option>';
    (j.categorias || []).forEach((c) => {
      const o = document.createElement("option");
      o.value = c.id;
      o.textContent = c.nome;
      el.id_categoria.appendChild(o);
    });
  }

  function rotuloAttr(atributos) {
    if (!atributos || typeof atributos !== "object") return "—";
    return (
      Object.entries(atributos)
        .map(([k, v]) => `${k}: ${v}`)
        .join(" · ") || "—"
    );
  }

  function renderAtributos() {
    if (!el.lista_atributos) return;
    if (!atributosProduto.length) {
      el.lista_atributos.innerHTML = '<span class="Cat_ImagemHint">Nenhum atributo. Ex.: Cor → Azul, Verde.</span>';
      return;
    }
    el.lista_atributos.innerHTML = atributosProduto
      .map(
        (a) =>
          `<span class="Cat_VarTag">${a.nome}: ${(a.valores || []).join(", ")}
          <button type="button" class="Cat_VarTagRm" data-nome="${a.nome}" title="Remover">×</button></span>`
      )
      .join("");
  }

  async function carregarVariantes() {
    if (!idProduto || !el.lista_variantes) return;
    const r = await fetch(`${BASE}/variantes/lista?id_produto=${idProduto}`);
    const j = await r.json();
    if (!r.ok || !j.success) return;
    atributosProduto = j.atributos || [];
    renderRegrasAtributo();
    renderAtributos();
    const u = util();
    const rows = (j.variantes || []).filter((v) => Object.keys(v.atributos || {}).length > 0);
    if (!rows.length) {
      el.lista_variantes.innerHTML =
        "<tr><td colspan='7'>Nenhuma variante. Adicione uma variação ou aplique um modelo.</td></tr>";
      return;
    }
    el.lista_variantes.innerHTML = rows
      .map(
        (v) => `<tr>
        <td>${v.sku || "—"}</td>
        <td>${v.nome_exibicao || ""}</td>
        <td>${rotuloAttr(v.atributos)}</td>
        <td>${Number(v.preco || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" })}</td>
        <td>${v.estoque ?? 0}</td>
        <td>${v.herda_pai !== false ? "Sim" : "Não"}</td>
        <td class="Cl_TableActions">
          <button type="button" class="Cl_BtnAcao btnEditVar" data-id="${v.id}">${u.gerarIconeTech("editar")}</button>
        </td>
      </tr>`
      )
      .join("");
    window.lucide?.createIcons?.();
  }

  function abrirVariante(idVar) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: `${BASE}/variante/editar?id_variante=${idVar}&id_produto=${idProduto}`,
      titulo: "Detalhes da variação",
      largura: 880,
      altura: 580,
      nivel: 2,
      id: idVar,
    });
  }

  async function confirmarRegenerarVariacoes(acao) {
    const temAtributos = atributosProduto.length > 0;
    if (!temAtributos) return true;
    const c = await Swal.fire({
      title: "Recriar variações?",
      html:
        `Ao ${acao}, <strong>todas as variações atuais serão excluídas</strong> e geradas novamente ` +
        "com a combinação de atributos resultante.<br><br>Deseja continuar?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, continuar",
      cancelButtonText: "Cancelar",
    });
    return c.isConfirmed;
  }

  async function adicionarVariacao() {
    const nome = (el.attr_nome?.value || "").trim();
    const raw = (el.attr_valores?.value || "").trim();
    if (!nome || !raw) throw new Error("Informe nome e opções do atributo.");
    if (!(await confirmarRegenerarVariacoes("adicionar este atributo"))) return;
    const valores = raw
      .split(/[,;\n]+/)
      .map((s) => s.trim())
      .filter(Boolean);
    const r = await fetch(`${BASE}/variantes/adicionar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_produto: idProduto, nome, valores }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    if (el.attr_nome) el.attr_nome.value = "";
    if (el.attr_valores) el.attr_valores.value = "";
    if (el.formato) el.formato.value = j.criadas ? "E" : "S";
    syncFormatoUi();
    await Swal.fire(j.criadas ? "Sucesso" : "Atenção", j.message, j.criadas ? "success" : "info");
    await carregarVariantes();
  }

  async function aplicarPreset() {
    const idPreset = el.preset_variacao?.value;
    if (!idPreset) throw new Error("Selecione um modelo.");
    if (!(await confirmarRegenerarVariacoes("aplicar este modelo"))) return;
    const r = await fetch(`${BASE}/variantes/aplicar-preset`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_produto: idProduto, id_preset: Number(idPreset) }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    if (el.formato) el.formato.value = "E";
    syncFormatoUi();
    await Swal.fire("Sucesso", j.message, "success");
    await carregarVariantes();
  }

  async function excluirAtributo(nome) {
    const c = await Swal.fire({
      title: "Excluir atributo?",
      html:
        `O atributo <strong>${nome}</strong> será removido.<br><br>` +
        "<strong>Todas as variações criadas serão excluídas</strong> e, se ainda houver " +
        "mais de uma combinação possível com os atributos restantes, elas serão geradas novamente.",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, excluir e recriar",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;
    const r = await fetch(`${BASE}/atributos/excluir`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_produto: idProduto, nome }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    if (el.formato && !j.criadas) el.formato.value = "S";
    syncFormatoUi();
    await Swal.fire("Pronto", j.message || "Atributo removido.", "success");
    await carregarVariantes();
  }

  async function novaVarianteDialog() {
    const { value: form } = await Swal.fire({
      title: "Nova variante",
      html: `
        <input id="sw_sku" class="swal2-input" placeholder="SKU" />
        <input id="sw_nome" class="swal2-input" placeholder="Nome (ex. Tam. 40)" />
        <input id="sw_preco" class="swal2-input" type="number" placeholder="Preço" />
        <input id="sw_est" class="swal2-input" type="number" placeholder="Estoque" />`,
      focusConfirm: false,
      showCancelButton: true,
      preConfirm: () => ({
        sku: document.getElementById("sw_sku").value,
        nome_exibicao: document.getElementById("sw_nome").value,
        preco: document.getElementById("sw_preco").value,
        quantidade: document.getElementById("sw_est").value,
      }),
    });
    if (!form) return;
    const r = await fetch(`${BASE}/variantes/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_produto: idProduto,
        sku: form.sku,
        nome_exibicao: form.nome_exibicao || form.sku,
        preco: form.preco,
        quantidade: form.quantidade,
      }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await carregarVariantes();
  }

  function condicaoParaSalvar() {
    const v = (el.condicao?.value || "").trim();
    return CONDICOES.has(v) ? v : "";
  }

  function preencherDados(d) {
    el.nome.value = d.nome || "";
    el.sku.value = d.sku || "";
    el.formato.value = d.formato === "E" ? "E" : "S";
    el.preco.value = d.preco ?? d.valor_atacado ?? "";
    el.valor_drop.value = d.valor_drop ?? "";
    valorDropManual = !!d.valor_drop_manual;
    syncValorDropUi();
    el.preco_custo.value = d.preco_custo ?? "";
    el.unidade.value = d.unidade || "UN";
    const cond = d.condicao || d.referencia || "";
    el.condicao.value = CONDICOES.has(cond) ? cond : "";
    if (window.CatDescricaoEditor) {
      CatDescricaoEditor.setValue(d.descricao || "");
    } else if (el.descricao) {
      el.descricao.value = d.descricao || "";
    }
    el.marca.value = d.marca || "";
    el.peso_liquido_kg.value = d.peso_liquido_kg ?? "";
    el.peso_bruto_kg.value = d.peso_bruto_kg ?? "";
    el.largura_cm.value = d.largura_cm ?? "";
    el.altura_cm.value = d.altura_cm ?? "";
    el.profundidade_cm.value = d.profundidade_cm ?? "";
    el.itens_por_caixa.value = d.moq ?? d.itens_por_caixa ?? 1;
    el.gtin.value = d.gtin || "";
    el.ncm.value = d.ncm || "";
    el.cest.value = d.cest || "";
    el.origem_fiscal.value = d.origem_fiscal || "";
    el.volumes.value = d.volumes ?? "";
    el.producao.value = d.producao || "";
    if (el.frete_gratis) el.frete_gratis.checked = !!d.frete_gratis;
    el.id_categoria.value = d.id_categoria ? String(d.id_categoria) : "";
    el.quantidade.value = d.quantidade ?? 0;
    el.ativo.checked = d.ativo !== false;
    el.publicado.checked = !!d.publicado;
    el.btnExcluir.style.display = "inline-block";
    syncFormatoUi();
    syncEstoqueUi();
    carregarImagens().then(syncAvisoImagens);
  }

  async function carregarApoio(id) {
    const r = await fetch(`${BASE}/apoio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    preencherDados(j.dados);
  }

  function imagemParaSalvar() {
    syncImagemHidden();
    return (el.imagem_caminho?.value || "").trim() || (el.imagem_url?.value || "").trim() || "";
  }

  async function salvar() {
    const preco = el.preco?.value;
    const pesoLiq = el.peso_liquido_kg?.value;
    const body = {
      id: idProduto,
      nome: (el.nome.value || "").trim(),
      sku: (el.sku.value || "").trim(),
      formato: formatoAtual(),
      preco,
      valor_atacado: preco,
      unidade: (el.unidade.value || "UN").trim().slice(0, 20),
      referencia: condicaoParaSalvar() || null,
      condicao: condicaoParaSalvar() || null,
      preco_custo: el.preco_custo?.value || null,
      ncm: (el.ncm?.value || "").trim(),
      cest: (el.cest?.value || "").trim() || null,
      origem_fiscal: (el.origem_fiscal?.value || "").trim() || null,
      volumes: el.volumes?.value || null,
      producao: (el.producao?.value || "").trim() || null,
      frete_gratis: !!el.frete_gratis?.checked,
      descricao: window.CatDescricaoEditor
        ? CatDescricaoEditor.getValue()
        : (el.descricao?.value || "").trim(),
      marca: (el.marca.value || "").trim(),
      peso_liquido_kg: pesoLiq || null,
      peso_bruto_kg: el.peso_bruto_kg?.value || null,
      largura_cm: el.largura_cm?.value || null,
      altura_cm: el.altura_cm?.value || null,
      profundidade_cm: el.profundidade_cm?.value || null,
      moq: el.itens_por_caixa?.value || 1,
      peso_gramas: pesoLiq ? Math.round(Number(pesoLiq) * 1000) : null,
      gtin: (el.gtin.value || "").trim(),
      id_categoria: el.id_categoria.value || null,
      quantidade: el.quantidade.value,
      imagem_url: imagemParaSalvar(),
      ativo: !!el.ativo.checked,
      publicado: !!el.publicado.checked,
    };
    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    idProduto = j.id || idProduto;
    if (el.id) el.id.value = String(idProduto);
    syncFormatoUi();
    syncAvisoImagens();
    await Swal.fire("Sucesso", j.message, "success");
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  async function excluir() {
    if (!idProduto) return;
    const c = await Swal.fire({
      title: "Excluir produto?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, excluir",
    });
    if (!c.isConfirmed) return;
    const r = await fetch(`${BASE}/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idProduto }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await Swal.fire("Sucesso", j.message, "success");
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  el.btnSalvar?.addEventListener("click", () => salvar().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnExcluir?.addEventListener("click", () => excluir().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnNovaVariante?.addEventListener("click", () => novaVarianteDialog().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnAdicionarVariacao?.addEventListener("click", () => adicionarVariacao().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnAplicarPreset?.addEventListener("click", () => aplicarPreset().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnImgLink?.addEventListener("click", () => incluirLink().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnImgUpload?.addEventListener("click", () => enviarUpload().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnImgAtributo?.addEventListener("click", () =>
    associarImagemAtributo().catch((e) => Swal.fire("Erro", e.message, "error"))
  );
  el.lista_atributos?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".Cat_VarTagRm");
    if (!btn) return;
    excluirAtributo(btn.dataset.nome).catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  el.lista_variantes?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".btnEditVar");
    if (!btn) return;
    abrirVariante(+btn.dataset.id);
  });
  el.galeria_imagens?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".Cat_GaleriaRm");
    if (!btn) return;
    const rawId = (btn.dataset.id || "").trim();
    const idImg = rawId ? Number(rawId) : null;
    removerImagem(idImg, Number(btn.dataset.idx)).catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  window.addEventListener("message", (ev) => {
    if (ev.data?.grupo === "atualizarVariantes" && ev.data.id_produto == idProduto) {
      carregarVariantes().catch(() => {});
    }
  });

  if (el.btnExcluir) el.btnExcluir.style.display = "none";

  let combosProntos = false;
  let idPendente = null;

  async function aplicarId(id, nivel) {
    idProduto = id ? Number(id) : null;
    nivelModal = nivel || 1;
    if (el.id) el.id.value = idProduto ? String(idProduto) : "";
    syncAvisoImagens();
    if (!idProduto) {
      syncFormatoUi();
      renderGaleria();
      return;
    }
    if (!combosProntos) {
      idPendente = idProduto;
      return;
    }
    await carregarApoio(idProduto);
  }

  if (window.GlobalUtils?.receberDadosApoio) {
    window.GlobalUtils.receberDadosApoio((id, nivel) => aplicarId(id, nivel));
  }

  syncFormatoUi();
  syncAvisoImagens();
  renderGaleria();
  carregarCombos()
    .then(() => {
      combosProntos = true;
      if (idPendente != null) {
        const id = idPendente;
        idPendente = null;
        return carregarApoio(id);
      }
    })
    .catch((e) => Swal.fire("Erro", e.message, "error"));
})();
