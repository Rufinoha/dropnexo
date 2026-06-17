(function () {
  const params = new URLSearchParams(window.location.search);
  let idVariante = Number(params.get("id_variante") || 0);
  let idProduto = Number(params.get("id_produto") || 0);
  let nivelModal = 2;
  let dadosPai = null;
  let atributosCache = {};
  let galeriaPai = [];
  let idImagemSelecionada = null;
  let integradoBling = false;
  let estoqueDepositos = [];

  const el = {
    id_variante: document.getElementById("id_variante"),
    id_produto: document.getElementById("id_produto"),
    titulo: document.getElementById("titulo_variante"),
    herda_pai: document.getElementById("herda_pai"),
    hint_herda: document.getElementById("hint_herda"),
    hint_imagem_variante: document.getElementById("hint_imagem_variante"),
    galeria_variante_pick: document.getElementById("galeria_variante_pick"),
    id_imagem_principal: document.getElementById("id_imagem_principal"),
    nome_exibicao: document.getElementById("nome_exibicao"),
    sku: document.getElementById("sku"),
    rotulo_attr: document.getElementById("rotulo_attr"),
    ativo: document.getElementById("ativo"),
    preco: document.getElementById("preco"),
    preco_promocional: document.getElementById("preco_promocional"),
    preco_custo: document.getElementById("preco_custo"),
    peso_liquido_kg: document.getElementById("peso_liquido_kg"),
    peso_bruto_kg: document.getElementById("peso_bruto_kg"),
    altura_cm: document.getElementById("altura_cm"),
    largura_cm: document.getElementById("largura_cm"),
    profundidade_cm: document.getElementById("profundidade_cm"),
    gtin: document.getElementById("gtin"),
    ncm: document.getElementById("ncm"),
    quantidade: document.getElementById("quantidade"),
    preview_imagem: document.getElementById("preview_imagem"),
    tblEstoqueDepositosVar: document.getElementById("tblEstoqueDepositosVar"),
    btnSalvar: document.getElementById("btnSalvar"),
    btnExcluir: document.getElementById("btnExcluir"),
  };
  if (!el.nome_exibicao) return;

  const BASE = "/catalogos";
  const camposHerdaveis = document.querySelectorAll(
    "#preco, #preco_promocional, #preco_custo, #peso_liquido_kg, #peso_bruto_kg, #altura_cm, #largura_cm, #profundidade_cm, #gtin, #ncm"
  );

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

  async function carregarEstoqueDepositos() {
    if (!idVariante || !el.tblEstoqueDepositosVar) return;
    const r = await fetch(
      `${BASE}/estoque/depositos?id_produto=${idProduto}&id_variante=${idVariante}`,
      { credentials: "include" }
    );
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar estoque.");
    integradoBling = !!j.integrado_bling;
    estoqueDepositos = j.depositos || [];
    if (!estoqueDepositos.length) {
      el.tblEstoqueDepositosVar.innerHTML =
        `<tr><td colspan="3">Nenhum depósito cadastrado. Cadastre em Fornecedor → Depósitos.</td></tr>`;
      return;
    }
    el.tblEstoqueDepositosVar.innerHTML = estoqueDepositos
      .map(
        (d) => `<tr data-dep="${d.id_deposito}">
          <td>${d.nome}${d.vinculado_bling ? ' <span class="Cat_EstoqueTag">Bling</span>' : ""}</td>
          <td class="Cat_EstoqueSaldo" title="Duplo clique para editar">${d.quantidade}</td>
          <td>${fmtData(d.atualizado_em)}</td>
        </tr>`
      )
      .join("");
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
        id_variante: idVariante,
        id_deposito: idDeposito,
        quantidade: qtd,
        sincronizar_bling: sincronizarBling,
      }),
    });
    const j = await resp.json();
    if (!resp.ok || !j.success) throw new Error(j.message || "Erro ao salvar saldo.");
    await Swal.fire({ icon: "success", title: "Salvo", text: j.message, timer: 2200, showConfirmButton: false });
    await carregarEstoqueDepositos();
  }

  el.tblEstoqueDepositosVar?.addEventListener("dblclick", (ev) => {
    const cell = ev.target.closest(".Cat_EstoqueSaldo");
    if (!cell || !idVariante) return;
    const row = cell.closest("tr");
    const idDep = parseInt(row?.dataset?.dep || "0", 10);
    if (!idDep) return;
    const atual = parseInt(cell.textContent || "0", 10) || 0;
    editarSaldoDeposito(idDep, atual).catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  function syncHerdaUi() {
    const h = !!el.herda_pai?.checked;
    camposHerdaveis.forEach((inp) => {
      inp.disabled = h;
      inp.classList.toggle("Cat_CampoHerdado", h);
    });
    if (el.hint_herda) {
      el.hint_herda.textContent = h
        ? "Preço, peso e GTIN seguem o cadastro do pai. A imagem usa a principal do pai."
        : "Esta variante usa valores próprios (independentes do pai).";
    }
    if (el.hint_imagem_variante) {
      el.hint_imagem_variante.hidden = h;
    }
    if (el.galeria_variante_pick) {
      el.galeria_variante_pick.hidden = h;
    }
    if (h) {
      idImagemSelecionada = null;
      if (el.id_imagem_principal) el.id_imagem_principal.value = "";
      const princ = galeriaPai.find((i) => i.principal) || galeriaPai[0];
      if (el.preview_imagem && princ?.url) {
        el.preview_imagem.src = princ.url;
        el.preview_imagem.hidden = false;
      } else if (el.preview_imagem && dadosPai?.imagem_url) {
        el.preview_imagem.src = dadosPai.imagem_url;
        el.preview_imagem.hidden = false;
      }
    } else {
      renderGaleriaPick();
    }
  }

  function rotuloAttr(atributos) {
    if (!atributos || typeof atributos !== "object") return "";
    return Object.entries(atributos)
      .map(([k, v]) => `${k}: ${v}`)
      .join(" · ");
  }

  function renderGaleriaPick() {
    if (!el.galeria_variante_pick) return;
    if (!galeriaPai.length) {
      el.galeria_variante_pick.innerHTML =
        '<p class="Cat_ImagemHint">Nenhuma imagem na galeria do pai. Cadastre na aba Imagens do produto.</p>';
      return;
    }
    el.galeria_variante_pick.innerHTML = galeriaPai
      .map(
        (img) => `<button type="button" class="Cat_GaleriaPickItem${
          Number(img.id) === Number(idImagemSelecionada) ? " is-selected" : ""
        }" data-id="${img.id}">
        <img src="${img.url || ""}" alt="" loading="lazy" />
        <span>${img.principal ? "Principal" : `#${(img.ordem || 0) + 1}`}</span>
      </button>`
      )
      .join("");
    el.galeria_variante_pick.querySelectorAll(".Cat_GaleriaPickItem").forEach((btn) => {
      btn.addEventListener("click", () => {
        idImagemSelecionada = Number(btn.dataset.id);
        if (el.id_imagem_principal) el.id_imagem_principal.value = String(idImagemSelecionada);
        const img = galeriaPai.find((i) => Number(i.id) === idImagemSelecionada);
        if (el.preview_imagem && img?.url) {
          el.preview_imagem.src = img.url;
          el.preview_imagem.hidden = false;
        }
        renderGaleriaPick();
      });
    });
    const sel = galeriaPai.find((i) => Number(i.id) === Number(idImagemSelecionada));
    if (el.preview_imagem && sel?.url) {
      el.preview_imagem.src = sel.url;
      el.preview_imagem.hidden = false;
    }
  }

  async function carregarGaleriaPai() {
    if (!idProduto) return;
    const r = await fetch(`${BASE}/imagens/lista?id_produto=${idProduto}`);
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
    if (el.rotulo_attr) el.rotulo_attr.value = rotuloAttr(d.atributos);
    atributosCache = d.atributos || {};
    el.ativo.checked = !!d.ativo;
    el.preco.value = d.preco ?? "";
    el.preco_promocional.value = d.preco_promocional ?? "";
    el.preco_custo.value = d.preco_custo ?? "";
    el.peso_liquido_kg.value = d.peso_liquido_kg ?? "";
    el.peso_bruto_kg.value = d.peso_bruto_kg ?? "";
    el.altura_cm.value = d.altura_cm ?? "";
    el.largura_cm.value = d.largura_cm ?? "";
    el.profundidade_cm.value = d.profundidade_cm ?? "";
    el.gtin.value = d.gtin || "";
    el.ncm.value = d.ncm || "";
    el.quantidade.value = d.estoque ?? 0;
    idImagemSelecionada = d.id_imagem_principal || null;
    if (el.id_imagem_principal) {
      el.id_imagem_principal.value = idImagemSelecionada ? String(idImagemSelecionada) : "";
    }
    syncHerdaUi();
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
    await carregarGaleriaPai();
    preencher(j.dados, j.pai);
    await carregarEstoqueDepositos().catch(() => {});
  }

  async function salvar() {
    const body = {
      id: idVariante,
      id_produto: idProduto,
      nome_exibicao: (el.nome_exibicao.value || "").trim(),
      sku: (el.sku.value || "").trim(),
      ativo: !!el.ativo.checked,
      herda_pai: !!el.herda_pai.checked,
      preco: el.preco.value,
      preco_promocional: el.preco_promocional.value,
      preco_custo: el.preco_custo.value,
      peso_liquido_kg: el.peso_liquido_kg.value,
      peso_bruto_kg: el.peso_bruto_kg.value,
      altura_cm: el.altura_cm.value,
      largura_cm: el.largura_cm.value,
      profundidade_cm: el.profundidade_cm.value,
      gtin: (el.gtin.value || "").trim(),
      ncm: (el.ncm.value || "").trim(),
      quantidade: el.quantidade.value,
      id_imagem_principal: el.herda_pai?.checked ? null : idImagemSelecionada,
      atributos: atributosCache,
    };
    const r = await fetch(`${BASE}/variantes/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    await Swal.fire("Sucesso", j.message, "success");
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.parent.postMessage({ grupo: "atualizarVariantes", id_produto: idProduto }, "*");
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
    const r = await fetch(`${BASE}/variantes/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idVariante }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await Swal.fire("Sucesso", j.message, "success");
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.parent.postMessage({ grupo: "atualizarVariantes", id_produto: idProduto }, "*");
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  el.herda_pai?.addEventListener("change", syncHerdaUi);
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
