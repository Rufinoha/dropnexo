(function () {
  const params = new URLSearchParams(window.location.search);
  let idVariante = Number(params.get("id_variante") || 0);
  let idProduto = Number(params.get("id_produto") || 0);
  let nivelModal = 2;
  let dadosPai = null;
  let atributosCache = {};

  const el = {
    id_variante: document.getElementById("id_variante"),
    id_produto: document.getElementById("id_produto"),
    titulo: document.getElementById("titulo_variante"),
    herda_pai: document.getElementById("herda_pai"),
    hint_herda: document.getElementById("hint_herda"),
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
    imagem_url: document.getElementById("imagem_url"),
    imagem_caminho: document.getElementById("imagem_caminho"),
    preview_imagem: document.getElementById("preview_imagem"),
    btnSalvar: document.getElementById("btnSalvar"),
    btnExcluir: document.getElementById("btnExcluir"),
  };
  if (!el.nome_exibicao) return;

  const BASE = "/catalogos";
  const camposHerdaveis = document.querySelectorAll(
    "#preco, #preco_promocional, #preco_custo, #peso_liquido_kg, #peso_bruto_kg, #altura_cm, #largura_cm, #profundidade_cm, #gtin, #ncm, #imagem_url"
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
    btn.addEventListener("click", () => ativarTab(btn.dataset.tab));
  });

  function syncHerdaUi() {
    const h = !!el.herda_pai?.checked;
    camposHerdaveis.forEach((inp) => {
      inp.disabled = h;
      inp.classList.toggle("Cat_CampoHerdado", h);
    });
    if (el.hint_herda) {
      el.hint_herda.textContent = h
        ? "Preço, peso, GTIN e imagem seguem o cadastro do pai."
        : "Esta variante usa valores próprios (independentes do pai).";
    }
  }

  function rotuloAttr(atributos) {
    if (!atributos || typeof atributos !== "object") return "";
    return Object.entries(atributos)
      .map(([k, v]) => `${k}: ${v}`)
      .join(" · ");
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
    const img = d.imagem_url || "";
    if (el.imagem_caminho) el.imagem_caminho.value = d.imagem_caminho || "";
    if (el.imagem_url) el.imagem_url.value = d.imagem_caminho ? "" : img;
    if (el.preview_imagem) {
      if (img) {
        el.preview_imagem.src = img;
        el.preview_imagem.hidden = false;
      } else {
        el.preview_imagem.hidden = true;
      }
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
    preencher(j.dados, j.pai);
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
      imagem_url: (el.imagem_caminho?.value || "").trim() || (el.imagem_url?.value || "").trim(),
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
  el.imagem_url?.addEventListener("input", () => {
    if (el.imagem_caminho) el.imagem_caminho.value = "";
    const u = (el.imagem_url.value || "").trim();
    if (el.preview_imagem) {
      if (u) {
        el.preview_imagem.src = u;
        el.preview_imagem.hidden = false;
      } else el.preview_imagem.hidden = true;
    }
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
