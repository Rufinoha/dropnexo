(function () {
  const lista = document.getElementById("cfg_seg_lista");
  const BASE = "/configuracoes/segmentos-plataforma";
  const fld = {
    id: document.getElementById("cfg_seg_id"),
    nome: document.getElementById("cfg_seg_nome"),
    slug: document.getElementById("cfg_seg_slug"),
    ordem: document.getElementById("cfg_seg_ordem"),
  };

  function limpar() {
    fld.id.value = "";
    fld.nome.value = "";
    fld.slug.value = "";
    fld.ordem.value = "0";
  }

  async function carregar() {
    const r = await fetch(BASE + "/dados", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    lista.innerHTML = (j.segmentos || [])
      .map(
        (s) => `
      <article class="CfgSeg_Card${s.ativo ? "" : " is-off"}">
        <div class="CfgSeg_CardHead">
          <strong>${s.nome}</strong>
          <code>${s.slug}</code>
        </div>
        <p class="CfgSeg_Meta">${s.qtd_fornecedores} fornecedor(es) · ${s.qtd_categorias} categoria(s) na rede</p>
        <div class="CfgSeg_Acoes">
          <button type="button" class="Cl_BtnLink" data-edit="${s.id}">Editar</button>
          <button type="button" class="Cl_BtnExcluir" data-del="${s.id}">Excluir</button>
        </div>
      </article>`
      )
      .join("");
  }

  document.getElementById("cfg_seg_btnNovo").onclick = limpar;
  document.getElementById("cfg_seg_btnSalvar").onclick = async () => {
    const body = {
      id: fld.id.value || null,
      nome: fld.nome.value.trim(),
      slug: fld.slug.value.trim(),
      ordem: +fld.ordem.value || 0,
      ativo: true,
    };
    const r = await fetch(BASE + "/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    alert(j.message || (j.success ? "OK" : "Erro"));
    if (j.success) {
      limpar();
      carregar();
    }
  };

  lista.addEventListener("click", async (e) => {
    const edit = e.target.closest("[data-edit]");
    const del = e.target.closest("[data-del]");
    if (edit) {
      const r = await fetch(BASE + "/dados", { credentials: "same-origin" });
      const j = await r.json();
      const s = (j.segmentos || []).find((x) => String(x.id) === edit.getAttribute("data-edit"));
      if (s) {
        fld.id.value = s.id;
        fld.nome.value = s.nome;
        fld.slug.value = s.slug;
        fld.ordem.value = s.ordem;
      }
      return;
    }
    if (del && confirm("Excluir este segmento?")) {
      const r = await fetch(BASE + "/excluir", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: +del.getAttribute("data-del") }),
      });
      const j = await r.json();
      alert(j.message);
      if (j.success) carregar();
    }
  });

  carregar();
})();
