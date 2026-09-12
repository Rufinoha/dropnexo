(() => {
  "use strict";

  const BASE = (window.PAR_API_BASE || "/fornecedor/parametros") + "/precificacao";
  const qs = (s) => document.querySelector(s);
  const qsa = (s) => [...document.querySelectorAll(s)];

  let modoAtual = "global";

  function esc(s) {
    return String(s ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;");
  }

  function fmtMoeda(v) {
    return Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function num(el, def = 0) {
    const v = parseFloat(el?.value);
    return Number.isFinite(v) ? v : def;
  }

  function calcularDrop(preco, ajuste, taxas, comissao) {
    const aposAjuste = preco * (1 + ajuste / 100);
    const aposTaxa = aposAjuste + Math.max(0, taxas);
    return Math.max(0, aposTaxa * (1 + comissao / 100));
  }

  function regrasSimulacaoAtivas() {
    if (modoAtual === "categoria") {
      return {
        ajuste: num(qs("#pctAjusteCat")),
        taxas: num(qs("#pctTaxasCat")),
        comissao: num(qs("#pctComissaoCat")),
        margem: num(qs("#pctMargemRevendaCat"), 80),
      };
    }
    return {
      ajuste: num(qs("#pctAjusteGlobal")),
      taxas: num(qs("#pctTaxasGlobal")),
      comissao: num(qs("#pctComissaoGlobal")),
      margem: num(qs("#pctMargemRevendaGlobal"), 80),
    };
  }

  function atualizarSimulacao() {
    const precoBase = Math.max(0, num(qs("#precoSimulacao"), 100));
    const { ajuste, taxas, comissao, margem } = regrasSimulacaoAtivas();
    const drop = calcularDrop(precoBase, ajuste, taxas, comissao);
    const sugestao = drop * (1 + margem / 100);
    const lucro = Math.max(0, sugestao - drop);

    const setTxt = (sel, txt) => {
      const el = qs(sel);
      if (el) el.textContent = txt;
    };
    setTxt("#simPrecoBase", fmtMoeda(precoBase));
    setTxt("#simValorDrop", fmtMoeda(drop));
    setTxt("#simSugestao", fmtMoeda(sugestao));
    setTxt("#simLucro", fmtMoeda(lucro));

    const detalheDrop = [];
    if (ajuste) detalheDrop.push(`${ajuste > 0 ? "+" : ""}${ajuste}%`);
    if (taxas) detalheDrop.push(`+ ${fmtMoeda(taxas)}`);
    if (comissao) detalheDrop.push(`comissão ${comissao}%`);
    setTxt("#simDropDetalhe", detalheDrop.length ? detalheDrop.join(" · ") : "sem ajuste");
    setTxt("#simSugestaoDetalhe", `margem ${margem}% sobre o Drop`);
    setTxt("#simLucroDetalhe", "sugestão − Drop");
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
    atualizarSimulacao();
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
    qs("#pctMargemRevendaGlobal").value = g.pct_margem_revenda ?? 80;
    atualizarSimulacao();
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
          <td>${esc(r.categoria_nome || r.id_categoria)}</td>
          <td>${r.pct_ajuste}</td>
          <td>${fmtMoeda(r.pct_taxas)}</td>
          <td>${r.pct_comissao}</td>
          <td>${r.pct_margem_revenda ?? 80}</td>
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
    atualizarSimulacao();
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
      pct_margem_revenda: qs("#pctMargemRevendaGlobal")?.value || 80,
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
      pct_margem_revenda: qs("#pctMargemRevendaCat")?.value || 80,
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

  function iniciarEdicaoPrecoBase() {
    const card = qs("#cardPrecoBase");
    const valor = qs("#simPrecoBase");
    const input = qs("#precoSimulacao");
    if (!card || !valor || !input || card.classList.contains("is-editing")) return;
    card.classList.add("is-editing");
    valor.hidden = true;
    input.hidden = false;
    input.focus();
    input.select();
  }

  function finalizarEdicaoPrecoBase() {
    const card = qs("#cardPrecoBase");
    const valor = qs("#simPrecoBase");
    const input = qs("#precoSimulacao");
    if (!card || !valor || !input) return;
    const n = Math.max(0, num(input, 100));
    input.value = String(n);
    card.classList.remove("is-editing");
    input.hidden = true;
    valor.hidden = false;
    atualizarSimulacao();
  }

  const inputsSim = [
    "#precoSimulacao",
    "#pctAjusteGlobal",
    "#pctTaxasGlobal",
    "#pctComissaoGlobal",
    "#pctMargemRevendaGlobal",
    "#pctAjusteCat",
    "#pctTaxasCat",
    "#pctComissaoCat",
    "#pctMargemRevendaCat",
  ];

  if (window.GlobalUtils?.receberDadosApoio) GlobalUtils.receberDadosApoio(() => carregar());
  document.addEventListener("DOMContentLoaded", () => {
    inputsSim.forEach((sel) => qs(sel)?.addEventListener("input", atualizarSimulacao));
    qs("#cardPrecoBase")?.addEventListener("dblclick", iniciarEdicaoPrecoBase);
    qs("#precoSimulacao")?.addEventListener("keydown", (ev) => {
      if (ev.key === "Enter") {
        ev.preventDefault();
        finalizarEdicaoPrecoBase();
      } else if (ev.key === "Escape") {
        ev.preventDefault();
        const input = qs("#precoSimulacao");
        if (input) input.value = String(Math.max(0, num(input, 100)));
        finalizarEdicaoPrecoBase();
      }
    });
    qs("#precoSimulacao")?.addEventListener("blur", finalizarEdicaoPrecoBase);
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
})();
