(function () {
  "use strict";

  let nivelModal = 1;
  let idCupom = 0;
  let tenantsCache = [];
  let planosCache = [];
  const tenantsSel = new Map(); // id -> {id,nome,slug,tipo}
  const planosSel = new Map(); // key (slug|tipo) -> {key,slug,tipo_negocio,nome}

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("cup_apoio_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
  }

  const el = {
    id: document.getElementById("id"),
    codigo: document.getElementById("codigo"),
    descricao: document.getElementById("descricao"),
    ativo: document.getElementById("ativo"),
    tipo: document.getElementById("tipo_desconto"),
    valor: document.getElementById("valor_desconto"),
    valorLbl: document.getElementById("valor_lbl"),
    periodo: document.getElementById("periodo"),
    publico: document.getElementById("publico_alvo"),
    valido: document.getElementById("valido_ate"),
    usos: document.getElementById("usos_max"),
    tenantCombo: document.getElementById("tenant_combo"),
    planoCombo: document.getElementById("plano_combo"),
    listaTenants: document.getElementById("lista_tenants"),
    listaPlanos: document.getElementById("lista_planos"),
    btnAddTenant: document.getElementById("btnAddTenant"),
    btnAddPlano: document.getElementById("btnAddPlano"),
    btnSalvar: document.getElementById("btnSalvar"),
    btnCancelar: document.getElementById("btnCancelar"),
  };

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function syncValorLabel() {
    if (!el.valorLbl) return;
    el.valorLbl.textContent = el.tipo?.value === "fixo" ? "Valor (R$)" : "Valor (%)";
  }

  function ativarAba(tab) {
    document.querySelectorAll(".Cup_SideTab").forEach(function (b) {
      b.classList.toggle("is-active", b.dataset.tab === tab);
    });
    document.querySelectorAll(".Cup_Panel").forEach(function (p) {
      const on = p.dataset.panel === tab;
      p.hidden = !on;
      p.classList.toggle("is-active", on);
    });
  }

  function fillTenantCombo() {
    if (!el.tenantCombo) return;
    const opts = ['<option value="">Selecione…</option>'];
    tenantsCache.forEach(function (t) {
      if (tenantsSel.has(+t.id)) return;
      opts.push(
        '<option value="' +
          t.id +
          '">#' +
          t.id +
          " — " +
          esc(t.nome || t.slug || "Tenant") +
          " (" +
          esc(t.tipo_negocio || "?") +
          ")</option>"
      );
    });
    el.tenantCombo.innerHTML = opts.join("");
  }

  function fillPlanoCombo() {
    if (!el.planoCombo) return;
    const opts = ['<option value="">Selecione…</option>'];
    planosCache.forEach(function (p) {
      const key = p.key || p.slug;
      if (planosSel.has(key)) return;
      opts.push(
        '<option value="' +
          esc(key) +
          '">' +
          esc(p.nome || key) +
          "</option>"
      );
    });
    el.planoCombo.innerHTML = opts.join("");
  }

  function renderTenants() {
    if (!el.listaTenants) return;
    const itens = Array.from(tenantsSel.values());
    if (!itens.length) {
      el.listaTenants.innerHTML = '<li class="Cup_Empty">Nenhum tenant selecionado (vale para todos).</li>';
      fillTenantCombo();
      return;
    }
    el.listaTenants.innerHTML = itens
      .map(function (t) {
        return (
          '<li class="Cup_Chip" data-tid="' +
          t.id +
          '"><div><strong>#' +
          t.id +
          " — " +
          esc(t.nome || t.slug || "Tenant") +
          "</strong><span>" +
          esc(t.tipo_negocio || "") +
          (t.slug ? " · " + esc(t.slug) : "") +
          '</span></div><button type="button" class="Cl_BtnCancelar" data-rm-tenant="' +
          t.id +
          '">Remover</button></li>'
        );
      })
      .join("");
    el.listaTenants.querySelectorAll("[data-rm-tenant]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        tenantsSel.delete(+btn.getAttribute("data-rm-tenant"));
        renderTenants();
      });
    });
    fillTenantCombo();
  }

  function renderPlanos() {
    if (!el.listaPlanos) return;
    const itens = Array.from(planosSel.values());
    if (!itens.length) {
      el.listaPlanos.innerHTML = '<li class="Cup_Empty">Nenhum plano selecionado (vale para todos).</li>';
      fillPlanoCombo();
      return;
    }
    el.listaPlanos.innerHTML = itens
      .map(function (p) {
        const key = p.key || p.slug;
        return (
          '<li class="Cup_Chip" data-pkey="' +
          esc(key) +
          '"><div><strong>' +
          esc(p.nome || key) +
          "</strong><span>" +
          esc(key) +
          '</span></div><button type="button" class="Cl_BtnCancelar" data-rm-plano="' +
          esc(key) +
          '">Remover</button></li>'
        );
      })
      .join("");
    el.listaPlanos.querySelectorAll("[data-rm-plano]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        planosSel.delete(btn.getAttribute("data-rm-plano"));
        renderPlanos();
      });
    });
    fillPlanoCombo();
  }

  function limparForm() {
    if (el.id) el.id.value = "";
    if (el.codigo) el.codigo.value = "";
    if (el.descricao) el.descricao.value = "";
    if (el.ativo) el.ativo.checked = true;
    if (el.tipo) el.tipo.value = "percentual";
    if (el.valor) el.valor.value = "10";
    if (el.periodo) el.periodo.value = "mensal";
    if (el.publico) el.publico.value = "";
    if (el.valido) el.valido.value = "";
    if (el.usos) el.usos.value = "";
    tenantsSel.clear();
    planosSel.clear();
    renderTenants();
    renderPlanos();
    syncValorLabel();
    ativarAba("geral");
  }

  function preencher(d) {
    if (el.id) el.id.value = d.id || "";
    if (el.codigo) el.codigo.value = d.codigo || "";
    if (el.descricao) el.descricao.value = d.descricao || "";
    if (el.ativo) el.ativo.checked = !!d.ativo;
    if (el.tipo) el.tipo.value = d.tipo_desconto || "percentual";
    if (el.valor) el.valor.value = d.valor_desconto ?? 0;
    if (el.periodo) el.periodo.value = d.periodo || "mensal";
    if (el.publico) el.publico.value = d.publico_alvo || "";
    if (el.valido) el.valido.value = d.valido_ate || "";
    if (el.usos) el.usos.value = d.usos_max == null ? "" : d.usos_max;

    tenantsSel.clear();
    (d.ids_tenants || []).forEach(function (tid) {
      const t = tenantsCache.find(function (x) {
        return +x.id === +tid;
      });
      tenantsSel.set(+tid, t || { id: +tid, nome: "Tenant #" + tid, slug: "", tipo_negocio: "" });
    });
    planosSel.clear();
    (d.planos_slug || []).forEach(function (chave) {
      const p = planosCache.find(function (x) {
        return (x.key || x.slug) === chave || x.slug === chave;
      });
      if (p) {
        planosSel.set(p.key || p.slug, p);
      } else {
        planosSel.set(chave, { key: chave, slug: chave, nome: chave });
      }
    });
    renderTenants();
    renderPlanos();
    syncValorLabel();
  }

  async function carregarCombos() {
    const r = await fetch(cfg.apiCombos, { headers: { Accept: "application/json" } });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar combos.");
    tenantsCache = j.tenants || [];
    planosCache = j.planos || [];
    fillTenantCombo();
    fillPlanoCombo();
  }

  async function carregarApoio(id) {
    const r = await fetch(cfg.apiApoio, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ id: id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar cupom.");
    if (j.tenants) tenantsCache = j.tenants;
    if (j.planos) planosCache = j.planos;
    preencher(j.dados || {});
  }

  async function salvar() {
    const codigo = (el.codigo?.value || "").trim();
    if (codigo.length < 3) {
      await Swal.fire("Atenção", "Informe um código com ao menos 3 caracteres.", "warning");
      return;
    }
    const body = {
      id: idCupom > 0 ? idCupom : null,
      codigo: codigo,
      descricao: (el.descricao?.value || "").trim(),
      tipo_desconto: el.tipo?.value || "percentual",
      valor_desconto: el.valor?.value,
      periodo: el.periodo?.value || "mensal",
      publico_alvo: el.publico?.value || "",
      ids_tenants: Array.from(tenantsSel.keys()),
      planos_slug: Array.from(planosSel.keys()),
      valido_ate: el.valido?.value || null,
      usos_max: el.usos?.value || null,
      ativo: !!el.ativo?.checked,
    };
    const r = await fetch(cfg.apiSalvar, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    await Swal.fire("Sucesso", j.message || "Cupom salvo.", "success");
    window.parent.postMessage({ grupo: "atualizarTabela", nivel: nivelModal }, "*");
    window.parent.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  el.tipo?.addEventListener("change", syncValorLabel);
  el.btnAddTenant?.addEventListener("click", function () {
    const tid = +(el.tenantCombo?.value || 0);
    if (!tid) return;
    const t = tenantsCache.find(function (x) {
      return +x.id === tid;
    });
    if (!t) return;
    tenantsSel.set(tid, t);
    renderTenants();
  });
  el.btnAddPlano?.addEventListener("click", function () {
    const key = (el.planoCombo?.value || "").trim();
    if (!key) return;
    const p = planosCache.find(function (x) {
      return (x.key || x.slug) === key;
    });
    if (!p) return;
    planosSel.set(p.key || p.slug, p);
    renderPlanos();
  });
  el.btnSalvar?.addEventListener("click", function () {
    salvar().catch(function (e) {
      Swal.fire("Erro", e.message, "error");
    });
  });
  el.btnCancelar?.addEventListener("click", function () {
    window.parent.GlobalUtils?.fecharJanelaApoio(nivelModal);
  });
  document.querySelectorAll(".Cup_SideTab").forEach(function (btn) {
    btn.addEventListener("click", function () {
      ativarAba(btn.dataset.tab);
    });
  });

  async function aplicarId(id, nivel) {
    idCupom = id ? Number(id) : 0;
    nivelModal = nivel || 1;
    if (el.id) el.id.value = idCupom ? String(idCupom) : "";
    try {
      await carregarCombos();
      if (idCupom > 0) await carregarApoio(idCupom);
      else limparForm();
    } catch (e) {
      Swal.fire("Erro", e.message, "error");
    }
  }

  if (window.GlobalUtils?.receberDadosApoio) {
    window.GlobalUtils.receberDadosApoio(function (id, nivel) {
      aplicarId(id, nivel);
    });
  } else {
    const params = new URLSearchParams(window.location.search);
    aplicarId(params.get("id"), params.get("nivel") || 1);
  }
})();
