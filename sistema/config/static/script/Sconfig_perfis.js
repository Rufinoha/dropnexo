(function () {
  const el = {
    filtroBusca: document.getElementById("ob_filtroBusca"),
    btnFiltrar: document.getElementById("ob_btnFiltrar"),
    btnLimpar: document.getElementById("ob_btnLimpar"),
    tbody: document.getElementById("ob_listaPerfis"),
  };
  if (!el.tbody) return;

  let perfisCache = [];

  function util() {
    return window.Util || { gerarIconeTech: () => "…" };
  }

  function filtrarLista() {
    const q = (el.filtroBusca?.value || "").trim().toLowerCase();
    if (!q) return perfisCache;
    return perfisCache.filter(
      (p) =>
        (p.nome || "").toLowerCase().includes(q) ||
        (p.codigo || "").toLowerCase().includes(q)
    );
  }

  function render() {
    const lista = filtrarLista();
    if (!lista.length) {
      el.tbody.innerHTML = "<tr><td colspan=\"5\">Nenhum perfil encontrado.</td></tr>";
      return;
    }
    const u = util();
    el.tbody.innerHTML = lista
      .map(
        (p) => `
      <tr>
        <td>${p.id}</td>
        <td>${p.codigo || ""}</td>
        <td>${p.nome || ""}</td>
        <td>${p.nivel ?? ""}</td>
        <td class="Cl_TableActions">
          <button type="button" class="Cl_BtnAcao btnMenus" data-id="${p.id}" data-nome="${(p.nome || "").replace(/"/g, "&quot;")}" title="Menus do perfil">${u.gerarIconeTech("configuracoes")}</button>
        </td>
      </tr>`
      )
      .join("");
    window.lucide?.createIcons?.();
  }

  async function carregar() {
    const r = await fetch("/configuracoes/perfis/dados");
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar perfis.");
    perfisCache = j.perfis || [];
    render();
  }

  async function abrirMenusPerfil(idPerfil, nomePerfil) {
    const rMenus = await fetch(`/configuracoes/perfis/${idPerfil}/menus`);
    const jMenus = await rMenus.json();
    if (!rMenus.ok || !jMenus.success) throw new Error(jMenus.message || "Erro ao carregar menus.");

    const itens = jMenus.itens || [];
    const html = itens.length
      ? `<div style="max-height:320px;overflow:auto;text-align:left;">${itens
          .map(
            (m) => `
          <label style="display:block;margin:6px 0;">
            <input type="checkbox" class="cfg-perfil-menu" data-id="${m.id_menu}" ${m.exibir ? "checked" : ""} />
            ${m.nome}${m.nav_codigo ? ` <small>(${m.nav_codigo})</small>` : ""}
          </label>`
          )
          .join("")}</div>`
      : "<p>Nenhum item de menu cadastrado.</p>";

    const result = await Swal.fire({
      title: `Menus — ${nomePerfil}`,
      html,
      width: 520,
      showCancelButton: true,
      confirmButtonText: "Salvar",
      cancelButtonText: "Cancelar",
      focusConfirm: false,
      preConfirm: () => {
        const checks = document.querySelectorAll(".cfg-perfil-menu");
        return Array.from(checks).map((c) => ({
          id_menu: Number(c.dataset.id),
          exibir: c.checked,
        }));
      },
    });
    if (!result.isConfirmed) return;

    const rSave = await fetch(`/configuracoes/perfis/${idPerfil}/menus`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itens: result.value }),
    });
    const jSave = await rSave.json();
    if (!rSave.ok || !jSave.success) throw new Error(jSave.message || "Erro ao salvar.");
    await Swal.fire("Sucesso", jSave.message || "Menus atualizados.", "success");
  }

  el.btnFiltrar?.addEventListener("click", () => render());
  el.btnLimpar?.addEventListener("click", () => {
    if (el.filtroBusca) el.filtroBusca.value = "";
    render();
  });

  el.tbody.addEventListener("click", async (ev) => {
    const btn = ev.target.closest(".btnMenus");
    if (!btn) return;
    const id = Number(btn.dataset.id);
    const nome = btn.dataset.nome || "Perfil";
    try {
      await abrirMenusPerfil(id, nome);
    } catch (e) {
      await Swal.fire("Erro", e.message, "error");
    }
  });

  carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
})();
