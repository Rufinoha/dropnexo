(function () {
  const MODO_SUGESTAO = "sugestao_fornecedor";
  const MODO_MARGEM = "margem_drop";

  const el = {
    escopo: document.getElementById("escopo"),
    idSegmento: document.getElementById("id_segmento"),
    wrapSegmento: document.getElementById("wrap_segmento"),
    pctMargem: document.getElementById("pct_margem_lucro"),
    arredondamento: document.getElementById("arredondamento_centavos"),
    margemMin: document.getElementById("margem_minima_alerta"),
    blocoMargem: document.getElementById("prec_bloco_margem"),
    blocoAlertaMin: document.getElementById("prec_bloco_alerta_min"),
    btnSalvar: document.getElementById("btn_salvar"),
    btnAplicar: document.getElementById("btn_aplicar"),
    msg: document.getElementById("prec_msg"),
    tbody: document.getElementById("prec_tbody"),
    tabelaWrap: document.getElementById("prec_tabela_wrap"),
    semAlertas: document.getElementById("prec_sem_alertas"),
    resSemPreco: document.getElementById("res_sem_preco"),
    resMargem: document.getElementById("res_margem_baixa"),
    resSemDrop: document.getElementById("res_sem_valor_drop"),
    alertaDesc: document.getElementById("prec_alerta_desc"),
    resumoItens: document.querySelectorAll(".Prec_ResumoItem"),
  };

  const fmtMoeda = (v) =>
    Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

  const fmtPct = (v) => (v == null ? "—" : `${Number(v).toFixed(1)}%`);

  const modoSelecionado = () =>
    document.querySelector('input[name="modo"]:checked')?.value || MODO_SUGESTAO;

  const labelsAlerta = {
    sem_preco: "Sem preço sugerido",
    margem_baixa: "Margem abaixo do mínimo",
    sem_valor_drop: "Sem valor Drop",
  };

  function atualizarVisibilidadeModo() {
    const modo = modoSelecionado();
    const margem = modo === MODO_MARGEM;
    el.blocoMargem.hidden = !margem;
    el.blocoAlertaMin.hidden = margem;

    el.resumoItens.forEach((item) => {
      const tipo = item.dataset.tipo;
      if (tipo === "sem_valor_drop") item.hidden = !margem;
      if (tipo === "sem_preco" || tipo === "margem_baixa") item.hidden = margem;
    });

    el.alertaDesc.textContent = margem
      ? "Modo margem sobre Drop: alerta apenas quando o valor Drop estiver zerado ou ausente."
      : "Modo sugestão do fornecedor: alerta quando não houver preço sugerido ou a margem ficar abaixo do mínimo.";
  }

  function setBotoesCarregando(carregando) {
    el.btnSalvar.disabled = carregando;
    el.btnAplicar.disabled = carregando;
  }

  let regrasCache = [];
  let defaultsCache = {};

  function regraAtiva() {
    const escopo = el.escopo.value;
    if (escopo === "segmento") {
      const idSeg = +el.idSegmento.value;
      return regrasCache.find((x) => x.escopo === "segmento" && +x.id_segmento === idSeg);
    }
    return regrasCache.find((x) => x.escopo === "global");
  }

  function aoMudarEscopo() {
    const seg = el.escopo.value === "segmento";
    if (el.wrapSegmento) el.wrapSegmento.hidden = !seg;
    preencherFormulario(regraAtiva(), defaultsCache);
  }

  function mostrarMsg(texto, erro) {
    el.msg.textContent = texto;
    el.msg.hidden = !texto;
    el.msg.classList.toggle("is-erro", !!erro);
  }

  function preencherFormulario(regra, defaults) {
    const g = regra || defaults || {};
    if (g.modo) {
      const radio = document.querySelector(`input[name="modo"][value="${g.modo}"]`);
      if (radio) radio.checked = true;
    }
    if (el.pctMargem) el.pctMargem.value = g.pct_margem_lucro ?? 30;
    if (el.margemMin) el.margemMin.value = g.margem_minima_alerta ?? 30;
    if (el.arredondamento) {
      el.arredondamento.value =
        g.arredondamento_centavos == null ? "" : String(g.arredondamento_centavos);
    }
    atualizarVisibilidadeModo();
  }

  function renderAlertas(alertas) {
    const res = alertas?.resumo || {};
    el.resSemPreco.textContent = res.sem_preco || 0;
    el.resMargem.textContent = res.margem_baixa || 0;
    el.resSemDrop.textContent = res.sem_valor_drop || 0;

    const itens = alertas?.itens || [];
    const tem = itens.length > 0;
    el.tabelaWrap.hidden = !tem;
    el.semAlertas.hidden = tem;

    el.tbody.innerHTML = itens
      .map(
        (i) => `
      <tr>
        <td>${escapeHtml(i.nome || "")}</td>
        <td>${escapeHtml(i.sku || "")}</td>
        <td>${fmtMoeda(i.valor_drop)}</td>
        <td>${fmtMoeda(i.preco_sugerido)}</td>
        <td>${fmtPct(i.margem_pct)}</td>
        <td><span class="Prec_Badge Prec_Badge--${i.tipo}">${labelsAlerta[i.tipo] || i.tipo}</span></td>
      </tr>`
      )
      .join("");
  }

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function corpoSalvar() {
    const arred = el.arredondamento.value;
    return {
      escopo: el.escopo.value,
      id_segmento: el.escopo.value === "segmento" ? el.idSegmento.value : null,
      modo: modoSelecionado(),
      pct_margem_lucro: +el.pctMargem.value,
      margem_minima_alerta: +el.margemMin.value,
      arredondamento_centavos: arred === "" ? null : +arred,
    };
  }

  async function carregar() {
    const r = await fetch("/vendedor/precificacao/dados", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;

    el.idSegmento.innerHTML = "";
    (j.segmentos || []).forEach((s) => {
      const o = document.createElement("option");
      o.value = s.id;
      o.textContent = s.nome;
      el.idSegmento.appendChild(o);
    });

    const global = (j.regras || []).find((x) => x.escopo === "global");
    regrasCache = j.regras || [];
    defaultsCache = j.defaults || {};
    preencherFormulario(global || regraAtiva(), defaultsCache);
    renderAlertas(j.alertas);
  }

  document.querySelectorAll('input[name="modo"]').forEach((r) => {
    r.addEventListener("change", atualizarVisibilidadeModo);
  });

  el.escopo.addEventListener("change", aoMudarEscopo);
  el.idSegmento.addEventListener("change", () => preencherFormulario(regraAtiva(), defaultsCache));

  el.btnSalvar.addEventListener("click", async () => {
    mostrarMsg("");
    setBotoesCarregando(true);
    try {
      const r = await fetch("/vendedor/precificacao/salvar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpoSalvar()),
      });
      const j = await r.json();
      mostrarMsg(j.message || (j.success ? "Salvo." : "Erro ao salvar."), !j.success);
      if (j.alertas) renderAlertas(j.alertas);
    } finally {
      setBotoesCarregando(false);
    }
  });

  el.btnAplicar.addEventListener("click", async () => {
    mostrarMsg("");
    setBotoesCarregando(true);
    try {
      const salvar = await fetch("/vendedor/precificacao/salvar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(corpoSalvar()),
      });
      const js = await salvar.json();
      if (!js.success) {
        mostrarMsg(js.message || "Erro ao salvar regra.", true);
        return;
      }

      const body = corpoSalvar();
      const r = await fetch("/vendedor/precificacao/aplicar", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          escopo: body.escopo,
          id_segmento: body.id_segmento,
        }),
      });
      const j = await r.json();
      mostrarMsg(j.message || (j.success ? "Aplicado." : "Erro ao aplicar."), !j.success);
      if (j.alertas) renderAlertas(j.alertas);
    } finally {
      setBotoesCarregando(false);
    }
  });

  carregar();
})();
