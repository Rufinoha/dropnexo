(function () {
  let dados = null;
  let aba = "previsao";
  let ano = 0;
  let mes = 0;
  let anoFaturado = 0;
  let loteAtual = null;
  let loteNfFile = null;
  let loteCompFile = null;

  const MESES = ["", "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho", "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro"];
  const painel = document.getElementById("com_painel");
  const tabs = document.getElementById("com_tabs");
  const loteModal = document.getElementById("com_lote_modal");

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

  function planosAtivos() {
    return dados?.planos_ativos || dados?.previsoes || [];
  }

  function somaCentavos(lista, campo) {
    return (lista || []).reduce((s, i) => s + Number(i?.[campo] || 0), 0);
  }

  function resumo() {
    const frase = document.getElementById("com_frase");
    const aviso = document.getElementById("com_aviso");
    if (!dados) return;
    const nPrev = document.getElementById("com_n_prev");
    const nAberto = document.getElementById("com_n_aberto");
    const nFat = document.getElementById("com_n_faturado");
    const nInad = document.getElementById("com_n_inad");
    if (nPrev) nPrev.textContent = String(planosAtivos().length);
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
    const elPrev = document.getElementById("com_total_prev");
    const elAberto = document.getElementById("com_total_aberto");
    const totalPrev =
      Number(dados.total_previsto_centavos) ||
      somaCentavos(planosAtivos(), "valor_comissao_centavos");
    const totalAberto =
      Number(dados.total_aberto_centavos) ||
      somaCentavos(dados.abertos || [], "valor_comissao_centavos");
    if (elPrev) elPrev.textContent = brl(totalPrev);
    if (elAberto) elAberto.textContent = brl(totalAberto);
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

  function htmlPlanosAtivos() {
    const rows = planosAtivos().map((i, idx) => {
      const st = esc(i.status_label || "Plano ativo");
      return `<tr>
        <td>${esc(i.vendedor)}${viaDe(i)}</td>
        <td>${esc(i.plano || "—")}</td>
        <td>${dataBr(i.vencimento_em)}</td>
        <td>${brl(i.valor_pago_centavos)}</td>
        <td><button type="button" class="Fin_ComLink" data-prev="${idx}">${brl(i.valor_comissao_centavos)}</button></td>
        <td><span class="Fin_Meta">${st}</span></td>
      </tr>`;
    });
    return (
      htmlFiltroPeriodo() +
      `<p class="Fin_Meta Fin_FiltroNota">Vendedores com plano ativo na sua rede e nos fornecedores indicados.</p>` +
      tabela(
        ["Vendedor", "Plano", "Vencimento", "Mensalidade", "Previsão", "Situação"],
        rows,
        "Nenhum plano ativo na rede neste período."
      )
    );
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
      <p class="Fin_Meta Fin_FiltroNota">Assinaturas pagas com comissão gerada, ainda sem fechamento.</p>
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
      return `<tr class="Fin_Lote" data-lote="${Number(f.id)}" tabindex="0" title="Abrir lote">
        <td>${dataBr(f.criado_em)}</td>
        <td>${dataBr(f.vencimento_em)}</td>
        <td>${brl(f.valor_centavos)}</td>
        <td>${badge}</td>
      </tr>`;
    });
    const vazio = Number(dados.ano_faturado)
      ? `Nenhum lote em ${dados.ano_faturado}.`
      : "Nenhum lote nos últimos 12 meses.";
    return (
      htmlFiltroAno() +
      `<p class="Fin_Meta Fin_FiltroNota">Clique no lote para gerenciar. Após confirmar o pagamento com comprovante, o lote fica bloqueado.</p>` +
      tabela(["Fechado em", "Vencimento", "Valor", "Situação"], rows, vazio)
    );
  }

  function htmlInad() {
    const rows = (dados.inadimplentes || []).map((i) => {
      return `<tr>
        <td>${esc(i.vendedor)}${viaDe(i)}</td>
        <td>${esc(i.plano || "—")}</td>
        <td>${dataBr(i.vencimento_em)}</td>
        <td>${brl(i.valor_centavos)}</td>
        <td><span class="Fin_Meta">${esc(i.status_label || "Em atraso")}</span></td>
      </tr>`;
    });
    return (
      `<p class="Fin_Meta Fin_FiltroNota">Planos ativos com cobrança vencida e ainda não paga.</p>` +
      tabela(
        ["Vendedor", "Plano", "Vencimento", "Mensalidade", "Situação"],
        rows,
        "Nenhum vendedor inadimplente na rede."
      )
    );
  }

  function render() {
    if (!painel || !dados) return;
    resumo();
    tabs?.querySelectorAll(".Fin_Tab").forEach((b) => b.classList.toggle("is-active", b.dataset.aba === aba));
    if (aba === "previsao") painel.innerHTML = htmlPlanosAtivos();
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

  function fecharLoteModal() {
    if (loteModal) loteModal.hidden = true;
    loteAtual = null;
    loteNfFile = null;
    loteCompFile = null;
    const nf = document.getElementById("com_lote_nf");
    const comp = document.getElementById("com_lote_comp");
    if (nf) nf.value = "";
    if (comp) comp.value = "";
  }

  function idsMarcadosLote() {
    return [...(loteModal?.querySelectorAll(".com_lote_item:checked") || [])].map((cb) => Number(cb.dataset.id));
  }

  function atualizarResumoLote() {
    const boxes = [...(loteModal?.querySelectorAll(".com_lote_item") || [])];
    const on = boxes.filter((cb) => cb.checked);
    const cents = on.reduce((s, b) => s + Number(b.dataset.valor || 0), 0);
    const info = document.getElementById("com_lote_sel_info");
    const valor = document.getElementById("com_lote_valor");
    if (info) {
      info.textContent = on.length
        ? `${on.length} selecionada${on.length > 1 ? "s" : ""} · ${brl(cents)}`
        : "Nenhuma selecionada";
    }
    if (valor && loteAtual?.editavel) valor.textContent = brl(cents || loteAtual.valor_centavos);
    boxes.forEach((cb) => cb.closest("tr")?.classList.toggle("is-off", !cb.checked));
  }

  function linhaItemLote(i, editavel, marcado) {
    const via = i.via ? ` <span class="Fin_Meta">via ${esc(i.via)}</span>` : "";
    const check = editavel
      ? `<input type="checkbox" class="com_lote_item" data-id="${Number(i.id)}" data-valor="${Number(i.valor_comissao_centavos || 0)}" ${marcado ? "checked" : ""} />`
      : "";
    const cls = i.no_lote === false || (!marcado && editavel) ? "is-disp" : "";
    return `<tr class="${cls}">
      <td>${check}</td>
      <td>${esc(i.vendedor)}${via}</td>
      <td>${dataBr(i.pago_em)}</td>
      <td>${brl(i.valor_pago_centavos)}</td>
      <td>${brl(i.valor_comissao_centavos)}</td>
    </tr>`;
  }

  function pintarItensLote(j) {
    const editavel = !!j.editavel && j.status !== "pago";
    const noLote = j.itens || [];
    const disp = j.disponiveis || [];
    let html = "";
    if (noLote.length) {
      html += `<div class="Fin_LoteGrupo">No lote</div>
        <table class="Fin_LoteTabela"><thead><tr>
          <th style="width:36px"></th><th>Vendedor</th><th>Pago em</th><th>Mensalidade</th><th>Comissão</th>
        </tr></thead><tbody>
        ${noLote.map((i) => linhaItemLote({ ...i, no_lote: true }, editavel, true)).join("")}
        </tbody></table>`;
    }
    if (editavel && disp.length) {
      html += `<div class="Fin_LoteGrupo">Em aberto — incluir no lote</div>
        <table class="Fin_LoteTabela"><thead><tr>
          <th style="width:36px"></th><th>Vendedor</th><th>Pago em</th><th>Mensalidade</th><th>Comissão</th>
        </tr></thead><tbody>
        ${disp.map((i) => linhaItemLote({ ...i, no_lote: false }, true, false)).join("")}
        </tbody></table>`;
    }
    if (!html) html = `<p class="Fin_Empty">Este lote não tem itens.</p>`;
    const box = document.getElementById("com_lote_itens");
    if (box) box.innerHTML = html;
    atualizarResumoLote();
  }

  function pintarDocsLote(j) {
    const id = Number(j.id);
    const editavel = !!j.editavel && j.status !== "pago";
    const pago = j.status === "pago";
    const nfAtual = document.getElementById("com_lote_nf_atual");
    const compAtual = document.getElementById("com_lote_comp_atual");
    const nfDrop = document.getElementById("com_lote_nf_drop");
    const compDrop = document.getElementById("com_lote_comp_drop");
    const nfHint = document.getElementById("com_lote_nf_hint");
    const compHint = document.getElementById("com_lote_comp_hint");

    if (nfAtual) {
      nfAtual.innerHTML = j.nf_nome
        ? `<a href="/api/comissoes/fechamento/${id}/nf" target="_blank" rel="noopener">${esc(j.nf_nome)}</a>`
        : `<span class="Fin_Meta">Nenhuma nota anexada</span>`;
    }
    if (compAtual) {
      if (pago && (j.tem_comprovante || j.comprovante_nome)) {
        compAtual.innerHTML = `<a href="/api/comissoes/fechamento/${id}/comprovante" target="_blank" rel="noopener">${esc(j.comprovante_nome || "comprovante")}</a>`;
      } else if (loteCompFile) {
        compAtual.innerHTML = `<span>${esc(loteCompFile.name)}</span>`;
      } else {
        compAtual.innerHTML = `<span class="Fin_Meta">Ainda sem comprovante</span>`;
      }
    }
    if (nfDrop) {
      nfDrop.hidden = !editavel;
      nfDrop.classList.toggle("has-file", !!loteNfFile);
      const strong = nfDrop.querySelector("strong");
      if (strong) strong.textContent = loteNfFile ? loteNfFile.name : "Trocar nota (PDF)";
    }
    if (compDrop) {
      compDrop.hidden = !editavel;
      compDrop.classList.toggle("has-file", !!loteCompFile);
      const strong = compDrop.querySelector("strong");
      if (strong) strong.textContent = loteCompFile ? loteCompFile.name : "Anexar comprovante";
    }
    if (nfHint) {
      nfHint.textContent = editavel
        ? "Pode trocar o PDF antes de confirmar o pagamento."
        : "Nota fiscal do fechamento.";
    }
    if (compHint) {
      compHint.textContent = editavel
        ? "Anexe o comprovante e use Confirmar pagamento."
        : pago
          ? `Pago em ${dataBr(j.pago_em)}.`
          : "Comprovante do depósito.";
    }
  }

  function pintarCabecalhoLote(j) {
    const pago = j.status === "pago";
    const sub = document.getElementById("com_lote_sub");
    const valor = document.getElementById("com_lote_valor");
    const badge = document.getElementById("com_lote_badge");
    if (sub) {
      sub.textContent = `Fechado em ${dataBr(j.criado_em)} · vence ${dataBr(j.vencimento_em)}${pago && j.pago_em ? ` · pago em ${dataBr(j.pago_em)}` : ""}`;
    }
    if (valor) valor.textContent = brl(j.valor_centavos);
    if (badge) {
      badge.textContent = pago ? "Pago" : "Aguardando";
      badge.className = `Fin_Badge ${pago ? "Fin_Badge--ok" : "Fin_Badge--warn"}`;
    }
    const editavel = !!j.editavel && !pago;
    ["com_lote_salvar", "com_lote_pagar", "com_lote_cancelar"].forEach((id) => {
      const el = document.getElementById(id);
      if (el) el.hidden = !editavel;
    });
  }

  async function abrirLote(id) {
    const r = await fetch(`/api/comissoes/fechamento/${id}`, { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao abrir o lote.");
    loteAtual = j;
    loteNfFile = null;
    loteCompFile = null;
    const nf = document.getElementById("com_lote_nf");
    const comp = document.getElementById("com_lote_comp");
    if (nf) nf.value = "";
    if (comp) comp.value = "";
    pintarCabecalhoLote(j);
    pintarItensLote(j);
    pintarDocsLote(j);
    if (loteModal) loteModal.hidden = false;
  }

  async function salvarLote() {
    if (!loteAtual?.editavel) return;
    const ids = idsMarcadosLote();
    if (!ids.length) {
      await Swal.fire("Atenção", "Selecione ao menos uma comissão no lote.", "warning");
      return;
    }
    const fd = new FormData();
    fd.append("ids", JSON.stringify(ids));
    if (loteNfFile) fd.append("nf", loteNfFile);
    const btn = document.getElementById("com_lote_salvar");
    if (btn) btn.disabled = true;
    try {
      const r = await fetch(`/api/comissoes/fechamento/${loteAtual.id}/alterar`, {
        method: "POST",
        credentials: "same-origin",
        body: fd,
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao salvar.");
      await carregar();
      await abrirLote(loteAtual.id);
      await Swal.fire({ icon: "success", title: "Lote atualizado", confirmButtonColor: "#021F81" });
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function confirmarPagamentoLote() {
    if (!loteAtual?.editavel) return;
    if (!loteCompFile) {
      await Swal.fire("Atenção", "Anexe o comprovante de pagamento (PDF, JPG ou PNG).", "warning");
      return;
    }
    const ids = idsMarcadosLote();
    if (!ids.length) {
      await Swal.fire("Atenção", "Selecione ao menos uma comissão no lote.", "warning");
      return;
    }
    const conf = await Swal.fire({
      icon: "question",
      title: "Confirmar pagamento?",
      text: "O lote será marcado como Pago e não poderá mais ser alterado.",
      showCancelButton: true,
      confirmButtonText: "Confirmar",
      cancelButtonText: "Voltar",
      confirmButtonColor: "#021F81",
    });
    if (!conf.isConfirmed) return;

    const btn = document.getElementById("com_lote_pagar");
    if (btn) btn.disabled = true;
    try {
      // Salva itens/NF pendentes antes da baixa
      const fdAlt = new FormData();
      fdAlt.append("ids", JSON.stringify(ids));
      if (loteNfFile) fdAlt.append("nf", loteNfFile);
      const rAlt = await fetch(`/api/comissoes/fechamento/${loteAtual.id}/alterar`, {
        method: "POST",
        credentials: "same-origin",
        body: fdAlt,
      });
      const jAlt = await rAlt.json().catch(() => ({}));
      if (!rAlt.ok || !jAlt.success) throw new Error(jAlt.message || "Falha ao salvar o lote.");

      const fd = new FormData();
      fd.append("comprovante", loteCompFile);
      const r = await fetch(`/api/comissoes/fechamento/${loteAtual.id}/comprovante`, {
        method: "POST",
        credentials: "same-origin",
        body: fd,
      });
      const j = await r.json().catch(() => ({}));
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao confirmar pagamento.");
      fecharLoteModal();
      await carregar();
      await Swal.fire({
        icon: "success",
        title: "Pagamento confirmado",
        text: j.message || "",
        confirmButtonColor: "#021F81",
      });
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function cancelarLote() {
    if (!loteAtual?.editavel) return;
    const conf = await Swal.fire({
      icon: "warning",
      title: "Cancelar esta fatura?",
      text: "As comissões voltam para Em aberto e o lote deixa de valer.",
      showCancelButton: true,
      confirmButtonText: "Cancelar fatura",
      cancelButtonText: "Manter",
      confirmButtonColor: "#b42318",
    });
    if (!conf.isConfirmed) return;
    const r = await fetch(`/api/comissoes/fechamento/${loteAtual.id}/cancelar`, {
      method: "POST",
      credentials: "same-origin",
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao cancelar.");
    fecharLoteModal();
    aba = "aberto";
    await carregar();
    await Swal.fire({
      icon: "success",
      title: "Fatura cancelada",
      text: j.message || "",
      confirmButtonColor: "#021F81",
    });
  }

  function bindDrop(dropId, inputId, kind) {
    const drop = document.getElementById(dropId);
    const input = document.getElementById(inputId);
    if (!drop || !input) return;
    const apply = (file) => {
      if (!file) return;
      if (kind === "nf") {
        if (!/\.pdf$/i.test(file.name || "")) {
          Swal.fire("Atenção", "A nota fiscal deve ser PDF.", "warning");
          return;
        }
        loteNfFile = file;
      } else {
        if (!/\.(pdf|jpe?g|png)$/i.test(file.name || "")) {
          Swal.fire("Atenção", "Comprovante deve ser PDF, JPG ou PNG.", "warning");
          return;
        }
        loteCompFile = file;
      }
      if (loteAtual) pintarDocsLote(loteAtual);
    };
    drop.addEventListener("click", (ev) => {
      if (ev.target === input) return;
      input.click();
    });
    input.addEventListener("change", () => apply(input.files?.[0]));
    drop.addEventListener("dragover", (ev) => {
      ev.preventDefault();
      drop.classList.add("is-drag");
    });
    drop.addEventListener("dragleave", () => drop.classList.remove("is-drag"));
    drop.addEventListener("drop", (ev) => {
      ev.preventDefault();
      drop.classList.remove("is-drag");
      apply(ev.dataTransfer?.files?.[0]);
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
      abrirDetalhe(planosAtivos()[Number(prev.dataset.prev)]);
      return;
    }
    const link = ev.target.closest(".Fin_ComLink");
    if (link && link.dataset.idx != null) {
      abrirDetalhe((dados?.abertos || [])[Number(link.dataset.idx)]);
      return;
    }
    const lote = ev.target.closest("tr.Fin_Lote[data-lote]");
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

  loteModal?.addEventListener("change", (ev) => {
    if (ev.target.classList.contains("com_lote_item")) atualizarResumoLote();
  });
  loteModal?.addEventListener("click", (ev) => {
    if (ev.target === loteModal) fecharLoteModal();
  });
  document.getElementById("com_lote_fechar")?.addEventListener("click", fecharLoteModal);
  document.getElementById("com_lote_fechar_x")?.addEventListener("click", fecharLoteModal);
  document.getElementById("com_lote_salvar")?.addEventListener("click", () => {
    salvarLote().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  document.getElementById("com_lote_pagar")?.addEventListener("click", () => {
    confirmarPagamentoLote().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  document.getElementById("com_lote_cancelar")?.addEventListener("click", () => {
    cancelarLote().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && loteModal && !loteModal.hidden) fecharLoteModal();
  });
  bindDrop("com_lote_nf_drop", "com_lote_nf", "nf");
  bindDrop("com_lote_comp_drop", "com_lote_comp", "comp");

  carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
})();
