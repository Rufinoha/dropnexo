(function () {
  const BASE = "/configuracoes/manutencao-tenant";
  let indicados = [];
  let impostos = [];
  let buscaTimer = null;

  const el = {
    ativo: document.getElementById("com_ativo"),
    corpo: document.getElementById("com_corpo"),
    proprio: document.getElementById("com_proprio"),
    indicado: document.getElementById("com_indicado"),
    base: document.getElementById("com_base"),
    impostos: document.getElementById("com_impostos"),
    preview: document.getElementById("com_preview"),
    busca: document.getElementById("com_busca"),
    buscaLista: document.getElementById("com_busca_lista"),
    indicados: document.getElementById("com_indicados"),
    vendedores: document.getElementById("com_vendedores"),
    pai: document.getElementById("com_pai"),
    salvar: document.getElementById("com_salvar"),
    add: document.getElementById("com_add_imposto"),
  };

  function tid() {
    return Number(document.getElementById("id")?.value || 0) || 0;
  }

  function syncCorpo() {
    const on = !!el.ativo?.checked;
    if (el.corpo) el.corpo.classList.toggle("is-off", !on);
  }

  function lerImpostos() {
    const rows = el.impostos?.querySelectorAll(".CfgMt_Imposto") || [];
    const out = [];
    rows.forEach((row) => {
      const nome = (row.querySelector("[data-nome]")?.value || "").trim();
      const percentual = Number(row.querySelector("[data-pct]")?.value || 0);
      if (nome) out.push({ nome, percentual });
    });
    return out;
  }

  function preview() {
    const pct = Number(el.proprio?.value || 0);
    const lista = lerImpostos();
    const taxa = lista.reduce((s, i) => s + Number(i.percentual || 0), 0);
    const base = el.base?.value === "liquido" ? 100 * (1 - Math.min(taxa, 100) / 100) : 100;
    const com = (base * Math.min(Math.max(pct, 0), 100)) / 100;
    if (el.preview) {
      el.preview.textContent = `Exemplo em R$ 100,00: comissão de ${com.toLocaleString("pt-BR", {
        style: "currency",
        currency: "BRL",
      })}.`;
    }
  }

  function renderImpostos() {
    if (!el.impostos) return;
    el.impostos.innerHTML = impostos
      .map(
        (i, idx) => `
        <div class="CfgMt_Imposto">
          <input type="text" data-nome maxlength="40" value="${esc(i.nome || "")}" placeholder="Nome" />
          <input type="number" data-pct min="0" max="100" step="0.01" value="${Number(i.percentual || 0)}" />
          <button type="button" class="Cl_BtnAuxiliar" data-rm="${idx}">Tirar</button>
        </div>`
      )
      .join("");
    preview();
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function renderIndicados() {
    if (!el.indicados) return;
    el.indicados.innerHTML = indicados.length
      ? indicados
          .map(
            (i) =>
              `<li><span>${esc(i.nome)}</span><button type="button" data-ind="${i.id}">Remover</button></li>`
          )
          .join("")
      : `<li class="is-empty">Nenhum indicado.</li>`;
  }

  function renderVendedores(lista) {
    if (!el.vendedores) return;
    el.vendedores.innerHTML = lista.length
      ? lista
          .map((v) => {
            const outro = v.marcado_em && !v.recebe_aqui ? `Comissão com ${v.marcado_nome}` : "";
            return `<li>
              <label>
                <input type="checkbox" data-vend="${v.id}" ${v.recebe_aqui ? "checked" : ""} />
                <span>${esc(v.nome)}</span>
                <em>${esc(v.vinculo || "")}</em>
              </label>
              ${outro ? `<small>${esc(outro)}</small>` : ""}
            </li>`;
          })
          .join("")
      : `<li class="is-empty">Nenhum vendedor vinculado.</li>`;
  }

  function preencher(j) {
    if (el.ativo) el.ativo.checked = !!j.ativo;
    if (el.proprio) el.proprio.value = j.percentual_proprio ?? 0;
    if (el.indicado) el.indicado.value = j.percentual_indicado ?? 0;
    if (el.base) el.base.value = j.base === "liquido" ? "liquido" : "faturamento";
    impostos = Array.isArray(j.impostos) ? j.impostos : [];
    indicados = Array.isArray(j.indicados) ? j.indicados : [];
    if (el.pai) {
      el.pai.hidden = !j.pai_nome;
      el.pai.textContent = j.pai_nome
        ? `Indicado por ${j.pai_nome}. A comissão nova vai para essa conta.`
        : "";
    }
    if (el.ativo) el.ativo.disabled = !!j.pai_id;
    renderImpostos();
    renderIndicados();
    renderVendedores(j.vendedores || []);
    syncCorpo();
  }

  async function carregar() {
    const id = tid();
    if (!id) return;
    const r = await fetch(`${BASE}/${id}/comissao`, { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar a comissão.");
    preencher(j);
  }

  async function salvar() {
    const id = tid();
    if (!id) return;
    const vendedores = [];
    el.vendedores?.querySelectorAll("[data-vend]").forEach((c) => {
      if (c.checked) vendedores.push(Number(c.dataset.vend));
    });
    const body = {
      ativo: !!el.ativo?.checked,
      base: el.base?.value || "faturamento",
      percentual_proprio: Number(el.proprio?.value || 0),
      percentual_indicado: Number(el.indicado?.value || 0),
      impostos: lerImpostos(),
      indicados: indicados.map((i) => i.id),
      vendedores,
    };
    Swal.fire({ title: "Salvando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    const r = await fetch(`${BASE}/${id}/comissao`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao salvar.");
    preencher(j);
    await Swal.fire({ icon: "success", title: "Comissão salva", confirmButtonColor: "#021F81" });
  }

  el.ativo?.addEventListener("change", () => {
    syncCorpo();
    preview();
  });
  el.proprio?.addEventListener("input", preview);
  el.base?.addEventListener("change", preview);
  el.add?.addEventListener("click", () => {
    impostos = lerImpostos();
    impostos.push({ nome: "", percentual: 0 });
    renderImpostos();
  });
  el.impostos?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-rm]");
    if (!btn) return;
    impostos = lerImpostos();
    impostos.splice(Number(btn.dataset.rm), 1);
    renderImpostos();
  });
  el.impostos?.addEventListener("input", preview);
  el.indicados?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-ind]");
    if (!btn) return;
    indicados = indicados.filter((i) => i.id !== Number(btn.dataset.ind));
    renderIndicados();
  });
  el.salvar?.addEventListener("click", () => salvar().catch((e) => Swal.fire("Erro", e.message, "error")));

  el.busca?.addEventListener("input", () => {
    clearTimeout(buscaTimer);
    const q = (el.busca.value || "").trim();
    if (q.length < 2) {
      if (el.buscaLista) el.buscaLista.hidden = true;
      return;
    }
    buscaTimer = setTimeout(async () => {
      const id = tid();
      const r = await fetch(`${BASE}/${id}/comissao/busca?q=${encodeURIComponent(q)}`, { credentials: "same-origin" });
      const j = await r.json().catch(() => ({}));
      const itens = (j.itens || []).filter((i) => !indicados.some((x) => x.id === i.id));
      if (!el.buscaLista) return;
      el.buscaLista.hidden = !itens.length;
      el.buscaLista.innerHTML = itens
        .map((i) => `<button type="button" data-pick="${i.id}" data-nome="${esc(i.nome)}">${esc(i.nome)}</button>`)
        .join("");
    }, 250);
  });
  el.buscaLista?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-pick]");
    if (!btn) return;
    const id = Number(btn.dataset.pick);
    if (!indicados.some((i) => i.id === id)) indicados.push({ id, nome: btn.dataset.nome || "" });
    renderIndicados();
    if (el.busca) el.busca.value = "";
    el.buscaLista.hidden = true;
  });

  document.addEventListener("cfg-comissao-abrir", () => {
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
})();
