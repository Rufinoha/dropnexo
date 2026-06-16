(function () {
  const elPage = document.getElementById("fn_int_page");
  const elSubnav = document.getElementById("fn_int_subnav");
  const elTitulo = document.getElementById("fn_int_titulo");
  const elSubtitulo = document.getElementById("fn_int_subtitulo");
  const elGrid = document.getElementById("fn_int_grid");
  const elCatalogo = document.getElementById("fn_int_catalogo");
  if (!elPage || !elSubnav || !elGrid || !elCatalogo) return;

  let categorias = [];
  try {
    categorias = JSON.parse(elCatalogo.textContent || "[]");
  } catch {
    categorias = [];
  }

  let categoriaAtiva = categorias[0]?.id || "";

  const ICONES_CATEGORIA = {
    marketplace: "store",
    ecommerce: "shopping-bag",
    frete: "truck",
    erp: "layout-grid",
  };

  function renderSubnav() {
    elSubnav.innerHTML = categorias
      .map(
        (cat) => `
      <button type="button" class="FnInt_SubItem${cat.id === categoriaAtiva ? " is-active" : ""}"
        data-cat="${cat.id}" aria-current="${cat.id === categoriaAtiva ? "page" : "false"}">
        <span class="FnInt_SubIco" aria-hidden="true"><i data-lucide="${ICONES_CATEGORIA[cat.id] || "plug"}"></i></span>
        <span>${cat.rotulo}</span>
      </button>`
      )
      .join("");
    window.lucide?.createIcons?.();
  }

  function cardHtml(item) {
    const cor = item.cor || "#475569";
    return `
      <button type="button" class="FnInt_Card" data-slug="${item.slug}" data-nome="${item.nome}" role="listitem">
        <div class="FnInt_CardIcon" style="--int-cor:${cor}">
          <img src="${item.icone_png}" alt="" loading="eager" decoding="async"
            onload="this.parentElement.classList.remove('is-fallback')"
            onerror="this.onerror=null;this.src='${item.icone_svg}';this.addEventListener('error',()=>{this.parentElement.classList.add('is-fallback')},{once:true})" />
          <span class="FnInt_CardFallback">${item.iniciais || item.nome.slice(0, 2).toUpperCase()}</span>
        </div>
        <div class="FnInt_CardBody">
          <p class="FnInt_CardNome">${item.nome}</p>
          <p class="FnInt_CardDesc">${item.descricao || ""}</p>
        </div>
      </button>`;
  }

  function renderCategoria(catId) {
    const cat = categorias.find((c) => c.id === catId);
    if (!cat) return;
    categoriaAtiva = cat.id;
    if (elTitulo) elTitulo.textContent = cat.titulo || cat.rotulo;
    if (elSubtitulo) elSubtitulo.textContent = cat.subtitulo || "";
    elGrid.innerHTML = (cat.itens || []).map(cardHtml).join("") || "<p class=\"FnInt_Subtitulo\">Nenhuma integração nesta categoria.</p>";
    renderSubnav();
  }

  function abrirIntegracao(slug, nome) {
    Swal.fire({
      title: nome,
      html: `<p style="color:#64748b;margin:0">A conexão com <strong>${nome}</strong> estará disponível em breve.</p>`,
      icon: "info",
      confirmButtonText: "Entendi",
      confirmButtonColor: "#021F81",
    });
  }

  elSubnav.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".FnInt_SubItem");
    if (!btn) return;
    renderCategoria(btn.dataset.cat || "");
  });

  elGrid.addEventListener("click", (ev) => {
    const card = ev.target.closest(".FnInt_Card");
    if (!card) return;
    abrirIntegracao(card.dataset.slug || "", card.dataset.nome || "Integração");
  });

  if (categorias.length) {
    renderCategoria(categoriaAtiva);
  } else {
    elGrid.innerHTML = "<p class=\"FnInt_Subtitulo\">Catálogo de integrações indisponível.</p>";
  }
})();
