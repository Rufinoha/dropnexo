(function () {
  let idMenu = null;
  let nivelModal = 1;

  const BASE = "/configuracoes/itens-menu";

  const el = {
    id: document.getElementById("id"),
    nome_menu: document.getElementById("nome_menu"),
    descricao: document.getElementById("descricao"),
    data_page: document.getElementById("data_page"),
    nav_codigo: document.getElementById("nav_codigo"),
    icone: document.getElementById("icone"),
    tipo_abrir: document.getElementById("tipo_abrir"),
    parent_id: document.getElementById("parent_id"),
    modulo: document.getElementById("modulo"),
    sequencia: document.getElementById("sequencia"),
    statusToggle: document.getElementById("statusToggle"),
    paiToggle: document.getElementById("paiToggle"),
    obs: document.getElementById("obs"),
    btnSalvar: document.getElementById("btnSalvar"),
    btnExcluir: document.getElementById("btnExcluir"),
  };
  if (!el.nome_menu) return;

  function montarComboIcones(extras) {
    el.icone.innerHTML = "";
    const oVazio = document.createElement("option");
    oVazio.value = "";
    oVazio.textContent = "(sem ícone)";
    el.icone.appendChild(oVazio);

    const catalogo =
      typeof window.Util?.listarIconesTech === "function"
        ? window.Util.listarIconesTech({ incluirFa: true })
        : [];
    const set = new Set();
    catalogo.forEach((k) => set.add(String(k).trim()));
    (extras || []).forEach((k) => {
      const s = String(k || "").trim();
      if (s) set.add(s);
    });

    [...set].sort((a, b) => a.localeCompare(b, "pt-BR")).forEach((nome) => {
      const o = document.createElement("option");
      o.value = nome;
      o.textContent = nome;
      el.icone.appendChild(o);
    });
  }

  async function carregarCombos() {
    const r = await fetch(`${BASE}/combos`);
    const c = await r.json();
    if (!r.ok) throw new Error(c.erro || c.message || "Erro ao carregar combos.");

    montarComboIcones(c.icones_em_uso || c.icones || []);
    (c.tipos_abrir || []).forEach((nome) => {
      const o = document.createElement("option");
      o.value = nome;
      o.textContent = nome;
      el.tipo_abrir.appendChild(o);
    });

    const oVazio = document.createElement("option");
    oVazio.value = "";
    oVazio.textContent = "(sem parent)";
    el.parent_id.appendChild(oVazio);
    (c.pais || []).forEach((p) => {
      const o = document.createElement("option");
      o.value = p.id;
      o.textContent = `${p.nome_menu} (${p.id})`;
      el.parent_id.appendChild(o);
    });

    const oModVazio = document.createElement("option");
    oModVazio.value = "";
    oModVazio.textContent = "(sem módulo)";
    el.modulo.appendChild(oModVazio);
    (c.modulos || []).forEach((m) => {
      const o = document.createElement("option");
      o.value = m.id;
      o.textContent = m.nome;
      el.modulo.appendChild(o);
    });
  }

  async function carregarApoio(id) {
    const r = await fetch(`${BASE}/apoio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const d = await r.json();
    if (!r.ok) throw new Error(d.erro || d.message || "Erro ao carregar menu.");

    el.nome_menu.value = d.nome_menu || "";
    el.descricao.value = d.descricao || "";
    el.data_page.value = d.data_page || "";
    if (el.nav_codigo) el.nav_codigo.value = d.nav_codigo || "";
    const iconeSalvo = (d.icone || "").trim();
    if (iconeSalvo && !Array.from(el.icone.options).some((o) => o.value === iconeSalvo)) {
      const o = document.createElement("option");
      o.value = iconeSalvo;
      o.textContent = `${iconeSalvo} (não catalogado)`;
      el.icone.appendChild(o);
    }
    el.icone.value = iconeSalvo;
    el.tipo_abrir.value = d.tipo_abrir || "";
    el.parent_id.value = d.parent_id || "";
    el.modulo.value = d.id_modulo || "";
    el.sequencia.value = d.sequencia ?? "";
    el.statusToggle.checked = !!d.status;
    el.paiToggle.checked = !!d.pai;
    el.obs.value = d.obs || "";
  }

  async function salvar() {
    const body = {
      id: idMenu,
      nome_menu: (el.nome_menu.value || "").trim(),
      descricao: (el.descricao.value || "").trim(),
      data_page: (el.data_page.value || "").trim(),
      nav_codigo: el.nav_codigo ? (el.nav_codigo.value || "").trim() : "",
      icone: el.icone.value || "",
      tipo_abrir: el.tipo_abrir.value || "",
      parent_id: el.parent_id.value || null,
      id_modulo: el.modulo.value ? Number(el.modulo.value) : null,
      sequencia: el.sequencia.value ? Number(el.sequencia.value) : null,
      status: !!el.statusToggle.checked,
      pai: !!el.paiToggle.checked,
      obs: (el.obs.value || "").trim(),
    };
    if (!body.nome_menu) {
      await Swal.fire("Atenção", "Informe o nome do menu.", "warning");
      return;
    }

    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.erro || j.message || "Erro ao salvar menu.");

    const q = await Swal.fire({
      title: "Menu salvo!",
      text: "Deseja cadastrar outro?",
      icon: "success",
      showCancelButton: true,
      confirmButtonText: "Sim",
      cancelButtonText: "Não",
    });
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    if (q.isConfirmed) {
      idMenu = null;
      if (el.id) el.id.value = "";
      el.nome_menu.value = "";
      el.descricao.value = "";
      el.data_page.value = "";
      if (el.nav_codigo) el.nav_codigo.value = "";
      el.parent_id.value = "";
      el.sequencia.value = "";
      el.obs.value = "";
      el.statusToggle.checked = true;
      el.paiToggle.checked = false;
      return;
    }
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  async function excluir() {
    if (!idMenu) {
      await Swal.fire("Atenção", "Nada para excluir.", "info");
      return;
    }
    const c = await Swal.fire({
      title: "Excluir menu?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, excluir",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;

    const r = await fetch(`${BASE}/delete`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idMenu }),
    });
    const j = await r.json();
    if (!r.ok || !j.ok) throw new Error(j.erro || j.message || "Erro ao excluir.");
    await Swal.fire("Sucesso", "Menu excluído.", "success");
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  el.btnSalvar?.addEventListener("click", () =>
    salvar().catch((e) => Swal.fire("Erro", e.message, "error"))
  );
  el.btnExcluir?.addEventListener("click", () =>
    excluir().catch((e) => Swal.fire("Erro", e.message, "error"))
  );

  let combosProntos = false;
  let idPendenteParaApoio = null;

  async function aplicarRecebimentoModal(id, nivel) {
    idMenu = id != null && id !== "" ? id : null;
    nivelModal = nivel || 1;
    if (el.id) el.id.value = idMenu ? String(idMenu) : "";
    if (!idMenu) return;
    if (!combosProntos) {
      idPendenteParaApoio = idMenu;
      return;
    }
    await carregarApoio(idMenu);
  }

  if (window.GlobalUtils?.receberDadosApoio) {
    window.GlobalUtils.receberDadosApoio((id, nivel) => {
      aplicarRecebimentoModal(id, nivel);
    });
  }

  carregarCombos()
    .then(async () => {
      combosProntos = true;
      if (idPendenteParaApoio != null) {
        const id = idPendenteParaApoio;
        idPendenteParaApoio = null;
        await carregarApoio(id);
      }
    })
    .catch((e) => Swal.fire("Erro", e.message, "error"));
})();
