(function () {
  "use strict";

  const BASE = window.USU_EQ_BASE || "";
  if (!BASE) return;

  let paginaAtual = 1;
  const porPagina = 20;
  let totalPaginas = 1;
  let idUsuario = null;
  let isDono = false;
  let tabAtiva = "usuario";
  /** Perfil interno padrão da equipe (UI de perfil oculta; menus são o controle real). */
  let idPerfilPadrao = null;

  const el = {
    filtroBusca: document.getElementById("ob_filtroBusca"),
    filtroStatus: document.getElementById("ob_filtroStatus"),
    filtroConvite: document.getElementById("ob_filtroConvite"),
    btnFiltrar: document.getElementById("ob_btnFiltrar"),
    btnLimpar: document.getElementById("ob_btnLimpar"),
    btnIncluir: document.getElementById("ob_btnIncluir"),
    tbody: document.getElementById("ob_listaUsuarios"),
    paginaAtual: document.getElementById("ob_paginaAtual"),
    totalPaginas: document.getElementById("ob_totalPaginas"),
    btnPrimeiro: document.getElementById("ob_btnPrimeiro"),
    btnAnterior: document.getElementById("ob_btnAnterior"),
    btnProximo: document.getElementById("ob_btnProximo"),
    btnUltimo: document.getElementById("ob_btnUltimo"),
    drawer: document.getElementById("usuEqDrawer"),
    titulo: document.getElementById("usuEqTitulo"),
    sub: document.getElementById("usuEqSub"),
    email: document.getElementById("usuEqEmail"),
    nome: document.getElementById("usuEqNome"),
    whatsapp: document.getElementById("usuEqWhatsapp"),
    perfil: document.getElementById("usuEqPerfil"),
    emailErro: document.getElementById("usuEqEmailErro"),
    status: document.getElementById("usuEqStatus"),
    enviarConvite: null,
    wrapConvite: null,
    hint: document.getElementById("usuEqHint"),
    bannerDono: document.getElementById("usuEqBannerDono"),
    menus: document.getElementById("usuEqMenus"),
    menusHint: document.getElementById("usuEqMenusHint"),
    btnSalvar: document.getElementById("usuEqBtnSalvar"),
    btnReenviar: document.getElementById("usuEqBtnReenviar"),
    btnFechar: document.getElementById("usuEqBtnFechar"),
    backdrop: document.getElementById("usuEqBackdrop"),
    btnCancelar: document.getElementById("usuEqBtnCancelar"),
    tabUsuario: document.getElementById("usuEqTabUsuario"),
    tabAcesso: document.getElementById("usuEqTabAcesso"),
    paneUsuario: document.getElementById("usuEqPaneUsuario"),
    paneAcesso: document.getElementById("usuEqPaneAcesso"),
    btnMenusTodos: document.getElementById("usuEqMenusTodos"),
    btnMenusNenhum: document.getElementById("usuEqMenusNenhum"),
  };
  if (!el.tbody || !el.drawer) return;

  function util() {
    return window.Util || { gerarIconeTech: () => "…" };
  }

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function iniciais(nome) {
    const p = String(nome || "?").trim().split(/\s+/).filter(Boolean);
    if (!p.length) return "?";
    if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
    return (p[0][0] + p[p.length - 1][0]).toUpperCase();
  }

  function emailValido(email) {
    const e = String(email || "").trim().toLowerCase();
    if (!e) return false;
    return /^[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}$/i.test(e);
  }

  function marcarEmailInvalido(ok) {
    el.email?.classList.toggle("is-invalid", !ok);
    if (el.emailErro) el.emailErro.hidden = ok;
  }

  function whatsappDigits(valor) {
    if (window.Util?.limparMascaraTelefone) return Util.limparMascaraTelefone(valor || "");
    return String(valor || "").replace(/\D/g, "");
  }

  function formatarWhatsappCampo(valor) {
    if (window.Util?.formatarTelefone) return Util.formatarTelefone(valor || "");
    return String(valor || "");
  }

  function badgeConvite(status) {
    const map = {
      PENDENTE: ["Pendente", "Cl_Badge--pendente"],
      ACEITO: ["Aceito", "Cl_Badge--aceito"],
      EXPIRADO: ["Expirado", "Cl_Badge--expirado"],
      SEM_CONVITE: ["Sem convite", "Cl_Badge--sem"],
    };
    const [txt, cls] = map[status] || [status || "-", "Cl_Badge--sem"];
    return `<span class="Cl_Badge ${cls}">${txt}</span>`;
  }

  function setTab(nome) {
    tabAtiva = nome;
    el.tabUsuario?.classList.toggle("is-on", nome === "usuario");
    el.tabAcesso?.classList.toggle("is-on", nome === "acesso");
    if (el.paneUsuario) el.paneUsuario.hidden = nome !== "usuario";
    if (el.paneAcesso) el.paneAcesso.hidden = nome !== "acesso";
  }

  function hintConvite(status, horas) {
    const h = horas || 24;
    const map = {
      PENDENTE: `Convite pendente — o usuário ainda não definiu a senha (válido por ${h}h).`,
      ACEITO: "Usuário já ativou o acesso.",
      EXPIRADO: `Convite expirado (após ${h}h) — use Reenviar convite.`,
      SEM_CONVITE: "Sem convite enviado.",
    };
    if (!el.hint) return;
    el.hint.textContent = map[status] || "";
    el.hint.classList.toggle("is-warn", status === "EXPIRADO" || status === "PENDENTE");
    el.hint.classList.toggle("is-ok", status === "ACEITO");
  }

  function renderMenus(menus) {
    if (!el.menus) return;
    const lista = menus || [];
    if (!lista.length) {
      el.menus.innerHTML = "<p class='UsuEq_Hint'>Nenhum menu disponível para este módulo.</p>";
      return;
    }
    const sidebar = lista.filter((m) => (m.grupo || "sidebar") !== "header");
    const header = lista.filter((m) => m.grupo === "header");

    function itemHtml(m) {
      const kids = (m.filhos || [])
        .map(
          (f) => `
        <label class="Cl_Switch UsuEq_MenuSwitch UsuEq_MenuSwitch--kid">
          <input type="checkbox" class="usu-eq-menu-filho" data-id="${f.id}" data-pai="${m.id}" ${f.exibir ? "checked" : ""} ${isDono ? "disabled" : ""} />
          <span class="Cl_SwitchSlider"></span>
          <span class="UsuEq_MenuNome">${esc(f.nome)}</span>
        </label>`
        )
        .join("");
      return `
      <div class="UsuEq_MenuItem" data-pai="${m.id}">
        <label class="Cl_Switch UsuEq_MenuSwitch">
          <input type="checkbox" class="usu-eq-menu-pai" data-id="${m.id}" ${m.exibir ? "checked" : ""} ${isDono ? "disabled" : ""} />
          <span class="Cl_SwitchSlider"></span>
          <span class="UsuEq_MenuNome">${esc(m.nome)}</span>
        </label>
        ${kids ? `<div class="UsuEq_MenuKids">${kids}</div>` : ""}
      </div>`;
    }

    const partes = [];
    if (sidebar.length) {
      partes.push(`<div class="UsuEq_MenuGrid">${sidebar.map(itemHtml).join("")}</div>`);
    }
    if (header.length) {
      partes.push(`
        <div class="UsuEq_MenuGroup">
          <h4 class="UsuEq_MenuGroupTitle">Menu do header</h4>
          <div class="UsuEq_MenuGrid">${header.map(itemHtml).join("")}</div>
        </div>`);
    }
    el.menus.innerHTML = partes.join("");
  }

  function idsMenusSelecionados() {
    return [...document.querySelectorAll(".usu-eq-menu-pai:checked, .usu-eq-menu-filho:checked")].map(
      (inp) => Number(inp.dataset.id)
    );
  }

  function marcarMenus(todos) {
    document.querySelectorAll(".usu-eq-menu-pai, .usu-eq-menu-filho").forEach((inp) => {
      if (!inp.disabled) inp.checked = !!todos;
    });
  }

  function escolherPerfilPadrao(perfis) {
    const lista = Array.isArray(perfis) ? perfis : [];
    const porCodigo = (cod) => lista.find((p) => String(p.codigo || "").toLowerCase() === cod);
    return porCodigo("operador") || porCodigo("admin") || lista[0] || null;
  }

  function garantirPerfilSelecionado() {
    if (!el.perfil) return idPerfilPadrao;
    if (!el.perfil.value && idPerfilPadrao) {
      el.perfil.value = String(idPerfilPadrao);
    }
    if (!el.perfil.value && el.perfil.options.length) {
      el.perfil.selectedIndex = 0;
    }
    const n = Number(el.perfil.value || idPerfilPadrao || 0);
    return n > 0 ? n : null;
  }

  async function carregarPerfis() {
    const r = await fetch(`${BASE}/combos`);
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar perfis.");
    if (!el.perfil) return;
    const perfis = j.perfis || [];
    el.perfil.innerHTML = "";
    perfis.forEach((p) => {
      const o = document.createElement("option");
      o.value = p.id;
      o.textContent = `${p.nome}`;
      o.dataset.codigo = p.codigo || "";
      el.perfil.appendChild(o);
    });
    const padrao = escolherPerfilPadrao(perfis);
    const id = padrao ? Number(padrao.id) : 0;
    idPerfilPadrao = id > 0 ? id : null;
    if (idPerfilPadrao) el.perfil.value = String(idPerfilPadrao);
  }

  async function carregarMenusPerfil(idPerfil) {
    if (!el.menus) return;
    el.menus.innerHTML = "<p class='UsuEq_Hint'>Carregando menus…</p>";
    try {
      const qs = idPerfil ? `?id_perfil=${encodeURIComponent(idPerfil)}` : "";
      const r = await fetch(`${BASE}/menus-perfil${qs}`);
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar menus.");
      renderMenus(j.menus || []);
    } catch (e) {
      el.menus.innerHTML = `<p class="UsuEq_Hint is-warn">${esc(e.message || "Não foi possível carregar os menus.")}</p>`;
    }
  }

  function abrirDrawerNovo() {
    if (!garantirPerfilSelecionado()) {
      Swal.fire(
        "Erro",
        "Nenhum perfil de equipe disponível para convite. Recarregue a página ou contate o suporte.",
        "error"
      );
      return;
    }
    idUsuario = null;
    isDono = false;
    el.titulo.textContent = "Novo usuário";
    el.sub.textContent = "Convide alguém da equipe para este tenant.";
    el.email.value = "";
    el.email.readOnly = false;
    marcarEmailInvalido(true);
    el.nome.value = "";
    el.whatsapp.value = "";
    el.status.checked = true;
    if (el.btnReenviar) el.btnReenviar.hidden = true;
    if (el.bannerDono) el.bannerDono.hidden = true;
    if (el.perfil) el.perfil.disabled = false;
    el.status.disabled = false;
    hintConvite("", 24);
    if (el.hint) {
      el.hint.textContent =
        "Ao salvar, enviamos automaticamente um e-mail com link para definir a senha (válido por 24h).";
      el.hint.classList.add("is-warn");
      el.hint.classList.remove("is-ok");
    }
    if (el.menusHint) {
      el.menusHint.textContent =
        "Ligue o que este usuário verá na sidebar e no menu do header. Padrão: tudo ligado, exceto Usuários, Financeiro e Meu Plano.";
    }
    setTab("usuario");
    const idPerfil = garantirPerfilSelecionado();
    carregarMenusPerfil(idPerfil || "");
    el.drawer.hidden = false;
    el.drawer.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  async function abrirDrawerEditar(id) {
    const r = await fetch(`${BASE}/apoio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar.");
    const d = j.dados;
    idUsuario = d.id;
    isDono = !!d.is_dono;
    el.titulo.textContent = isDono ? "Dono do tenant" : "Editar usuário";
    el.sub.textContent = d.email || "";
    el.email.value = d.email || "";
    el.email.readOnly = true;
    marcarEmailInvalido(true);
    el.nome.value = d.nome || "";
    el.whatsapp.value = formatarWhatsappCampo(d.whatsapp || "");
    if (isDono) {
      // Garante opção dono visível mesmo fora do combo
      let opt = [...(el.perfil?.options || [])].find((o) => o.value == d.id_perfil);
      if (!opt && el.perfil) {
        opt = document.createElement("option");
        opt.value = d.id_perfil;
        opt.textContent = d.perfil_nome || "Dono";
        el.perfil.appendChild(opt);
      }
      if (el.perfil) {
        el.perfil.value = d.id_perfil;
        el.perfil.disabled = true;
      }
      el.status.disabled = true;
      el.status.checked = true;
    } else {
      if (el.perfil) {
        el.perfil.disabled = false;
        el.perfil.value = d.id_perfil || "";
      }
      el.status.disabled = false;
      el.status.checked = !!d.status;
    }
    if (el.btnReenviar) {
      const st = d.convite_status || "";
      el.btnReenviar.hidden = isDono || !(st === "PENDENTE" || st === "EXPIRADO" || st === "SEM_CONVITE");
    }
    if (el.bannerDono) el.bannerDono.hidden = !isDono;
    hintConvite(d.convite_status, d.token_horas);
    if (el.menusHint) {
      el.menusHint.textContent = isDono
        ? "O Dono enxerga todos os menus — não é possível restringir."
        : "Menus liberados na sidebar e no header deste tenant.";
    }
    renderMenus(d.menus || []);
    if (isDono) marcarMenus(true);
    setTab("usuario");
    el.drawer.hidden = false;
    el.drawer.setAttribute("aria-hidden", "false");
    document.body.style.overflow = "hidden";
  }

  function fecharDrawer() {
    el.drawer.hidden = true;
    el.drawer.setAttribute("aria-hidden", "true");
    document.body.style.overflow = "";
  }

  function montarUrl() {
    const p = new URLSearchParams({
      pagina: paginaAtual,
      porPagina,
      busca: (el.filtroBusca?.value || "").trim(),
      status: el.filtroStatus?.value || "",
      convite: el.filtroConvite?.value || "",
    });
    return `${BASE}/dados?${p}`;
  }

  function renderPaginacao() {
    if (el.paginaAtual) el.paginaAtual.textContent = String(paginaAtual);
    if (el.totalPaginas) el.totalPaginas.textContent = String(totalPaginas);
    if (el.btnPrimeiro) el.btnPrimeiro.disabled = paginaAtual <= 1;
    if (el.btnAnterior) el.btnAnterior.disabled = paginaAtual <= 1;
    if (el.btnProximo) el.btnProximo.disabled = paginaAtual >= totalPaginas;
    if (el.btnUltimo) el.btnUltimo.disabled = paginaAtual >= totalPaginas;
  }

  function renderTabela(dados) {
    if (!dados?.length) {
      el.tbody.innerHTML = '<tr><td colspan="6">Nenhum usuário encontrado.</td></tr>';
      renderPaginacao();
      return;
    }
    const u = util();
    el.tbody.innerHTML = dados
      .map((row) => {
        const dono = !!row.is_dono;
        return `
      <tr data-id="${row.id}">
        <td class="UsuEq_ColUsuario">
          <div class="UsuEq_NomeCell">
            <span class="UsuEq_Avatar${dono ? " is-dono" : ""}">${esc(iniciais(row.nome))}</span>
            <span>
              <span class="UsuEq_NomeStrong">${esc(row.nome)}${dono ? " · Dono" : ""}</span>
              <span class="UsuEq_NomeSub">${esc(row.email)}</span>
            </span>
          </div>
        </td>
        <td class="UsuEq_ColPerfil">${esc(row.perfil_nome)}</td>
        <td class="UsuEq_ColConvite">${badgeConvite(row.convite_status)}</td>
        <td class="UsuEq_ColAcesso">${row.dt_ultimo_login ? row.dt_ultimo_login.slice(0, 16).replace("T", " ") : "—"}</td>
        <td class="UsuEq_ColStatus"><span class="Cl_Badge ${row.status ? "Cl_Badge--ativo" : "Cl_Badge--inativo"}">${row.status ? "Ativo" : "Inativo"}</span></td>
        <td class="UsuEq_ColAcoes" onclick="event.stopPropagation()">
          <button type="button" class="Cl_BtnAcao btnEditar" data-id="${row.id}" title="Editar">${u.gerarIconeTech("editar")}</button>
          <button type="button" class="Cl_BtnAcao btnInativar" data-id="${row.id}" title="${row.cannot_delete ? (dono ? "Dono não pode ser excluído" : "Não permitido") : "Inativar"}" ${row.cannot_delete ? "disabled" : ""}>${u.gerarIconeTech("excluir")}</button>
        </td>
      </tr>`;
      })
      .join("");
    window.lucide?.createIcons?.();
    renderPaginacao();
  }

  async function carregar() {
    const r = await fetch(montarUrl());
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar.");
    totalPaginas = j.total_paginas || 1;
    renderTabela(j.dados || []);
  }

  async function salvar() {
    const email = (el.email.value || "").trim();
    const nome = (el.nome.value || "").trim();
    const whatsapp = whatsappDigits(el.whatsapp.value);
    const idPerfil = garantirPerfilSelecionado();

    if (!email || !nome) {
      throw new Error("Preencha e-mail e nome.");
    }
    if (!emailValido(email)) {
      marcarEmailInvalido(false);
      el.email?.focus();
      throw new Error("Informe um e-mail válido.");
    }
    marcarEmailInvalido(true);
    if (whatsapp && !(window.Util?.validarTelefone?.(whatsapp) ?? (whatsapp.length === 10 || whatsapp.length === 11))) {
      el.whatsapp?.focus();
      throw new Error("WhatsApp inválido. Use DDD + número (10 ou 11 dígitos).");
    }
    if (!isDono && !idPerfil) {
      throw new Error("Não foi possível definir o acesso padrão. Recarregue a página.");
    }

    if (isDono) {
      const body = {
        id: idUsuario,
        email,
        nome,
        whatsapp,
        id_perfil: idPerfil,
        status: true,
        enviar_convite: false,
        ids_menus: null,
      };
      const r = await fetch(`${BASE}/salvar`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
      await Swal.fire("Sucesso", j.message, "success");
      fecharDrawer();
      await carregar();
      return;
    }

    const body = {
      id: idUsuario,
      email,
      nome,
      whatsapp,
      id_perfil: idPerfil,
      status: !!el.status.checked,
      enviar_convite: !idUsuario,
      ids_menus: idsMenusSelecionados(),
    };
    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    await Swal.fire("Sucesso", j.message, "success");
    fecharDrawer();
    await carregar();
  }

  async function reenviar() {
    if (!idUsuario) return;
    const r = await fetch(`${BASE}/reenviar-convite`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idUsuario }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await Swal.fire("Sucesso", j.message, "success");
    await abrirDrawerEditar(idUsuario);
  }

  async function inativar(id) {
    const c = await Swal.fire({
      title: "Inativar usuário?",
      text: "O acesso será removido apenas nesta conta. O Dono nunca pode ser excluído.",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, inativar",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;
    const r = await fetch(`${BASE}/inativar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await Swal.fire("Sucesso", j.message, "success");
    await carregar();
  }

  el.btnFiltrar?.addEventListener("click", () => {
    paginaAtual = 1;
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  el.btnLimpar?.addEventListener("click", () => {
    if (el.filtroBusca) el.filtroBusca.value = "";
    if (el.filtroStatus) el.filtroStatus.value = "ativo";
    if (el.filtroConvite) el.filtroConvite.value = "";
    paginaAtual = 1;
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  el.btnIncluir?.addEventListener("click", () => abrirDrawerNovo());
  el.btnPrimeiro?.addEventListener("click", () => {
    paginaAtual = 1;
    carregar();
  });
  el.btnAnterior?.addEventListener("click", () => {
    if (paginaAtual > 1) {
      paginaAtual -= 1;
      carregar();
    }
  });
  el.btnProximo?.addEventListener("click", () => {
    if (paginaAtual < totalPaginas) {
      paginaAtual += 1;
      carregar();
    }
  });
  el.btnUltimo?.addEventListener("click", () => {
    paginaAtual = totalPaginas;
    carregar();
  });

  el.tbody.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button");
    if (btn) {
      if (btn.disabled) return;
      const id = Number(btn.dataset.id || 0);
      if (!id) return;
      try {
        if (btn.classList.contains("btnEditar")) return await abrirDrawerEditar(id);
        if (btn.classList.contains("btnInativar")) return await inativar(id);
      } catch (e) {
        await Swal.fire("Erro", e.message, "error");
      }
      return;
    }
    const tr = ev.target.closest("tr[data-id]");
    if (!tr) return;
    try {
      await abrirDrawerEditar(Number(tr.dataset.id));
    } catch (e) {
      await Swal.fire("Erro", e.message, "error");
    }
  });

  el.btnFechar?.addEventListener("click", fecharDrawer);
  el.btnCancelar?.addEventListener("click", fecharDrawer);
  el.backdrop?.addEventListener("click", fecharDrawer);
  el.btnSalvar?.addEventListener("click", () => salvar().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnReenviar?.addEventListener("click", () => reenviar().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.tabUsuario?.addEventListener("click", () => setTab("usuario"));
  el.tabAcesso?.addEventListener("click", () => setTab("acesso"));
  el.btnMenusTodos?.addEventListener("click", () => marcarMenus(true));
  el.btnMenusNenhum?.addEventListener("click", () => marcarMenus(false));

  el.perfil?.addEventListener("change", () => {
    if (!idUsuario && !isDono) carregarMenusPerfil(el.perfil.value);
  });

  el.email?.addEventListener("blur", () => {
    const v = (el.email.value || "").trim();
    if (!v) {
      marcarEmailInvalido(true);
      return;
    }
    marcarEmailInvalido(emailValido(v));
  });
  el.email?.addEventListener("input", () => {
    if (el.email.classList.contains("is-invalid")) {
      marcarEmailInvalido(emailValido(el.email.value));
    }
  });

  if (el.whatsapp && window.Util?.aplicarMascaraTelefone) {
    Util.aplicarMascaraTelefone(el.whatsapp);
  }

  el.menus?.addEventListener("change", (ev) => {
    const pai = ev.target.closest(".usu-eq-menu-pai");
    if (pai) {
      const id = pai.dataset.id;
      document.querySelectorAll(`.usu-eq-menu-filho[data-pai="${id}"]`).forEach((c) => {
        c.checked = pai.checked;
      });
    }
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && el.drawer && !el.drawer.hidden) fecharDrawer();
  });

  carregarPerfis()
    .then(() => carregar())
    .catch((e) => Swal.fire("Erro", e.message, "error"));
})();
