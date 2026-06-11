(function () {
  let paginaAtual = 1;
  const porPagina = 20;
  let totalPaginas = 1;
  const dadosCache = {};

  const el = {
    filtroNome: document.getElementById("ob_filtroNome"),
    filtroMenuPai: document.getElementById("ob_filtroMenuPai"),
    filtroModulo: document.getElementById("ob_filtroModulo"),
    btnIncluir: document.getElementById("ob_btnIncluir"),
    btnFiltrar: document.getElementById("ob_btnFiltrar"),
    btnLimpar: document.getElementById("ob_btnlimparFiltro"),
    lista: document.getElementById("ob_listaMenus"),
    paginaAtual: document.getElementById("ob_paginaAtual"),
    totalPaginas: document.getElementById("ob_totalPaginas"),
    btnPrimeiro: document.getElementById("ob_btnPrimeiro"),
    btnAnterior: document.getElementById("ob_btnAnterior"),
    btnProximo: document.getElementById("ob_btnProximo"),
    btnUltimo: document.getElementById("ob_btnUltimo"),
  };
  if (!el.lista) return;

  const BASE = "/configuracoes/itens-menu";

  function urlDados() {
    const nome = (el.filtroNome?.value || "").trim();
    const pai = (el.filtroMenuPai?.value || "").trim();
    const modulo = (el.filtroModulo?.value || "").trim();
    let url = `${BASE}/dados?pagina=${paginaAtual}&porPagina=${porPagina}`;
    if (nome) url += `&nome=${encodeURIComponent(nome)}`;
    if (pai) url += `&menu_pai=${encodeURIComponent(pai)}`;
    if (modulo) url += `&id_modulo=${encodeURIComponent(modulo)}`;
    return url;
  }

  function atualizarPaginacao() {
    if (el.paginaAtual) el.paginaAtual.textContent = String(paginaAtual);
    if (el.totalPaginas) el.totalPaginas.textContent = String(totalPaginas);
    if (el.btnPrimeiro) el.btnPrimeiro.disabled = paginaAtual <= 1;
    if (el.btnAnterior) el.btnAnterior.disabled = paginaAtual <= 1;
    if (el.btnProximo) el.btnProximo.disabled = paginaAtual >= totalPaginas;
    if (el.btnUltimo) el.btnUltimo.disabled = paginaAtual >= totalPaginas;
  }

  function renderTabela() {
    const dados = dadosCache[paginaAtual] || [];
    const util = window.Util || { gerarIconeTech: () => "…" };
    if (!dados.length) {
      el.lista.innerHTML = "<tr><td colspan=\"8\">Nenhum menu encontrado.</td></tr>";
      atualizarPaginacao();
      return;
    }
    el.lista.innerHTML = dados
      .map(
        (item) => `
      <tr>
        <td>${item.id}</td>
        <td>${item.nome_menu || ""}</td>
        <td>${item.descricao || ""}</td>
        <td>${item.sequencia ?? ""}</td>
        <td>${item.pai ? "Sim" : "Não"}</td>
        <td>${item.data_page || ""}</td>
        <td>${item.modulo || ""}</td>
        <td class="Cl_TableActions">
          <button type="button" class="Cl_BtnAcao btnEditar" data-id="${item.id}">${util.gerarIconeTech("editar")}</button>
          <button type="button" class="Cl_BtnAcao btnExcluir" data-id="${item.id}">${util.gerarIconeTech("excluir")}</button>
        </td>
      </tr>`
      )
      .join("");
    window.lucide?.createIcons?.();
    atualizarPaginacao();
  }

  async function carregarDados() {
    const r = await fetch(urlDados());
    const j = await r.json();
    if (!r.ok) throw new Error(j.erro || j.message || "Erro ao carregar dados.");
    totalPaginas = j.total_paginas || 1;
    dadosCache[paginaAtual] = j.dados || [];
    renderTabela();
  }

  async function carregarCombos() {
    const r = await fetch(`${BASE}/combos`);
    const c = await r.json();
    if (!r.ok) throw new Error(c.erro || c.message || "Erro ao carregar filtros.");
    (c.menus_pai || []).forEach((nome) => {
      const op = document.createElement("option");
      op.value = nome;
      op.textContent = nome;
      el.filtroMenuPai.appendChild(op);
    });
    (c.modulos || []).forEach((m) => {
      const op = document.createElement("option");
      op.value = m.id;
      op.textContent = m.nome;
      el.filtroModulo.appendChild(op);
    });
  }

  function abrirApoio(id) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: id ? `${BASE}/editar` : `${BASE}/incluir`,
      id: id || null,
      titulo: id ? "Editar menu" : "Novo menu",
      largura: 980,
      altura: 640,
      nivel: 1,
    });
  }

  async function excluir(id) {
    const c = await Swal.fire({
      title: "Excluir menu?",
      text: "Essa ação não poderá ser desfeita.",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, excluir",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;

    const r = await fetch(`${BASE}/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.erro || j.message || "Erro ao excluir.");
    await Swal.fire("Sucesso", "Menu excluído.", "success");
    await carregarDados();
  }

  el.btnIncluir?.addEventListener("click", () => abrirApoio(null));
  el.btnFiltrar?.addEventListener("click", () => {
    paginaAtual = 1;
    carregarDados().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  el.btnLimpar?.addEventListener("click", () => {
    el.filtroNome.value = "";
    el.filtroMenuPai.value = "";
    el.filtroModulo.value = "";
    paginaAtual = 1;
    carregarDados().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  el.btnPrimeiro?.addEventListener("click", () => {
    paginaAtual = 1;
    carregarDados();
  });
  el.btnAnterior?.addEventListener("click", () => {
    if (paginaAtual > 1) {
      paginaAtual -= 1;
      carregarDados();
    }
  });
  el.btnProximo?.addEventListener("click", () => {
    if (paginaAtual < totalPaginas) {
      paginaAtual += 1;
      carregarDados();
    }
  });
  el.btnUltimo?.addEventListener("click", () => {
    paginaAtual = totalPaginas;
    carregarDados();
  });

  el.lista.addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    const id = Number(btn.dataset.id || 0);
    if (!id) return;
    try {
      if (btn.classList.contains("btnEditar")) return abrirApoio(id);
      if (btn.classList.contains("btnExcluir")) return await excluir(id);
    } catch (err) {
      await Swal.fire("Erro", err.message, "error");
    }
  });

  window.addEventListener("message", (event) => {
    if (event.data?.grupo === "atualizarTabela") {
      carregarDados().catch((e) => Swal.fire("Erro", e.message, "error"));
    }
  });

  carregarCombos()
    .then(() => carregarDados())
    .catch((e) => Swal.fire("Erro", e.message, "error"));
})();
