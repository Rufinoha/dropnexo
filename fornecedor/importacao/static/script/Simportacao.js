(() => {
  "use strict";

  if (window.__DN_IMPORT_MODAL__) return;
  window.__DN_IMPORT_MODAL__ = true;

  const BASE = "/fornecedor/importacao";
  const qs = (s, r = document) => r.querySelector(s);
  const qsa = (s, r = document) => Array.from(r.querySelectorAll(s));

  const CARD_SCOPES = {
    arquivo: {
      total: "#impResTotal",
      inseridas: "#impResInseridas",
      erros: "#impResErros",
      lote: "#impResLote",
      obs: "#impResObs",
      emptyObs: "Nenhuma importação registrada ainda.",
    },
    bling: {
      total: "#impBlingResTotal",
      inseridas: "#impBlingResInseridas",
      erros: "#impBlingResErros",
      lote: "#impBlingResLote",
      obs: "#impBlingResObs",
      emptyObs: "Nenhuma importação via Bling ainda.",
    },
  };

  let cfg = { bling_conectado: false, layouts: [], pode_editar: false, bling_config: null };
  let loteSelecionado = { arquivo: null, bling: null };
  let tabAtiva = "nova";
  let blingCategorias = [];
  const blingCatsSel = new Set();
  let catPickerAberto = false;

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function isoHoje() {
    return new Date().toISOString().slice(0, 10);
  }

  function isoMesesAtras(n) {
    const d = new Date();
    d.setMonth(d.getMonth() - Number(n || 3));
    return d.toISOString().slice(0, 10);
  }

  function setModalOpen(open) {
    const modal = qs("#impModal");
    if (!modal) return;
    modal.setAttribute("aria-hidden", open ? "false" : "true");
    document.body.style.overflow = open ? "hidden" : "";
  }

  function renderTabsBling(conectado) {
    const tabBling = qs("#impTabBling");
    if (tabBling) tabBling.hidden = !conectado;
  }

  function pickTab(tab) {
    tabAtiva = tab;
    qsa(".imp-tab").forEach((b) => b.classList.toggle("ativa", b.dataset.tab === tab));
    qs("#impPaneBling")?.classList.toggle("ativa", tab === "bling");
    qs("#impPaneNova")?.classList.toggle("ativa", tab === "nova");
    qs("#impPaneManutencao")?.classList.toggle("ativa", tab === "manutencao");
    if (tab === "manutencao") carregarLotes();
  }

  function setCards(scope, d = {}) {
    const map = CARD_SCOPES[scope];
    if (!map) return;

    const total = Number(d.total ?? 0);
    const ins = Number(d.inseridas ?? 0);
    const rej = Number(d.erros ?? 0);
    const numero = d.numero != null ? String(d.numero) : "—";

    qs(map.total).textContent = String(total);
    qs(map.inseridas).textContent = String(ins);
    qs(map.erros).textContent = String(rej);
    qs(map.lote).textContent = numero;

    const obs = [];
    if (d.origem_rotulo) obs.push(d.origem_rotulo);
    if (d.nome_arquivo) obs.push(d.nome_arquivo);
    if (d.importado_em) {
      try {
        obs.push(new Date(d.importado_em).toLocaleString("pt-BR"));
      } catch {
        /* ignore */
      }
    }
    qs(map.obs).textContent = obs.length
      ? `Última importação: ${obs.join(" · ")}`
      : map.emptyObs;

    loteSelecionado[scope] = d.lote != null ? Number(d.lote) : null;

    qsa(`.imp-card-click[data-scope="${scope}"]`).forEach((card) => {
      card.style.opacity = rej > 0 && loteSelecionado[scope] ? "1" : "0.85";
      if (card.dataset.card === "erros") {
        card.title = rej > 0 ? "Duplo clique para abrir manutenção de erros" : "Sem erros na última importação";
      }
    });
  }

  async function carregarCards(scope, idLote) {
    const params = new URLSearchParams();
    if (idLote) params.set("id_lote", String(idLote));
    if (scope === "bling") params.set("origem", "integracao");
    const r = await fetch(`${BASE}/cards?${params}`, { credentials: "include" });
    const j = await r.json();
    if (!r.ok || !j.success) {
      setCards(scope, {});
      return;
    }
    setCards(scope, j.dados || {});
  }

  function atualizarStatusBling() {
    const status = qs("#impBlingStatus");
    const titulo = qs("#impBlingStatusTitulo");
    const sub = qs("#impBlingStatusSub");
    if (!status || !cfg.bling_conectado) return;

    const bc = cfg.bling_config || {};
    const syncAtivo = bc.estoque_baixa_pedido || bc.estoque_importar_bling;

    status.classList.toggle("inativo", !syncAtivo);
    titulo.textContent = "Conectado ao Bling";
    if (syncAtivo) {
      const partes = [];
      if (bc.estoque_baixa_pedido) partes.push("baixa de estoque em pedidos");
      if (bc.estoque_importar_bling) partes.push(`consulta a cada ${bc.estoque_polling_minutos || 30} min`);
      sub.textContent = `Sincronização ativa — ${partes.join(" · ")}`;
    } else {
      sub.textContent = "Integração conectada — configure a sincronização de estoque abaixo";
    }
  }

  function preencherFormEstoque() {
    const bc = cfg.bling_config || {};
    qs("#impEstoqueBaixaPedido").checked = !!bc.estoque_baixa_pedido;
    qs("#impEstoqueImportarBling").checked = !!bc.estoque_importar_bling;
    qs("#impEstoquePolling").value = String(bc.estoque_polling_minutos || 30);
    toggleEstoquePolling();

    const ult = bc.ultima_sync_estoque;
    qs("#impEstoqueUltimaSync").textContent = ult
      ? `Última sync de estoque: ${new Date(ult).toLocaleString("pt-BR")}`
      : "Nenhuma sincronização de estoque registrada ainda.";
    atualizarStatusBling();
    atualizarAnimacaoEstoque();
  }

  function atualizarAnimacaoEstoque() {
    const visual = qs("#impSyncVisual");
    if (!visual) return;

    const baixa = qs("#impEstoqueBaixaPedido")?.checked === true;
    const importar = qs("#impEstoqueImportarBling")?.checked === true;
    const ativo = baixa || importar;

    visual.classList.toggle("inativo", !ativo);
    visual.classList.toggle("sync-out", baixa);
    visual.classList.toggle("sync-in", importar);
    visual.classList.toggle("sync-both", baixa && importar);
    visual.setAttribute("aria-hidden", ativo ? "false" : "true");
  }

  function toggleEstoquePolling() {
    const on = qs("#impEstoqueImportarBling")?.checked;
    qs("#impEstoquePollingWrap").hidden = !on;
  }

  async function carregarDadosIniciais() {
    const r = await fetch(`${BASE}/dados`, { credentials: "include" });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar importação.");

    cfg = j;
    renderTabsBling(!!j.bling_conectado);

    const sel = qs("#impLayout");
    if (sel) {
      sel.innerHTML = (j.layouts || [])
        .map((l) => `<option value="${l.id}">${esc(l.nome)}${l.padrao ? " (padrão)" : ""}</option>`)
        .join("");
    }

    if (j.bling_conectado) {
      await carregarCategoriasBling();
      preencherFormEstoque();
      await carregarCards("bling", j.ultimo_lote_bling?.id || null);
    }

    await carregarCards("arquivo", j.ultimo_lote?.id || null);
  }

  async function carregarCategoriasBling() {
    try {
      const r = await fetch("/api/integracoes/bling/categorias", { credentials: "include" });
      const j = await r.json();
      if (!j.success) return;
      blingCategorias = [];
      function walk(nodes, depth) {
        (nodes || j.categorias || []).forEach((n) => {
          blingCategorias.push({
            id: String(n.id),
            nome: n.label || n.nome || String(n.id),
            depth,
          });
          if (n.filhos?.length) walk(n.filhos, depth + 1);
        });
      }
      walk(j.categorias || j.dados || [], 0);
      renderCatList();
      renderCatChips();
      atualizarCatTrigger();
    } catch {
      /* ignore */
    }
  }

  function renderCatList(filtro = "") {
    const list = qs("#impCatList");
    if (!list) return;
    const termo = filtro.trim().toLowerCase();
    const itens = blingCategorias.filter((c) => !termo || c.nome.toLowerCase().includes(termo));
    if (!itens.length) {
      list.innerHTML = `<div class="imp-cat-empty">${termo ? "Nenhuma categoria encontrada." : "Sem categorias no Bling."}</div>`;
      return;
    }
    list.innerHTML = itens
      .map((c) => {
        const pad = c.depth > 0 ? `padding-left:${8 + c.depth * 14}px` : "";
        const checked = blingCatsSel.has(c.id) ? "checked" : "";
        const ativa = blingCatsSel.has(c.id) ? " ativa" : "";
        return `<label class="imp-cat-item${ativa}" style="${pad}" data-id="${esc(c.id)}">
          <input type="checkbox" value="${esc(c.id)}" ${checked} />
          <span>${esc(c.nome)}</span>
        </label>`;
      })
      .join("");
  }

  function renderCatChips() {
    const wrap = qs("#impCatChips");
    if (!wrap) return;
    if (!blingCatsSel.size) {
      wrap.innerHTML = "";
      return;
    }
    const map = new Map(blingCategorias.map((c) => [c.id, c.nome]));
    wrap.innerHTML = Array.from(blingCatsSel)
      .map(
        (id) => `<span class="imp-cat-chip">${esc(map.get(id) || id)}
          <button type="button" data-rm-cat="${esc(id)}" aria-label="Remover">×</button></span>`
      )
      .join("");
  }

  function atualizarCatTrigger() {
    const txt = qs("#impCatTriggerText");
    if (!txt) return;
    const n = blingCatsSel.size;
    txt.textContent = n
      ? `${n} categoria${n > 1 ? "s" : ""} selecionada${n > 1 ? "s" : ""}`
      : "Selecione as categorias…";
  }

  function toggleCat(id, on) {
    if (on) blingCatsSel.add(String(id));
    else blingCatsSel.delete(String(id));
    renderCatList(qs("#impCatSearch")?.value || "");
    renderCatChips();
    atualizarCatTrigger();
  }

  function fecharCatPicker() {
    catPickerAberto = false;
    qs("#impCatPanel")?.setAttribute("hidden", "");
    qs("#impCatTrigger")?.setAttribute("aria-expanded", "false");
  }

  function abrirCatPicker() {
    catPickerAberto = true;
    qs("#impCatPanel")?.removeAttribute("hidden");
    qs("#impCatTrigger")?.setAttribute("aria-expanded", "true");
    qs("#impCatSearch")?.focus();
  }

  function getSelectedCatIds() {
    return Array.from(blingCatsSel);
  }

  function bindCatPicker() {
    qs("#impCatTrigger")?.addEventListener("click", () => {
      if (catPickerAberto) fecharCatPicker();
      else abrirCatPicker();
    });
    qs("#impCatSearch")?.addEventListener("input", (ev) => {
      renderCatList(ev.target.value || "");
    });
    qs("#impCatList")?.addEventListener("change", (ev) => {
      const cb = ev.target.closest('input[type="checkbox"]');
      if (!cb) return;
      toggleCat(cb.value, cb.checked);
    });
    qs("#impCatChips")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-rm-cat]");
      if (btn) toggleCat(btn.dataset.rmCat, false);
    });
    document.addEventListener("click", (ev) => {
      if (!catPickerAberto) return;
      if (ev.target.closest("#impCatPicker")) return;
      fecharCatPicker();
    });
  }

  function toggleBlingCats() {
    const porCat = qs('input[name="imp_bling_modo"]:checked')?.value === "categorias";
    qs("#impBlingCatsWrap").hidden = !porCat;
    if (!porCat) fecharCatPicker();
  }

  async function importarArquivo() {
    const file = qs("#impArquivo")?.files?.[0];
    if (!file) {
      await Swal.fire({ icon: "warning", title: "Atenção", text: "Selecione um arquivo CSV." });
      return;
    }
    const fd = new FormData();
    fd.append("arquivo", file);

    Swal.fire({ title: "Importando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
      const r = await fetch(`${BASE}/arquivo`, { method: "POST", body: fd, credentials: "include" });
      const j = await r.json();
      Swal.close();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha na importação.");
      await carregarCards("arquivo", j.id_lote);
      pickTab("nova");
      await Swal.fire({
        icon: (j.rejeitadas || 0) > 0 ? "warning" : "success",
        title: "Concluído",
        text: j.message,
        confirmButtonColor: "#021F81",
      });
      window.dispatchEvent(new CustomEvent("catalogo:importacao-concluida"));
    } catch (e) {
      Swal.close();
      await Swal.fire("Erro", e.message, "error");
    }
  }

  async function importarBling() {
    const modo = qs('input[name="imp_bling_modo"]:checked')?.value || "todos";
    const body = { contexto: "fornecedor" };
    if (modo === "categorias") {
      const ids = getSelectedCatIds();
      if (!ids.length) {
        await Swal.fire({ icon: "warning", title: "Atenção", text: "Selecione ao menos uma categoria." });
        return;
      }
      body.ids_categorias_bling = ids;
      body.incluir_subcategorias = qs("#impBlingSub")?.checked !== false;
    }

    Swal.fire({ title: "Importando do Bling…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
      const r = await fetch(`${BASE}/integracao/bling`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        credentials: "include",
      });
      const j = await r.json();
      Swal.close();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha na importação.");
      await carregarCards("bling", j.lote?.id || j.dados?.id_importacao_lote);
      pickTab("bling");
      const st = j.dados?.status;
      await Swal.fire({
        icon: st === "ok" ? "success" : st === "aviso" ? "warning" : "error",
        title: "Concluído",
        text: j.message,
        confirmButtonColor: "#021F81",
      });
      window.dispatchEvent(new CustomEvent("catalogo:importacao-concluida"));
    } catch (e) {
      Swal.close();
      await Swal.fire("Erro", e.message, "error");
    }
  }

  async function salvarEstoqueBling() {
    const body = {
      estoque_baixa_pedido: qs("#impEstoqueBaixaPedido")?.checked === true,
      estoque_importar_bling: qs("#impEstoqueImportarBling")?.checked === true,
      estoque_polling_minutos: Number(qs("#impEstoquePolling")?.value || 30),
    };

    Swal.fire({ title: "Salvando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
      const r = await fetch(`${BASE}/bling/estoque`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
        credentials: "include",
      });
      const j = await r.json();
      Swal.close();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao salvar.");
      cfg.bling_config = j.bling_config || body;
      preencherFormEstoque();
      await Swal.fire({
        icon: "success",
        title: "Salvo",
        text: j.message,
        confirmButtonColor: "#021F81",
      });
    } catch (e) {
      Swal.close();
      await Swal.fire("Erro", e.message, "error");
    }
  }

  function abrirErrosManutencao(scope) {
    const idLote = loteSelecionado[scope];
    const errosEl = scope === "bling" ? "#impBlingResErros" : "#impResErros";
    const erros = Number(qs(errosEl)?.textContent || 0);

    if (!idLote) {
      Swal.fire({ icon: "warning", title: "Atenção", text: "Nenhum lote selecionado." });
      return;
    }
    if (erros <= 0) {
      Swal.fire({ icon: "info", title: "Sem erros", text: "A última importação não possui erros." });
      return;
    }
    if (!window.GlobalUtils?.abrirJanelaApoioModal) {
      Swal.fire("Erro", "Modal institucional não disponível.", "error");
      return;
    }
    GlobalUtils.abrirJanelaApoioModal({
      rota: `${BASE}/erro`,
      titulo: "Erros da importação",
      largura: 1000,
      altura: "auto",
      nivel: 2,
      id: idLote,
    });
  }

  async function carregarLotes() {
    const de = qs("#impFiltroDe")?.value || isoMesesAtras(3);
    const ate = qs("#impFiltroAte")?.value || isoHoje();
    const params = new URLSearchParams({ de, ate });
    const r = await fetch(`${BASE}/lotes?${params}`, { credentials: "include" });
    const j = await r.json();
    const tbody = qs("#impTblLotes");
    if (!tbody) return;
    if (!j.success || !j.dados?.length) {
      tbody.innerHTML = `<tr><td colspan="7">Nenhuma importação no período.</td></tr>`;
      return;
    }
    tbody.innerHTML = j.dados
      .map((l) => {
        const data = l.importado_em ? new Date(l.importado_em).toLocaleString("pt-BR") : "—";
        return `<tr>
          <td><button type="button" class="imp-btn-link" data-ver="${l.id}" data-origem="${esc(l.origem || "")}">${esc(l.numero || l.id)}</button></td>
          <td>${esc(l.origem_rotulo || l.origem)}</td>
          <td>${esc(l.nome_arquivo || "—")}</td>
          <td>${data}</td>
          <td style="text-align:center">${l.total_importadas ?? 0}</td>
          <td style="text-align:center">${l.total_rejeitadas ?? 0}</td>
          <td>
            ${cfg.pode_editar ? `<button type="button" class="imp-btn-link imp-btn-danger" data-del="${l.id}">Excluir</button>` : "—"}
          </td>
        </tr>`;
      })
      .join("");
  }

  async function verLote(id, origem) {
    const scope = origem === "integracao" ? "bling" : "arquivo";
    await carregarCards(scope, id);
    pickTab(scope === "bling" && cfg.bling_conectado ? "bling" : "nova");
  }

  async function excluirLote(id) {
    const ok = await Swal.fire({
      icon: "warning",
      title: "Excluir importação?",
      text: "Produtos inseridos neste lote serão removidos (exceto os já editados manualmente).",
      showCancelButton: true,
      confirmButtonColor: "#b42318",
      confirmButtonText: "Excluir",
      cancelButtonText: "Cancelar",
    });
    if (!ok.isConfirmed) return;
    const r = await fetch(`${BASE}/lote/${id}`, { method: "DELETE", credentials: "include" });
    const j = await r.json();
    if (!r.ok || !j.success) {
      await Swal.fire("Erro", j.message || "Não foi possível excluir.", "error");
      return;
    }
    await Swal.fire({ icon: "success", title: "Excluído", text: j.message });
    await carregarLotes();
    await carregarCards("arquivo", null);
    if (cfg.bling_conectado) await carregarCards("bling", null);
    window.dispatchEvent(new CustomEvent("catalogo:importacao-concluida"));
  }

  function bindCardsInteracao() {
    qsa(".imp-card-click").forEach((card) => {
      card.addEventListener("dblclick", () => {
        const scope = card.dataset.scope || "arquivo";
        if (card.dataset.card === "erros") abrirErrosManutencao(scope);
        else if (card.dataset.card === "lote" && loteSelecionado[scope]) {
          const errosEl = scope === "bling" ? "#impBlingResErros" : "#impResErros";
          const erros = Number(qs(errosEl)?.textContent || 0);
          if (erros > 0) abrirErrosManutencao(scope);
        }
      });
    });
  }

  function bind() {
    qsa(".imp-tab").forEach((b) => b.addEventListener("click", () => pickTab(b.dataset.tab)));
    qsa("[data-acao='fechar']").forEach((b) => b.addEventListener("click", () => setModalOpen(false)));
    qs("#impBtnArquivo")?.addEventListener("click", importarArquivo);
    qs("#impBtnBling")?.addEventListener("click", importarBling);
    qs("#impBtnSalvarEstoque")?.addEventListener("click", salvarEstoqueBling);
    qs("#impBtnFiltrar")?.addEventListener("click", carregarLotes);
    qs("#impBtnLimpar")?.addEventListener("click", () => {
      qs("#impFiltroDe").value = "";
      qs("#impFiltroAte").value = "";
      carregarLotes();
    });
    qsa('input[name="imp_bling_modo"]').forEach((r) => r.addEventListener("change", toggleBlingCats));
    qs("#impEstoqueImportarBling")?.addEventListener("change", () => {
      toggleEstoquePolling();
      atualizarStatusBling();
      atualizarAnimacaoEstoque();
    });
    qs("#impEstoqueBaixaPedido")?.addEventListener("change", () => {
      atualizarStatusBling();
      atualizarAnimacaoEstoque();
    });
    bindCatPicker();
    qs("#impTblLotes")?.addEventListener("click", (ev) => {
      const ver = ev.target.closest("[data-ver]");
      const del = ev.target.closest("[data-del]");
      if (ver) verLote(Number(ver.dataset.ver), ver.dataset.origem || "");
      if (del) excluirLote(Number(del.dataset.del));
    });
    bindCardsInteracao();
  }

  async function abrir() {
    if (!qs("#impModal")) return;
    setModalOpen(true);
    try {
      await carregarDadosIniciais();
      pickTab(cfg.bling_conectado ? "bling" : "nova");
    } catch (e) {
      pickTab("nova");
      await Swal.fire("Erro", e.message, "error");
    }
  }

  window.CatImportacao = { abrir, fechar: () => setModalOpen(false) };

  document.addEventListener("DOMContentLoaded", bind);
})();
