(function () {
  let dados = null;
  let aba = "aberto";

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
    const total = document.getElementById("com_total");
    const janela = document.getElementById("com_janela");
    const pix = document.getElementById("com_pix");
    const aviso = document.getElementById("com_aviso");
    if (!dados) return;
    const nAberto = document.getElementById("com_n_aberto");
    const nFat = document.getElementById("com_n_faturado");
    const nInad = document.getElementById("com_n_inad");
    if (nAberto) nAberto.textContent = String((dados.abertos || []).length);
    if (nFat) nFat.textContent = String((dados.faturados || []).length);
    if (nInad) nInad.textContent = String((dados.inadimplentes || []).length);
    if (total) total.textContent = brl(dados.total_aberto_centavos);
    if (janela) {
      janela.textContent = dados.janela_aberta
        ? `Aberto até dia 10 · vence ${dataBr(dados.vencimento_se_fechar)}`
        : "De 1 a 10 do mês";
    }
    if (pix) pix.textContent = dados.pix_ok ? dados.pix_chave : "PIX Manual desconectado";
    if (aviso) {
      const msgs = [];
      if (dados.pai_nome) {
        msgs.push(`Novas comissões vão para ${dados.pai_nome}. Aqui ficam só os valores que já estavam em aberto.`);
      }
      if (!dados.pix_ok) msgs.push("Conecte o PIX Manual em Integrações para conseguir faturar.");
      if (!dados.janela_aberta) msgs.push("Fora da janela, os abertos continuam aqui até o próximo dia 1.");
      aviso.hidden = !msgs.length;
      aviso.textContent = msgs.join(" ");
    }
  }

  function tabela(cols, rows, vazio) {
    if (!rows.length) return `<p class="Fin_Empty">${esc(vazio)}</p>`;
    return `<div class="Fin_TableWrap"><table class="Fin_Table"><thead><tr>${cols
      .map((c, i) => `<th${i === 0 && String(c).includes("checkbox") ? ' class="Fin_Sel"' : ""}>${c}</th>`)
      .join("")}</tr></thead><tbody>${rows.join("")}</tbody></table></div>`;
  }

  function htmlAberto() {
    const rows = (dados.abertos || []).map((i, idx) => {
      const via = i.via ? ` <span class="Fin_Meta">via ${esc(i.via)}</span>` : "";
      return `<tr>
        <td class="Fin_Sel"><input type="checkbox" class="Fin_Chk com_sel" data-id="${Number(i.id)}" data-valor="${Number(i.valor_comissao_centavos || 0)}" aria-label="Selecionar ${esc(i.referencia || i.vendedor)}" /></td>
        <td>${esc(i.vendedor)}${via}</td>
        <td>${esc(i.referencia || "—")}</td>
        <td>${dataBr(i.pago_em)}</td>
        <td>${brl(i.valor_pago_centavos)}</td>
        <td>${Number(i.percentual || 0).toLocaleString("pt-BR")}%</td>
        <td><button type="button" class="Fin_ComLink" data-idx="${idx}">${brl(i.valor_comissao_centavos)}</button></td>
      </tr>`;
    });
    const cabeca = `<input type="checkbox" class="Fin_Chk" id="com_sel_todos" aria-label="Selecionar todos" />`;
    return `
      ${tabela([cabeca, "Vendedor", "Referência", "Pago em", "Mensalidade", "%", "Comissão"], rows, "Nenhuma comissão em aberto.")}
      <div class="Fin_Fechar" id="com_fechar_bar">
        <label class="Fin_Nf">
          <span>Nota fiscal do período (PDF)</span>
          <input type="file" id="com_nf" accept="application/pdf,.pdf" />
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
      return `<tr>
        <td>${dataBr(f.criado_em)}</td>
        <td>${dataBr(f.vencimento_em)}</td>
        <td>${brl(f.valor_centavos)}</td>
        <td>${badge}</td>
        <td>${f.nf_nome ? `<a href="/api/comissoes/fechamento/${f.id}/nf" target="_blank" rel="noopener">${esc(f.nf_nome)}</a>` : "—"}</td>
      </tr>`;
    });
    return tabela(["Fechado em", "Vencimento", "Valor", "Situação", "Nota"], rows, "Nenhum fechamento ainda.");
  }

  function htmlInad() {
    const rows = (dados.inadimplentes || []).map((i) => {
      const via = i.via ? ` <span class="Fin_Meta">via ${esc(i.via)}</span>` : "";
      return `<tr>
        <td>${esc(i.vendedor)}${via}</td>
        <td>${esc(i.referencia || "—")}</td>
        <td>${esc(i.plano || "—")}</td>
        <td>${dataBr(i.vencimento_em)}</td>
        <td>${brl(i.valor_centavos)}</td>
      </tr>`;
    });
    return tabela(
      ["Vendedor", "Referência", "Plano", "Vencimento", "Valor"],
      rows,
      "Nenhum vendedor inadimplente."
    );
  }

  function render() {
    if (!painel || !dados) return;
    resumo();
    tabs?.querySelectorAll(".Fin_Tab").forEach((b) => b.classList.toggle("is-active", b.dataset.aba === aba));
    if (aba === "faturado") painel.innerHTML = htmlFaturado();
    else if (aba === "inadimplente") painel.innerHTML = htmlInad();
    else painel.innerHTML = htmlAberto();
  }

  async function carregar() {
    const r = await fetch("/api/comissoes/painel", { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar.");
    dados = j;
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
    const linhas = [["Mensalidade paga", brl(pago)]];
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
    return `<p class="Fin_ContaSub">${esc(origem)} · plano ${esc(i.plano || "—")}</p>${corpo}`;
  }

  function abrirDetalhe(i) {
    if (!i) return;
    Swal.fire({
      title: brl(i.valor_comissao_centavos),
      html: htmlDetalhe(i),
      confirmButtonText: "Fechar",
      confirmButtonColor: "#021F81",
      width: 440,
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
    if (btn) btn.disabled = !(dados?.janela_aberta && dados?.pix_ok && on.length);
    boxes.forEach((cb) => cb.closest("tr")?.classList.toggle("is-marcada", cb.checked));
    const bar = document.getElementById("com_fechar_bar");
    if (bar) bar.classList.toggle("is-ativa", on.length > 0);
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
    await carregar();
    await Swal.fire({ icon: "success", title: "Faturamento registrado", confirmButtonColor: "#021F81" });
  }

  tabs?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".Fin_Tab");
    if (!btn) return;
    aba = btn.dataset.aba || "aberto";
    render();
  });
  painel?.addEventListener("click", (ev) => {
    const link = ev.target.closest(".Fin_ComLink");
    if (link) {
      abrirDetalhe((dados?.abertos || [])[Number(link.dataset.idx)]);
      return;
    }
    if (ev.target.closest("#com_fechar")) fechar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  painel?.addEventListener("change", (ev) => {
    if (ev.target.id === "com_sel_todos") {
      painel.querySelectorAll(".com_sel").forEach((cb) => {
        cb.checked = ev.target.checked;
      });
    }
    if (ev.target.id === "com_sel_todos" || ev.target.classList.contains("com_sel")) atualizarSelecao();
  });

  carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
})();
