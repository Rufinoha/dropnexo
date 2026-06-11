(function () {
  const elPage = document.getElementById("fn_int_page");
  const elSubnav = document.getElementById("fn_int_subnav");
  const elTitulo = document.getElementById("fn_int_titulo");
  const elSubtitulo = document.getElementById("fn_int_subtitulo");
  const elGrid = document.getElementById("fn_int_grid");
  const elCatalogo = document.getElementById("fn_int_catalogo");
  const elOverlay = document.getElementById("fn_int_overlay");
  const elDialog = document.getElementById("fn_int_connect_dialog");
  if (!elPage || !elSubnav || !elGrid || !elCatalogo) return;

  let categorias = [];
  try {
    categorias = JSON.parse(elCatalogo.textContent || "[]");
  } catch {
    categorias = [];
  }

  let categoriaAtiva = categorias[0]?.id || "";
  let itemModalAberto = null;
  let hubStatus = {
    bling: {
      conectado: false,
      config_url: "/integracoes/bling",
      oauth_url: "/api/integracoes/bling/oauth/iniciar",
    },
  };

  const ICONES_CATEGORIA = {
    marketplace: "store",
    ecommerce: "shopping-bag",
    frete: "truck",
    erp: "layout-grid",
  };

  const INTEGRACOES_ATIVAS = new Set(["bling"]);

  async function carregarStatusHub() {
    try {
      const r = await fetch("/api/integracoes/hub/status");
      const j = await r.json();
      if (j.success && j.integracoes) hubStatus = j.integracoes;
    } catch {
      /* mantém defaults */
    }
  }

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

  function statusIntegracao(slug) {
    return hubStatus[slug] || {};
  }

  function limparModal() {
    itemModalAberto = null;
    if (elDialog) {
      elDialog.hidden = true;
      elDialog.classList.remove("is-visible");
      elDialog.innerHTML = "";
    }
    if (elOverlay) {
      elOverlay.hidden = true;
      elOverlay.classList.remove("is-visible");
      elOverlay.setAttribute("aria-hidden", "true");
    }
    document.body.classList.remove("FnInt-modal-open");
    elGrid?.querySelectorAll(".FnInt_CardWrap.is-picked").forEach((el) => el.classList.remove("is-picked"));
  }

  function fecharModalCard() {
    limparModal();
  }

  function dialogHtml(item) {
    const st = statusIntegracao(item.slug);
    const cor = item.cor || "#28A745";
    const oauth = st.oauth_url || "/api/integracoes/bling/oauth/iniciar";
    return `
      <div class="FnInt_ConnectDialog__bar" aria-hidden="true"></div>
      <button type="button" class="FnInt_ConnectDialog__close" data-action="fechar-modal" aria-label="Fechar">
        <i data-lucide="x"></i>
      </button>
      <div class="FnInt_ConnectDialog__body">
        <div class="FnInt_ConnectDialog__logoWrap">
          <div class="FnInt_ConnectDialog__logo" style="--int-cor:${cor}">
            <img src="${item.icone_png}" alt=""
              onerror="this.style.display='none';var f=this.nextElementSibling;if(f)f.style.display='flex'" />
            <span class="FnInt_ConnectDialog__logoFallback" style="display:none">${item.iniciais || item.nome.slice(0, 2).toUpperCase()}</span>
          </div>
          <span class="FnInt_ConnectDialog__chip">Integração oficial</span>
        </div>
        <h2 class="FnInt_ConnectDialog__title" id="fn_int_dialog_title">Conectar ${item.nome}</h2>
        <p class="FnInt_ConnectDialog__desc">${item.descricao || "Sincronize dados entre plataformas."}</p>
        <div class="FnInt_ConnectDialog__actions">
          <a href="${oauth}" class="FnInt_ConnectDialog__btnPrimary">
            <i data-lucide="link-2"></i>
            <span>Conectar conta</span>
          </a>
          <button type="button" class="FnInt_ConnectDialog__btnGhost" data-action="fechar-modal">Agora não</button>
        </div>
        <p class="FnInt_ConnectDialog__hint">
          <i data-lucide="shield-check"></i>
          Redirecionamento seguro para autorizar o acesso.
        </p>
      </div>`;
  }

  function abrirModalCard(item) {
    itemModalAberto = item;
    if (elDialog) {
      elDialog.innerHTML = dialogHtml(item);
      elDialog.hidden = false;
    }
    if (elOverlay) {
      elOverlay.hidden = false;
      elOverlay.setAttribute("aria-hidden", "false");
      requestAnimationFrame(() => {
        elOverlay.classList.add("is-visible");
        elDialog?.classList.add("is-visible");
      });
    }
    document.body.classList.add("FnInt-modal-open");
    const wrap = elGrid?.querySelector(`.FnInt_CardWrap[data-slug="${item.slug}"]`);
    wrap?.classList.add("is-picked");
    window.lucide?.createIcons?.();
    elDialog?.querySelector(".FnInt_ConnectDialog__btnPrimary")?.focus();
  }

  function cardHtml(item) {
    const slug = item.slug || "";
    const ativa = INTEGRACOES_ATIVAS.has(slug);
    const st = statusIntegracao(slug);
    const conectado = !!st.conectado;
    const picked = itemModalAberto?.slug === slug;
    const badge = conectado ? `<span class="FnInt_Badge FnInt_Badge--on">Conectado</span>` : "";

    return `
      <div class="FnInt_CardWrap${conectado ? " is-connected" : ""}${picked ? " is-picked" : ""}" data-slug="${slug}" role="listitem">
        <button type="button" class="FnInt_Card" data-slug="${slug}" data-nome="${item.nome}" data-ativa="${ativa ? "1" : "0"}" data-conectado="${conectado ? "1" : "0"}">
          <div class="FnInt_CardIcon is-fallback" style="background:${item.cor || "#475569"}">
            <img src="${item.icone_png}" alt="" loading="lazy"
              onload="this.parentElement.classList.remove('is-fallback')"
              onerror="this.onerror=null;this.src='${item.icone_svg}';this.addEventListener('error',()=>{this.parentElement.classList.add('is-fallback')},{once:true})" />
            <span class="FnInt_CardFallback">${item.iniciais || item.nome.slice(0, 2).toUpperCase()}</span>
          </div>
          <div class="FnInt_CardBody">
            <div class="FnInt_CardHead">
              <p class="FnInt_CardNome">${item.nome}</p>
              ${badge}
            </div>
            <p class="FnInt_CardDesc">${item.descricao || ""}</p>
          </div>
        </button>
      </div>`;
  }

  function renderCategoria(catId) {
    const cat = categorias.find((c) => c.id === catId);
    if (!cat) return;
    categoriaAtiva = catId;
    if (elTitulo) elTitulo.textContent = cat.titulo || cat.rotulo;
    if (elSubtitulo) elSubtitulo.textContent = cat.subtitulo || "";
    elGrid.innerHTML =
      (cat.itens || []).map(cardHtml).join("") ||
      '<p class="FnInt_Subtitulo">Nenhuma integração nesta categoria.</p>';
    renderSubnav();
    window.lucide?.createIcons?.();
    if (itemModalAberto) {
      const wrap = elGrid.querySelector(`.FnInt_CardWrap[data-slug="${itemModalAberto.slug}"]`);
      wrap?.classList.add("is-picked");
    }
  }

  function abrirIntegracao(slug, nome, conectado, ativa) {
    if (!ativa) {
      Swal.fire({
        title: nome,
        html: `<p style="color:#64748b;margin:0">A conexão com <strong>${nome}</strong> estará disponível em breve.</p>`,
        icon: "info",
        confirmButtonText: "Entendi",
        confirmButtonColor: "#021F81",
      });
      return;
    }
    if (conectado) {
      const st = statusIntegracao(slug);
      window.location.href = st.config_url || `/integracoes/${slug}`;
      return;
    }
    const cat = categorias.find((c) => c.id === categoriaAtiva);
    const item = cat?.itens?.find((i) => i.slug === slug) || { slug, nome, descricao: "" };
    abrirModalCard(item);
  }

  elSubnav.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".FnInt_SubItem");
    if (!btn) return;
    limparModal();
    renderCategoria(btn.dataset.cat || "");
  });

  elOverlay?.addEventListener("click", (ev) => {
    if (ev.target === elOverlay) fecharModalCard();
  });

  elDialog?.addEventListener("click", (ev) => {
    if (ev.target.closest('[data-action="fechar-modal"]')) {
      ev.preventDefault();
      fecharModalCard();
    }
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && itemModalAberto) fecharModalCard();
  });

  elGrid.addEventListener("click", (ev) => {
    const card = ev.target.closest(".FnInt_Card");
    if (!card) return;
    abrirIntegracao(
      card.dataset.slug || "",
      card.dataset.nome || "Integração",
      card.dataset.conectado === "1",
      card.dataset.ativa === "1"
    );
  });

  async function init() {
    limparModal();
    await carregarStatusHub();
    if (!categorias.length) {
      elGrid.innerHTML = '<p class="FnInt_Subtitulo">Catálogo de integrações indisponível.</p>';
      return;
    }

    const params = new URLSearchParams(location.search);
    if (params.get("conectado") === "bling") {
      categoriaAtiva = categorias.some((c) => c.id === "erp") ? "erp" : categoriaAtiva;
      await carregarStatusHub();
      Swal.fire({
        icon: "success",
        title: "Conectado",
        text: "Integração configurada com sucesso.",
        confirmButtonColor: "#021F81",
      });
      window.history.replaceState({}, "", location.pathname);
    }
    const erroParam = params.get("erro");
    if (erroParam) {
      categoriaAtiva = categorias.some((c) => c.id === "erp") ? "erp" : categoriaAtiva;
      Swal.fire({
        icon: "error",
        title: "Não foi possível conectar",
        text: erroParam,
        confirmButtonColor: "#021F81",
      });
      window.history.replaceState({}, "", location.pathname);
    }

    renderCategoria(categoriaAtiva);
  }

  init();
})();
