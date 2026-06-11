(function () {
  const tbody = document.getElementById("ob_listaNovidades");
  const btnIncluir = document.getElementById("ob_btnIncluir");
  if (!tbody) return;

  let cache = [];

  function util() {
    return window.Util || { gerarIconeTech: () => "…" };
  }

  function render() {
    if (!cache.length) {
      tbody.innerHTML = "<tr><td colspan=\"7\">Nenhuma novidade cadastrada.</td></tr>";
      return;
    }
    const u = util();
    tbody.innerHTML = cache
      .map(
        (n) => `
      <tr>
        <td>${n.id}</td>
        <td>${n.titulo || ""}</td>
        <td>${n.resumo || ""}</td>
        <td>${n.ordem ?? 0}</td>
        <td>${n.ativo ? "Sim" : "Não"}</td>
        <td>${n.publicado_em ? n.publicado_em.slice(0, 10) : ""}</td>
        <td class="Cl_TableActions">
          <button type="button" class="Cl_BtnAcao btnEditar" data-id="${n.id}">${u.gerarIconeTech("editar")}</button>
        </td>
      </tr>`
      )
      .join("");
    window.lucide?.createIcons?.();
  }

  async function carregar() {
    const r = await fetch("/configuracoes/novidades/dados");
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar.");
    cache = j.dados || [];
    render();
  }

  async function abrirForm(item) {
    const isEdit = !!item?.id;
    const html = `
      <input type="hidden" id="sw-id" value="${item?.id || ""}" />
      <div class="Cl_FormCampo" style="text-align:left;margin-bottom:8px;">
        <label>Título</label>
        <input type="text" id="sw-titulo" class="swal2-input" style="width:100%;margin:4px 0 0;" value="${(item?.titulo || "").replace(/"/g, "&quot;")}" />
      </div>
      <div class="Cl_FormCampo" style="text-align:left;margin-bottom:8px;">
        <label>Resumo</label>
        <input type="text" id="sw-resumo" class="swal2-input" style="width:100%;margin:4px 0 0;" value="${(item?.resumo || "").replace(/"/g, "&quot;")}" />
      </div>
      <div class="Cl_FormCampo" style="text-align:left;margin-bottom:8px;">
        <label>Conteúdo</label>
        <textarea id="sw-conteudo" rows="3" style="width:100%;margin:4px 0 0;">${item?.conteudo || ""}</textarea>
      </div>
      <div class="Cl_FormCampo" style="text-align:left;margin-bottom:8px;">
        <label>Ordem</label>
        <input type="number" id="sw-ordem" style="width:100%;margin:4px 0 0;" value="${item?.ordem ?? 0}" />
      </div>
      <label style="display:block;text-align:left;"><input type="checkbox" id="sw-ativo" ${item?.ativo !== false ? "checked" : ""} /> Ativo</label>
    `;

    const result = await Swal.fire({
      title: isEdit ? "Editar novidade" : "Nova novidade",
      html,
      width: 480,
      showCancelButton: true,
      confirmButtonText: "Salvar",
      cancelButtonText: "Cancelar",
      focusConfirm: false,
      preConfirm: () => {
        const titulo = (document.getElementById("sw-titulo")?.value || "").trim();
        if (!titulo) {
          Swal.showValidationMessage("Informe o título.");
          return false;
        }
        return {
          id: document.getElementById("sw-id")?.value || null,
          titulo,
          resumo: (document.getElementById("sw-resumo")?.value || "").trim(),
          conteudo: (document.getElementById("sw-conteudo")?.value || "").trim(),
          ordem: Number(document.getElementById("sw-ordem")?.value || 0),
          ativo: !!document.getElementById("sw-ativo")?.checked,
        };
      },
    });
    if (!result.isConfirmed) return;

    const r = await fetch("/configuracoes/novidades/salvar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(result.value),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    await Swal.fire("Sucesso", j.message || "Salvo.", "success");
    await carregar();
  }

  btnIncluir?.addEventListener("click", () => abrirForm(null).catch((e) => Swal.fire("Erro", e.message, "error")));

  tbody.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".btnEditar");
    if (!btn) return;
    const id = Number(btn.dataset.id);
    const item = cache.find((n) => n.id === id);
    abrirForm(item).catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
})();
