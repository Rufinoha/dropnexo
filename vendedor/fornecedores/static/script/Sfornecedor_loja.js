(function () {
  let idFornecedor = null;
  let idArmazemFornecedor = null;
  let paginaAtual = 1;
  let totalPaginas = 1;
  let statusVinculo = "nenhum";

  const el = {
    id: document.getElementById("id_fornecedor"),
    titulo: document.getElementById("lojaTitulo"),
    subtitulo: document.getElementById("lojaSubtitulo"),
    segmentos: document.getElementById("lojaSegmentos"),
    status: document.getElementById("lojaStatus"),
    busca: document.getElementById("lojaBusca"),
    btnBuscar: document.getElementById("lojaBtnBuscar"),
    grid: document.getElementById("lojaGrid"),
    vazio: document.getElementById("lojaVazio"),
    paginacao: document.getElementById("lojaPaginacao"),
    btnVinculo: document.getElementById("lojaBtnVinculo"),
    btnCancelarVinculo: document.getElementById("lojaBtnCancelarVinculo"),
    logoWrap: document.getElementById("lojaLogoWrap"),
    logoImg: document.getElementById("lojaLogoImg"),
    monogram: document.getElementById("lojaMonogram"),
    monogramMark: document.getElementById("lojaMonogramMark"),
  };

  if (!el.grid) return;

  const fmtMoeda = (v) =>
    window.Util?.formatarMoeda
      ? Util.formatarMoeda(v)
      : "R$ " + Number(v || 0).toFixed(2).replace(".", ",");

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function iniciaisNome(nome) {
    const p = String(nome || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (!p.length) return "?";
    if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
    return (p[0][0] + p[p.length - 1][0]).toUpperCase();
  }

  function hueDoNome(nome) {
    let h = 0;
    const s = String(nome || "");
    for (let i = 0; i < s.length; i++) h = (h * 33 + s.charCodeAt(i)) >>> 0;
    return h % 360;
  }

  function mostrarMonograma(nome) {
    const hue = hueDoNome(nome);
    if (el.logoWrap) el.logoWrap.style.setProperty("--logo-hue", String(hue));
    if (el.monogramMark) el.monogramMark.textContent = iniciaisNome(nome);
    if (el.monogram) el.monogram.hidden = false;
    if (el.logoImg) {
      el.logoImg.hidden = true;
      el.logoImg.removeAttribute("src");
    }
  }

  function aplicarLogoHero(forn) {
    const nome = forn.nome || "Fornecedor";
    const logo = String(forn.logo_url || "").trim();
    if (!logo) {
      mostrarMonograma(nome);
      return;
    }
    if (!el.logoImg) {
      mostrarMonograma(nome);
      return;
    }
    const hue = hueDoNome(nome);
    if (el.logoWrap) el.logoWrap.style.setProperty("--logo-hue", String(hue));
    if (el.monogramMark) el.monogramMark.textContent = iniciaisNome(nome);
    el.logoImg.onload = () => {
      el.logoImg.hidden = false;
      if (el.monogram) el.monogram.hidden = true;
    };
    el.logoImg.onerror = () => mostrarMonograma(nome);
    el.logoImg.src = logo;
  }

  function renderSegmentos(lista) {
    if (!el.segmentos) return;
    const segs = Array.isArray(lista) ? lista.filter(Boolean) : [];
    if (!segs.length) {
      el.segmentos.hidden = true;
      el.segmentos.innerHTML = "";
      return;
    }
    el.segmentos.hidden = false;
    el.segmentos.innerHTML = segs
      .map((s) => `<span class="Loja_SegChip">${esc(s)}</span>`)
      .join("");
  }

  function urlParaExibir(url) {
    const u = String(url || "").trim();
    if (!u) return "";
    // Já veio proxied (evitar proxy-de-proxy → 400).
    if (/\/imagens\/proxy\?/i.test(u)) {
      try {
        const inner = new URL(u, window.location.origin).searchParams.get("url");
        if (inner && /^https?:\/\//i.test(inner)) {
          return `/catalogos/imagens/proxy?url=${encodeURIComponent(inner)}`;
        }
      } catch (_) {
        /* usa u abaixo */
      }
      return u;
    }
    if (!/^https?:\/\//i.test(u)) return u;
    // Mesmo endpoint do catálogo do fornecedor (já validado com Postimages).
    return `/catalogos/imagens/proxy?url=${encodeURIComponent(u)}`;
  }

  function statusBadge(st) {
    const map = {
      ativo: { cls: "is-ativo", txt: "Conectado — pode integrar produtos" },
      aguardando: { cls: "is-pending", txt: "Aguardando aprovação do fornecedor" },
      pausado: { cls: "", txt: "Vínculo pausado — novos produtos bloqueados até despausar" },
      recusado: { cls: "", txt: "Vínculo não aprovado — solicite novamente na lista" },
      inativo: { cls: "", txt: "Vínculo encerrado — solicite novamente na lista" },
      nenhum: { cls: "", txt: "Solicite vínculo para integrar produtos" },
    };
    const m = map[st] || map.nenhum;
    if (el.status) {
      el.status.className = "Loja_StatusBadge " + m.cls;
      el.status.textContent = m.txt;
    }
    if (el.btnVinculo) {
      el.btnVinculo.hidden = !["nenhum", "recusado", "inativo"].includes(st);
    }
    if (el.btnCancelarVinculo) {
      el.btnCancelarVinculo.hidden = st !== "aguardando";
    }
  }

  function renderVariacoesResumo(p) {
    const resumo = p.atributos_resumo || [];
    if (resumo.length) {
      return `<div class="Loja_VarResumo">${resumo
        .map(
          (a) =>
            `<div class="Loja_VarLinha"><span class="Loja_VarNome">${esc(a.nome)}:</span> ${esc((a.valores || []).join(", "))}</div>`
        )
        .join("")}</div>`;
    }
    if (!p.tem_variacoes) return "";
    const grades = [...new Set((p.grades || []).map((g) => String(g || "").trim()).filter(Boolean))];
    if (grades.length <= 1) return "";
    return `<div class="Loja_VarResumo">${grades
      .slice(0, 6)
      .map((g) => `<div class="Loja_VarLinha">${esc(g)}</div>`)
      .join("")}</div>`;
  }

  function renderProdutos(produtos) {
    if (!produtos.length) {
      el.grid.innerHTML = "";
      if (el.vazio) el.vazio.hidden = false;
      return;
    }
    if (el.vazio) el.vazio.hidden = true;

    const vinculoAtivo = statusVinculo === "ativo";
    const podeSolicitar =
      !vinculoAtivo && statusVinculo !== "aguardando" && statusVinculo !== "pausado";

    el.grid.innerHTML = produtos
      .map((p) => {
        const variacoesHtml = renderVariacoesResumo(p);
        const img = p.imagem_url
          ? `<img src="${esc(urlParaExibir(p.imagem_url))}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.removeAttribute('src');this.parentElement&&this.parentElement.classList.add('is-img-broken');" />`
          : '<div class="Loja_CardImgVazio">📦</div>';

        let btnHtml;
        if (p.ativado) {
          btnHtml = '<button type="button" class="Loja_BtnIntegrar is-done" disabled>Integrado</button>';
        } else if (vinculoAtivo) {
          btnHtml = `<button type="button" class="Loja_BtnIntegrar" data-acao="integrar" data-prod="${p.id_produto}">Integrar produto</button>`;
        } else if (statusVinculo === "aguardando") {
          btnHtml = '<button type="button" class="Loja_BtnIntegrar" disabled>Aguardando vínculo</button>';
        } else {
          btnHtml = `<button type="button" class="Loja_BtnIntegrar Loja_BtnVinculo" data-acao="vinculo">Solicitar vínculo</button>`;
        }

        return `
        <article class="Loja_Card">
          <div class="Loja_CardImgWrap">
            ${p.tem_variacoes ? '<span class="Loja_CardBadge">Variações</span>' : ""}
            ${img}
          </div>
          <div class="Loja_CardBody">
            <h3 class="Loja_CardNome" title="${esc(p.nome)}">${esc(p.nome)}</h3>
            ${variacoesHtml}
            <div class="Loja_Precos">
              <div>
                <span class="Loja_PrecoLbl">Venda sugerida</span>
                <span class="Loja_PrecoSug">${fmtMoeda(p.preco_sugerido)}</span>
              </div>
              <div>
                <span class="Loja_PrecoLbl">Lucro est.</span>
                <span class="Loja_PrecoLucro">${fmtMoeda(p.lucro_estimado)}</span>
              </div>
              ${p.margem_pct > 0 ? `<span class="Loja_Margem">Margem: ${p.margem_pct}%</span>` : ""}
            </div>
            ${btnHtml}
          </div>
        </article>`;
      })
      .join("");
  }

  function renderPaginacao() {
    if (!el.paginacao) return;
    if (totalPaginas <= 1) {
      el.paginacao.hidden = true;
      return;
    }
    el.paginacao.hidden = false;
    let html = "";
    if (paginaAtual > 1) {
      html += `<button type="button" class="Loja_PagBtn" data-pag="${paginaAtual - 1}">‹</button>`;
    }
    for (let i = 1; i <= totalPaginas; i++) {
      if (totalPaginas > 7 && Math.abs(i - paginaAtual) > 2 && i !== 1 && i !== totalPaginas) {
        if (i === 2 || i === totalPaginas - 1) html += '<span style="padding:6px">…</span>';
        continue;
      }
      html += `<button type="button" class="Loja_PagBtn ${i === paginaAtual ? "is-active" : ""}" data-pag="${i}">${i}</button>`;
    }
    if (paginaAtual < totalPaginas) {
      html += `<button type="button" class="Loja_PagBtn" data-pag="${paginaAtual + 1}">›</button>`;
    }
    el.paginacao.innerHTML = html;
  }

  async function carregar() {
    if (!idFornecedor) return;
    el.grid.innerHTML = '<p class="Loja_Vazio">Carregando produtos…</p>';
    const busca = (el.busca?.value || "").trim();
    let url = `/fornecedores/${idFornecedor}/loja/dados?pagina=${paginaAtual}&porPagina=24`;
    if (busca) url += "&busca=" + encodeURIComponent(busca);
    if (idArmazemFornecedor) url += "&id_armazem_fornecedor=" + encodeURIComponent(String(idArmazemFornecedor));

    const r = await fetch(url, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      el.grid.innerHTML = "";
      if (el.vazio) {
        el.vazio.hidden = false;
        el.vazio.textContent = j.message || "Erro ao carregar.";
      }
      return;
    }

    const forn = j.fornecedor || {};
    statusVinculo = forn.status_vinculo || "nenhum";
    if (el.titulo) el.titulo.textContent = forn.nome || "Fornecedor";
    if (el.subtitulo) {
      const loc = [forn.cidade, forn.uf].filter(Boolean).join(" / ");
      el.subtitulo.textContent = loc || "";
    }
    aplicarLogoHero(forn);
    renderSegmentos(forn.segmentos || []);
    statusBadge(statusVinculo);

    totalPaginas = j.total_paginas || 1;
    renderProdutos(j.produtos || []);
    renderPaginacao();
  }

  async function integrarProduto(idProduto) {
    const r = await fetch("/fornecedores/loja/ativar-produto", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        id_produto: idProduto,
        id_fornecedor: idFornecedor,
        id_armazem_fornecedor: idArmazemFornecedor || null,
      }),
    });
    const j = await r.json();
    if (window.Util?.alertar) Util.alertar(j.message || (j.success ? "OK" : "Erro"), j.success ? "success" : "error");
    else if (window.Swal) Swal.fire(j.success ? "Sucesso" : "Erro", j.message, j.success ? "success" : "error");
    if (j.success) carregar();
  }

  async function solicitarVinculo() {
    if (!window.VinculoRequisitos?.solicitarComRequisitos || !idFornecedor) return;
    try {
      const ok = await VinculoRequisitos.solicitarComRequisitos(idFornecedor, el.titulo?.textContent, {
        id_armazem_fornecedor: idArmazemFornecedor || null,
      });
      if (ok) carregar();
    } catch (e) {
      if (window.Swal) Swal.fire("Erro", e.message, "error");
      else alert(e.message);
    }
  }

  async function cancelarSolicitacaoVinculo() {
    if (!idFornecedor) return;
    const nome = el.titulo?.textContent || "fornecedor";
    const ok = window.Swal
      ? (
          await Swal.fire({
            title: "Cancelar solicitação?",
            html: `<p style="text-align:left;margin:0;line-height:1.45">Retirar o pedido de vínculo com <strong>${esc(nome)}</strong>?</p>`,
            icon: "question",
            showCancelButton: true,
            confirmButtonText: "Cancelar solicitação",
            cancelButtonText: "Manter",
            confirmButtonColor: "#b91c1c",
          })
        ).isConfirmed
      : confirm("Cancelar solicitação de vínculo?");
    if (!ok) return;
    try {
      const r = await fetch("/fornecedores/vinculo-acao", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_fornecedor: idFornecedor,
          id_armazem_fornecedor: idArmazemFornecedor || null,
          acao: "cancelar",
        }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao cancelar.");
      if (window.Swal) await Swal.fire("OK", j.message, "success");
      else alert(j.message);
      carregar();
    } catch (e) {
      if (window.Swal) Swal.fire("Erro", e.message, "error");
      else alert(e.message);
    }
  }

  el.grid.addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-acao]");
    if (!btn) return;
    if (btn.getAttribute("data-acao") === "integrar") {
      integrarProduto(Number(btn.getAttribute("data-prod")));
    }
    if (btn.getAttribute("data-acao") === "vinculo") {
      solicitarVinculo();
    }
  });

  el.paginacao?.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-pag]");
    if (!btn) return;
    paginaAtual = Number(btn.getAttribute("data-pag")) || 1;
    carregar();
  });

  el.btnBuscar?.addEventListener("click", () => {
    paginaAtual = 1;
    carregar();
  });
  el.busca?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      paginaAtual = 1;
      carregar();
    }
  });

  el.btnVinculo?.addEventListener("click", () => solicitarVinculo());
  el.btnCancelarVinculo?.addEventListener("click", () => cancelarSolicitacaoVinculo());

  window.addEventListener("message", (ev) => {
    if (ev.data?.grupo === "vinculoSolicitado") carregar();
  });

  function iniciar(id) {
    idFornecedor = id ? Number(id) : null;
    const qs = new URLSearchParams(window.location.search);
    const azf = Number(qs.get("azf") || qs.get("id_armazem_fornecedor") || 0);
    idArmazemFornecedor = azf || null;
    if (el.id) el.id.value = idFornecedor ? String(idFornecedor) : "";
    if (!idFornecedor) {
      idFornecedor = Number(qs.get("id")) || null;
    }
    if (idFornecedor) carregar();
    else if (el.vazio) {
      el.vazio.hidden = false;
      el.vazio.textContent = "Fornecedor não informado.";
    }
  }

  if (window.GlobalUtils?.receberDadosApoio) {
    GlobalUtils.receberDadosApoio((id) => iniciar(id));
  } else {
    iniciar(null);
  }
})();
