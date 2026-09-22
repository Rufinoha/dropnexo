(function () {
  const root = document.getElementById("dash_vd");
  if (!root) return;

  const loading = document.getElementById("dash_vd_loading");
  const erro = document.getElementById("dash_vd_erro");
  const alertasWrap = document.getElementById("dash_vd_alertas_wrap");
  const alertasEl = document.getElementById("dash_vd_alertas");
  const mostrarAvisos = document.getElementById("dash_vd_avisos_mostrar");
  const AVISO_KEY = "dash_vd_avisos_lidos";
  const MESES_CURTO = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"];
  const pop = document.getElementById("dash_vd_mes_pop");
  const btnMes = document.getElementById("dash_vd_rotulo");
  const grade = document.getElementById("dash_vd_mes_grade");
  const popAnoEl = document.getElementById("dash_vd_pop_ano");

  let avisosAtuais = [];
  let anoSel = null;
  let mesSel = null;
  let hojeAno = null;
  let hojeMes = null;
  let anoMin = null;
  let popAno = null;
  let ehMesAtual = true;

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function moeda(n) {
    return (Number(n) || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function curto(n) {
    const v = Math.round(Number(n) || 0);
    if (v <= 0) return "";
    if (v >= 10000) {
      const mil = v / 1000;
      const s = (mil >= 100 ? String(Math.round(mil)) : mil.toFixed(1).replace(".", ",")).replace(",0", "");
      return s + " mil";
    }
    return v.toLocaleString("pt-BR");
  }

  function lerAvisos() {
    try {
      const raw = JSON.parse(localStorage.getItem(AVISO_KEY) || "{}");
      return raw && typeof raw === "object" ? raw : {};
    } catch (e) {
      return {};
    }
  }

  function gravarAvisos(map) {
    localStorage.setItem(AVISO_KEY, JSON.stringify(map));
  }

  function chaveAviso(a) {
    return (a.tipo || "aviso") + "|" + (a.titulo || "");
  }

  function renderAlertas(list) {
    avisosAtuais = list || [];
    if (!alertasEl || !alertasWrap) return;
    if (!avisosAtuais.length) {
      alertasWrap.hidden = true;
      alertasEl.innerHTML = "";
      if (mostrarAvisos) mostrarAvisos.hidden = true;
      return;
    }
    const lidos = lerAvisos();
    const visiveis = avisosAtuais.filter((a) => !lidos[chaveAviso(a)]);
    const ocultos = avisosAtuais.length - visiveis.length;
    alertasWrap.hidden = false;
    alertasEl.innerHTML = visiveis
      .map((a) => {
        const nivel = a.nivel || "baixa";
        const texto = a.url
          ? '<a class="DashVd_AvisoTxt" href="' + esc(a.url) + '">' + esc(a.titulo) + "</a>"
          : '<span class="DashVd_AvisoTxt">' + esc(a.titulo) + "</span>";
        return (
          '<div class="DashVd_Aviso is-' + esc(nivel) + '">' +
          texto +
          '<button type="button" class="DashVd_AvisoX" data-chave="' + esc(chaveAviso(a)) +
          '" aria-label="Marcar como lido">×</button></div>'
        );
      })
      .join("");
    if (mostrarAvisos) {
      mostrarAvisos.hidden = ocultos <= 0;
      mostrarAvisos.textContent = ocultos === 1 ? "1 aviso oculto" : ocultos + " avisos ocultos";
    }
  }

  function textoDelta(k, comparacao) {
    const el = document.getElementById("dash_vd_delta");
    if (!el) return;
    el.className = "";
    const base = comparacao ? comparacao : "o mês anterior";
    if (k.delta_pct == null) {
      el.textContent = (k.vendido || 0) > 0 ? "Primeira venda neste mês" : "Nada vendido neste mês";
      return;
    }
    const n = Number(k.delta_pct);
    const sinal = n > 0 ? "+" : "";
    el.textContent = sinal + String(n).replace(".", ",") + "% em relação a " + base;
    el.classList.add(n > 0 ? "is-up" : n < 0 ? "is-down" : "");
  }

  function renderKpis(k, rotulo, comparacao) {
    const vendido = document.getElementById("dash_vd_vendido");
    const custo = document.getElementById("dash_vd_custo");
    const margem = document.getElementById("dash_vd_margem");
    const pct = document.getElementById("dash_vd_margem_pct");
    const pedidos = document.getElementById("dash_vd_pedidos");
    const titulo = document.getElementById("dash_vd_rotulo");
    if (titulo) titulo.textContent = rotulo || "Mês atual";
    if (vendido) vendido.textContent = k.vendido_fmt || "R$ 0,00";
    if (custo) custo.textContent = k.custo_fmt || "R$ 0,00";
    if (margem) {
      margem.textContent = k.margem_fmt || "R$ 0,00";
      margem.classList.toggle("is-down", (k.margem || 0) < 0);
      margem.classList.toggle("is-up", (k.margem || 0) > 0);
    }
    if (pct) {
      pct.textContent = k.margem_pct == null
        ? "Sem venda no mês"
        : String(k.margem_pct).replace(".", ",") + "% sobre o vendido";
    }
    if (pedidos) pedidos.textContent = String(k.pedidos ?? 0);
    textoDelta(k, comparacao);
    const rodape = document.getElementById("dash_vd_rodape");
    if (rodape) {
      const prod = k.produtos_ativos ?? 0;
      const forn = k.fornecedores_ativos ?? 0;
      rodape.textContent =
        prod + (prod === 1 ? " produto ativo" : " produtos ativos") +
        " · " +
        forn + (forn === 1 ? " fornecedor na rede" : " fornecedores na rede");
    }
  }

  function barra(d, max, maxH, label, valorTxt, extraCls, attrs) {
    const valor = Number(d.vendido) || 0;
    const h = max > 0 && valor > 0 ? Math.max(8, Math.round((valor / max) * maxH)) : 4;
    const zero = valor <= 0;
    const cls = "DashVd_Bar" + (d.hoje || d.atual ? " is-hoje" : "") + (zero ? " is-zero" : "") + (extraCls || "");
    return (
      '<button type="button" class="' + cls + '" style="--h:' + h + 'px"' + (attrs || "") + ">" +
      '<span class="DashVd_Tip"><b>' + esc(d.vendido_fmt || moeda(valor)) + "</b>" +
      "<span>" + esc(d.pedidos) + (d.pedidos === 1 ? " pedido" : " pedidos") + "</span>" +
      (d.margem_fmt ? "<span>Margem " + esc(d.margem_fmt) + "</span>" : "") +
      "</span>" +
      (valorTxt ? '<b class="DashVd_BarVal">' + esc(valorTxt) + "</b>" : "") +
      "<i></i><small>" + esc(label) + "</small></button>"
    );
  }

  function renderChart(serie) {
    const box = document.getElementById("dash_vd_chart");
    if (!box) return;
    const rows = serie || [];
    const legenda = document.getElementById("dash_vd_chart_legenda");
    const ultimo = rows.length ? rows[rows.length - 1].dia_num : 0;
    if (legenda && ultimo) {
      legenda.textContent = ehMesAtual
        ? "Do dia 1 ao " + ultimo + ". Ouro é hoje."
        : "Do dia 1 ao " + ultimo + ".";
    }
    if (!rows.length) {
      box.innerHTML = '<p class="DashVd_Vazio">Sem dias neste mês.</p>';
      return;
    }
    const max = Math.max(...rows.map((d) => Number(d.vendido) || 0), 0);
    box.innerHTML = rows
      .map((d, i) => {
        const valor = Number(d.vendido) || 0;
        const alt = valor > 0 && i % 2 === 1 ? " is-alt" : "";
        return barra(d, max, 108, String(d.dia_num), valor > 0 ? curto(valor) : "", alt);
      })
      .join("");
  }

  function renderAno(serie, ano) {
    const box = document.getElementById("dash_vd_ano_chart");
    const titulo = document.getElementById("dash_vd_ano");
    const totalEl = document.getElementById("dash_vd_ano_total");
    if (titulo) titulo.textContent = ano ? String(ano) : "—";
    const rows = serie || [];
    const total = rows.reduce((s, m) => s + (Number(m.vendido) || 0), 0);
    if (totalEl) {
      totalEl.textContent = total > 0 ? moeda(total) + " no ano" : "Nada vendido neste ano";
    }
    if (!box) return;
    if (!rows.length) {
      box.innerHTML = '<p class="DashVd_Vazio">Sem meses neste ano.</p>';
      return;
    }
    const max = Math.max(...rows.map((d) => Number(d.vendido) || 0), 0);
    box.innerHTML = rows
      .map((d) => {
        const valor = Number(d.vendido) || 0;
        const txt = valor > 0 ? curto(valor) : "";
        const futuro = ano != null && hojeAno != null && (ano > hojeAno || (ano === hojeAno && d.mes > hojeMes));
        const attrs = futuro ? "" : ' data-mes="' + esc(d.mes) + '"';
        return barra(d, max, 96, d.label || "", txt, futuro ? " is-futuro" : "", attrs);
      })
      .join("");
  }

  function renderTop(rows) {
    const box = document.getElementById("dash_vd_top");
    if (!box) return;
    if (!rows.length) {
      box.innerHTML = '<p class="DashVd_Vazio">Nenhum produto vendido neste mês.</p>';
      return;
    }
    box.innerHTML =
      '<ol class="DashVd_Top">' +
      rows
        .map((p, i) => {
          const down = (p.margem || 0) < 0 ? " is-down" : "";
          const pct = p.margem_pct == null ? "" : String(p.margem_pct).replace(".", ",") + "%";
          const sku = p.sku ? esc(p.sku) + " · " : "";
          return (
            "<li><span class=\"DashVd_Rank\">" + (i + 1) + "</span><div>" +
            '<span class="DashVd_TopNome">' + esc(p.nome) + "</span>" +
            '<span class="DashVd_TopMeta">' + sku + esc(p.quantidade) + " un. · " + esc(p.vendido_fmt) + "</span>" +
            "</div><div class=\"DashVd_TopMargem" + down + "\">" + esc(p.margem_fmt) +
            (pct ? "<small>" + esc(pct) + "</small>" : "") + "</div></li>"
          );
        })
        .join("") +
      "</ol>";
  }

  function fecharMes() {
    if (!pop || !btnMes) return;
    pop.hidden = true;
    btnMes.setAttribute("aria-expanded", "false");
  }

  function pintarGrade() {
    if (!grade || popAno == null) return;
    if (popAnoEl) popAnoEl.textContent = String(popAno);
    const prev = document.getElementById("dash_vd_ano_prev");
    const next = document.getElementById("dash_vd_ano_next");
    if (prev) prev.disabled = anoMin != null && popAno <= anoMin;
    if (next) next.disabled = hojeAno != null && popAno >= hojeAno;
    grade.innerHTML = MESES_CURTO.map((nome, i) => {
      const m = i + 1;
      const futuro = hojeAno != null && (popAno > hojeAno || (popAno === hojeAno && m > hojeMes));
      const on = popAno === anoSel && m === mesSel;
      const hoje = popAno === hojeAno && m === hojeMes;
      const cls = (on ? " is-on" : "") + (hoje ? " is-hoje" : "");
      return (
        '<button type="button" class="' + cls.trim() + '" data-mes="' + m + '"' +
        (futuro ? " disabled" : "") + ">" + nome + "</button>"
      );
    }).join("");
  }

  function abrirMes() {
    if (!pop || !btnMes) return;
    popAno = anoSel || hojeAno;
    pintarGrade();
    pop.hidden = false;
    btnMes.setAttribute("aria-expanded", "true");
  }

  function irPara(ano, mes) {
    anoSel = ano;
    mesSel = mes;
    fecharMes();
    carregar();
  }

  async function carregar() {
    try {
      if (erro) erro.hidden = true;
      const qs = new URLSearchParams();
      if (anoSel && mesSel) {
        qs.set("ano", String(anoSel));
        qs.set("mes", String(mesSel));
      }
      const url = "/index/dados-vendedor" + (qs.toString() ? "?" + qs.toString() : "");
      const r = await fetch(url, { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao carregar.");
      const d = j.dados || {};
      anoSel = d.ano || anoSel;
      mesSel = d.mes || mesSel;
      hojeAno = d.hoje_ano || hojeAno;
      hojeMes = d.hoje_mes || hojeMes;
      anoMin = d.ano_min || anoMin;
      ehMesAtual = !!d.eh_mes_atual;
      renderKpis(d.kpis || {}, d.rotulo, d.comparacao);
      renderChart(d.serie || []);
      renderAno(d.ano_serie || [], d.ano);
      renderTop(d.top_produtos || []);
      renderAlertas(d.alertas || []);
      if (pop && !pop.hidden) pintarGrade();
      if (loading) loading.hidden = true;
      root.removeAttribute("data-loading");
    } catch (e) {
      if (loading) loading.hidden = true;
      if (erro) {
        erro.hidden = false;
        erro.textContent = e.message || "Erro ao carregar o dashboard.";
      }
    }
  }

  if (alertasEl) {
    alertasEl.addEventListener("click", (ev) => {
      const btn = ev.target.closest(".DashVd_AvisoX");
      if (!btn) return;
      const map = lerAvisos();
      map[btn.getAttribute("data-chave") || ""] = 1;
      gravarAvisos(map);
      renderAlertas(avisosAtuais);
    });
  }

  if (mostrarAvisos) {
    mostrarAvisos.addEventListener("click", () => {
      const map = lerAvisos();
      avisosAtuais.forEach((a) => {
        delete map[chaveAviso(a)];
      });
      gravarAvisos(map);
      renderAlertas(avisosAtuais);
    });
  }

  if (btnMes) {
    btnMes.addEventListener("click", () => {
      if (pop && !pop.hidden) fecharMes();
      else abrirMes();
    });
  }

  if (grade) {
    grade.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button[data-mes]");
      if (!btn || btn.disabled || popAno == null) return;
      irPara(popAno, Number(btn.getAttribute("data-mes")));
    });
  }

  const anoPrev = document.getElementById("dash_vd_ano_prev");
  const anoNext = document.getElementById("dash_vd_ano_next");
  if (anoPrev) {
    anoPrev.addEventListener("click", () => {
      if (anoMin != null && popAno <= anoMin) return;
      popAno -= 1;
      pintarGrade();
    });
  }
  if (anoNext) {
    anoNext.addEventListener("click", () => {
      if (hojeAno != null && popAno >= hojeAno) return;
      popAno += 1;
      pintarGrade();
    });
  }

  const btnHoje = document.getElementById("dash_vd_mes_hoje");
  if (btnHoje) {
    btnHoje.addEventListener("click", () => {
      if (hojeAno && hojeMes) irPara(hojeAno, hojeMes);
    });
  }

  const anoChart = document.getElementById("dash_vd_ano_chart");
  if (anoChart) {
    anoChart.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-mes]");
      if (!btn || !anoSel) return;
      irPara(anoSel, Number(btn.getAttribute("data-mes")));
    });
  }

  document.addEventListener("click", (ev) => {
    if (!pop || pop.hidden) return;
    if (ev.target.closest(".DashVd_MesWrap")) return;
    fecharMes();
  });

  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape") fecharMes();
  });

  carregar();
})();
