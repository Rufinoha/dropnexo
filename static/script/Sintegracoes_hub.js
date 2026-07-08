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
    "mercado-pago": {
      conectado: false,
      config_url: "/integracoes/mercadopago",
      oauth_url: "/api/integracoes/mercadopago/oauth/iniciar",
    },
    "pix-manual": {
      conectado: false,
      config_url: "/integracoes/pix-manual",
      oauth_url: "",
    },
    "melhor-envio": {
      conectado: false,
      config_url: "/integracoes/melhor-envio",
      oauth_url: "/api/integracoes/melhor-envio/oauth/iniciar",
    },
  };

  const ICONES_CATEGORIA = {
    financeiro: "landmark",
    catalogo: "package",
    pedidos: "shopping-cart",
    frete: "truck",
  };

  function configUrlIntegracao(item) {
    const st = statusIntegracao(item.slug);
    if (item.slug === "bling" && item.bling_papel) {
      return `/integracoes/bling?papel=${encodeURIComponent(item.bling_papel)}`;
    }
    if (item.slug === "mercado-pago") return st.config_url || "/integracoes/mercadopago";
    if (item.slug === "pix-manual") return st.config_url || "/integracoes/pix-manual";
    if (item.slug === "melhor-envio") return st.config_url || "/integracoes/melhor-envio";
    return st.config_url || `/integracoes/${item.slug}`;
  }

  const INTEGRACOES_ATIVAS = new Set(["bling", "mercado-pago", "pix-manual", "melhor-envio"]);

  function seloEmBreveHtml() {
    return `
    <span class="FnInt_SoonTag" title="Disponível em breve">
      <span class="FnInt_SoonTag__spark" aria-hidden="true"></span>
      <span class="FnInt_SoonTag__label">Em breve</span>
    </span>`;
  }

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
        <p class="FnInt_ConnectDialog__manual">
          <a href="/ajuda/bling" target="_blank" rel="noopener noreferrer">Como conectar? Ver manual passo a passo</a>
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

  function itemConectado(item) {
    const slug = item.slug || "";
    if (!INTEGRACOES_ATIVAS.has(slug)) return false;
    return !!statusIntegracao(slug).conectado;
  }

  function agruparItensIntegracao(itens) {
    const conectados = [];
    const outros = [];
    for (const item of itens || []) {
      if (itemConectado(item)) conectados.push(item);
      else outros.push(item);
    }
    return { conectados, outros };
  }

  function grupoHtml(rotulo, itens) {
    if (!itens.length) return "";
    return `
      <section class="FnInt_Grupo">
        <h4 class="FnInt_GrupoTitulo">${rotulo}</h4>
        <div class="FnInt_GrupoGrid" role="list">
          ${itens.map(cardHtml).join("")}
        </div>
      </section>`;
  }

  function cardHtml(item) {
    const slug = item.slug || "";
    const ativa = INTEGRACOES_ATIVAS.has(slug);
    const st = statusIntegracao(slug);
    const conectado = !!st.conectado;
    const picked = itemModalAberto?.slug === slug;
    const badge = conectado ? `<span class="FnInt_Badge FnInt_Badge--on">Conectado</span>` : "";
    const soonSeal = !ativa ? seloEmBreveHtml() : "";

    return `
      <div class="FnInt_CardWrap${conectado ? " is-connected" : ""}${!ativa ? " is-soon" : ""}${picked ? " is-picked" : ""}" data-slug="${slug}" role="listitem">
        ${soonSeal}
        <button type="button" class="FnInt_Card" data-slug="${slug}" data-nome="${item.nome}" data-ativa="${ativa ? "1" : "0"}" data-conectado="${conectado ? "1" : "0"}" data-bling-papel="${item.bling_papel || ""}"${!ativa ? ' title="Em breve"' : ""}>
          <div class="FnInt_CardIcon" style="--int-cor:${item.cor || "#475569"}">
            <img src="${item.icone_png}" alt="" loading="eager" decoding="async"
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

    const { conectados, outros } = agruparItensIntegracao(cat.itens);
    const total = conectados.length + outros.length;
    if (!total) {
      elGrid.innerHTML = '<p class="FnInt_Subtitulo">Nenhuma integração nesta categoria.</p>';
      elGrid.classList.remove("FnInt_Grid--grouped");
    } else if (!conectados.length || !outros.length) {
      elGrid.classList.remove("FnInt_Grid--grouped");
      elGrid.innerHTML = [...conectados, ...outros].map(cardHtml).join("");
    } else {
      elGrid.classList.add("FnInt_Grid--grouped");
      elGrid.innerHTML = grupoHtml("Conectados", conectados) + grupoHtml("Não conectados", outros);
    }

    renderSubnav();
    window.lucide?.createIcons?.();
    if (itemModalAberto) {
      const wrap = elGrid.querySelector(`.FnInt_CardWrap[data-slug="${itemModalAberto.slug}"]`);
      wrap?.classList.add("is-picked");
    }
  }

  function abrirIntegracao(slug, nome, conectado, ativa, dblclick = false, blingPapel = "") {
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
    const cat = categorias.find((c) => c.id === categoriaAtiva);
    const item =
      cat?.itens?.find((i) => i.slug === slug && (!blingPapel || i.bling_papel === blingPapel)) ||
      cat?.itens?.find((i) => i.slug === slug) ||
      { slug, nome, descricao: "", bling_papel: blingPapel };

    if (slug === "pix-manual" || slug === "melhor-envio") {
      window.location.href = configUrlIntegracao(item);
      return;
    }
    if (conectado) {
      let url = configUrlIntegracao(item);
      if (dblclick && slug === "bling" && item.bling_papel === "catalogo") url += (url.includes("?") ? "&" : "?") + "aba=estoque";
      window.location.href = url;
      return;
    }
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

  let clickTimer = null;

  elGrid.addEventListener("click", (ev) => {
    const card = ev.target.closest(".FnInt_Card");
    if (!card) return;
    if (clickTimer) clearTimeout(clickTimer);
    clickTimer = setTimeout(() => {
      abrirIntegracao(
        card.dataset.slug || "",
        card.dataset.nome || "Integração",
        card.dataset.conectado === "1",
        card.dataset.ativa === "1",
        false,
        card.dataset.blingPapel || ""
      );
      clickTimer = null;
    }, 260);
  });

  elGrid.addEventListener("dblclick", (ev) => {
    const card = ev.target.closest(".FnInt_Card");
    if (!card) return;
    ev.preventDefault();
    if (clickTimer) {
      clearTimeout(clickTimer);
      clickTimer = null;
    }
    abrirIntegracao(
      card.dataset.slug || "",
      card.dataset.nome || "Integração",
      card.dataset.conectado === "1",
      card.dataset.ativa === "1",
      true,
      card.dataset.blingPapel || ""
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
      categoriaAtiva = categorias.some((c) => c.id === "catalogo")
        ? "catalogo"
        : categorias.some((c) => c.id === "pedidos")
          ? "pedidos"
          : categoriaAtiva;
      await carregarStatusHub();
      Swal.fire({
        icon: "success",
        title: "Conectado",
        text: "Integração Bling configurada com sucesso.",
        confirmButtonColor: "#021F81",
      });
      window.history.replaceState({}, "", location.pathname);
    } else if (params.get("conectado") === "mercadopago") {
      categoriaAtiva = categorias.some((c) => c.id === "financeiro") ? "financeiro" : categoriaAtiva;
      await carregarStatusHub();
      Swal.fire({
        icon: "success",
        title: "Conectado",
        text: "Mercado Pago configurado com sucesso.",
        confirmButtonColor: "#021F81",
      });
      window.history.replaceState({}, "", location.pathname);
    } else if (params.get("conectado") === "melhorenvio") {
      categoriaAtiva = categorias.some((c) => c.id === "frete") ? "frete" : categoriaAtiva;
      await carregarStatusHub();
      Swal.fire({
        icon: "success",
        title: "Conectado",
        text: "Melhor Envio configurado com sucesso.",
        confirmButtonColor: "#021F81",
      });
      window.history.replaceState({}, "", location.pathname);
    }
    const erroParam = params.get("erro");
    if (erroParam) {
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
