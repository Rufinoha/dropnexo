(function () {
  const grid = document.getElementById("ob_gridFornecedores");
  const msgVazio = document.getElementById("ob_msgVazio");
  const inpBusca = document.getElementById("ob_filtroBusca");
  const btnBuscar = document.getElementById("ob_btnBuscar");
  const modal = document.getElementById("ob_modalCatalogo");
  const modalTitulo = document.getElementById("ob_modalTitulo");
  const modalProdutos = document.getElementById("ob_modalProdutos");
  const fecharModal = document.getElementById("ob_fecharModal");

  if (!grid) return;

  function fecharModalCatalogo() {
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    document.body.classList.remove("forn-modal-aberto");
  }

  function abrirModalCatalogo() {
    if (!modal) return;
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("forn-modal-aberto");
  }

  if (modal) {
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
  }

  const fmtMoeda = (v) =>
    (window.Util && Util.formatarMoeda
      ? Util.formatarMoeda(v)
      : "R$ " + Number(v || 0).toFixed(2).replace(".", ","));

  const statusLabel = {
    nenhum: { cls: "", txt: "Não conectado" },
    aguardando: { cls: "is-pending", txt: "Aguardando aprovação do fornecedor" },
    ativo: { cls: "is-active", txt: "Conectado" },
    recusado: { cls: "is-denied", txt: "Não aprovado" },
    inativo: { cls: "is-denied", txt: "Vínculo encerrado" },
  };

  async function carregar() {
    const busca = (inpBusca && inpBusca.value) || "";
    const url = "/fornecedores/rede" + (busca ? "?busca=" + encodeURIComponent(busca) : "");
    const r = await fetch(url, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      grid.innerHTML = "";
      if (msgVazio) {
        msgVazio.hidden = false;
        msgVazio.textContent = j.message || "Erro ao carregar.";
      }
      return;
    }
    const lista = j.fornecedores || [];
    if (!lista.length) {
      grid.innerHTML = "";
      if (msgVazio) msgVazio.hidden = false;
      return;
    }
    if (msgVazio) msgVazio.hidden = true;
    grid.innerHTML = lista
      .map((f) => {
        const st = statusLabel[f.status_vinculo] || statusLabel.nenhum;
        const chips = (f.segmentos || [])
          .map((s) => `<span class="Forn_Chip">${s}</span>`)
          .join("");
        const podeAtivar = !f.status_vinculo || f.status_vinculo === "nenhum" || f.status_vinculo === "recusado" || f.status_vinculo === "inativo";
        return `
        <article class="Forn_Card ${st.cls}" data-id="${f.id}">
          <h3 class="Forn_CardNome">${f.nome}</h3>
          <p class="Forn_CardLocal">${f.cidade || "—"}${f.uf ? " / " + f.uf : ""}</p>
          <div class="Forn_CardChips">${chips || '<span class="Forn_Chip Forn_Chip--muted">Segmentos em breve</span>'}</div>
          <p class="Forn_CardContato">${f.telefone ? "Tel: " + f.telefone + "<br>" : ""}${f.email || ""}</p>
          <p class="Forn_CardStatus">${st.txt}</p>
          <div class="Forn_CardAcoes">
            <button type="button" class="Cl_BtnSecundario" data-acao="catalogo" data-id="${f.id}" data-nome="${f.nome}">Ver catálogo</button>
            ${podeAtivar ? `<button type="button" class="Cl_BtnPrincipal" data-acao="ativar" data-id="${f.id}">Ativar fornecedor</button>` : ""}
          </div>
        </article>`;
      })
      .join("");
  }

  async function abrirCatalogo(id, nome) {
    modalTitulo.textContent = "Catálogo — " + (nome || "");
    modalProdutos.innerHTML = "<p>Carregando…</p>";
    abrirModalCatalogo();
    const r = await fetch("/fornecedores/" + id + "/catalogo", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      modalProdutos.innerHTML = "<p>" + (j.message || "Erro") + "</p>";
      return;
    }
    const prods = j.produtos || [];
    if (!prods.length) {
      modalProdutos.innerHTML = "<p>Nenhum produto publicado.</p>";
      return;
    }
    modalProdutos.innerHTML = prods
      .map(
        (p) => `
      <div class="Forn_ProdCard">
        ${p.imagem_url ? `<img src="${p.imagem_url}" alt="" />` : ""}
        <strong>${p.nome}</strong>
        <span>${fmtMoeda(p.preco)}</span>
        <small>Estoque: ${p.estoque}</small>
      </div>`
      )
      .join("");
  }

  async function solicitarVinculo(id) {
    const r = await fetch("/fornecedores/solicitar-vinculo", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_fornecedor: id }),
    });
    const j = await r.json();
    if (window.Util && Util.alertar) Util.alertar(j.message || (j.success ? "OK" : "Erro"), j.success ? "success" : "error");
    if (j.success) carregar();
  }

  grid.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-acao]");
    if (!btn) return;
    const id = btn.getAttribute("data-id");
    if (btn.getAttribute("data-acao") === "catalogo") abrirCatalogo(id, btn.getAttribute("data-nome"));
    if (btn.getAttribute("data-acao") === "ativar") solicitarVinculo(id);
  });

  if (btnBuscar) btnBuscar.addEventListener("click", carregar);
  if (inpBusca) inpBusca.addEventListener("keydown", (e) => e.key === "Enter" && carregar());
  if (fecharModal) fecharModal.addEventListener("click", fecharModalCatalogo);
  if (modal) {
    modal.addEventListener("click", (e) => {
      if (e.target === modal) fecharModalCatalogo();
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && !modal.hidden) fecharModalCatalogo();
  });

  carregar();
})();
