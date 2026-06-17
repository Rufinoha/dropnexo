(() => {
  "use strict";

  const BASE = "/fornecedor/parametros/precificacao";
  const qs = (s) => document.querySelector(s);
  const qsa = (s) => [...document.querySelectorAll(s)];

  let modoAtual = "global";

  function esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
  }

  function aplicarModoUI(modo) {
    modoAtual = modo === "categoria" ? "categoria" : "global";
    const secGlobal = qs("#secGlobal");
    const secCategoria = qs("#secCategoria");
    if (secGlobal) secGlobal.hidden = modoAtual !== "global";
    if (secCategoria) secCategoria.hidden = modoAtual !== "categoria";
    qsa(".FnPar_ModoBtn").forEach((btn) => {
      const on = btn.dataset.modo === modoAtual;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-checked", on ? "true" : "false");
    });
  }

  async function salvarModo(modo) {
    const r = await fetch(`${BASE}/modo`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ modo }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar modo.");
    aplicarModoUI(j.modo || modo);
  }

  function preencherGlobal(regras) {
    const g = regras.find((r) => r.escopo === "global");
    if (!g) return;
    qs("#pctAjusteGlobal").value = g.pct_ajuste ?? 0;
    qs("#pctTaxasGlobal").value = g.pct_taxas ?? 0;
    qs("#pctComissaoGlobal").value = g.pct_comissao ?? 0;
  }

  function fmtMoeda(v) {
    return Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function renderTabela(regras) {
    const tbody = qs("#tblRegras");
    if (!tbody) return;
    const cats = regras.filter((r) => r.escopo === "categoria");
    if (!cats.length) {
      tbody.innerHTML = `<tr><td colspan="5">Nenhuma regra por categoria.</td></tr>`;
      return;
    }
    tbody.innerHTML = cats
      .map(
        (r) => `<tr>
          <td>Categoria</td>
          <td>${esc(r.categoria_nome || r.id_categoria)}</td>
          <td>${r.pct_ajuste}</td>
          <td>${fmtMoeda(r.pct_taxas)}</td>
          <td>${r.pct_comissao}</td>
        </tr>`
      )
      .join("");
  }

  function preencherCategorias(categorias) {
    const sel = qs("#selCategoria");
    if (!sel) return;
    sel.innerHTML =
      `<option value="">Selecione…</option>` +
      categorias
        .map((c) => {
          const pad = c.nivel > 1 ? "— ".repeat(c.nivel - 1) : "";
          return `<option value="${c.id}">${pad}${esc(c.nome)}</option>`;
        })
        .join("");
  }

  async function carregar() {
    const r = await fetch(`${BASE}/dados`, { credentials: "include" });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar.");
    aplicarModoUI("global");
    preencherGlobal(j.regras || []);
    renderTabela(j.regras || []);
    preencherCategorias(j.categorias || []);
  }

  async function salvar(payload) {
    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify(payload),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    await Swal.fire({ icon: "success", title: "Salvo", text: j.message, timer: 2000, showConfirmButton: false });
    await carregar();
  }

  qsa(".FnPar_ModoBtn").forEach((btn) => {
    btn.addEventListener("click", () => {
      const modo = btn.dataset.modo;
      if (!modo || modo === modoAtual) return;
      salvarModo(modo).catch((e) => Swal.fire("Erro", e.message, "error"));
    });
  });

  qs("#btnSalvarGlobal")?.addEventListener("click", () =>
    salvar({
      escopo: "global",
      pct_ajuste: qs("#pctAjusteGlobal")?.value || 0,
      pct_taxas: qs("#pctTaxasGlobal")?.value || 0,
      pct_comissao: qs("#pctComissaoGlobal")?.value || 0,
    }).catch((e) => Swal.fire("Erro", e.message, "error"))
  );

  qs("#btnSalvarCategoria")?.addEventListener("click", () => {
    const id = qs("#selCategoria")?.value;
    if (!id) return Swal.fire("Atenção", "Selecione uma categoria.", "warning");
    salvar({
      escopo: "categoria",
      id_categoria: id,
      pct_ajuste: qs("#pctAjusteCat")?.value || 0,
      pct_taxas: qs("#pctTaxasCat")?.value || 0,
      pct_comissao: qs("#pctComissaoCat")?.value || 0,
    }).catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  qs("#btnAplicarAgora")?.addEventListener("click", async () => {
    const ok = await Swal.fire({
      icon: "question",
      title: "Aplicar precificação?",
      text: "Todos os produtos terão valor_drop recalculado pelas regras (valores manuais serão substituídos) e serão publicados na rede.",
      showCancelButton: true,
      confirmButtonText: "Aplicar agora",
      cancelButtonText: "Cancelar",
    });
    if (!ok.isConfirmed) return;
    try {
      const r = await fetch(`${BASE}/aplicar`, { method: "POST", credentials: "include" });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha.");
      await Swal.fire("Concluído", j.message, "success");
    } catch (e) {
      Swal.fire("Erro", e.message, "error");
    }
  });

  if (window.GlobalUtils?.receberDadosApoio) GlobalUtils.receberDadosApoio(() => carregar());
  document.addEventListener("DOMContentLoaded", () => carregar().catch((e) => Swal.fire("Erro", e.message, "error")));
})();
