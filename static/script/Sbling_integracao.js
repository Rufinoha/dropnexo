(function () {
  const badge = document.getElementById("bl_status_badge");
  const btnConectar = document.getElementById("bl_btn_conectar");
  const btnDesconectar = document.getElementById("bl_btn_desconectar");
  const painelConfig = document.getElementById("bl_painel_config");
  const tituloModulo = document.getElementById("bl_titulo_modulo");
  const ctxInput = document.getElementById("bl_contexto_ativo");
  const logsEl = document.getElementById("bl_logs");
  const ultimaSync = document.getElementById("bl_ultima_sync");
  const btnSalvar = document.getElementById("bl_btn_salvar");
  const btnSalvarEstoque = document.getElementById("bl_btn_salvar_estoque");
  const paneConfig = document.getElementById("bl_pane_config");
  const paneEstoque = document.getElementById("bl_pane_estoque");
  const paneCategorias = document.getElementById("bl_pane_categorias");
  const paneLogs = document.getElementById("bl_pane_logs");
  const alertDep = document.getElementById("bl_estoque_alert_dep");
  const webhookHint = document.getElementById("bl_webhook_hint");
  const syncRecebido = document.getElementById("bl_sync_recebido");
  const syncEnviado = document.getElementById("bl_sync_enviado");
  const chkReceber = document.getElementById("bl_estoque_receber");
  const chkBaixa = document.getElementById("bl_estoque_baixa");
  const syncVisual = document.getElementById("bl_sync_visual");

  let estado = {
    conectado: false,
    contexto_modulo: "fornecedor",
    configs: [],
    depositos: { vinculados: 0, pendentes: 0 },
    webhook_url: "",
    bling_conta: null,
  };

  let tabAtiva = "config";
  let catPainel = { segmentos: [], opcoes: [] };
  let catBulkBound = false;

  function cfgAtual() {
    return estado.configs.find((c) => c.contexto === estado.contexto_modulo) || {};
  }

  function cfgFornecedor() {
    return estado.configs.find((c) => c.contexto === "fornecedor") || {};
  }

  function definirVisivel(el, visivel) {
    if (!el) return;
    el.hidden = !visivel;
    el.style.display = visivel ? "" : "none";
  }

  function fmtSync(iso, rotulo) {
    if (!iso) return `${rotulo}: nunca`;
    try {
      return `${rotulo}: ${new Date(iso).toLocaleString("pt-BR")}`;
    } catch {
      return `${rotulo}: —`;
    }
  }

  function atualizarAnimacaoEstoque() {
    if (!syncVisual) return;
    const baixa = chkBaixa?.checked === true;
    const importar = chkReceber?.checked === true;
    const ativo = baixa || importar;

    syncVisual.classList.toggle("inativo", !ativo);
    syncVisual.classList.toggle("sync-out", baixa);
    syncVisual.classList.toggle("sync-in", importar);
    syncVisual.classList.toggle("sync-both", baixa && importar);
    syncVisual.setAttribute("aria-hidden", ativo ? "false" : "true");
  }

  function pickTab(tab) {
    tabAtiva = tab;
    document.querySelectorAll(".Bl_SubTab").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.blTab === tab);
    });
    definirVisivel(paneConfig, tab === "config");
    definirVisivel(paneEstoque, tab === "estoque");
    definirVisivel(paneCategorias, tab === "categorias");
    definirVisivel(paneLogs, tab === "logs");
    if (tab === "estoque") carregarDepositos().catch(() => {});
    if (tab === "categorias") carregarCategorias().catch(() => {});
  }

  function aplicarEstoqueTela() {
    const cfg = cfgFornecedor();
    const opcoes = cfg.opcoes || {};
    if (chkReceber) {
      chkReceber.checked =
        opcoes.estoque_importar_bling !== undefined ? !!opcoes.estoque_importar_bling : true;
    }
    if (chkBaixa) chkBaixa.checked = !!opcoes.estoque_baixa_pedido;

    const vinc = Number(estado.depositos?.vinculados || 0);
    if (alertDep) alertDep.hidden = vinc > 0;

    if (syncRecebido) {
      syncRecebido.textContent = fmtSync(cfg.ultima_sync_estoque_recebido, "Recebido do Bling");
    }
    if (syncEnviado) {
      syncEnviado.textContent = fmtSync(cfg.ultima_sync_estoque_enviado, "Enviado ao Bling");
    }
    if (webhookHint) {
      const url = estado.webhook_url || "";
      webhookHint.textContent = url
        ? `Configure o webhook de Estoque no app DropNexo (Central de Extensões Bling) apontando para: ${url}`
        : "";
    }
    atualizarAnimacaoEstoque();
  }

  function aplicarConfigTela() {
    const cfg = cfgAtual();
    const map = {
      bl_modo_imagem: cfg.modo_imagem,
      bl_fonte: cfg.fonte_principal,
      bl_produtos_modo: cfg.produtos_modo,
      bl_estoque_modo: cfg.estoque_modo,
      bl_pedidos_modo: cfg.pedidos_modo,
    };
    Object.entries(map).forEach(([id, val]) => {
      const el = document.getElementById(id);
      if (el && val) el.value = val;
    });
    if (ctxInput) ctxInput.value = estado.contexto_modulo || "";
    if (tituloModulo) tituloModulo.textContent = "Configurações";
    if (ultimaSync) {
      ultimaSync.textContent = cfg.ultima_sync_produtos
        ? `Última sync produtos: ${new Date(cfg.ultima_sync_produtos).toLocaleString("pt-BR")}`
        : "";
    }
    aplicarEstoqueTela();
  }

  const CRIAR_IGUAL = "__criar_igual__";

  function escHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function badgeCatStatus(st) {
    if (st === "mapeada") return `<span class="Bl_CatBadge Bl_CatBadge--ok">Mapeada</span>`;
    if (st === "ignorada") return `<span class="Bl_CatBadge Bl_CatBadge--ign">Não importar</span>`;
    return `<span class="Bl_CatBadge Bl_CatBadge--pend">Pendente</span>`;
  }

  function opcoesSegmentoHtml(segmentos, selected) {
    const opts = (segmentos || [])
      .map((s) => `<option value="${s.id}"${String(s.id) === String(selected || "") ? " selected" : ""}>${escHtml(s.nome)}</option>`)
      .join("");
    return `<option value="">— segmento —</option>${opts}`;
  }

  function opcoesDropHtml(opcoes, idSegmento, selected) {
    const filtradas = (opcoes || []).filter((o) => {
      if (!idSegmento) return true;
      return String(o.id_segmento || "") === String(idSegmento);
    });
    const opts = filtradas
      .map(
        (o) =>
          `<option value="${o.id}"${String(o.id) === String(selected || "") ? " selected" : ""}>${escHtml(o.caminho || o.nome)}</option>`
      )
      .join("");
    return `<option value="">— categoria —</option>${opts}`;
  }

  function opcoesPaiHtml(opcoes, idSegmento, selected) {
    const filtradas = (opcoes || []).filter((o) => {
      if (idSegmento && String(o.id_segmento || "") !== String(idSegmento)) return false;
      return Number(o.nivel || 1) < 3;
    });
    const opts = filtradas
      .map(
        (o) =>
          `<option value="${o.id}"${String(o.id) === String(selected || "") ? " selected" : ""}>${escHtml(o.caminho || o.nome)}</option>`
      )
      .join("");
    return `<option value="">— raiz (nível 1) —</option>${opts}`;
  }

  function atualizarDestCatRow(tr) {
    const acao = tr.querySelector(".Bl_CatAcao")?.value || "";
    const wrapV = tr.querySelector(".Bl_CatDestVincular");
    const wrapC = tr.querySelector(".Bl_CatDestCriar");
    if (wrapV) wrapV.hidden = acao !== "vincular";
    if (wrapC) wrapC.hidden = acao !== "criar";
  }

  function hintCriarArvore() {
    return `<span class="Bl_CatCriarHint">Recria a árvore do Bling automaticamente (pais inclusos).</span>`;
  }

  function aplicarResumoCategorias(resumo) {
    const el = document.getElementById("bl_cat_resumo");
    if (!el || !resumo) return;
    const { total = 0, mapeadas = 0, ignoradas = 0, pendentes = 0, pronto = false } = resumo;
    el.hidden = false;
    el.className = "Bl_CatResumo " + (pronto ? "Bl_CatResumo--ok" : "Bl_CatResumo--pend");
    el.textContent = pronto
      ? `${total} categorias mapeadas — importação liberada (${mapeadas} vinculadas/criadas, ${ignoradas} excluídas).`
      : `${pendentes} de ${total} categorias pendentes — conclua o mapeamento para importar produtos.`;
  }

  function linhasCatSelecionadas() {
    const tbody = document.getElementById("bl_tbl_categorias");
    if (!tbody) return [];
    return Array.from(tbody.querySelectorAll("tr[data-bling] .Bl_CatChk:checked")).map((cb) =>
      cb.closest("tr")
    );
  }

  function syncCatChkAll() {
    const tbody = document.getElementById("bl_tbl_categorias");
    const chkAll = document.getElementById("bl_cat_chk_all");
    if (!tbody || !chkAll) return;
    const boxes = tbody.querySelectorAll(".Bl_CatChk");
    if (!boxes.length) {
      chkAll.checked = false;
      chkAll.indeterminate = false;
      return;
    }
    const n = Array.from(boxes).filter((b) => b.checked).length;
    chkAll.checked = n === boxes.length;
    chkAll.indeterminate = n > 0 && n < boxes.length;
  }

  function atualizarBulkDestCat() {
    const acao = document.getElementById("bl_cat_bulk_acao")?.value || "";
    const vinc = document.getElementById("bl_cat_bulk_vincular");
    const hint = document.getElementById("bl_cat_bulk_criar_hint");
    if (vinc) vinc.hidden = acao !== "vincular";
    if (hint) hint.hidden = acao !== "criar";
  }

  function preencherBulkCategorias() {
    const segEl = document.getElementById("bl_cat_bulk_seg");
    const vincEl = document.getElementById("bl_cat_bulk_vincular");
    const idSeg = segEl?.value || "";
    if (segEl) {
      const prev = segEl.value;
      segEl.innerHTML = opcoesSegmentoHtml(catPainel.segmentos, prev);
      if (!prev && catPainel.segmentos.length === 1) {
        segEl.value = String(catPainel.segmentos[0].id);
      }
    }
    const seg = segEl?.value || idSeg;
    if (vincEl) {
      const prev = vincEl.value;
      vincEl.innerHTML = opcoesDropHtml(catPainel.opcoes, seg, prev);
    }
    atualizarBulkDestCat();
  }

  function aplicarValoresLinhaCat(tr, { seg, acao, idDrop }) {
    const segSel = tr.querySelector(".Bl_CatSegmento");
    const acaoSel = tr.querySelector(".Bl_CatAcao");
    if (seg && segSel) {
      segSel.value = seg;
      segSel.dispatchEvent(new Event("change"));
    }
    if (acao && acaoSel) {
      acaoSel.value = acao;
      atualizarDestCatRow(tr);
    }
    if (acao === "vincular" && idDrop) {
      const v = tr.querySelector(".Bl_CatDropVincular");
      if (v) v.value = idDrop;
    }
    atualizarDestCatRow(tr);
  }

  function aplicarBulkCategorias() {
    const rows = linhasCatSelecionadas();
    if (!rows.length) {
      Swal.fire({ icon: "warning", title: "Nenhuma seleção", text: "Marque ao menos uma categoria." });
      return;
    }
    const seg = document.getElementById("bl_cat_bulk_seg")?.value || "";
    const acao = document.getElementById("bl_cat_bulk_acao")?.value || "";
    const idDrop = document.getElementById("bl_cat_bulk_vincular")?.value || "";

    if (!seg && !acao) {
      Swal.fire({ icon: "warning", title: "Em lote", text: "Escolha segmento e/ou ação na linha Em lote." });
      return;
    }
    if (acao && acao !== "ignorar" && !seg) {
      Swal.fire({ icon: "warning", title: "Segmento", text: "Selecione o segmento na linha Em lote." });
      return;
    }
    if (acao === "vincular" && !idDrop) {
      Swal.fire({ icon: "warning", title: "DropNexo", text: "Selecione a categoria DropNexo na linha Em lote." });
      return;
    }

    rows.forEach((tr) => {
      aplicarValoresLinhaCat(tr, {
        seg: seg || undefined,
        acao: acao || undefined,
        idDrop: acao === "vincular" ? idDrop : undefined,
      });
    });

    Swal.fire({
      icon: "success",
      title: "Aplicado",
      text: `${rows.length} categoria(s) atualizada(s). Revise e clique em Salvar selecionadas.`,
      timer: 1800,
      showConfirmButton: false,
    });
  }

  function coletarAcoesCatRows(rows) {
    const ctx = estado.contexto_modulo || "fornecedor";
    return rows.map((tr) => {
      const acao = tr.querySelector(".Bl_CatAcao")?.value || "";
      const idSeg = tr.querySelector(".Bl_CatSegmento")?.value || "";
      const idDrop = tr.querySelector(".Bl_CatDropVincular")?.value || "";
      return {
        id_bling: tr.dataset.bling || "",
        acao,
        id_segmento: idSeg ? Number(idSeg) : null,
        id_dropnexo: acao === "vincular" && idDrop ? Number(idDrop) : null,
        nivel: Number(tr.dataset.nivel || 99),
      };
    });
  }

  function pollSyncCategorias(jobId, onTick) {
    return new Promise((resolve, reject) => {
      const poll = async () => {
        try {
          const r = await fetch(
            `/api/integracoes/bling/categorias/progresso/${encodeURIComponent(jobId)}`
          );
          const j = await r.json();
          if (r.status === 404) {
            setTimeout(poll, 1500);
            return;
          }
          if (!r.ok || !j.success) throw new Error(j.message || "Erro no progresso.");
          const p = j.progresso || {};
          if (onTick) onTick(p);
          if (p.status === "concluido") {
            resolve(p);
            return;
          }
          if (p.status === "erro") throw new Error(p.mensagem || "Falha ao salvar categorias.");
          setTimeout(poll, 1200);
        } catch (e) {
          reject(e);
        }
      };
      poll();
    });
  }

  async function salvarCategoriasSelecionadas() {
    const rows = linhasCatSelecionadas();
    if (!rows.length) {
      Swal.fire({ icon: "warning", title: "Nenhuma seleção", text: "Marque ao menos uma categoria." });
      return;
    }

    const ordenadas = [...rows].sort(
      (a, b) => Number(a.dataset.nivel || 99) - Number(b.dataset.nivel || 99)
    );
    const acoes = coletarAcoesCatRows(ordenadas);
    const ctx = estado.contexto_modulo || "fornecedor";

    const btnSalvar = document.getElementById("bl_cat_btn_salvar_sel");
    if (btnSalvar) btnSalvar.disabled = true;

    Swal.fire({
      title: "Salvando categorias…",
      html: htmlProgSync("Iniciando…"),
      allowOutsideClick: false,
      showConfirmButton: false,
      didOpen: () => {
        Swal.showLoading();
      },
    });

    try {
      const resp = await fetch("/api/integracoes/bling/categorias/salvar-lote", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ contexto: ctx, acoes }),
      });
      const jj = await resp.json();
      if (!resp.ok || !jj.success) throw new Error(jj.message || "Erro ao iniciar salvamento.");

      const resultado = await pollSyncCategorias(jj.sync_job_id, (p) => {
        const bar = Swal.getHtmlContainer()?.querySelector(".Bl_DepProgBar");
        const label = Swal.getHtmlContainer()?.querySelector(".Bl_DepProgLabel");
        const pct = pctSync(p);
        if (bar) bar.style.width = `${pct}%`;
        if (label) {
          label.textContent = p.mensagem || `Processados ${p.processados || 0}/${p.total || "?"}`;
        }
      });

      Swal.close();
      await carregarCategorias();

      const falhas = Number(resultado.falhas) || 0;
      const ok = Number(resultado.sincronizados) || 0;
      let errosHtml = "";
      try {
        const res = resultado.resumo ? JSON.parse(resultado.resumo) : {};
        const erros = res.erros || [];
        if (erros.length) {
          errosHtml = `<small>${erros.slice(0, 8).map(escHtml).join("<br>")}</small>`;
        }
      } catch {
        /* ignore */
      }

      if (falhas) {
        await Swal.fire({
          icon: ok > 0 ? "warning" : "error",
          title: ok > 0 ? "Concluído com avisos" : "Erro",
          html: `<p>${escHtml(resultado.mensagem || "")}</p>${errosHtml}`,
          confirmButtonColor: "#021F81",
        });
      } else {
        await Swal.fire({
          icon: "success",
          title: "Salvo",
          text: resultado.mensagem || `${ok} categoria(s) salva(s).`,
          timer: 1800,
          showConfirmButton: false,
        });
      }
    } catch (e) {
      Swal.close();
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    } finally {
      if (btnSalvar) btnSalvar.disabled = false;
    }
  }

  function bindBulkCategoriasOnce() {
    if (catBulkBound) return;
    catBulkBound = true;

    document.getElementById("bl_cat_chk_all")?.addEventListener("change", (ev) => {
      const on = ev.target.checked;
      document.querySelectorAll("#bl_tbl_categorias .Bl_CatChk").forEach((cb) => {
        cb.checked = on;
      });
      syncCatChkAll();
    });

    document.getElementById("bl_cat_bulk_acao")?.addEventListener("change", atualizarBulkDestCat);
    document.getElementById("bl_cat_bulk_seg")?.addEventListener("change", () => {
      const seg = document.getElementById("bl_cat_bulk_seg")?.value || "";
      const vinc = document.getElementById("bl_cat_bulk_vincular");
      if (vinc) vinc.innerHTML = opcoesDropHtml(catPainel.opcoes, seg, vinc.value);
    });

    document.getElementById("bl_cat_btn_aplicar")?.addEventListener("click", aplicarBulkCategorias);
    document.getElementById("bl_cat_btn_salvar_sel")?.addEventListener("click", () => {
      salvarCategoriasSelecionadas().catch((e) => {
        Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
      });
    });
  }

  async function salvarCategoriaRow(tr, opts = {}) {
    const idB = tr.dataset.bling || "";
    const acao = tr.querySelector(".Bl_CatAcao")?.value || "";
    const idSeg = tr.querySelector(".Bl_CatSegmento")?.value || "";
    const idDrop = tr.querySelector(".Bl_CatDropVincular")?.value || "";
    const ctx = estado.contexto_modulo || "fornecedor";

    if (!idB || !acao) throw new Error("Selecione a ação.");
    if (acao !== "ignorar" && !idSeg) throw new Error("Selecione o segmento.");
    if (acao === "vincular" && !idDrop) throw new Error("Selecione a categoria DropNexo.");

    const body = {
      contexto: ctx,
      id_bling: idB,
      acao,
      id_segmento: idSeg ? Number(idSeg) : null,
      id_dropnexo: acao === "vincular" && idDrop ? Number(idDrop) : null,
    };

    const r = await fetch("/api/integracoes/bling/categorias/salvar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    if (opts.reload !== false) await carregarCategorias();
  }

  function htmlCatCarregando() {
    const skels = Array.from({ length: 5 }, (_, i) => {
      const wNome = 55 + (i % 3) * 12;
      return (
        `<tr class="Bl_CatSkeletonRow" aria-hidden="true">` +
        `<td class="Bl_CatColChk"><div class="Bl_CatSkel Bl_CatSkel--sm"></div></td>` +
        `<td><div class="Bl_CatSkel" style="width:${wNome}%"></div></td>` +
        `<td><div class="Bl_CatSkel Bl_CatSkel--field"></div></td>` +
        `<td><div class="Bl_CatSkel Bl_CatSkel--field"></div></td>` +
        `<td><div class="Bl_CatSkel Bl_CatSkel--field"></div></td>` +
        `<td><div class="Bl_CatSkel Bl_CatSkel--badge"></div></td>` +
        `<td><div class="Bl_CatSkel Bl_CatSkel--btn"></div></td>` +
        `</tr>`
      );
    }).join("");

    return (
      `<tr class="Bl_CatLoadingRow">` +
      `<td colspan="7">` +
      `<div class="Bl_CatLoading" role="status" aria-live="polite" aria-busy="true">` +
      `<div class="Bl_CatSpinner" aria-hidden="true"></div>` +
      `<span class="Bl_CatLoadingText">Buscando categorias no Bling…</span>` +
      `<span class="Bl_CatLoadingSub">Isso pode levar alguns segundos se houver muitas categorias.</span>` +
      `</div></td></tr>${skels}`
    );
  }

  function mostrarCarregandoCategorias() {
    const tbody = document.getElementById("bl_tbl_categorias");
    const resumo = document.getElementById("bl_cat_resumo");
    const wrap = document.querySelector(".Bl_CatTblWrap");
    if (tbody) tbody.innerHTML = htmlCatCarregando();
    if (resumo) {
      resumo.hidden = false;
      resumo.className = "Bl_CatResumo Bl_CatResumo--load";
      resumo.textContent = "Consultando categorias do Bling…";
    }
    wrap?.classList.add("is-loading");
    document.getElementById("bl_cat_btn_aplicar")?.setAttribute("disabled", "disabled");
    document.getElementById("bl_cat_btn_salvar_sel")?.setAttribute("disabled", "disabled");
    document.getElementById("bl_cat_chk_all")?.setAttribute("disabled", "disabled");
  }

  function finalizarCarregandoCategorias() {
    document.querySelector(".Bl_CatTblWrap")?.classList.remove("is-loading");
    document.getElementById("bl_cat_btn_aplicar")?.removeAttribute("disabled");
    document.getElementById("bl_cat_btn_salvar_sel")?.removeAttribute("disabled");
    document.getElementById("bl_cat_chk_all")?.removeAttribute("disabled");
  }

  async function carregarCategorias() {
    const tbody = document.getElementById("bl_tbl_categorias");
    if (!tbody) return;
    mostrarCarregandoCategorias();
    const ctx = estado.contexto_modulo || "fornecedor";
    try {
    const r = await fetch(`/api/integracoes/bling/categorias/mapeamento?contexto=${encodeURIComponent(ctx)}`);
    const j = await r.json();
    if (!r.ok || !j.success) {
      tbody.innerHTML = `<tr><td colspan="7">${escHtml(j.message || "Erro ao carregar categorias.")}</td></tr>`;
      return;
    }

    const dados = j.dados || {};
    catPainel = {
      segmentos: dados.segmentos || [],
      opcoes: dados.opcoes_dropnexo || [],
    };
    aplicarResumoCategorias(dados.resumo);
    preencherBulkCategorias();
    bindBulkCategoriasOnce();

    const cats = dados.categorias || [];
    if (!cats.length) {
      tbody.innerHTML = `<tr><td colspan="7">Nenhuma categoria retornada pelo Bling.</td></tr>`;
      syncCatChkAll();
      return;
    }

    const segUnico = catPainel.segmentos.length === 1 ? String(catPainel.segmentos[0].id) : "";

    tbody.innerHTML = cats
      .map((c) => {
        const st = c.status || "pendente";
        const acaoSalva = c.acao || (st === "ignorada" ? "ignorar" : st === "mapeada" ? "vincular" : "");
        const acaoSel =
          acaoSalva === "criar"
            ? "criar"
            : acaoSalva === "ignorar"
              ? "ignorar"
              : acaoSalva === "vincular"
                ? "vincular"
                : "";
        const idSeg = c.id_segmento || segUnico || "";
        const caminho = c.caminho_bling || c.label_bling || c.nome_bling || "";
        return `<tr data-bling="${escHtml(c.id_bling)}" data-status="${escHtml(st)}" data-nivel="${c.nivel || 1}">
          <td class="Bl_CatColChk"><input type="checkbox" class="Bl_CatChk" aria-label="Selecionar categoria" /></td>
          <td><span class="Bl_CatNomeBling" title="${escHtml(caminho)}">${escHtml(c.label_bling || c.nome_bling)}</span></td>
          <td><select class="Bl_CatSegmento">${opcoesSegmentoHtml(catPainel.segmentos, idSeg)}</select></td>
          <td>
            <select class="Bl_CatAcao">
              <option value="">— pendente —</option>
              <option value="vincular"${acaoSel === "vincular" ? " selected" : ""}>Vincular existente</option>
              <option value="criar"${acaoSel === "criar" ? " selected" : ""}>Criar no DropNexo</option>
              <option value="ignorar"${acaoSel === "ignorar" ? " selected" : ""}>Não importar</option>
            </select>
          </td>
          <td>
            <div class="Bl_CatDestWrap Bl_CatDestVincular"${acaoSel === "vincular" ? "" : " hidden"}>
              <select class="Bl_CatDropVincular">${opcoesDropHtml(catPainel.opcoes, idSeg, c.id_dropnexo)}</select>
            </div>
            <div class="Bl_CatDestWrap Bl_CatDestCriar"${acaoSel === "criar" ? "" : " hidden"}>${hintCriarArvore()}</div>
          </td>
          <td>${badgeCatStatus(st)}</td>
          <td><button type="button" class="Cl_BtnSalvar Bl_CatBtnSalvar">Salvar</button></td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll("tr").forEach((tr) => {
      tr.querySelector(".Bl_CatChk")?.addEventListener("change", syncCatChkAll);
      tr.querySelector(".Bl_CatAcao")?.addEventListener("change", () => atualizarDestCatRow(tr));
      tr.querySelector(".Bl_CatSegmento")?.addEventListener("change", () => {
        const seg = tr.querySelector(".Bl_CatSegmento")?.value || "";
        const vinc = tr.querySelector(".Bl_CatDropVincular");
        if (vinc) {
          const sel = vinc.value;
          vinc.innerHTML = opcoesDropHtml(catPainel.opcoes, seg, sel);
        }
      });
      tr.querySelector(".Bl_CatBtnSalvar")?.addEventListener("click", async () => {
        try {
          await salvarCategoriaRow(tr);
          await Swal.fire({ icon: "success", title: "Salvo", timer: 1200, showConfirmButton: false });
        } catch (e) {
          Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
        }
      });
      atualizarDestCatRow(tr);
    });
    syncCatChkAll();
    } catch (e) {
      tbody.innerHTML = `<tr><td colspan="7">${escHtml(e.message || "Erro ao carregar categorias.")}</td></tr>`;
    } finally {
      finalizarCarregandoCategorias();
    }
  }

  function pctSync(p) {
    const total = Number(p.total) || 0;
    const proc = Number(p.processados) || 0;
    if (p.status === "concluido") return 100;
    if (!total) return proc > 0 ? 5 : 0;
    return Math.min(100, Math.round((proc / total) * 100));
  }

  function htmlProgSync(mensagem) {
    const msg = mensagem || "Iniciando…";
    return (
      `<div class="Bl_DepProg">` +
      `<div class="Bl_DepProgTrack"><div class="Bl_DepProgBar" style="width:0%"></div></div>` +
      `<span class="Bl_DepProgLabel">${msg}</span></div>`
    );
  }

  function fmtDepSync(iso) {
    if (!iso) return "";
    try {
      return new Date(iso).toLocaleString("pt-BR");
    } catch {
      return "";
    }
  }

  function htmlDepSyncOk(concluidoEm) {
    const quando = fmtDepSync(concluidoEm);
    return (
      `<span class="Bl_DepSyncBadge Bl_DepSyncBadge--ok">` +
      `<span class="Bl_DepSyncBadgeIcon" aria-hidden="true">✓</span>` +
      `<span class="Bl_DepSyncBadgeText"><strong>Estoque sincronizado</strong>` +
      (quando ? `<small>${quando}</small>` : "") +
      `</span></span>`
    );
  }

  function htmlDepSyncPendente() {
    return (
      `<span class="Bl_DepSyncBadge Bl_DepSyncBadge--pend">` +
      `<span class="Bl_DepSyncBadgeText"><strong>Pendente</strong><small>Clique em Atualizar estoque</small></span></span>`
    );
  }

  async function refreshLinhaDeposito(tr) {
    const idB = tr.dataset.bling;
    if (!idB) return;
    const r = await fetch("/api/integracoes/bling/depositos");
    const j = await r.json();
    if (!r.ok || !j.success) return;
    const meta = (j.mapa || []).find((m) => String(m.id_bling_deposito) === idB) || {};
    const sel = tr.querySelector(".Bl_DepSelect");
    const saved = meta.id_deposito_dropnexo ? String(meta.id_deposito_dropnexo) : "";
    if (sel && saved) sel.value = saved;
    tr.dataset.savedDrop = saved;
    tr._blDepMeta = meta;
    renderCelulaSync(tr, meta);
  }

  async function pollSyncDeposito(tr, jobId) {
    const cell = tr.querySelector(".Bl_DepSyncCell");
    const btnSave = tr.querySelector(".Bl_DepBtnSalvar");
    if (!cell) return;
    if (btnSave) btnSave.disabled = true;
    cell.innerHTML = htmlProgSync("Iniciando…");

    const poll = async () => {
      const r = await fetch(`/api/integracoes/bling/estoque/sync-progresso/${encodeURIComponent(jobId)}`);
      const j = await r.json();
      if (r.status === 404) {
        setTimeout(poll, 1500);
        return;
      }
      if (!r.ok || !j.success) throw new Error(j.message || "Erro no progresso.");
      const p = j.progresso || {};
      const bar = cell.querySelector(".Bl_DepProgBar");
      const label = cell.querySelector(".Bl_DepProgLabel");
      const pct = pctSync(p);
      if (bar) bar.style.width = `${pct}%`;
      if (label) {
        label.textContent = p.mensagem || `Processados ${p.processados || 0}/${p.total || "?"}`;
      }
      if (p.status === "concluido") {
        if (btnSave) btnSave.disabled = false;
        tr.dataset.syncPendente = "0";
        await carregarStatus();
        await refreshLinhaDeposito(tr);
        return;
      }
      if (p.status === "erro") throw new Error(p.mensagem || "Falha na sincronização.");
      setTimeout(poll, 1200);
    };

    try {
      await poll();
    } catch (e) {
      if (btnSave) btnSave.disabled = false;
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
      await carregarDepositos();
    }
  }

  async function iniciarSyncDeposito(tr, idBling) {
    const cell = tr.querySelector(".Bl_DepSyncCell");
    const btnSave = tr.querySelector(".Bl_DepBtnSalvar");
    if (btnSave) btnSave.disabled = true;
    if (cell) cell.innerHTML = htmlProgSync("Preparando…");

    const resp = await fetch("/api/integracoes/bling/depositos/sincronizar-estoque", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_bling_deposito: idBling }),
    });
    const jj = await resp.json();
    if (!resp.ok || !jj.success) throw new Error(jj.message || "Erro ao iniciar sincronização.");
    await pollSyncDeposito(tr, jj.sync_job_id);
  }

  function renderCelulaSync(tr, meta) {
    const cell = tr.querySelector(".Bl_DepSyncCell");
    const btnSave = tr.querySelector(".Bl_DepBtnSalvar");
    if (!cell) return;

    const vinculado = meta?.id_deposito_dropnexo;
    const pendente = !!meta?.estoque_sync_pendente;
    const job = meta?.sync_job;

    if (job?.job_id) {
      pollSyncDeposito(tr, job.job_id).catch(() => {});
      return;
    }

    if (!vinculado) {
      cell.innerHTML = "";
      if (btnSave) btnSave.disabled = false;
      tr.dataset.syncPendente = "0";
      return;
    }

    if (pendente) {
      cell.innerHTML =
        `<div class="Bl_DepSyncStack">` +
        htmlDepSyncPendente() +
        `<button type="button" class="Bl_DepBtnSync">Atualizar estoque</button></div>`;
      tr.dataset.syncPendente = "1";
      if (btnSave) btnSave.disabled = false;
      cell.querySelector(".Bl_DepBtnSync")?.addEventListener("click", async () => {
        try {
          await iniciarSyncDeposito(tr, tr.dataset.bling || "");
        } catch (e) {
          Swal.fire({ icon: "error", title: "Erro", text: e.message });
        }
      });
      return;
    }

    if (meta.estoque_sync_concluido_em) {
      cell.innerHTML = `<div class="Bl_DepSyncStack">${htmlDepSyncOk(meta.estoque_sync_concluido_em)}</div>`;
      tr.dataset.syncPendente = "0";
      if (btnSave) btnSave.disabled = false;
      return;
    }

    if (vinculado) {
      cell.innerHTML =
        `<div class="Bl_DepSyncStack">` +
        `<span class="Bl_DepSyncBadge Bl_DepSyncBadge--neutro">` +
        `<span class="Bl_DepSyncBadgeText"><strong>Vinculado</strong><small>Sync não registrada</small></span></span></div>`;
      tr.dataset.syncPendente = "0";
      if (btnSave) btnSave.disabled = false;
      return;
    }

    cell.innerHTML = "";
    tr.dataset.syncPendente = "0";
    if (btnSave) btnSave.disabled = false;
  }

  async function carregarDepositos() {
    const tbody = document.getElementById("bl_tbl_depositos");
    if (!tbody) return;
    const r = await fetch("/api/integracoes/bling/depositos");
    const j = await r.json();
    if (!r.ok || !j.success) {
      tbody.innerHTML = `<tr><td colspan="4">${j.message || "Erro ao carregar depósitos."}</td></tr>`;
      return;
    }
    const avisoBling = j.aviso_bling || "";
    const painelDep = document.getElementById("bl_painel_depositos");
    let avisoEl = document.getElementById("bl_dep_aviso_bling");
    if (avisoBling && painelDep) {
      if (!avisoEl) {
        avisoEl = document.createElement("div");
        avisoEl.id = "bl_dep_aviso_bling";
        avisoEl.className = "Bl_SyncAlert";
        avisoEl.setAttribute("role", "alert");
        painelDep.insertBefore(avisoEl, painelDep.querySelector(".Bl_DepTblWrap"));
      }
      avisoEl.textContent =
        "Lista do Bling temporariamente indisponível — exibindo depósitos já conhecidos. Tente atualizar a página em alguns minutos.";
      avisoEl.hidden = false;
    } else if (avisoEl) {
      avisoEl.hidden = true;
    }
    const dropOpts = (j.depositos_dropnexo || [])
      .map((d) => `<option value="${d.id}">${d.nome}</option>`)
      .join("");
    const bling = j.depositos_bling || [];
    if (!bling.length) {
      tbody.innerHTML = `<tr><td colspan="4">Nenhum depósito retornado pelo Bling.</td></tr>`;
      return;
    }
    const mapa = {};
    (j.mapa || []).forEach((m) => {
      mapa[m.id_bling_deposito] = m;
    });
    tbody.innerHTML = bling
      .map((b) => {
        const id = String(b.id || "");
        const nome = (b.descricao || b.nome || id).replace(/</g, "&lt;");
        const padrao = b.padrao ? "1" : "0";
        return `<tr data-bling="${id}" data-padrao="${padrao}" data-saved-drop="">
          <td>${nome}</td>
          <td><select class="Bl_DepSelect"><option value="">— não vincular —</option><option value="${CRIAR_IGUAL}">— Criar igual —</option>${dropOpts}</select></td>
          <td class="Bl_DepSyncCell"></td>
          <td><button type="button" class="Cl_BtnSalvar Bl_DepBtnSalvar">Salvar</button></td>
        </tr>`;
      })
      .join("");
    tbody.querySelectorAll("tr").forEach((tr) => {
      const idB = tr.dataset.bling;
      const meta = mapa[idB] || {};
      const sel = tr.querySelector(".Bl_DepSelect");
      const saved = meta.id_deposito_dropnexo ? String(meta.id_deposito_dropnexo) : "";
      if (sel && saved) sel.value = saved;
      tr.dataset.savedDrop = saved;
      tr._blDepMeta = meta;

      renderCelulaSync(tr, meta);

      sel?.addEventListener("change", () => {
        const valor = sel.value || "";
        const mudou = valor !== (tr.dataset.savedDrop || "");
        if (mudou) {
          const cell = tr.querySelector(".Bl_DepSyncCell");
          if (cell) cell.innerHTML = "";
          return;
        }
        renderCelulaSync(tr, tr._blDepMeta || meta);
      });

      tr.querySelector(".Bl_DepBtnSalvar")?.addEventListener("click", async () => {
        try {
          const valor = sel?.value || "";
          if (valor === (tr.dataset.savedDrop || "") && valor) {
            await Swal.fire({
              icon: "info",
              title: "Sem alterações",
              text: "O vínculo deste depósito não foi alterado.",
              timer: 1400,
              showConfirmButton: false,
            });
            return;
          }
          if (!valor && !(tr.dataset.savedDrop || "")) {
            return;
          }
          const criarIgual = valor === CRIAR_IGUAL;
          const resp = await fetch("/api/integracoes/bling/depositos/vincular", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              id_bling_deposito: idB,
              nome_bling: tr.cells[0]?.textContent?.trim(),
              id_deposito_dropnexo: criarIgual ? CRIAR_IGUAL : valor || null,
              criar_igual: criarIgual,
              padrao_bling: tr.dataset.padrao === "1",
            }),
          });
          const jj = await resp.json();
          if (!resp.ok || !jj.success) throw new Error(jj.message || "Erro.");
          await carregarStatus();
          if (!jj.alterado) {
            await Swal.fire({
              icon: "info",
              title: "Sem alterações",
              text: jj.message || "Nenhuma alteração no vínculo.",
              timer: 1400,
              showConfirmButton: false,
            });
            return;
          }
          if (jj.criou_deposito) {
            await carregarDepositos();
            return;
          }
          tr.dataset.savedDrop = jj.id_deposito_dropnexo ? String(jj.id_deposito_dropnexo) : "";
          if (sel && jj.id_deposito_dropnexo) sel.value = String(jj.id_deposito_dropnexo);
          tr._blDepMeta = {
            id_deposito_dropnexo: jj.id_deposito_dropnexo,
            estoque_sync_pendente: !!jj.estoque_sync_pendente,
            estoque_sync_concluido_em: jj.estoque_sync_concluido_em || null,
          };
          renderCelulaSync(tr, tr._blDepMeta);
          await Swal.fire({
            icon: "success",
            title: "Vínculo salvo",
            text: jj.id_deposito_dropnexo
              ? "Use «Atualizar estoque» para importar os saldos deste depósito."
              : jj.message || "",
            timer: 2200,
            showConfirmButton: false,
          });
        } catch (e) {
          Swal.fire({ icon: "error", title: "Erro", text: e.message });
        }
      });
    });
  }

  function renderStatus(data) {
    estado = data;
    const on = !!data.conectado;
    if (badge) {
      badge.textContent = on ? "Conectado" : "Desconectado";
      badge.className = "Bl_ConnBadge " + (on ? "is-on" : "is-off");
    }
    definirVisivel(btnConectar, !on);
    definirVisivel(btnDesconectar, on);
    definirVisivel(painelConfig, on);

    if (logsEl) {
      logsEl.innerHTML = (data.logs || [])
        .map(
          (l) =>
            `<li class="Bl_LogItem${l.status === "erro" ? " is-erro" : l.status === "aviso" ? " is-aviso" : ""}">` +
            `<strong>${l.status}</strong> — ${l.resumo || ""}` +
            (l.criado_em ? ` <span>(${new Date(l.criado_em).toLocaleString("pt-BR")})</span>` : "") +
            `</li>`
        )
        .join("") || '<li class="Bl_LogItem">Nenhum log ainda.</li>';
    }
    aplicarConfigTela();
    if (on && tabAtiva === "estoque") carregarDepositos().catch(() => {});
  }

  async function carregarStatus() {
    const r = await fetch("/api/integracoes/bling/status");
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Falha ao carregar status.");
    renderStatus(j);
  }

  async function salvarConfig() {
    const ctx = estado.contexto_modulo;
    const body = {
      contexto: ctx,
      fonte_principal: document.getElementById("bl_fonte")?.value,
      modo_imagem: document.getElementById("bl_modo_imagem")?.value,
      produtos_modo: document.getElementById("bl_produtos_modo")?.value,
      estoque_modo: document.getElementById("bl_estoque_modo")?.value,
      pedidos_modo: document.getElementById("bl_pedidos_modo")?.value,
    };
    const r = await fetch("/api/integracoes/bling/config/salvar", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Erro ao salvar.");
    await Swal.fire({ icon: "success", title: "Salvo", timer: 1400, showConfirmButton: false });
    await carregarStatus();
  }

  async function salvarEstoque() {
    const body = {
      estoque_baixa_pedido: chkBaixa?.checked === true,
      estoque_importar_bling: chkReceber?.checked === true,
    };
    const r = await fetch("/fornecedor/importacao/bling/estoque", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "include",
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar estoque.");
    await Swal.fire({ icon: "success", title: "Salvo", timer: 1400, showConfirmButton: false });
    await carregarStatus();
  }

  document.getElementById("bl_subtabs")?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".Bl_SubTab");
    if (!btn) return;
    pickTab(btn.dataset.blTab || "config");
  });

  chkReceber?.addEventListener("change", atualizarAnimacaoEstoque);
  chkBaixa?.addEventListener("change", atualizarAnimacaoEstoque);

  btnSalvar?.addEventListener("click", async () => {
    try {
      await salvarConfig();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    }
  });

  btnSalvarEstoque?.addEventListener("click", async () => {
    try {
      await salvarEstoque();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    }
  });

  btnDesconectar?.addEventListener("click", async () => {
    const ok = await Swal.fire({
      title: "Desconectar Bling?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Desconectar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
    });
    if (!ok.isConfirmed) return;
    const r = await fetch("/api/integracoes/bling/desconectar", { method: "POST" });
    const j = await r.json();
    if (!j.success) {
      Swal.fire({ icon: "error", title: "Erro", text: j.message, confirmButtonColor: "#021F81" });
      return;
    }
    await Swal.fire({ icon: "success", title: "Desconectado", timer: 1500, showConfirmButton: false });
    await carregarStatus();
  });

  const params = new URLSearchParams(location.search);
  if (params.get("conectado") === "1") {
    Swal.fire({ icon: "success", title: "Conectado", timer: 1500, showConfirmButton: false });
    window.history.replaceState({}, "", location.pathname);
  }
  const aba = params.get("aba");
  if (aba === "estoque" || aba === "logs" || aba === "config" || aba === "categorias") pickTab(aba);

  carregarStatus().catch((e) => {
    Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
  });

  window.lucide?.createIcons?.();
})();
