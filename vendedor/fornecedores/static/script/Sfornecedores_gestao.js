(function () {
  const el = {
    filtro: document.getElementById("ob_filtroBusca"),
    btnFiltrar: document.getElementById("ob_btnFiltrar"),
    btnLimpar: document.getElementById("ob_btnLimpar"),
    btnIncluir: document.getElementById("ob_btnIncluir"),
    tbody: document.getElementById("ob_listaFornecedores"),
  };
  if (!el.tbody) return;

  const BASE = window.DN_GESTAO_BASE || "/configuracoes/fornecedores-plataforma";

  function util() {
    return window.Util || { gerarIconeTech: () => "…" };
  }

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function fmtCnpj(v) {
    const d = (v || "").replace(/\D/g, "");
    if (d.length !== 14) return v || "";
    return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
  }

  function abrirApoio(id) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: id ? `${BASE}/editar` : `${BASE}/incluir`,
      id,
      titulo: id ? "Editar fornecedor" : "Cadastro de fornecedor",
      largura: 1000,
      altura: 720,
      onFechar: () => carregar().catch(() => {}),
    });
  }

  function renderTabela(dados) {
    const u = util();
    if (!dados?.length) {
      el.tbody.innerHTML = '<tr><td colspan="7">Nenhum fornecedor cadastrado.</td></tr>';
      return;
    }
    el.tbody.innerHTML = dados
      .map((f) => {
        const loc = [f.cidade, f.uf].filter(Boolean).join("/") || "—";
        const st = f.ativo
          ? '<span class="Cat_BadgePub Cat_BadgePub--sim">Ativo</span>'
          : '<span class="Cat_BadgePub Cat_BadgePub--nao">Inativo</span>';
        return `<tr>
          <td><strong>${esc(f.nome)}</strong>${f.razao_social ? `<br><small>${esc(f.razao_social)}</small>` : ""}</td>
          <td>${esc(fmtCnpj(f.documento))}</td>
          <td>${esc(loc)}</td>
          <td>${f.qtd_depositos}</td>
          <td>${f.qtd_produtos}</td>
          <td>${st}</td>
          <td class="Cl_TableActions">
            <button type="button" class="Cl_BtnAcao btnEditar" data-id="${f.id}">${u.gerarIconeTech("editar")}</button>
          </td>
        </tr>`;
      })
      .join("");
    window.lucide?.createIcons?.();
  }

  async function carregar() {
    const q = (el.filtro?.value || "").trim();
    const r = await fetch(`${BASE}/dados?busca=${encodeURIComponent(q)}`);
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar.");
    renderTabela(j.dados || []);
  }

  el.btnFiltrar?.addEventListener("click", () => carregar().catch((e) => Swal.fire("Erro", e.message, "error")));
  el.btnLimpar?.addEventListener("click", () => {
    if (el.filtro) el.filtro.value = "";
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  el.btnIncluir?.addEventListener("click", () => abrirApoio(null));
  el.filtro?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
    }
  });
  el.tbody.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".btnEditar");
    if (!btn) return;
    abrirApoio(Number(btn.dataset.id || 0));
  });

  carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
})();
