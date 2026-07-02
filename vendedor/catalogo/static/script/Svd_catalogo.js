(function () {
  "use strict";

  const el = {
    busca: document.getElementById("vdCatBusca"),
    btnBuscar: document.getElementById("vdCatBtnBuscar"),
    emEstoque: document.getElementById("vdCatEmEstoque"),
    grid: document.getElementById("vdCatGrid"),
    vazio: document.getElementById("vdCatVazio"),
    modal: document.getElementById("vdCatModal"),
    backdrop: document.getElementById("vdCatModalBackdrop"),
    modalFechar: document.getElementById("vdCatModalFechar"),
    modalForn: document.getElementById("vdCatModalForn"),
    modalTitulo: document.getElementById("vdCatModalTitulo"),
    modalBody: document.getElementById("vdCatModalBody"),
    modalFoot: document.getElementById("vdCatModalFoot"),
  };

  if (!el.grid) return;

  let produtosCache = [];
  let produtoAberto = null;

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

  function fmtFaixa(min, max, fmt) {
    if (max && max !== min) return `${fmt(min)} – ${fmt(max)}`;
    return fmt(min);
  }

  function fmtPrecoSug(p) {
    return fmtFaixa(p.preco_sugerido, p.preco_sugerido_max, fmtMoeda);
  }

  function fmtDrop(p) {
    const drops = (p.variantes || []).map((v) => v.preco_fornecedor).filter((n) => n != null);
    if (drops.length > 1) {
      return fmtFaixa(Math.min(...drops), Math.max(...drops), fmtMoeda);
    }
    return fmtMoeda(p.preco_fornecedor);
  }

  function renderVarResumo(p, cls) {
    const resumo = p.atributos_resumo || [];
    if (!resumo.length) return "";
    return `<div class="${cls || "VdCat_VarResumo"}">${resumo
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
              <span class="VdCat_PrecoDrop">${fmtDrop(p)}</span>
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

  function fecharModal() {
    if (!el.modal) return;
    el.modal.hidden = true;
    el.modal.setAttribute("aria-hidden", "true");
    produtoAberto = null;
    document.body.classList.remove("VdCat_ModalAberto");
  }

  function abrirModal() {
    if (!el.modal) return;
    el.modal.hidden = false;
    el.modal.setAttribute("aria-hidden", "false");
    document.body.classList.add("VdCat_ModalAberto");
  }

  function renderVarChips(p) {
    const vars = p.variantes || [];
    if (!vars.length) return "";
    if (p.tem_variacoes && (p.atributos_resumo || []).length) {
      return renderVarResumo(p, "VdCat_VarChips");
    }
    return `<ul class="VdCat_VarListaSimples">${vars
      .map((v) => `<li>${esc(v.rotulo || v.sku || "Variação")}</li>`)
      .join("")}</ul>`;
  }

  function renderFooter(p) {
    const lucro = fmtFaixa(p.lucro_estimado, p.lucro_estimado_max || p.lucro_estimado, fmtMoeda);
    const qtdVar = (p.variantes || []).length;
    let btnHtml;
    if (p.ativado) {
      btnHtml = `<span class="VdCat_BadgeIntegrado">Integrado na vitrine</span>`;
    } else {
      const lbl =
        qtdVar > 1 ? `Ativar produto (${qtdVar} variações)` : "Ativar produto";
      btnHtml = `<button type="button" class="Cl_BtnSalvar VdCat_BtnAtivarPai" data-produto="${p.id_produto}">${lbl}</button>`;
    }
    return `
      <div class="VdCat_FootPrecos">
        <div class="VdCat_FootPrecoBox">
          <span class="VdCat_PrecoLbl">Valor Drop</span>
          <strong class="VdCat_PrecoDrop">${fmtDrop(p)}</strong>
        </div>
        <div class="VdCat_FootPrecoBox">
          <span class="VdCat_PrecoLbl">Venda sugerida</span>
          <strong class="VdCat_PrecoSug">${fmtPrecoSug(p)}</strong>
        </div>
        <div class="VdCat_FootPrecoBox">
          <span class="VdCat_PrecoLbl">Lucro est.</span>
          <strong class="VdCat_PrecoLucro">${lucro}</strong>
        </div>
      </div>
      <div class="VdCat_FootAcao">${btnHtml}</div>`;
  }

  function renderDetalhe(p) {
    produtoAberto = p;
    if (el.modalForn) el.modalForn.textContent = p.fornecedor_nome || "";
    if (el.modalTitulo) el.modalTitulo.textContent = p.nome || "Produto";

    const img = p.imagem_url
      ? `<div class="VdCat_ModalImgWrap"><img class="VdCat_ModalImg" src="${esc(p.imagem_url)}" alt="" /></div>`
      : `<div class="VdCat_ModalImgWrap VdCat_ModalImgWrap--vazio">📦</div>`;

    const descHtml = p.descricao_html || "";
    const desc = descHtml
      ? `<div class="VdCat_ModalDesc">${descHtml}</div>`
      : "";

    const meta = [
      p.categoria ? esc(p.categoria) : "",
      p.estoque_total != null ? `Estoque total: ${p.estoque_total}` : "",
      p.qtd_variantes > 1 ? `${p.qtd_variantes} variações` : "",
    ]
      .filter(Boolean)
      .join(" · ");

    el.modalBody.innerHTML = `
      <div class="VdCat_ModalGrid">
        ${img}
        <div class="VdCat_ModalInfo">
          ${meta ? `<p class="VdCat_ModalMeta">${meta}</p>` : ""}
          ${desc}
          ${
            p.tem_variacoes
              ? `<div class="VdCat_ModalSecao">
                  <h3>Variações incluídas</h3>
                  <p class="VdCat_ModalHint">Ao ativar, todas as variações entram juntas na sua vitrine.</p>
                  ${renderVarChips(p)}
                </div>`
              : ""
          }
        </div>
      </div>`;

    if (el.modalFoot) el.modalFoot.innerHTML = renderFooter(p);
  }

  async function abrirProduto(idProduto) {
    if (el.modalBody) el.modalBody.innerHTML = '<p class="VdCat_Loading">Carregando…</p>';
    if (el.modalFoot) el.modalFoot.innerHTML = "";
    abrirModal();
    const r = await fetch(`/vendedor/catalogo/produto/${idProduto}`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      if (el.modalBody) el.modalBody.innerHTML = `<p>${esc(j.message || "Erro ao carregar.")}</p>`;
      return;
    }
    const p = j.produto;
    const lucros = (p.variantes || []).map((v) => (v.preco_sugerido || 0) - (v.preco_fornecedor || 0));
    if (lucros.length) {
      p.lucro_estimado = Math.min(...lucros.map((x) => Math.round(x * 100) / 100));
      p.lucro_estimado_max = Math.max(...lucros.map((x) => Math.round(x * 100) / 100));
    }
    renderDetalhe(p);
  }

  async function ativarProduto(idProduto) {
    const r = await fetch("/vendedor/catalogo/ativar-produto", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_produto: idProduto }),
    });
    const j = await r.json();
    if (window.Swal) {
      await Swal.fire(j.success ? "Sucesso" : "Erro", j.message, j.success ? "success" : "error");
    } else {
      alert(j.message);
    }
    if (!j.success) return;
    await carregar();
    if (el.modal && !el.modal.hidden) {
      await abrirProduto(idProduto);
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
    if (e.target.closest("button")) return;
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

  el.modalFoot?.addEventListener("click", (e) => {
    const btn = e.target.closest(".VdCat_BtnAtivarPai");
    if (!btn) return;
    ativarProduto(Number(btn.getAttribute("data-produto")));
  });

  el.modalFechar?.addEventListener("click", fecharModal);
  el.backdrop?.addEventListener("click", fecharModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && el.modal && !el.modal.hidden) fecharModal();
  });

  carregar();
})();
