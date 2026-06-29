(() => {
  "use strict";

  if (window.__DN_IMPORT_MODAL__) return;
  window.__DN_IMPORT_MODAL__ = true;

  const BASE = "/fornecedor/importacao";
  const MODULO = "catalogo_produto";
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

  async function lerJsonResposta(r) {
    const texto = await r.text();
    try {
      return JSON.parse(texto);
    } catch {
      const snippet = texto.replace(/\s+/g, " ").trim().slice(0, 120);
      throw new Error(
        r.status >= 500
          ? `Erro no servidor (${r.status}). Tente de novo ou contate o suporte.`
          : `Resposta inválida do servidor (${r.status}). ${snippet || "Sem detalhes."}`
      );
    }
  }

  function icoHtml(nome) {
    if (window.Util?.gerarIconeTech) return Util.gerarIconeTech(nome);
    return "";
  }

  function aplicarIcones(root = document) {
    if (!window.Util?.gerarIconeTech) return;
    qsa(".Cl_BtnAcao[data-ico]", root).forEach((btn) => {
      if (btn.dataset.icoLoaded) return;
      Util.gerarIconeTech({ dest: btn, nome: btn.dataset.ico });
      btn.dataset.icoLoaded = "1";
    });
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
    qs("#impPaneLayout")?.classList.toggle("ativa", tab === "layout");
    if (tab === "manutencao") carregarLotes();
    if (tab === "layout") carregarLayoutsTabela();
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

  function fmtSync(iso, rotulo) {
    if (!iso) return `${rotulo}: nunca`;
    try {
      return `${rotulo}: ${new Date(iso).toLocaleString("pt-BR")}`;
    } catch {
      return `${rotulo}: —`;
    }
  }

  function atualizarStatusBling() {
    const status = qs("#impBlingStatus");
    const titulo = qs("#impBlingStatusTitulo");
    const sub = qs("#impBlingStatusSub");
    if (!status || !cfg.bling_conectado) return;

    const bc = cfg.bling_config || {};
    const depsOk = Number(bc.depositos_vinculados || 0) > 0;
    const alertDep = qs("#impEstoqueAlertDep");
    if (alertDep) alertDep.hidden = depsOk;

    const syncAtivo = depsOk && (bc.estoque_baixa_pedido || bc.estoque_importar_bling);
    status.classList.toggle("inativo", !syncAtivo);
    titulo.textContent = "Conectado ao Bling";
    if (!depsOk) {
      sub.textContent = "Estoque pausado — vincule depósitos em Integrações → Bling";
    } else if (syncAtivo) {
      const partes = [];
      if (bc.estoque_importar_bling) partes.push("recebimento via webhook");
      if (bc.estoque_baixa_pedido) partes.push("baixa em pedidos confirmados");
      sub.textContent = `Sincronização configurada — ${partes.join(" · ")}`;
    } else {
      sub.textContent = "Depósitos vinculados — ative as opções de estoque abaixo";
    }
  }

  function preencherFormEstoque() {
    const bc = cfg.bling_config || {};
    qs("#impEstoqueBaixaPedido").checked = !!bc.estoque_baixa_pedido;
    qs("#impEstoqueImportarBling").checked = bc.estoque_importar_bling !== false;
    qs("#impEstoqueUltimaRecebido").textContent = fmtSync(
      bc.ultima_sync_estoque_recebido,
      "Recebido do Bling"
    );
    qs("#impEstoqueUltimaEnviado").textContent = fmtSync(
      bc.ultima_sync_estoque_enviado,
      "Enviado ao Bling"
    );
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

  async function montarBodyBling() {
    const modo = qs('input[name="imp_bling_modo"]:checked')?.value || "todos";
    const body = { contexto: "fornecedor" };
    if (modo === "categorias") {
      const ids = getSelectedCatIds();
      if (!ids.length) {
        await Swal.fire({ icon: "warning", title: "Atenção", text: "Selecione ao menos uma categoria." });
        return null;
      }
      body.ids_categorias_bling = ids;
      body.incluir_subcategorias = qs("#impBlingSub")?.checked !== false;
    }
    return body;
  }

  function opcoesCategoriaHtml(opcoes, selectedId) {
    const opts = (opcoes || [])
      .map(
        (o) =>
          `<option value="${esc(o.id)}"${String(o.id) === String(selectedId) ? " selected" : ""}>${esc(o.caminho || o.nome)}</option>`
      )
      .join("");
    return `<option value="">— Selecione categoria DropNexo —</option>${opts}`;
  }

  function abrirModalMapeamentoCategorias(dados) {
    return new Promise((resolve) => {
      const modal = qs("#impCatMapModal");
      if (!modal) {
        resolve(null);
        return;
      }

      const mapeadas = dados.mapeadas || [];
      const pendentes = dados.pendentes || [];
      const opcoesDn = dados.categorias_dropnexo || [];
      const estado = { correcoes: {}, decisoes: {} };

      qs("#impCatMapSecMapeadas").hidden = !mapeadas.length;
      qs("#impCatMapSecPendentes").hidden = !pendentes.length;

      const listaMap = qs("#impCatMapListaMapeadas");
      listaMap.innerHTML = mapeadas
        .map((m) => {
          const badge =
            m.origem === "mapa"
              ? '<span class="imp-catmap-badge imp-catmap-badge--mapa">Mapa salvo</span>'
              : '<span class="imp-catmap-badge">Match automático</span>';
          const editavel = m.editavel === true;
          const correcao = editavel
            ? `<div class="imp-catmap-row-actions" data-tipo="match" data-id-bling="${esc(m.id_bling)}">
                <label><input type="radio" name="match_${esc(m.id_bling)}" value="manter" checked /> Manter vínculo</label>
                <label><input type="radio" name="match_${esc(m.id_bling)}" value="vincular" /> Vincular a outra</label>
                <select hidden disabled data-select-match="${esc(m.id_bling)}">${opcoesCategoriaHtml(opcoesDn, m.id_dropnexo)}</select>
              </div>`
            : "";
          return `<div class="imp-catmap-row">
            <div class="imp-catmap-row-head">
              <div class="imp-catmap-bling"><strong>${esc(m.nome_bling)}</strong><small>Bling · ${esc(m.caminho_bling || m.id_bling)}</small></div>
              ${badge}
            </div>
            <div class="imp-catmap-arrow">→</div>
            <div class="imp-catmap-drop"><strong>${esc(m.nome_dropnexo || "—")}</strong></div>
            ${editavel ? `<small class="imp-hint">${esc(m.motivo_match || "")}</small>` : ""}
            ${correcao}
          </div>`;
        })
        .join("");

      const listaPen = qs("#impCatMapListaPendentes");
      listaPen.innerHTML = pendentes
        .map(
          (p) => `<div class="imp-catmap-row">
            <div class="imp-catmap-bling"><strong>${esc(p.nome_bling)}</strong><small>Bling · ${esc(p.caminho_bling || p.id_bling)}</small></div>
            <div class="imp-catmap-row-actions" data-tipo="pendente" data-id-bling="${esc(p.id_bling)}">
              <label><input type="radio" name="pend_${esc(p.id_bling)}" value="criar" checked /> Criar nova categoria</label>
              <label><input type="radio" name="pend_${esc(p.id_bling)}" value="vincular" /> Vincular existente</label>
              <select hidden disabled data-select-pend="${esc(p.id_bling)}">${opcoesCategoriaHtml(opcoesDn, "")}</select>
            </div>
          </div>`
        )
        .join("");

      const atualizarResumo = () => {
        const criarDefault = pendentes.filter((p) => {
          const r = modal.querySelector(`input[name="pend_${p.id_bling}"]:checked`);
          return !r || r.value === "criar";
        }).length;
        qs("#impCatMapResumo").textContent =
          `${mapeadas.length} mapeada(s) · ${pendentes.length} pendente(s) · ${criarDefault} será(ão) criada(s) por padrão`;
      };
      atualizarResumo();

      modal.querySelectorAll('[data-tipo="match"]').forEach((wrap) => {
        const idBling = wrap.dataset.idBling;
        const sel = wrap.querySelector(`[data-select-match="${idBling}"]`);
        wrap.querySelectorAll(`input[name="match_${idBling}"]`).forEach((radio) => {
          radio.addEventListener("change", () => {
            const vincular = radio.value === "vincular" && radio.checked;
            if (sel) {
              sel.hidden = !vincular;
              sel.disabled = !vincular;
            }
          });
        });
      });

      modal.querySelectorAll('[data-tipo="pendente"]').forEach((wrap) => {
        const idBling = wrap.dataset.idBling;
        const sel = wrap.querySelector(`[data-select-pend="${idBling}"]`);
        wrap.querySelectorAll(`input[name="pend_${idBling}"]`).forEach((radio) => {
          radio.addEventListener("change", () => {
            const vincular = radio.value === "vincular" && radio.checked;
            if (sel) {
              sel.hidden = !vincular;
              sel.disabled = !vincular;
            }
            atualizarResumo();
          });
        });
      });

      const fechar = (resultado) => {
        modal.setAttribute("aria-hidden", "true");
        document.body.style.overflow = "";
        btnCancel.removeEventListener("click", onCancel);
        btnOk.removeEventListener("click", onOk);
        resolve(resultado);
      };

      const onCancel = () => fechar(null);
      const onOk = () => {
        const correcoes = [];
        mapeadas.filter((m) => m.editavel).forEach((m) => {
          const vincular = modal.querySelector(`input[name="match_${m.id_bling}"][value="vincular"]`)?.checked;
          if (!vincular) return;
          const sel = modal.querySelector(`[data-select-match="${m.id_bling}"]`);
          const idDrop = sel?.value;
          if (!idDrop) {
            Swal.fire({ icon: "warning", title: "Atenção", text: `Selecione a categoria DropNexo para «${m.nome_bling}».` });
            throw new Error("categoria_obrigatoria");
          }
          if (String(idDrop) !== String(m.id_dropnexo)) {
            correcoes.push({ id_bling: m.id_bling, id_dropnexo: Number(idDrop) });
          }
        });

        const decisoes = [];
        pendentes.forEach((p) => {
          const vincular = modal.querySelector(`input[name="pend_${p.id_bling}"][value="vincular"]`)?.checked;
          if (vincular) {
            const sel = modal.querySelector(`[data-select-pend="${p.id_bling}"]`);
            const idDrop = sel?.value;
            if (!idDrop) {
              Swal.fire({ icon: "warning", title: "Atenção", text: `Selecione a categoria DropNexo para «${p.nome_bling}».` });
              throw new Error("categoria_obrigatoria");
            }
            decisoes.push({ id_bling: p.id_bling, acao: "vincular", id_dropnexo: Number(idDrop) });
          } else {
            decisoes.push({ id_bling: p.id_bling, acao: "criar" });
          }
        });

        fechar({ correcoes, decisoes, confirmar_categorias: true });
      };

      const btnCancel = qs("#impCatMapCancel");
      const btnOk = qs("#impCatMapContinuar");
      btnCancel.addEventListener("click", onCancel);
      btnOk.addEventListener("click", () => {
        try {
          onOk();
        } catch {
          /* validação inline */
        }
      });

      modal.setAttribute("aria-hidden", "false");
      document.body.style.overflow = "hidden";
    });
  }

  function htmlProgressoBling(p, totalPrevisto) {
    const total = Number(p?.total || totalPrevisto || 0);
    const proc = Number(p?.processados || 0);
    const pct = Number(p?.percentual ?? (total ? Math.min(100, Math.round((proc / total) * 100)) : 0));
    const fase = p?.fase || "processando";
    const faseTxt =
      fase === "listando" || fase === "iniciando"
        ? "Preparando lista de produtos no Bling…"
        : fase === "concluido"
          ? "Finalizando…"
          : "Importando produtos do Bling…";
    return `<div class="imp-swal-progress">
      <p style="margin:0 0 12px;text-align:left;font-size:0.95em">${faseTxt}</p>
      <div style="background:#e2e8f0;border-radius:6px;height:12px;overflow:hidden">
        <div style="width:${pct}%;background:#021F81;height:100%;transition:width .35s ease"></div>
      </div>
      <p style="margin:12px 0 0;text-align:center;font-size:1.05em">
        <strong>${proc}</strong>${total ? ` de <strong>${total}</strong>` : ""} produto(s)
      </p>
      <p style="margin:8px 0 0;text-align:center;font-size:0.85em;color:#64748b">
        Inseridos: ${Number(p?.importados || 0)} · Atualizados: ${Number(p?.atualizados || 0)} · Erros: ${Number(p?.erros || 0)}
      </p>
    </div>`;
  }

  function aguardar(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function pollProgressoImportacaoBling(idLote, totalPrevisto) {
    const intervaloMs = 1500;
    for (;;) {
      const r = await fetch(`${BASE}/integracao/bling/lote/${idLote}/progresso`, {
        credentials: "include",
        headers: { Accept: "application/json" },
      });
      const j = await lerJsonResposta(r);
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao consultar progresso.");
      const p = j.progresso || {};
      Swal.update({ html: htmlProgressoBling(p, totalPrevisto) });
      if (p.concluido) {
        if (p.erro_fatal) throw new Error(p.erro_fatal);
        return p;
      }
      await aguardar(intervaloMs);
    }
  }

  async function executarImportacaoBling(body, totalPrevisto = 0) {
    Swal.fire({
      title: "Importando do Bling",
      html: htmlProgressoBling({ processados: 0, total: totalPrevisto, percentual: 0 }, totalPrevisto),
      allowOutsideClick: false,
      showConfirmButton: false,
      didOpen: () => Swal.showLoading(),
    });

    try {
      const r = await fetch(`${BASE}/integracao/bling/iniciar`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
        credentials: "include",
      });
      const j = await lerJsonResposta(r);
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao iniciar importação.");

      const progresso = await pollProgressoImportacaoBling(j.id_lote, totalPrevisto);
      Swal.close();

      await carregarCards("bling", j.id_lote);
      pickTab("bling");

      const stImport = progresso.status_importacao || (progresso.erros > 0 ? "aviso" : "ok");
      const icon = stImport === "erro" ? "error" : stImport === "aviso" || progresso.erros > 0 ? "warning" : "success";
      const msg =
        progresso.mensagem ||
        (progresso.erros > 0
          ? `Importação ${j.numero} concluída com ${progresso.erros} falha(s).`
          : `Importação ${j.numero} concluída.`);

      await Swal.fire({
        icon,
        title: "Concluído",
        text: msg,
        confirmButtonColor: "#021F81",
      });
      window.dispatchEvent(new CustomEvent("catalogo:importacao-concluida"));
    } catch (e) {
      Swal.close();
      await Swal.fire("Erro", e.message, "error");
    }
  }

  async function importarBling() {
    const body = await montarBodyBling();
    if (!body) return;

    Swal.fire({ title: "Analisando categorias…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    try {
      const r = await fetch(`${BASE}/integracao/bling/categorias/pre-analise`, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
        credentials: "include",
      });
      const j = await lerJsonResposta(r);
      Swal.close();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha na pré-análise.");

      const dados = j.dados || {};
      if (dados.exibir_modal) {
        const escolhas = await abrirModalMapeamentoCategorias(dados);
        if (!escolhas) return;
        body.confirmar_categorias = true;
        body.decisoes_categorias = escolhas.decisoes;
        body.correcoes_match = escolhas.correcoes;
      }

      await executarImportacaoBling(body, Number(dados.total_produtos_escopo || 0));
    } catch (e) {
      Swal.close();
      await Swal.fire("Erro", e.message, "error");
    }
  }

  async function salvarEstoqueBling() {
    const body = {
      estoque_baixa_pedido: qs("#impEstoqueBaixaPedido")?.checked === true,
      estoque_importar_bling: qs("#impEstoqueImportarBling")?.checked === true,
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
          <td class="col-acoes Cl_TableActions">
            ${cfg.pode_editar ? `<button type="button" class="Cl_BtnAcao" data-del="${l.id}" data-ico="excluir" title="Excluir lote"></button>` : "—"}
          </td>
        </tr>`;
      })
      .join("");
    aplicarIcones(tbody);
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

  async function recarregarLayoutSelect() {
    const r = await fetch(`${BASE}/dados`, { credentials: "include" });
    const j = await r.json();
    if (!r.ok || !j.success) return;
    cfg.layouts = j.layouts || [];
    const sel = qs("#impLayout");
    if (sel) {
      sel.innerHTML = (j.layouts || [])
        .map((l) => `<option value="${l.id}">${esc(l.nome)}${l.padrao ? " (padrão)" : ""}</option>`)
        .join("");
    }
  }

  function abrirApoioLayout(id = null) {
    if (!window.GlobalUtils?.abrirJanelaApoioModal) {
      Swal.fire("Erro", "Modal institucional não disponível.", "error");
      return;
    }
    const isNovo = id == null;
    GlobalUtils.abrirJanelaApoioModal({
      rota: isNovo ? `${BASE}/layout/incluir` : `${BASE}/layout/editar`,
      titulo: isNovo ? "Novo layout de importação" : "Editar layout de importação",
      largura: 920,
      altura: "auto",
      nivel: 2,
      id: isNovo ? undefined : id,
    });
  }

  function renderTabelaLayouts(rows) {
    const tbody = qs("#impTblLayouts");
    if (!tbody) return;
    const dados = Array.isArray(rows) ? rows : [];
    if (!dados.length) {
      tbody.innerHTML = `<tr><td colspan="6">Nenhum layout.</td></tr>`;
      return;
    }
    tbody.innerHTML = dados
      .map((l) => {
        const padraoBtn = l.padrao
          ? ""
          : `<button type="button" class="Cl_BtnAcao" data-acao="set-padrao" data-id="${l.id}" data-ico="padrao" title="Definir como padrão"></button>`;
        return `<tr>
          <td>${l.id ?? "—"}</td>
          <td>${esc(l.nome || l.nome_layout || "—")}</td>
          <td>${esc(l.descricao || "—")}</td>
          <td>${l.padrao ? "Sim" : "Não"}</td>
          <td>${l.ativo ? "Ativo" : "Inativo"}</td>
          <td class="col-acoes Cl_TableActions">
            <button type="button" class="Cl_BtnAcao" data-acao="edit-layout" data-id="${l.id}" data-ico="editar" title="Editar layout"></button>
            ${padraoBtn}
            ${cfg.pode_editar ? `<button type="button" class="Cl_BtnAcao" data-acao="del-layout" data-id="${l.id}" data-ico="excluir" title="Excluir layout"></button>` : ""}
          </td>
        </tr>`;
      })
      .join("");
    aplicarIcones(tbody);
  }

  async function carregarLayoutsTabela() {
    const nome = (qs("#impLayoutFiltroNome")?.value || "").trim();
    const status = qs("#impLayoutFiltroStatus")?.value || "";
    const padrao = qs("#impLayoutFiltroPadrao")?.value || "";
    const params = new URLSearchParams({ modulo: MODULO });
    if (nome) params.set("nome", nome);
    if (status) params.set("status", status);
    if (padrao) params.set("padrao", padrao);
    const r = await fetch(`${BASE}/layout/dados?${params}`, { credentials: "include" });
    const j = await r.json();
    if (!r.ok || !j.success) {
      renderTabelaLayouts([]);
      return;
    }
    renderTabelaLayouts(j.dados || []);
  }

  async function definirLayoutPadrao(id) {
    const ok = await Swal.fire({
      icon: "question",
      title: "Definir padrão?",
      text: "Este layout passará a ser o padrão do catálogo.",
      showCancelButton: true,
      confirmButtonText: "Confirmar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
    });
    if (!ok.isConfirmed) return;
    const r = await fetch(`${BASE}/layout/padrao`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, modulo: MODULO }),
      credentials: "include",
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao definir padrão.");
    await carregarLayoutsTabela();
    await recarregarLayoutSelect();
    await Swal.fire({ icon: "success", title: "Concluído", text: j.message, timer: 1400, showConfirmButton: false });
  }

  async function excluirLayout(id) {
    const ok = await Swal.fire({
      icon: "warning",
      title: "Excluir layout?",
      showCancelButton: true,
      confirmButtonColor: "#b42318",
      confirmButtonText: "Excluir",
      cancelButtonText: "Cancelar",
    });
    if (!ok.isConfirmed) return;
    const r = await fetch(`${BASE}/layout/${id}?modulo=${encodeURIComponent(MODULO)}`, {
      method: "DELETE",
      credentials: "include",
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao excluir layout.");
    await carregarLayoutsTabela();
    await recarregarLayoutSelect();
    await Swal.fire({ icon: "success", title: "Excluído", text: j.message, timer: 1400, showConfirmButton: false });
  }

  function bindLayoutTab() {
    qs("#impBtnLayoutFiltrar")?.addEventListener("click", carregarLayoutsTabela);
    qs("#impBtnLayoutLimpar")?.addEventListener("click", () => {
      qs("#impLayoutFiltroNome").value = "";
      qs("#impLayoutFiltroStatus").value = "";
      qs("#impLayoutFiltroPadrao").value = "";
      carregarLayoutsTabela();
    });
    qs("#impBtnNovoLayout")?.addEventListener("click", () => abrirApoioLayout(null));
    qs("#impTblLayouts")?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-acao]");
      if (!btn) return;
      const id = Number(btn.dataset.id);
      if (btn.dataset.acao === "edit-layout") abrirApoioLayout(id);
      if (btn.dataset.acao === "del-layout") excluirLayout(id).catch((e) => Swal.fire("Erro", e.message, "error"));
      if (btn.dataset.acao === "set-padrao") definirLayoutPadrao(id).catch((e) => Swal.fire("Erro", e.message, "error"));
    });
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
      atualizarStatusBling();
      atualizarAnimacaoEstoque();
    });
    qs("#impEstoqueBaixaPedido")?.addEventListener("change", () => {
      atualizarStatusBling();
      atualizarAnimacaoEstoque();
    });
    bindCatPicker();
    bindLayoutTab();
    window.addEventListener("message", async (event) => {
      if (event.origin !== window.location.origin) return;
      if (event.data?.grupo === "import_layout_atualizar") {
        await carregarLayoutsTabela();
        await recarregarLayoutSelect();
      }
    });
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
