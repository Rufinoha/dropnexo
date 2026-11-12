(function () {
  let pagina = 1, totalPaginas = 1, menuAberto = null;
  const notas = new Map();
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const dataBR = (v) => v ? new Date(v).toLocaleDateString("pt-BR") : "—";
  const dataHora = (v) => v ? new Date(v).toLocaleString("pt-BR") : "—";
  const ICO_COPY = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';
  const ICO_CHECK = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M20 6 9 17l-5-5"/></svg>';
  const ICO_KEBAB = '<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="5" r="1.7" fill="currentColor"/><circle cx="12" cy="12" r="1.7" fill="currentColor"/><circle cx="12" cy="19" r="1.7" fill="currentColor"/></svg>';
  const ICO_OLHO = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/></svg>';
  const ICO_EDIT = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/></svg>';
  const ICO_PDF = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/></svg>';
  const ICO_X = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="9"/><path d="m15 9-6 6M9 9l6 6"/></svg>';

  function diaBrasilia(valor) {
    if (!valor) return null;
    const texto = String(valor);
    const temFuso = /[zZ]|[+-]\d{2}:?\d{2}$/.test(texto);
    const d = valor instanceof Date ? valor : new Date(temFuso ? texto : texto.replace(" ", "T") + "-03:00");
    if (Number.isNaN(d.getTime())) return null;
    const [y, m, day] = new Intl.DateTimeFormat("en-CA", {
      timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit", day: "2-digit"
    }).format(d).split("-").map(Number);
    return { y, m, day };
  }

  function bloqueioCancelamento(iso) {
    const emitida = diaBrasilia(iso);
    if (!emitida) {
      return "Esta NFS-e não tem data de autorização gravada. Sem ela não dá para conferir o prazo de cancelamento de Louveira.";
    }
    const limite = emitida.m === 12
      ? { y: emitida.y + 1, m: 1, day: 15 }
      : { y: emitida.y, m: emitida.m + 1, day: 15 };
    const hoje = diaBrasilia(new Date());
    const n = (d) => d.y * 10000 + d.m * 100 + d.day;
    if (n(hoje) <= n(limite)) return null;
    const br = (d) => `${String(d.day).padStart(2, "0")}/${String(d.m).padStart(2, "0")}/${d.y}`;
    return `Esta NFS-e foi emitida em ${br(emitida)}. Em Louveira, a Lei 3.023/2025 permite cancelar só até o dia 15 do mês seguinte — neste caso, até ${br(limite)}. Esse prazo já passou.`;
  }

  function emitida(status) {
    return status === "autorizada" || status === "cancelada";
  }
  function statusHtml(n) {
    const status = String(n?.status || "");
    const amb = String(n?.ambiente || "").toLowerCase();
    const marcaHomolog = amb === "homologacao"
      ? `<small class="nfse-amb-homolog">homologação</small>`
      : "";
    return `<span class="nfse-status ${esc(status)}">${esc(status)}</span>${marcaHomolog}`;
  }

  function fecharMenu() {
    if (!menuAberto) return;
    menuAberto.menu.remove();
    menuAberto.btn.classList.remove("is-on");
    menuAberto.btn.setAttribute("aria-expanded", "false");
    menuAberto = null;
  }

  function posicionarMenu(menu, btn) {
    const r = btn.getBoundingClientRect();
    const largura = menu.offsetWidth;
    const altura = menu.offsetHeight;
    let left = Math.min(r.right - largura, window.innerWidth - largura - 8);
    let top = r.bottom + 6;
    if (left < 8) left = 8;
    if (top + altura > window.innerHeight - 8) top = Math.max(8, r.top - altura - 6);
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
  }

  function itemMenu(acao, rotulo, icone, perigo) {
    const b = document.createElement("button");
    b.type = "button";
    b.setAttribute("role", "menuitem");
    b.dataset.acao = acao;
    if (perigo) b.className = "is-danger";
    b.innerHTML = icone;
    b.append(document.createTextNode(rotulo));
    return b;
  }

  function abrirMenu(btn, nota) {
    if (menuAberto?.btn === btn) {
      fecharMenu();
      return;
    }
    fecharMenu();
    const menu = document.createElement("div");
    menu.className = "nfse-menu";
    menu.setAttribute("role", "menu");
    const ver = emitida(nota.status);
    menu.append(
      itemMenu(ver ? "ver" : "editar", ver ? "Ver nota" : "Editar", ver ? ICO_OLHO : ICO_EDIT),
      itemMenu("danfse", "Gerar DANFSe", ICO_PDF)
    );
    const sep = document.createElement("div");
    sep.className = "nfse-menu-sep";
    menu.append(sep, itemMenu("cancelar", "Cancelar nota", ICO_X, true));
    document.body.appendChild(menu);
    posicionarMenu(menu, btn);
    btn.classList.add("is-on");
    btn.setAttribute("aria-expanded", "true");
    menuAberto = { menu, btn, id: nota.id };
    menu.addEventListener("click", (ev) => {
      const alvo = ev.target.closest("[data-acao]");
      if (!alvo) return;
      const acao = alvo.dataset.acao;
      const atual = notas.get(nota.id) || nota;
      fecharMenu();
      if (acao === "ver" || acao === "editar") abrir(atual.id, atual.status);
      else if (acao === "danfse") gerarDanfse(atual);
      else if (acao === "cancelar") cancelarNota(atual);
    });
  }

  async function copiarChave(btn) {
    const chave = btn.getAttribute("data-copiar-chave") || "";
    if (!chave) return;
    try {
      await navigator.clipboard.writeText(chave);
    } catch (e) {
      const ta = document.createElement("textarea");
      ta.value = chave;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.left = "-999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      ta.remove();
    }
    btn.classList.add("is-ok");
    btn.innerHTML = ICO_CHECK;
    btn.title = "Chave copiada";
    setTimeout(() => {
      btn.classList.remove("is-ok");
      btn.innerHTML = ICO_COPY;
      btn.title = "Copiar chave";
    }, 1200);
  }

  function aguardarGlobalUtils(ms = 8000) {
    if (window.GlobalUtils?.requestJSON) return Promise.resolve(true);
    return new Promise((resolve) => {
      const t0 = Date.now();
      const id = setInterval(() => {
        if (window.GlobalUtils?.requestJSON) {
          clearInterval(id);
          resolve(true);
        } else if (Date.now() - t0 > ms) {
          clearInterval(id);
          resolve(false);
        }
      }, 25);
    });
  }

  function mensagemLista(texto) {
    listaNotas.innerHTML = `<tr><td colspan="8" class="Fin_Empty">${esc(texto)}</td></tr>`;
  }

  async function carregar() {
    fecharMenu();
    listaNotas.innerHTML = '<tr><td colspan="8" class="Fin_Empty">Carregando…</td></tr>';
    if (!(await aguardarGlobalUtils())) {
      mensagemLista("Não foi possível carregar os utilitários da página. Atualize (F5).");
      return;
    }
    const qs = new URLSearchParams({pagina, status: filtroStatus.value, termo: filtroTermo.value});
    let r;
    try {
      r = await GlobalUtils.requestJSON({url: `/nfse/api/notas?${qs}`});
    } catch (e) {
      mensagemLista(e?.message || "Falha ao consultar as notas.");
      return;
    }
    if (!r) return;
    if (!r.ok) {
      const msg = r.json?.message || r.json?.detalhe || "Não foi possível listar as notas.";
      mensagemLista(msg);
      return;
    }
    const j = r.json || {};
    const dados = Array.isArray(j.dados) ? j.dados : [];
    totalPaginas = Number(j.total_paginas) || 1;
    pagina = Number(j.pagina) || 1;
    notas.clear();
    listaNotas.replaceChildren();
    if (!dados.length) {
      mensagemLista("Nenhuma nota encontrada.");
    } else {
      dados.forEach(n => {
        const id = Number(n.id);
        notas.set(id, n);
        const tr = document.createElement("tr");
        const chave = String(n.chave_nfse || "").trim();
        const copiar = chave
          ? `<span class="nfse-chave-linha"><small>${esc(chave)}</small><button type="button" class="nfse-copiar" data-copiar-chave="${esc(chave)}" title="Copiar chave" aria-label="Copiar chave de acesso">${ICO_COPY}</button></span>`
          : "";
        tr.innerHTML = `<td>${esc(n.numero_dps || "—")}/${esc(n.serie_dps || "—")}</td>
      <td class="nfse-quando">${dataBR(n.dt_criacao)}</td>
      <td class="nfse-quando">${dataHora(n.dt_autorizacao)}</td>
      <td class="nfse-chave"><strong>${esc(n.numero_nfse || "—")}</strong>${copiar}</td>
      <td title="${esc(n.cliente)}">${esc(n.cliente || "—")}</td>
      <td class="nfse-valor">R$ ${Number(n.valor_servico || 0).toLocaleString("pt-BR",{minimumFractionDigits:2})}</td>
      <td class="nfse-status-cel">${statusHtml(n)}</td>`;
        const td = document.createElement("td");
        td.className = "Cl_TableActions";
        const btn = document.createElement("button");
        btn.type = "button";
        btn.className = "nfse-kebab";
        btn.setAttribute("aria-label", "Ações da nota");
        btn.setAttribute("aria-haspopup", "menu");
        btn.setAttribute("aria-expanded", "false");
        btn.dataset.menuNota = String(id);
        btn.innerHTML = ICO_KEBAB;
        td.appendChild(btn);
        tr.appendChild(td);
        listaNotas.appendChild(tr);
      });
    }
    paginaAtual.textContent = pagina; document.getElementById("totalPaginas").textContent = totalPaginas;
    pagAnterior.disabled = pagina <= 1; pagProxima.disabled = pagina >= totalPaginas;
  }

  function abrir(id, status) {
    const notaId = Number(id);
    const existe = Number.isFinite(notaId) && notaId > 0;
    const titulo = !existe ? "Nova DPS"
      : status === "autorizada" ? "NFS-e autorizada"
      : status === "cancelada" ? "NFS-e cancelada"
      : "Editar rascunho DPS";
    GlobalUtils.abrirJanelaApoioModal({
      rota: existe ? `/nfse/notas/editar?id=${notaId}` : "/nfse/notas/incluir",
      titulo,
      largura: 1220,
      altura: 760,
      id: existe ? notaId : null
    });
  }

  async function gerarDanfse(nota) {
    if (!emitida(nota.status)) {
      return GlobalUtils.swalFire(
        "DANFSe indisponível",
        "A DANFSe só é gerada depois que a NFS-e é autorizada.",
        "info"
      );
    }
    const resposta = await fetch(`/nfse/api/notas/${nota.id}/danfse`);
    if (!resposta.ok) {
      let mensagem = "Não foi possível gerar a DANFSe.";
      try { mensagem = (await resposta.json()).message || mensagem; } catch (e) {}
      return GlobalUtils.swalFire("DANFSe", mensagem, "error");
    }
    const blob = await resposta.blob();
    window.open(URL.createObjectURL(blob), "_blank");
  }

  async function cancelarNota(nota) {
    if (nota.status === "cancelada") {
      return GlobalUtils.swalFire("Nota já cancelada", "Esta NFS-e já está cancelada.", "info");
    }
    if (nota.status !== "autorizada") {
      return GlobalUtils.swalFire(
        "Nota ainda não emitida",
        "Só dá para cancelar uma NFS-e depois que ela foi autorizada.",
        "info"
      );
    }
    const bloqueio = bloqueioCancelamento(nota.dt_autorizacao);
    if (bloqueio) return GlobalUtils.swalFire("Prazo de cancelamento encerrado", bloqueio, "warning");
    const escolha = await GlobalUtils.swalFire({
      title: "Cancelar NFS-e?",
      input: "select",
      inputOptions: {"1": "Erro na emissão", "2": "Serviço não prestado", "9": "Outros"},
      inputValue: "1",
      showCancelButton: true,
      confirmButtonText: "Continuar",
      cancelButtonText: "Voltar"
    });
    if (!escolha?.isConfirmed) return;
    const texto = await GlobalUtils.swalFire({
      title: "Justificativa",
      input: "textarea",
      inputPlaceholder: "Descreva o motivo, com pelo menos 15 caracteres.",
      showCancelButton: true,
      confirmButtonText: "Cancelar nota",
      cancelButtonText: "Voltar"
    });
    if (!texto?.isConfirmed) return;
    const motivo = String(texto.value || "").trim();
    if (motivo.length < 15) {
      return GlobalUtils.swalFire("Justificativa curta", "Descreva o motivo com pelo menos 15 caracteres.", "warning");
    }
    const r = await GlobalUtils.requestJSON({
      url: `/nfse/api/notas/${nota.id}/cancelar`,
      method: "POST",
      payload: {codigo: escolha.value, motivo}
    });
    if (!r?.ok) {
      return GlobalUtils.swalFire("Cancelamento não concluído", r?.json?.message || "A Sefin não cancelou a nota.", "error");
    }
    await GlobalUtils.swalFire("NFS-e cancelada", r.json?.message || "Cancelada.", "success");
    carregar();
  }

  listaNotas.addEventListener("click", (ev) => {
    const copiar = ev.target.closest("[data-copiar-chave]");
    if (copiar) {
      ev.preventDefault();
      copiarChave(copiar);
      return;
    }
    const menuBtn = ev.target.closest("[data-menu-nota]");
    if (!menuBtn) return;
    ev.preventDefault();
    ev.stopPropagation();
    const nota = notas.get(Number(menuBtn.dataset.menuNota));
    if (nota) abrirMenu(menuBtn, nota);
  });
  document.addEventListener("click", (ev) => {
    if (!menuAberto) return;
    if (menuAberto.menu.contains(ev.target) || menuAberto.btn.contains(ev.target)) return;
    fecharMenu();
  });
  document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") fecharMenu(); });
  window.addEventListener("resize", fecharMenu);
  window.addEventListener("scroll", fecharMenu, true);
  document.querySelector(".nfse-table")?.addEventListener("scroll", fecharMenu, true);

  btnNovaNota.onclick = () => abrir(null);
  btnImportarNotas.onclick = async () => {
    btnImportarNotas.disabled = true;
    const swal = GlobalUtils.obterSwal();
    GlobalUtils.swalFire({
      title: "Importando notas",
      html: "Consultando as NFS-e já emitidas na Sefin Nacional.<br>A busca pode levar um minuto. Esta janela fica aberta até terminar.",
      allowOutsideClick: false,
      allowEscapeKey: false,
      showConfirmButton: false,
      didOpen: () => { if (swal?.showLoading) swal.showLoading(); }
    });
    const r = await GlobalUtils.requestJSON({
      url: "/nfse/api/notas/importar",
      method: "POST",
      payload: {},
      timeoutMs: 180000
    });
    if (swal?.close) swal.close();
    btnImportarNotas.disabled = false;
    if (!r) return;
    if (!r.ok) {
      if (r.status === 403) return;
      return GlobalUtils.swalFire("Importação não concluída", r.json?.message || "A Sefin não devolveu as notas.", "error");
    }
    await GlobalUtils.swalFire("Importação concluída", r.json?.message || "Busca encerrada.", "success");
    carregar();
  };
  btnFiltrar.onclick = () => { pagina = 1; carregar(); };
  pagAnterior.onclick = () => { if (pagina > 1) { pagina--; carregar(); } };
  pagProxima.onclick = () => { if (pagina < totalPaginas) { pagina++; carregar(); } };
  window.addEventListener("message", e => { if(e.data?.grupo === "nfse:salvo") carregar(); });
  carregar();
})();
