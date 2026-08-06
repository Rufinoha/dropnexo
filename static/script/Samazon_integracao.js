(function () {
  const PANES = {
    pedidos: document.getElementById("amz_pane_pedidos"),
    produtos: document.getElementById("amz_pane_produtos"),
    estoque: document.getElementById("amz_pane_estoque"),
  };

  const el = {
    badge: document.getElementById("amz_status_badge"),
    alertSrv: document.getElementById("amz_alert_servidor"),
    secGuia: document.getElementById("amz_sec_guia"),
    painel: document.getElementById("amz_painel_config"),
    contaInfo: document.getElementById("amz_conta_info"),
    btnDesconectar: document.getElementById("amz_btn_desconectar"),
    btnConectar: document.getElementById("amz_btn_conectar"),
    btnSync: document.getElementById("amz_btn_sync"),
    btnMapearCategorias: document.getElementById("amz_btn_mapear_categorias"),
    btnSyncEstoque: document.getElementById("amz_btn_sync_estoque"),
    pedidosAuto: document.getElementById("amz_pedidos_auto"),
    produtosAuto: document.getElementById("amz_produtos_auto"),
    estoqueAuto: document.getElementById("amz_estoque_auto"),
    msg: document.getElementById("amz_msg"),
    subtabs: document.getElementById("amz_subtabs"),
    modalCat: document.getElementById("amz_modal_categorias"),
    tbodyCat: document.getElementById("amz_tbody_categorias"),
    btnModalCatSalvar: document.getElementById("amz_modal_cat_salvar"),
    btnModalCatFechar: document.getElementById("amz_modal_cat_fechar"),
    btnModalCatCancelar: document.getElementById("amz_modal_cat_cancelar"),
    msgModal: document.getElementById("amz_msg_modal"),
    pickerModal: document.getElementById("amz_modal_picker_cat"),
    pickerBusca: document.getElementById("amz_picker_busca"),
    pickerLista: document.getElementById("amz_picker_lista"),
    pickerHint: document.getElementById("amz_picker_hint"),
    btnPickerFechar: document.getElementById("amz_picker_fechar"),
    btnPickerCancelar: document.getElementById("amz_picker_cancelar"),
  };

  let categoriasMap = [];
  let salvando = false;
  let pickerTr = null;
  let pickerTimer = null;

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function feedbackCat(msg, isErr) {
    if (!el.msgModal) return;
    if (!msg) {
      el.msgModal.hidden = true;
      el.msgModal.textContent = "";
      return;
    }
    el.msgModal.hidden = false;
    el.msgModal.textContent = msg;
    el.msgModal.classList.toggle("is-erro", !!isErr);
  }

  function ativarAba(tab) {
    const id = tab in PANES ? tab : "pedidos";
    document.querySelectorAll(".Mp_SubTab").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.amzTab === id);
    });
    Object.entries(PANES).forEach(([k, pane]) => {
      if (pane) pane.hidden = k !== id;
    });
    try {
      localStorage.setItem("amz_integracao_aba", id);
    } catch {
      /* ignore */
    }
  }

  function setConectado(on) {
    if (el.badge) {
      el.badge.textContent = on ? "Conectado" : "Desconectado";
      el.badge.classList.toggle("is-on", on);
      el.badge.classList.toggle("is-off", !on);
    }
    el.secGuia?.toggleAttribute("hidden", on);
    el.painel?.toggleAttribute("hidden", !on);
  }

  function setServidorConfigurado(ok) {
    if (el.alertSrv) el.alertSrv.hidden = !!ok;
    if (el.btnConectar && !ok) {
      el.btnConectar.classList.add("is-disabled");
      el.btnConectar.setAttribute("aria-disabled", "true");
      el.btnConectar.addEventListener("click", (ev) => {
        ev.preventDefault();
        alert("Integração indisponível. Configure o app Amazon no servidor.");
      });
    }
  }

  function mostrarMsg(t, erro) {
    if (!el.msg) return;
    el.msg.textContent = t;
    el.msg.hidden = !t;
    el.msg.classList.toggle("is-erro", !!erro);
  }

  function renderConta(cfg) {
    const c = cfg.seller_info || cfg.conta || {};
    const nome = c.name || c.seller_name || cfg.seller_id || "";
    if (!nome && !cfg.seller_id) {
      el.contaInfo?.setAttribute("hidden", "");
      return;
    }
    if (el.contaInfo) {
      el.contaInfo.hidden = false;
      el.contaInfo.textContent = [nome, cfg.seller_id && `Seller ${cfg.seller_id}`]
        .filter(Boolean)
        .join(" · ");
    }
  }

  function aplicarConfig(cfg) {
    if (el.pedidosAuto) el.pedidosAuto.checked = !!cfg.pedidos_importar_auto;
    if (el.produtosAuto) el.produtosAuto.checked = !!cfg.produtos_exportar_auto;
    if (el.estoqueAuto) el.estoqueAuto.checked = cfg.estoque_sync_ativo !== false;
    const modo = cfg.produtos_modo || "vincular_sku";
    document.querySelectorAll('input[name="amz_produtos_modo"]').forEach((r) => {
      r.checked = r.value === modo;
    });
  }

  function payloadConfig() {
    const body = {};
    if (el.pedidosAuto) body.pedidos_importar_auto = el.pedidosAuto.checked;
    if (el.produtosAuto) body.produtos_exportar_auto = el.produtosAuto.checked;
    if (el.estoqueAuto) body.estoque_sync_ativo = el.estoqueAuto.checked;
    const modo = document.querySelector('input[name="amz_produtos_modo"]:checked');
    if (modo) body.produtos_modo = modo.value;
    return body;
  }

  async function salvarConfig() {
    if (salvando) return;
    salvando = true;
    try {
      const r = await fetch("/api/integracoes/amazon/config/salvar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payloadConfig()),
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao salvar.");
      mostrarMsg(j.message || "Preferências salvas.", false);
    } catch (e) {
      mostrarMsg(e.message, true);
    } finally {
      salvando = false;
    }
  }

  async function carregarStatus() {
    try {
      const r = await fetch("/api/integracoes/amazon/status", { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success) return;
      const cfg = j.config || {};
      setServidorConfigurado(!!(cfg.configurado_servidor ?? cfg.configurado));
      setConectado(!!cfg.conectado);
      aplicarConfig(cfg);
      renderConta(cfg);
    } catch {
      /* silencioso */
    }
  }

  document.querySelectorAll("[data-amz-config]").forEach((inp) => {
    inp.addEventListener("change", () => salvarConfig());
  });
  document.querySelectorAll('input[name="amz_produtos_modo"]').forEach((inp) => {
    inp.addEventListener("change", () => salvarConfig());
  });

  el.subtabs?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-amz-tab]");
    if (btn) ativarAba(btn.dataset.amzTab);
  });

  el.btnSync?.addEventListener("click", async () => {
    el.btnSync.disabled = true;
    try {
      const r = await fetch("/api/integracoes/amazon/sync/pedidos", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha na sincronização.");
      await Swal.fire({
        icon: "success",
        title: "Pedidos",
        text: j.message || "Sincronização concluída.",
        confirmButtonColor: "#021F81",
      });
    } catch (e) {
      await Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    } finally {
      el.btnSync.disabled = false;
    }
  });

  el.btnSyncEstoque?.addEventListener("click", async () => {
    el.btnSyncEstoque.disabled = true;
    try {
      const r = await fetch("/api/integracoes/amazon/sync/estoque", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: "{}",
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha na sincronização.");
      await Swal.fire({
        icon: "success",
        title: "Estoque",
        text: j.message || "Estoque sincronizado.",
        confirmButtonColor: "#021F81",
      });
    } catch (e) {
      await Swal.fire({ icon: "error", title: "Erro", text: e.message, confirmButtonColor: "#021F81" });
    } finally {
      el.btnSyncEstoque.disabled = false;
    }
  });

  el.btnDesconectar?.addEventListener("click", async () => {
    const conf = await Swal.fire({
      icon: "warning",
      title: "Desconectar Amazon?",
      text: "A conta deixará de sincronizar até reconectar.",
      showCancelButton: true,
      confirmButtonText: "Desconectar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
    });
    if (!conf.isConfirmed) return;
    const r = await fetch("/api/integracoes/amazon/desconectar", {
      method: "POST",
      credentials: "same-origin",
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) {
      await Swal.fire({ icon: "error", title: "Erro", text: j.message || "Falha.", confirmButtonColor: "#021F81" });
      return;
    }
    setConectado(false);
    mostrarMsg("Desconectado.", false);
  });

  function setProductTypeLinha(tr, productType, displayName) {
    const hid = tr.querySelector(".amz-hid-pt");
    const label = tr.querySelector(".amz-lbl-pt");
    const id = String(productType || "").trim();
    const nome = String(displayName || productType || "").trim();
    const ok = !!id;
    if (hid) hid.value = ok ? id : "";
    if (label) {
      label.textContent = ok ? nome : "Escolher Product Type";
      label.classList.toggle("is-empty", !ok);
      label.title = ok ? id : "";
    }
  }

  function valorProductTypeLinha(tr) {
    return (tr.querySelector(".amz-hid-pt")?.value || "").trim();
  }

  function renderTabelaCategorias() {
    if (!el.tbodyCat) return;
    if (!categoriasMap.length) {
      el.tbodyCat.innerHTML =
        '<tr><td colspan="2" class="Mp_Hint">Cadastre categorias em Categorias antes de mapear.</td></tr>';
      return;
    }
    el.tbodyCat.innerHTML = categoriasMap
      .map((c) => {
        const id = c.id_categoria;
        const pt = (c.amazon_product_type || "").trim();
        const ptNome = (c.amazon_product_type_nome || pt || "").trim();
        const ok = !!pt;
        const label = ok ? esc(ptNome) : "Escolher Product Type";
        const emptyCls = ok ? "" : " is-empty";
        return `<tr data-cat-id="${id}">
          <td>${esc(c.nome)}</td>
          <td class="amz-cell-pt">
            <input type="hidden" class="amz-hid-pt" value="${esc(pt)}" />
            <div class="Mp_CatPick">
              <span class="amz-lbl-pt${emptyCls}" title="${esc(pt)}">${label}</span>
              <button type="button" class="Cl_botaoFiltro Mp_CatMapBtn amz-btn-escolher">Escolher</button>
            </div>
          </td>
        </tr>`;
      })
      .join("");
  }

  async function abrirModalCategorias() {
    const r = await fetch("/api/integracoes/amazon/categorias-mapeamento", { credentials: "same-origin" });
    const j = await r.json();
    if (!r.ok || !j.success) {
      await Swal.fire({ icon: "error", title: "Erro", text: j.message || "Falha.", confirmButtonColor: "#021F81" });
      return;
    }
    categoriasMap = j.itens || j.categorias || [];
    feedbackCat("", false);
    renderTabelaCategorias();
    el.modalCat?.showModal?.();
  }

  function fecharPickerCat() {
    pickerTr = null;
    el.pickerModal?.close();
  }

  function renderPickerLista(itens, message) {
    if (!el.pickerLista) return;
    if (el.pickerHint) {
      el.pickerHint.hidden = !message;
      el.pickerHint.textContent = message || "";
    }
    if (!itens.length) {
      el.pickerLista.innerHTML =
        '<p class="Mp_Hint">Nenhum resultado. Ajuste a busca ou rode o cache em Tarefas secundárias.</p>';
      return;
    }
    el.pickerLista.innerHTML = itens
      .map(
        (x) => {
          const code = x.product_type || x.category_id || "";
          const nome = x.nome || x.display_name || code;
          return `<button type="button" class="Mp_PickerItem" role="option"
          data-id="${esc(code)}" data-nome="${esc(nome)}">
          <strong>${esc(nome)}</strong>
          ${code && code !== nome ? `<span>${esc(code)}</span>` : ""}
        </button>`;
        }
      )
      .join("");
  }

  async function buscarPicker(termo) {
    const qs = new URLSearchParams();
    if (termo) qs.set("q", termo);
    const r = await fetch(`/api/integracoes/amazon/categorias/cache/buscar?${qs}`, {
      credentials: "same-origin",
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha na busca.");
    renderPickerLista(j.itens || [], j.message || "");
  }

  function abrirPickerCat(tr) {
    pickerTr = tr;
    if (!el.pickerModal) return;
    if (el.pickerBusca) el.pickerBusca.value = "";
    renderPickerLista([], "Digite para filtrar ou aguarde a lista…");
    el.pickerModal.showModal();
    buscarPicker("").catch((e) => renderPickerLista([], e.message));
    setTimeout(() => el.pickerBusca?.focus(), 50);
  }

  el.btnMapearCategorias?.addEventListener("click", () =>
    abrirModalCategorias().catch((e) => Swal.fire("Erro", e.message, "error"))
  );
  el.btnModalCatFechar?.addEventListener("click", () => el.modalCat?.close?.());
  el.btnModalCatCancelar?.addEventListener("click", () => el.modalCat?.close?.());
  el.tbodyCat?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".amz-btn-escolher");
    if (!btn) return;
    const tr = btn.closest("tr[data-cat-id]");
    if (tr) abrirPickerCat(tr);
  });
  el.btnPickerFechar?.addEventListener("click", () => fecharPickerCat());
  el.btnPickerCancelar?.addEventListener("click", () => fecharPickerCat());
  el.pickerModal?.addEventListener("close", () => {
    pickerTr = null;
    if (pickerTimer) {
      clearTimeout(pickerTimer);
      pickerTimer = null;
    }
  });
  el.pickerBusca?.addEventListener("input", () => {
    if (pickerTimer) clearTimeout(pickerTimer);
    pickerTimer = setTimeout(() => {
      const termo = (el.pickerBusca?.value || "").trim();
      buscarPicker(termo).catch((e) => renderPickerLista([], e.message));
    }, 280);
  });
  el.pickerLista?.addEventListener("click", (ev) => {
    const item = ev.target.closest(".Mp_PickerItem");
    if (!item || !pickerTr) return;
    setProductTypeLinha(pickerTr, item.dataset.id || "", item.dataset.nome || "");
    fecharPickerCat();
  });

  el.btnModalCatSalvar?.addEventListener("click", async () => {
    const itens = [];
    el.tbodyCat?.querySelectorAll("tr[data-cat-id]").forEach((tr) => {
      const id = parseInt(tr.dataset.catId, 10);
      const pt = valorProductTypeLinha(tr);
      if (id && pt) itens.push({ id_categoria: id, amazon_product_type: pt });
    });
    if (!itens.length) {
      feedbackCat("Escolha ao menos um Product Type Amazon.", true);
      return;
    }
    const r = await fetch("/api/integracoes/amazon/categorias-mapeamento/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itens }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) {
      feedbackCat(j.message || "Falha.", true);
      return;
    }
    el.modalCat?.close?.();
    mostrarMsg(j.message || "Categorias salvas.", false);
  });

  try {
    ativarAba(localStorage.getItem("amz_integracao_aba") || "pedidos");
  } catch {
    ativarAba("pedidos");
  }
  carregarStatus();
  window.lucide?.createIcons?.();
})();
