(function () {
  let paginaAtual = 1;
  const porPagina = 20;
  let totalPaginas = 1;

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
  };
  if (!el.tbody) return;

  const BASE = "/configuracoes/usuarios";

  function util() {
    return window.Util || { gerarIconeTech: () => "…" };
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
      el.tbody.innerHTML = "<tr><td colspan=\"7\">Nenhum usuário encontrado.</td></tr>";
      renderPaginacao();
      return;
    }
    const u = util();
    el.tbody.innerHTML = dados
      .map(
        (row) => `
      <tr>
        <td>${row.nome || ""}</td>
        <td>${row.email || ""}</td>
        <td>${row.perfil_nome || ""}</td>
        <td>${badgeConvite(row.convite_status)}</td>
        <td>${row.dt_ultimo_login ? row.dt_ultimo_login.slice(0, 16).replace("T", " ") : "—"}</td>
        <td><span class="Cl_Badge ${row.status ? "Cl_Badge--ativo" : "Cl_Badge--inativo"}">${row.status ? "Ativo" : "Inativo"}</span></td>
        <td class="Cl_TableActions">
          <button type="button" class="Cl_BtnAcao btnEditar" data-id="${row.id}">${u.gerarIconeTech("editar")}</button>
          <button type="button" class="Cl_BtnAcao btnInativar" data-id="${row.id}" ${row.cannot_delete ? "disabled" : ""}>${u.gerarIconeTech("excluir")}</button>
        </td>
      </tr>`
      )
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

  function abrirApoio(id) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: id ? `${BASE}/editar` : `${BASE}/incluir`,
      id: id || null,
      titulo: id ? "Editar usuário" : "Novo usuário",
      largura: 920,
      altura: 520,
      nivel: 1,
    });
  }

  async function inativar(id) {
    const c = await Swal.fire({
      title: "Inativar usuário?",
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
  el.btnIncluir?.addEventListener("click", () => abrirApoio(null));
  el.btnPrimeiro?.addEventListener("click", () => { paginaAtual = 1; carregar(); });
  el.btnAnterior?.addEventListener("click", () => { if (paginaAtual > 1) { paginaAtual -= 1; carregar(); } });
  el.btnProximo?.addEventListener("click", () => { if (paginaAtual < totalPaginas) { paginaAtual += 1; carregar(); } });
  el.btnUltimo?.addEventListener("click", () => { paginaAtual = totalPaginas; carregar(); });

  el.tbody.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button");
    if (!btn || btn.disabled) return;
    const id = Number(btn.dataset.id || 0);
    if (!id) return;
    try {
      if (btn.classList.contains("btnEditar")) return abrirApoio(id);
      if (btn.classList.contains("btnInativar")) return await inativar(id);
    } catch (e) {
      await Swal.fire("Erro", e.message, "error");
    }
  });

  window.addEventListener("message", (ev) => {
    if (ev.data?.grupo === "atualizarTabela") {
      carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
    }
  });

  carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
})();
