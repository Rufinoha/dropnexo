(function () {
  const sidebar = document.getElementById("fg-sidebar");
  const btnCollapse = document.getElementById("fg-btn-collapse");
  const navSearch = document.getElementById("fg-nav-search");
  const userTrigger = document.getElementById("fg-user-trigger");
  const btnKebab = document.getElementById("fg-btn-kebab");
  const userDropdown = document.getElementById("fg-user-dropdown");
  const btnLogout = document.getElementById("fg-btn-logout");
  const tenantSwitcher = document.getElementById("fg-tenant-switcher");
  const tenantTrigger = document.getElementById("fg-tenant-trigger");
  const tenantDropdown = document.getElementById("fg-tenant-dropdown");
  const tenantList = document.getElementById("fg-tenant-list");
  const tenantHint = document.getElementById("fg-tenant-hint");
  const tenantChipLabel = document.getElementById("fg-tenant-chip-label");
  const tenantSearch = document.getElementById("fg-tenant-search");

  let tenantsCarregados = false;
  let tenantsItens = [];
  let modoDevFornecedor = false;
  let trocandoTenant = false;

  /**
   * Sincroniza o avatar do header (iniciais ou foto).
   * @param {string|null} fotoUrl — URL da foto ou null para voltar às iniciais
   * @param {string} [iniciais]
   */
  function syncAvatarHeader(fotoUrl, iniciais) {
    const el = document.getElementById("fg-avatar") || document.querySelector(".fg-avatar");
    if (!el) return;

    const ini =
      iniciais ||
      el.dataset.iniciais ||
      (window.OSB_SHELL && window.OSB_SHELL.iniciaisUsuario) ||
      el.textContent.trim() ||
      "OS";

    if (fotoUrl) {
      const bust =
        fotoUrl + (String(fotoUrl).indexOf("?") >= 0 ? "&" : "?") + "t=" + Date.now();
      el.classList.add("has-foto");
      el.style.backgroundImage = 'url("' + bust + '")';
      el.textContent = "";
    } else {
      el.classList.remove("has-foto");
      el.style.backgroundImage = "";
      el.textContent = ini;
    }
  }

  async function carregarAvatarHeader() {
    const cfg = window.OSB_SHELL;
    if (!cfg || !cfg.apiFotoUsuario) return;

    try {
      const r = await fetch(cfg.apiFotoUsuario, {
        method: "GET",
        credentials: "same-origin",
      });
      if (r.ok) {
        syncAvatarHeader(cfg.apiFotoUsuario, cfg.iniciaisUsuario);
      } else {
        syncAvatarHeader(cfg.fotoUrlPadrao || null, cfg.iniciaisUsuario);
      }
    } catch {
      syncAvatarHeader(cfg.fotoUrlPadrao || null, cfg.iniciaisUsuario);
    }
  }

  window.OsbAvatar = {
    sync: syncAvatarHeader,
    reload: carregarAvatarHeader,
  };

  function toggleUserMenu() {
    if (!userDropdown) return;
    const open = userDropdown.classList.toggle("is-open");
    userDropdown.setAttribute("aria-hidden", open ? "false" : "true");
    if (userTrigger) userTrigger.setAttribute("aria-expanded", open ? "true" : "false");
    if (btnKebab) btnKebab.setAttribute("aria-expanded", open ? "true" : "false");
  }

  function closeUserMenu() {
    if (!userDropdown) return;
    userDropdown.classList.remove("is-open");
    userDropdown.setAttribute("aria-hidden", "true");
    if (userTrigger) userTrigger.setAttribute("aria-expanded", "false");
    if (btnKebab) btnKebab.setAttribute("aria-expanded", "false");
  }

  function closeTenantMenu() {
    if (!tenantDropdown) return;
    tenantDropdown.hidden = true;
    if (tenantTrigger) tenantTrigger.setAttribute("aria-expanded", "false");
  }

  function toggleTenantMenu() {
    if (!tenantDropdown || !tenantTrigger) return;
    const abrir = tenantDropdown.hidden;
    closeUserMenu();
    if (abrir) {
      tenantDropdown.hidden = false;
      tenantTrigger.setAttribute("aria-expanded", "true");
      if (!tenantsCarregados) carregarTenants();
    } else {
      closeTenantMenu();
    }
  }

  function filtrarTenants(itens) {
    if (!tenantSearch || !modoDevFornecedor) return itens;
    const termo = tenantSearch.value.trim().toLowerCase();
    if (!termo) return itens;
    return itens.filter(function (t) {
      const alvo = [t.nome, t.slug, t.meta, t.papel_label, t.plano]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return alvo.includes(termo);
    });
  }

  function renderTenantList(itens) {
    if (!tenantList) return;
    const visiveis = filtrarTenants(itens);
    tenantList.innerHTML = "";
    if (!visiveis.length) {
      if (tenantHint) {
        tenantHint.hidden = false;
        tenantHint.textContent = modoDevFornecedor
          ? "Nenhum fornecedor encontrado."
          : "Nenhuma conta vinculada.";
      }
      return;
    }
    if (tenantHint) tenantHint.hidden = true;

    visiveis.forEach(function (t) {
      const li = document.createElement("li");
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "fg-tenant-item" + (t.is_atual ? " is-atual" : "");
      btn.setAttribute("role", "option");
      btn.setAttribute("aria-selected", t.is_atual ? "true" : "false");
      btn.dataset.idTenant = String(t.id);
      if (t.is_atual) btn.disabled = true;

      const nome = document.createElement("span");
      nome.className = "fg-tenant-item-name";
      nome.textContent = t.nome || "Conta";

      const meta = document.createElement("span");
      meta.className = "fg-tenant-item-meta";
      const partes = [];
      if (t.meta) partes.push(String(t.meta));
      if (!t.meta && t.plano) partes.push(String(t.plano));
      if (!t.meta && t.papel_label) partes.push(t.papel_label);
      meta.textContent = partes.join(" · ") || t.slug || "";

      btn.appendChild(nome);
      btn.appendChild(meta);
      if (t.is_atual) {
        const badge = document.createElement("span");
        badge.className = "fg-tenant-item-badge";
        badge.textContent = modoDevFornecedor ? "Ativo" : "Conta atual";
        btn.appendChild(badge);
      }

      btn.addEventListener("click", function () {
        trocarTenant(t.id);
      });
      li.appendChild(btn);
      tenantList.appendChild(li);
    });
  }

  async function carregarTenants() {
    const cfg = window.OSB_SHELL;
    if (!cfg?.apiTenants || !tenantList) return;

    if (tenantHint) {
      tenantHint.hidden = false;
      tenantHint.textContent = "Carregando…";
    }
    tenantList.innerHTML = "";

    try {
      const r = await fetch(cfg.apiTenants, {
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      const j = await r.json();
      if (!j.success) {
        if (tenantHint) {
          tenantHint.hidden = false;
          tenantHint.textContent = j.message || "Não foi possível carregar as contas.";
        }
        return;
      }
      tenantsItens = j.itens || [];
      modoDevFornecedor = !!(j.modo_dev_fornecedor || cfg.ehDesenvolvedor);
      tenantsCarregados = true;
      renderTenantList(tenantsItens);

      if (tenantTrigger && !modoDevFornecedor && tenantsItens.length <= 1) {
        tenantTrigger.classList.add("is-single");
        tenantTrigger.setAttribute("title", tenantsItens[0]?.nome || "");
      } else if (tenantTrigger) {
        tenantTrigger.classList.remove("is-single");
      }
    } catch {
      if (tenantHint) {
        tenantHint.hidden = false;
        tenantHint.textContent = "Falha ao carregar contas.";
      }
    }
  }

  async function trocarTenant(idTenant) {
    const cfg = window.OSB_SHELL;
    if (!cfg?.apiTrocarTenant || trocandoTenant) return;
    if (idTenant === cfg.idTenantAtual) return;

    trocandoTenant = true;
    closeTenantMenu();

    try {
      const r = await fetch(cfg.apiTrocarTenant, {
        method: "POST",
        headers: {
          Accept: "application/json",
          "Content-Type": "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({
          id_tenant: idTenant,
          redirect: window.location.pathname + window.location.search,
        }),
      });
      const j = await r.json();
      if (!j.success) {
        alert(j.message || "Não foi possível trocar de conta.");
        trocandoTenant = false;
        return;
      }
      window.location.href = j.redirect || window.location.pathname || cfg.urlDashboard || "/";
    } catch {
      alert("Falha de conexão ao trocar de conta.");
      trocandoTenant = false;
    }
  }

  if (btnCollapse && sidebar) {
    btnCollapse.addEventListener("click", () => {
      sidebar.classList.toggle("is-collapsed");
      const collapsed = sidebar.classList.contains("is-collapsed");
      btnCollapse.textContent = collapsed ? "»" : "«";
      btnCollapse.setAttribute("aria-label", collapsed ? "Expandir menu" : "Recolher menu");
    });
  }

  if (navSearch) {
    navSearch.addEventListener("input", () => {
      const termo = navSearch.value.trim().toLowerCase();
      document.querySelectorAll(".fg-nav-item").forEach((el) => {
        const label = (el.querySelector(".fg-nav-label")?.textContent || "").toLowerCase();
        el.style.display = !termo || label.includes(termo) ? "" : "none";
      });
    });
  }

  if (userDropdown) {
    if (userTrigger) {
      userTrigger.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleUserMenu();
      });
    }
    if (btnKebab) {
      btnKebab.addEventListener("click", (e) => {
        e.stopPropagation();
        toggleUserMenu();
      });
    }
    document.addEventListener("click", function () {
      closeUserMenu();
      closeTenantMenu();
    });
    userDropdown.addEventListener("click", (e) => e.stopPropagation());
  }

  if (tenantSearch) {
    tenantSearch.addEventListener("input", function () {
      renderTenantList(tenantsItens);
    });
    tenantSearch.addEventListener("click", function (e) {
      e.stopPropagation();
    });
  }

  if (tenantSwitcher && tenantTrigger && tenantDropdown) {
    tenantTrigger.addEventListener("click", function (e) {
      e.stopPropagation();
      if (tenantTrigger.classList.contains("is-single")) return;
      toggleTenantMenu();
      if (!tenantDropdown.hidden && tenantSearch) {
        tenantSearch.focus();
      }
    });
    tenantDropdown.addEventListener("click", function (e) {
      e.stopPropagation();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeTenantMenu();
    });
    carregarTenants();
  }

  if (btnLogout) {
    btnLogout.addEventListener("click", async () => {
      const url = btnLogout.dataset.logoutUrl;
      const home = btnLogout.dataset.homeUrl || "/";
      if (url) {
        await fetch(url, { method: "POST", headers: { Accept: "application/json" } });
      }
      window.location.href = home;
    });
  }

  const moduloSwitcher = document.getElementById("fg-modulo-switcher");
  const moduloTrigger = document.getElementById("fg-modulo-trigger");
  const moduloDropdown = document.getElementById("fg-modulo-dropdown");
  const moduloLabel = document.getElementById("fg-modulo-trigger-label");

  function closeModuloMenu() {
    if (!moduloDropdown) return;
    moduloDropdown.hidden = true;
    if (moduloTrigger) moduloTrigger.setAttribute("aria-expanded", "false");
  }

  function toggleModuloMenu() {
    if (!moduloDropdown || !moduloTrigger) return;
    const abrir = moduloDropdown.hidden;
    closeUserMenu();
    closeTenantMenu();
    moduloDropdown.hidden = !abrir;
    moduloTrigger.setAttribute("aria-expanded", abrir ? "true" : "false");
  }

  async function trocarModulo(codigo) {
    const cfg = window.OSB_SHELL;
    if (!cfg || !cfg.apiTrocarModulo) return;
    const r = await fetch(cfg.apiTrocarModulo, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ modulo: codigo }),
    });
    const j = await r.json();
    if (!j.success) {
      if (window.Util && Util.alertar) Util.alertar(j.message || "Erro", "error");
      return;
    }
    window.location.href = j.redirect || cfg.urlDashboard || "/";
  }

  if (moduloSwitcher && moduloTrigger && moduloDropdown) {
    moduloTrigger.addEventListener("click", function (e) {
      e.stopPropagation();
      toggleModuloMenu();
    });
    moduloDropdown.addEventListener("click", function (e) {
      const btn = e.target.closest("button[data-modulo]");
      if (!btn) return;
      e.preventDefault();
      closeModuloMenu();
      trocarModulo(btn.getAttribute("data-modulo"));
    });
    document.addEventListener("click", function () {
      closeModuloMenu();
    });
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") closeModuloMenu();
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    carregarAvatarHeader();
  });
})();
