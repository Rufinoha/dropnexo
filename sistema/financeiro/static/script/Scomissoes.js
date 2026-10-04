(function () {
  let dados = null;
  let aba = "previsao";
  let ano = 0;
  let mes = 0;
  let anoFaturado = 0;

  const MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
  const painel = document.getElementById("com_painel");
  const tabs = document.getElementById("com_tabs");

  function brl(cents) {
    return (Number(cents || 0) / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }
  function dataBr(iso) {
    if (!iso) return "—";
    const s = String(iso).slice(0, 10);
    const [y, m, d] = s.split("-");
    if (!y || !m || !d) return s;
    return `${d}/${m}/${y}`;
  }
  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function resumo() {
    const frase = document.getElementById("com_frase");
    const aviso = document.getElementById("com_aviso");
    if (!dados) return;
    const nPrev = document.getElementById("com_n_prev");
    const nAberto = document.getElementById("com_n_aberto");
    const nFat = document.getElementById("com_n_faturado");
    const nInad = document.getElementById("com_n_inad");
    if (nPrev) nPrev.textContent = String((dados.previsoes || []).length);
    if (nAberto) nAberto.textContent = String((dados.abertos || []).length);
    if (nFat) nFat.textContent = String((dados.faturados || []).length);
    if (nInad) nInad.textContent = String((dados.inadimplentes || []).length);
    if (frase) frase.textContent = dados.frase || "";
    if (aviso) {
      aviso.hidden = !dados.pai_nome;
      aviso.textContent = dados.pai_nome
        ? `Novas comissões vão para ${dados.pai_nome}. Aqui ficam só os valores que já estavam em aberto.`
        : "";
    }
  }

  function tabela(cols, rows, vazio) {
    if (!rows.length) return `<p class="Fin_Empty">${esc(vazio)}</p>`;
    return `<div class="Fin_TableWrap"><table class="Fin_Table"><thead><tr>${cols
      .map((c, i) => `<th${i === 0 && String(c).includes("checkbox") ? ' class="Fin_Sel"' : ""}>${c}</th>`)
      .join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
  }

  function viaDe(i) {
    return i.via ? ` <span class="Fin_Meta">via ${esc(i.via)}</span>` : "";
  }

  function htmlFiltroPeriodo() {
    const anos = dados.anos_periodo || [];
    const optsMes = MESES.slice(1)
      .map((nome, i) => `<option value="${i + 1}"${i + 1 === Number(dados.mes) ? " selected" : ""}>${nome}</option>`)
      .join("");
    const optsAno = anos
      .map((y) => `<option value="${y}"${Number(y) === Number(dados.ano) ? " selected" : ""}>${y}</option>`)
      .join("");
    return `<div class="Fin_Filtro" id="com_filtro">
      <label for="com_mes">Período</label>
      <select class="Fin_Select" id="com_mes">${optsMes}</select>
      <select class="Fin_Select" id="com_ano" aria-label="Ano">${optsAno}</select>
    </div>`;
  }

  function htmlFiltroAno() {
    const anos = dados.anos_faturado || [];
    const atual = Number(dados.ano_faturado || 0);
    const opts = [`<option value="0"${atual === 0 ? " selected" : ""}>Últimos 12 meses</option>`]
      .concat(anos.map((y) => `<option value="${y}"${Number(y) === atual ? " selected" : ""}>${y}</option>`))
      .join("");
    return `<div class="Fin_Filtro" id="com_filtro">
      <label for="com_ano_fat">Ano</label>
      <select class="Fin_Select" id="com_ano_fat">${opts}</select>
    </div>`;
  }

  function htmlPrevisao() {
    const rows = (dados.previsoes || []).map((i, idx) => {
      return `<tr>
        <td>${esc(i.vendedor)}${viaDe(i)}</td>
        <td>${esc(i.plano || "—")}</td>
        <td>${dataBr(i.vencimento_em)}</td>
        <td>${brl(i.valor_pago_centavos)}</td>
        <td><button type="button" class="Fin_ComLink" data-prev="${idx}">${brl(i.valor_comissao_centavos)}</button></td>
      </tr>`;
    });
    const [hy, hm] = String(dados.hoje || "").slice(0, 7).split("-").map(Number);
    const passado = Number(dados.ano) < hy || (Number(dados.ano) === hy && Number(dados.mes) < hm);
    const vazio = passado
      ? "Nenhuma previsão neste mês. Os vencimentos já passaram."
      : "Nenhum vencimento previsto neste mês.";
    return htmlFiltroPeriodo() + tabela(["Vendedor", "Plano", "Vencimento", "Mensalidade", "Previsão"], rows, vazio);
  }

  function htmlAberto() {
    const rows = (dados.abertos || []).map((i, idx) => {
      return `<tr>
        <td class="Fin_Sel"><input type="checkbox" class="Fin_Chk com_sel" data-id="${Number(i.id)}" data-valor="${Number(i.valor_comissao_centavos || 0)}" aria-label="Selecionar ${esc(i.referencia || i.vendedor)}" /></td>
        <td>${esc(i.vendedor)}${viaDe(i)}</td>
        <td>${esc(i.referencia || "—")}</td>
        <td>${dataBr(i.pago_em)}</td>
        <td>${brl(i.valor_pago_centavos)}</td>
        <td>${Number(i.percentual || 0).toLocaleString("pt-BR")}%</td>
        <td><button type="button" class="Fin_ComLink" data-idx="${idx}">${brl(i.valor_comissao_centavos)}</button></td>
      </tr>`;
    });
    const cabeca = `<input type="checkbox" class="Fin_Chk" id="com_sel_todos" aria-label="Selecionar todos" />`;
    return `
      <p class="Fin_Meta Fin_FiltroNota">Todos os meses ainda não faturados.</p>
      ${tabela([cabeca, "Vendedor", "Referência", "Pago em", "Mensalidade", "%", "Comissão"], rows, "Nenhuma comissão em aberto.")}
      <div class="Fin_Fechar" id="com_fechar_bar">
        <label class="Fin_Nf">
          <span>Nota fiscal do período (PDF)</span>
          <input type="file" id="com_nf" accept="application/pdf,.pdf" ${dados.pode_faturar ? "" : "disabled"} />
        </label>
        <div class="Fin_FecharAcao">
          <div class="Fin_SelResumo" id="com_sel_info">
            <span class="Fin_SelQtd">Selecione os itens</span>
            <strong class="Fin_SelValor">R$ 0,00</strong>
          </div>
          <button type="button" class="Cl_botaoprimario" id="com_fechar" disabled>Faturar selecionados</button>
        </div>
      </div>`;
  }

  function htmlFaturado() {
    const rows = (dados.faturados || []).map((f) => {
      const pago = f.status === "pago";
      const badge = pago
        ? `<span class="Fin_Badge Fin_Badge--ok">Pago</span>`
        : `<span class="Fin_Badge Fin_Badge--warn">Aguardando</span>`;
      return `<tr class="Fin_Lote" data-lote="${Number(f.id)}" tabindex="0">
        <td>${dataBr(f.criado_em)}</td>
        <td>${dataBr(f.vencimento_em)}</td>
        <td>${brl(f.valor_centavos)}</td>
        <td>${badge}</td>
      </tr>`;
    });
    const vazio = Number(dados.ano_faturado)
      ? `Nenhum lote em ${dados.ano_faturado}.`
      : "Nenhum lote nos últimos 12 meses.";
    return htmlFiltroAno() + tabela(["Fechado em", "Vencimento", "Valor", "Situação"], rows, vazio);
  }

  function htmlInad() {
    const rows = (dados.inadimplentes || []).map((i) => {
      return `<tr>
        <td>${esc(i.vendedor)}${viaDe(i)}</td>
        <td>${esc(i.plano || "—")}</td>
        <td>${dataBr(i.vencimento_em)}</td>
        <td>${brl(i.valor_centavos)}</td>
      </tr>`;
    });
    return (
      htmlFiltroPeriodo() +
      tabela(
        ["Vendedor", "Plano", "Vencimento", "Mensalidade"],
        rows,
        "Nenhum vencimento passou sem pagamento neste mês."
      )
    );
  }

  function render() {
    if (!painel || !dados) return;
    resumo();
    tabs?.querySelectorAll(".Fin_Tab").forEach((b) => b.classList.toggle("is-active", b.dataset.aba === aba));
    if (aba === "previsao") painel.innerHTML = htmlPrevisao();
    else if (aba === "faturado") painel.innerHTML = htmlFaturado();
    else if (aba === "inadimplente") painel.innerHTML = htmlInad();
    else painel.innerHTML = htmlAberto();
  }

  async function carregar() {
    const p = new URLSearchParams();
    if (ano) p.set("ano", String(ano));
    if (mes) p.set("mes", String(mes));
    p.set("ano_faturado", String(anoFaturado || 0));
    const r = await fetch(`/api/comissoes/painel?${p.toString()}`, { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar.");
    dados = j;
    ano = Number(j.ano || ano || 0);
    mes = Number(j.mes || mes || 0);
    anoFaturado = Number(j.ano_faturado || 0);
    render();
  }

  function arred(n) {
    return Math.round(Number(n) || 0);
  }

  function impostosDo(i) {
    let raw = i?.impostos;
    if (typeof raw === "string") {
      try {
        raw = JSON.parse(raw);
      } catch (e) {
        raw = [];
      }
    }
    return Array.isArray(raw) ? raw : [];
  }

  function htmlDetalhe(i) {
    const pago = Number(i.valor_pago_centavos || 0);
    const pct = Number(i.percentual || 0);
    const impostos = impostosDo(i);
    const taxa = Math.min(
      100,
      impostos.reduce((s, t) => s + Number(t.percentual || 0), 0)
    );
    const liquido = i.base === "liquido";
    const linhas = [[i.previsao ? "Mensalidade prevista" : "Mensalidade paga", brl(pago)]];
    let base = pago;
    if (liquido) {
      base = arred((pago * (100 - taxa)) / 100);
      const desconto = pago - base;
      const partes = impostos.map((t) => ({
        nome: t.nome,
        p: Number(t.percentual || 0),
        valor: arred((pago * Number(t.percentual || 0)) / 100),
      }));
      if (partes.length) {
        const soma = partes.reduce((s, t) => s + t.valor, 0);
        partes[partes.length - 1].valor += desconto - soma;
      }
      partes.forEach((t) => {
        linhas.push([`${t.nome} ${t.p.toLocaleString("pt-BR")}%`, `− ${brl(t.valor)}`]);
      });
      if (!partes.length) linhas.push(["Impostos", "Nenhum cadastrado"]);
      linhas.push(["Base líquida", brl(base)]);
    } else {
      impostos.forEach((t) => {
        const p = Number(t.percentual || 0);
        linhas.push([`${t.nome} ${p.toLocaleString("pt-BR")}%`, "não entra na base"]);
      });
      if (!impostos.length) linhas.push(["Impostos", "Nenhum cadastrado"]);
      linhas.push(["Base", "Faturamento"]);
    }
    linhas.push([`Comissão ${pct.toLocaleString("pt-BR")}%`, brl(i.valor_comissao_centavos)]);
    const corpo = linhas
      .map(
        (l, n) =>
          `<div class="Fin_ContaLinha${n === linhas.length - 1 ? " is-total" : ""}"><span>${esc(l[0])}</span><strong>${esc(l[1])}</strong></div>`
      )
      .join("");
    const origem = i.origem === "indicado" ? "Percentual de indicado" : "Percentual próprio";
    const aviso = i.previsao ? `<p class="Fin_ContaSub">Previsão com o percentual de agora. O valor fecha no pagamento.</p>` : "";
    return `${aviso}<p class="Fin_ContaSub">${esc(origem)} · plano ${esc(i.plano || "—")}</p>${corpo}`;
  }

  function abrirDetalhe(i) {
    if (!i) return;
    Swal.fire({
      title: i.previsao ? "Previsão" : brl(i.valor_comissao_centavos),
      html: htmlDetalhe(i),
      confirmButtonText: "Fechar",
      confirmButtonColor: "#021F81",
      width: 440,
    });
  }

  async function abrirLote(id) {
    Swal.fire({ title: "Carregando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    const r = await fetch(`/api/comissoes/fechamento/${id}`, { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao abrir o lote.");
    const linhas = (j.itens || [])
      .map((i) => {
        const via = i.via ? ` <span class="Fin_Meta">via ${esc(i.via)}</span>` : "";
        return `<tr><td>${esc(i.vendedor)}${via}</td><td>${dataBr(i.pago_em)}</td><td>${brl(i.valor_pago_centavos)}</td><td>${brl(i.valor_comissao_centavos)}</td></tr>`;
      })
      .join("");
    const corpo = linhas
      ? `<div class="Fin_TableWrap"><table class="Fin_Table"><thead><tr><th>Vendedor</th><th>Pago em</th><th>Mensalidade</th><th>Comissão</th></tr></thead><tbody>${linhas}</tbody></table></div>`
      : `<p class="Fin_Empty">Este lote não tem itens.</p>`;
    const nota = j.nf_nome
      ? `<p class="Fin_ContaSub"><a href="/api/comissoes/fechamento/${id}/nf" target="_blank" rel="noopener">${esc(j.nf_nome)}</a></p>`
      : `<p class="Fin_ContaSub">Sem nota anexada.</p>`;
    const situacao = j.status === "pago" ? "Pago" : "Aguardando";
    await Swal.fire({
      title: brl(j.valor_centavos),
      html: `<p class="Fin_ContaSub">Fechado em ${dataBr(j.criado_em)} · vence ${dataBr(j.vencimento_em)} · ${situacao}</p>${nota}${corpo}`,
      confirmButtonText: "Fechar",
      confirmButtonColor: "#021F81",
      width: 640,
    });
  }

  function marcados() {
    return [...(painel?.querySelectorAll(".com_sel:checked") || [])];
  }

  function atualizarSelecao() {
    const boxes = [...(painel?.querySelectorAll(".com_sel") || [])];
    const on = marcados();
    const todos = document.getElementById("com_sel_todos");
    if (todos) {
      todos.checked = boxes.length > 0 && on.length === boxes.length;
      todos.indeterminate = on.length > 0 && on.length < boxes.length;
    }
    const btn = document.getElementById("com_fechar");
    if (btn) btn.disabled = !(dados?.pode_faturar && on.length);
    boxes.forEach((cb) => cb.closest("tr")?.classList.toggle("is-marcada", cb.checked));
    const bar = document.getElementById("com_fechar_bar");
    if (bar) bar.classList.toggle("is-ativa", on.length > 0 && !!dados?.pode_faturar);
    const qtd = document.querySelector("#com_sel_info .Fin_SelQtd");
    const valor = document.querySelector("#com_sel_info .Fin_SelValor");
    if (!qtd || !valor) return;
    if (!on.length) {
      qtd.textContent = "Selecione os itens";
      valor.textContent = "R$ 0,00";
      return;
    }
    const cents = on.reduce((s, b) => s + Number(b.dataset.valor || 0), 0);
    qtd.textContent = `${on.length} selecionado${on.length > 1 ? "s" : ""}`;
    valor.textContent = brl(cents);
  }

  async function fechar() {
    if (!dados?.pode_faturar) {
      await Swal.fire("Atenção", dados?.frase || "O fechamento não está disponível.", "warning");
      return;
    }
    const file = document.getElementById("com_nf")?.files?.[0];
    const on = marcados();
    if (!on.length) {
      await Swal.fire("Atenção", "Selecione ao menos uma comissão.", "warning");
      return;
    }
    if (!file) {
      await Swal.fire("Atenção", "Anexe a nota fiscal em PDF.", "warning");
      return;
    }
    const cents = on.reduce((s, b) => s + Number(b.dataset.valor || 0), 0);
    const conf = await Swal.fire({
      icon: "question",
      title: "Faturar os itens selecionados?",
      text: `${on.length} item(ns) · ${brl(cents)}. O depósito vence em ${dataBr(dados.vencimento_se_fechar)}.`,
      showCancelButton: true,
      confirmButtonText: "Faturar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
    });
    if (!conf.isConfirmed) return;
    const fd = new FormData();
    fd.append("nf", file);
    fd.append("ids", JSON.stringify(on.map((b) => Number(b.dataset.id))));
    Swal.fire({ title: "Faturando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    const r = await fetch("/api/comissoes/fechar", { method: "POST", credentials: "same-origin", body: fd });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao faturar.");
    aba = "faturado";
    anoFaturado = 0;
    await carregar();
    const restou = Number(j.qtd_restante || 0);
    await Swal.fire({
      icon: "success",
      title: "Faturamento registrado",
      text: restou ? `${restou} item(ns) ficaram em aberto para o próximo mês.` : "",
      confirmButtonColor: "#021F81",
    });
  }

  tabs?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".Fin_Tab");
    if (!btn) return;
    aba = btn.dataset.aba || "previsao";
    render();
  });
  painel?.addEventListener("click", (ev) => {
    const prev = ev.target.closest("[data-prev]");
    if (prev) {
      abrirDetalhe((dados?.previsoes || [])[Number(prev.dataset.prev)]);
      return;
    }
    const link = ev.target.closest(".Fin_ComLink");
    if (link) {
      abrirDetalhe((dados?.abertos || [])[Number(link.dataset.idx)]);
      return;
    }
    const lote = ev.target.closest("[data-lote]");
    if (lote) {
      abrirLote(Number(lote.dataset.lote)).catch((e) => Swal.fire("Erro", e.message, "error"));
      return;
    }
    if (ev.target.closest("#com_fechar")) fechar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  painel?.addEventListener("change", (ev) => {
    if (ev.target.id === "com_mes" || ev.target.id === "com_ano") {
      mes = Number(document.getElementById("com_mes")?.value || mes);
      ano = Number(document.getElementById("com_ano")?.value || ano);
      carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
      return;
    }
    if (ev.target.id === "com_ano_fat") {
      anoFaturado = Number(ev.target.value || 0);
      carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
      return;
    }
    if (ev.target.id === "com_sel_todos") {
      painel.querySelectorAll(".com_sel").forEach((cb) => {
        cb.checked = ev.target.checked;
      });
    }
    if (ev.target.id === "com_sel_todos" || ev.target.classList.contains("com_sel")) atualizarSelecao();
  });
  painel?.addEventListener("keydown", (ev) => {
    if (ev.key !== "Enter") return;
    const lote = ev.target.closest("[data-lote]");
    if (!lote) return;
    abrirLote(Number(lote.dataset.lote)).catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
})();
