(function () {
  "use strict";

  const el = {
    busca: document.getElementById("vdCatBusca"),
    btnBuscar: document.getElementById("vdCatBtnBuscar"),
    emEstoque: document.getElementById("vdCatEmEstoque"),
    grid: document.getElementById("vdCatGrid"),
    vazio: document.getElementById("vdCatVazio"),
    drawer: document.getElementById("vdCatDrawer"),
    backdrop: document.getElementById("vdCatDrawerBackdrop"),
    drawerFechar: document.getElementById("vdCatDrawerFechar"),
    drawerTitulo: document.getElementById("vdCatDrawerTitulo"),
    drawerBody: document.getElementById("vdCatDrawerBody"),
  };

  if (!el.grid) return;

  let produtosCache = [];

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function fmtMoeda(v) {
    return window.Util?.formatarMoeda
      ? Util.formatarMoeda(v)
      : Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function fmtPrecoSug(p) {
    const min = p.preco_sugerido;
    const max = p.preco_sugerido_max;
    if (max && max !== min) return `${fmtMoeda(min)} – ${fmtMoeda(max)}`;
    return fmtMoeda(min);
  }

  function renderVarResumo(p) {
    const resumo = p.atributos_resumo || [];
    if (!resumo.length) return "";
    return `<div class="VdCat_VarResumo">${resumo
      .slice(0, 2)
      .map(
        (a) =>
          `<div class="VdCat_VarLinha"><span class="VdCat_VarNome">${esc(a.nome)}:</span> ${esc((a.valores || []).join(", "))}</div>`
      )
      .join("")}</div>`;
  }

  function badgeCard(p) {
    if (p.ativado) return '<span class="VdCat_CardBadge is-ok">Integrado</span>';
    if (p.tem_variacoes) return `<span class="VdCat_CardBadge">${p.qtd_variantes} var.</span>`;
    return "";
  }

  function renderCard(p) {
    const img = p.imagem_url
      ? `<img src="${esc(p.imagem_url)}" alt="" loading="lazy" />`
      : '<div class="VdCat_CardImgVazio">📦</div>';
    return `
      <article class="VdCat_Card${p.ativado ? " is-ativo" : ""}" data-produto="${p.id_produto}" tabindex="0">
        <div class="VdCat_CardImg">
          ${badgeCard(p)}
          ${img}
        </div>
        <div class="VdCat_CardBody">
          <span class="VdCat_CardForn">${esc(p.fornecedor_nome)}</span>
          <h3 class="VdCat_CardNome">${esc(p.nome)}</h3>
          ${renderVarResumo(p)}
          <div class="VdCat_Precos">
            <div>
              <span class="VdCat_PrecoLbl">Valor Drop</span>
              <span class="VdCat_PrecoDrop">${fmtMoeda(p.preco_fornecedor)}</span>
            </div>
            <div>
              <span class="VdCat_PrecoLbl">Venda sugerida</span>
              <span class="VdCat_PrecoSug">${fmtPrecoSug(p)}</span>
            </div>
          </div>
        </div>
      </article>`;
  }

  function renderGrid(produtos) {
    produtosCache = produtos || [];
    if (!produtosCache.length) {
      el.grid.innerHTML = "";
      if (el.vazio) el.vazio.hidden = false;
      return;
    }
    if (el.vazio) el.vazio.hidden = true;
    el.grid.innerHTML = produtosCache.map(renderCard).join("");
  }

  function fecharDrawer() {
    if (!el.drawer) return;
    el.drawer.hidden = true;
    el.drawer.setAttribute("aria-hidden", "true");
  }

  function abrirDrawer() {
    if (!el.drawer) return;
    el.drawer.hidden = false;
    el.drawer.setAttribute("aria-hidden", "false");
  }

  function renderVarItem(v) {
    const btn = v.ativado
      ? '<span class="VdCat_BadgeOk">Integrado</span>'
      : `<button type="button" class="Cl_BtnSalvar VdCat_BtnAtivar" data-variante="${v.id_variante}">Ativar</button>`;
    return `
      <li class="VdCat_VarItem">
        <div class="VdCat_VarItemRotulo">${esc(v.rotulo)}</div>
        <div class="VdCat_VarItemSku">SKU ${esc(v.sku || "—")} · Estoque ${v.estoque ?? 0}</div>
        <div class="VdCat_VarItemPrecos">
          Drop ${fmtMoeda(v.preco_fornecedor)} · Sugerido <strong>${fmtMoeda(v.preco_sugerido)}</strong>
        </div>
        <div class="VdCat_VarItemAcao">${btn}</div>
      </li>`;
  }

  function renderDetalhe(p) {
    if (el.drawerTitulo) el.drawerTitulo.textContent = p.nome || "Produto";
    const img = p.imagem_url
      ? `<img class="VdCat_DetImg" src="${esc(p.imagem_url)}" alt="" />`
      : "";
    const desc = p.descricao
      ? `<p class="VdCat_DetDesc">${esc(p.descricao)}</p>`
      : "";
    const resumo = renderVarResumo(p);
    const vars = (p.variantes || []).map(renderVarItem).join("");

    el.drawerBody.innerHTML = `
      ${img}
      <p class="VdCat_DetMeta">${esc(p.fornecedor_nome)}${p.estoque_total != null ? ` · Estoque total: ${p.estoque_total}` : ""}</p>
      ${desc}
      ${resumo ? `<div class="VdCat_DetSecao"><h3>Variações disponíveis</h3>${resumo}</div>` : ""}
      <div class="VdCat_DetSecao">
        <h3>${p.tem_variacoes ? "Escolha a variação" : "Produto"}</h3>
        <ul class="VdCat_VarLista">${vars}</ul>
      </div>`;
  }

  async function abrirProduto(idProduto) {
    el.drawerBody.innerHTML = "<p>Carregando…</p>";
    abrirDrawer();
    const r = await fetch(`/vendedor/catalogo/produto/${idProduto}`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      el.drawerBody.innerHTML = `<p>${esc(j.message || "Erro ao carregar.")}</p>`;
      return;
    }
    renderDetalhe(j.produto);
  }

  async function ativar(idVariante) {
    const idProdutoAberto = produtosCache.find((p) =>
      (p.variantes || []).some((v) => Number(v.id_variante) === Number(idVariante))
    )?.id_produto;
    const drawerAberto = el.drawer && !el.drawer.hidden;

    const r = await fetch("/vendedor/catalogo/ativar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_variante: idVariante }),
    });
    const j = await r.json();
    if (window.Swal) {
      await Swal.fire(j.success ? "Sucesso" : "Erro", j.message, j.success ? "success" : "error");
    } else {
      alert(j.message);
    }
    if (!j.success) return;
    await carregar();
    if (drawerAberto && idProdutoAberto) {
      await abrirProduto(idProdutoAberto);
    }
  }

  async function carregar() {
    const params = new URLSearchParams();
    const busca = (el.busca?.value || "").trim();
    if (busca) params.set("busca", busca);
    if (el.emEstoque?.checked) params.set("em_estoque", "1");
    el.grid.innerHTML = '<p class="VdCat_Vazio">Carregando…</p>';
    const r = await fetch(`/vendedor/catalogo/dados?${params}`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      el.grid.innerHTML = "";
      if (el.vazio) {
        el.vazio.hidden = false;
        el.vazio.textContent = j.message || "Erro ao carregar.";
      }
      return;
    }
    renderGrid(j.produtos || []);
  }

  el.btnBuscar?.addEventListener("click", carregar);
  el.busca?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") carregar();
  });
  el.emEstoque?.addEventListener("change", carregar);

  el.grid.addEventListener("click", (e) => {
    if (e.target.closest(".VdCat_BtnAtivar, button")) return;
    const card = e.target.closest(".VdCat_Card");
    if (!card) return;
    abrirProduto(card.getAttribute("data-produto"));
  });

  el.grid.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const card = e.target.closest(".VdCat_Card");
    if (!card) return;
    e.preventDefault();
    abrirProduto(card.getAttribute("data-produto"));
  });

  el.drawerBody?.addEventListener("click", (e) => {
    const btn = e.target.closest(".VdCat_BtnAtivar");
    if (!btn) return;
    e.stopPropagation();
    ativar(Number(btn.getAttribute("data-variante")));
  });

  el.drawerFechar?.addEventListener("click", fecharDrawer);
  el.backdrop?.addEventListener("click", fecharDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && el.drawer && !el.drawer.hidden) fecharDrawer();
  });

  carregar();
})();
