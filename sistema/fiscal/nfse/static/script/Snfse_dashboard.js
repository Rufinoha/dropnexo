(function () {
  const reais = (v) => Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const META_CHAVE = "h74_nfse_meta_mensal";
  const MESES = ["JAN", "FEV", "MAR", "ABR", "MAI", "JUN", "JUL", "AGO", "SET", "OUT", "NOV", "DEZ"];
  let ano = new Date().getFullYear();
  let ultimo = null;

  function lerMeta(texto) {
    const limpo = String(texto ?? "").trim();
    if (!limpo) return 0;
    const normal = limpo.includes(",")
      ? limpo.replace(/\./g, "").replace(",", ".")
      : limpo.replace(/\./g, "");
    const n = Number(normal.replace(/[^\d.-]/g, ""));
    return Number.isFinite(n) && n > 0 ? n : 0;
  }
  function metaAtual() {
    const salva = lerMeta(localStorage.getItem(META_CHAVE) || "");
    return salva || 20000;
  }
  function formatarMeta(valor) {
    return Number(valor || 0).toLocaleString("pt-BR", { maximumFractionDigits: 0 });
  }
  function pctTexto(valor) {
    if (valor == null || Number.isNaN(Number(valor))) return "—";
    const n = Math.round(Number(valor) * 1000) / 10;
    return (n > 0 ? "+" : "") + n.toLocaleString("pt-BR") + "%";
  }
  function distancia(a, b) {
    return (b.ano - a.ano) * 12 + (b.mes - a.mes);
  }

  function kpis(j) {
    const cards = [
      ["Faturado no ano", reais(j.total_ano), `${j.qtd_ano} nota${j.qtd_ano === 1 ? "" : "s"}`],
      [j.ano === j.hoje_ano ? j.mes_foco_nome : `Melhor mês · ${j.mes_foco_nome}`, reais(j.total_mes), `${j.qtd_mes} nota${j.qtd_mes === 1 ? "" : "s"}`],
      ["Notas autorizadas", String(j.qtd_ano), "Canceladas não entram"],
      ["Ticket médio", reais(j.ticket), "Valor médio da nota"],
    ];
    dashKpis.innerHTML = cards.map(([rotulo, valor, detalhe]) =>
      `<article class="NfDash_Kpi"><span>${esc(rotulo)}</span><strong>${esc(valor)}</strong><small>${esc(detalhe)}</small></article>`
    ).join("");
  }

  function grafico(j) {
    dashTitulo.textContent = `Ano ${j.ano} — Faturamento`;
    dashTotalAno.textContent = `Ano ${j.ano} · ${reais(j.total_ano)} faturados`;
    const max = Math.max(...j.meses.map((m) => Number(m.total) || 0), 0);
    dashChart.innerHTML = j.meses.map((m) => {
      const total = Number(m.total) || 0;
      const tem = total > 0;
      const altura = tem ? Math.max(8, Math.round((total / max) * 100)) : 0;
      const atual = j.ano === j.hoje_ano && m.mes === j.hoje_mes;
      const titulo = tem ? `${m.nome}: ${reais(total)} · ${m.qtd} nota${m.qtd === 1 ? "" : "s"}` : `${m.nome}: sem nota autorizada`;
      return `<div class="NfDash_Col${atual ? " is-atual" : ""}" title="${esc(titulo)}">
        <span class="NfDash_Val${tem ? " is-on" : ""}">${tem ? esc(reais(total)) : "—"}</span>
        <div class="NfDash_Track"><div class="NfDash_Bar" style="height:${altura}%"></div></div>
        <span class="NfDash_Mes">${esc(m.label)}</span>
      </div>`;
    }).join("");
  }

  function clientes(j) {
    if (!j.clientes.length) {
      dashClientes.innerHTML = '<li class="NfDash_Vazio">Nenhuma NFS-e autorizada neste ano.</li>';
      return;
    }
    const topo = Math.max(...j.clientes.map((c) => Number(c.total) || 0), 1);
    dashClientes.innerHTML = j.clientes.map((c, i) => {
      const largura = Math.max(6, Math.round((Number(c.total) / topo) * 100));
      return `<li>
        <span class="NfDash_Pos">${i + 1}</span>
        <div>
          <strong>${esc(c.nome)}</strong>
          <div class="NfDash_Faixa"><i style="width:${largura}%"></i></div>
        </div>
        <em>${c.qtd} nota${c.qtd === 1 ? "" : "s"}</em>
        <b>${esc(reais(c.total))}</b>
      </li>`;
    }).join("");
  }

  function projecao(j) {
    const p = j.projecao;
    if (!p) return;
    const meta = metaAtual();
    dashMeta.value = formatarMeta(meta);
    const ritmo = Number(p.ritmo_mensal) || 0;
    const base = p.meses_ritmo || [];
    const origem = base[base.length - 1];
    const passosTotal = origem ? distancia(origem, { ano: 2027, mes: 12 }) : 0;
    const nomes = base.map((m) => m.nome.toLowerCase());
    const listaNomes = nomes.length > 1
      ? nomes.slice(0, -1).join(", ") + " e " + nomes[nomes.length - 1]
      : (nomes[0] || "os meses fechados");
    const crescimento = ritmo > 0 && meta > ritmo && passosTotal > 0
      ? Math.pow(meta / ritmo, 1 / passosTotal) - 1
      : (ritmo > 0 && meta <= ritmo ? 0 : null);
    const caminho = [];
    for (let mes = 1; mes <= 12; mes++) {
      if (!(ritmo > 0) || !origem || passosTotal <= 0) {
        caminho.push(0);
        continue;
      }
      if (meta <= ritmo) {
        caminho.push(ritmo);
        continue;
      }
      const passos = distancia(origem, { ano: 2027, mes });
      caminho.push(ritmo * Math.pow(meta / ritmo, passos / passosTotal));
    }
    const anualRitmo = ritmo * 12;
    const anualMeta = meta * 12;
    let texto = `Média de ${listaNomes}, sem contar o mês que ainda está aberto.`;
    if (!(ritmo > 0)) {
      texto = "Ainda não há meses fechados com NFS-e autorizada para projetar 2027.";
    } else if (meta <= ritmo) {
      texto = `O ritmo atual já passa da meta de ${reais(meta)} por mês. Se ele se mantiver, 2027 fecha em ${reais(anualRitmo)}.`;
    } else {
      texto = `Para chegar a ${reais(meta)} por mês em dezembro de 2027, o faturamento precisa crescer cerca de ${pctTexto(crescimento)} ao mês.`;
    }
    dashProjecaoTexto.textContent = texto;
    const recente = p.variacao_recente == null || base.length < 2
      ? "Sem variação mensal ainda."
      : `${base[base.length - 2].nome} → ${base[base.length - 1].nome}: ${pctTexto(p.variacao_recente)}.`;
    const cards = [
      ["Ritmo atual", reais(ritmo), `Média de ${listaNomes}`],
      ["Crescimento até a meta", crescimento == null ? "—" : (crescimento === 0 ? "Meta já coberta" : pctTexto(crescimento) + " ao mês"), crescimento === 0 ? `Ano no ritmo: ${reais(anualRitmo)}` : `Ano na meta: ${reais(anualMeta)}`],
      ["Comparativo anual", p.variacao_anual == null ? "—" : pctTexto(p.variacao_anual), p.variacao_anual == null ? `${p.ano_anterior} sem nota neste período. ${recente}` : recente],
    ];
    dashProjecaoKpis.innerHTML = cards.map(([rotulo, valor, detalhe]) =>
      `<article class="NfDash_Kpi"><span>${esc(rotulo)}</span><strong>${esc(valor)}</strong><small>${esc(detalhe)}</small></article>`
    ).join("");
    const topo = Math.max(meta, ritmo, ...caminho, 1) * 1.12;
    dashProjecaoChart.innerHTML = caminho.map((valor, i) => {
      const alturaCaminho = valor > 0 ? Math.max(6, Math.round((valor / topo) * 100)) : 0;
      const alturaRitmo = ritmo > 0 ? Math.max(6, Math.round((ritmo / topo) * 100)) : 0;
      const linha = Math.round((meta / topo) * 100);
      const titulo = `${MESES[i]} de 2027: caminho ${reais(valor)} · ritmo ${reais(ritmo)} · meta ${reais(meta)}`;
      return `<div class="NfDash_Col" title="${esc(titulo)}">
        <span class="NfDash_Val${valor ? " is-on" : ""}">${valor ? esc(reais(valor)) : "—"}</span>
        <div class="NfDash_Track">
          <i class="NfDash_MetaMarca" style="bottom:${linha}%"></i>
          <div class="NfDash_Bar is-ritmo" style="height:${alturaRitmo}%"></div>
          <div class="NfDash_Bar is-caminho" style="height:${alturaCaminho}%"></div>
        </div>
        <span class="NfDash_Mes">${MESES[i]}</span>
      </div>`;
    }).join("");
  }

  function preencherAnos(j) {
    const sel = dashAno;
    const atual = String(j.ano);
    sel.innerHTML = j.anos.map((a) => `<option value="${a}">${a}</option>`).join("");
    sel.value = atual;
  }

  async function carregar() {
    const r = await GlobalUtils.requestJSON({ url: `/nfse/api/dashboard?ano=${ano}` });
    if (!r?.ok) return;
    const j = r.json;
    ultimo = j;
    ano = j.ano;
    preencherAnos(j);
    kpis(j);
    grafico(j);
    projecao(j);
    clientes(j);
  }

  dashMeta.addEventListener("change", () => {
    const valor = lerMeta(dashMeta.value) || 20000;
    localStorage.setItem(META_CHAVE, String(valor));
    if (ultimo) projecao(ultimo);
  });

  dashAno.addEventListener("change", () => {
    ano = Number(dashAno.value) || ano;
    carregar();
  });
  carregar();
})();
