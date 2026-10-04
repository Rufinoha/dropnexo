(function () {
  let aba = "aguardando";
  const tbody = document.getElementById("bx_tbody");
  const tabs = document.getElementById("bx_tabs");

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

  function render(j) {
    const ag = document.getElementById("bx_n_ag");
    const pg = document.getElementById("bx_n_pg");
    if (ag) ag.textContent = String(j.qtd_aguardando || 0);
    if (pg) pg.textContent = String(j.qtd_pago || 0);
    tabs?.querySelectorAll(".CfgBx_Tab").forEach((b) => b.classList.toggle("is-active", b.dataset.aba === aba));
    const itens = j.itens || [];
    if (!tbody) return;
    if (!itens.length) {
      tbody.innerHTML = `<tr><td colspan="8" class="CfgBx_Vazio">${
        aba === "pago" ? "Nenhum fechamento pago." : "Nenhum fechamento aguardando."
      }</td></tr>`;
      return;
    }
    tbody.innerHTML = itens
      .map((f) => {
        const nota = f.nf_nome
          ? `<a href="/api/comissoes/fechamento/${f.id}/nf?tenant=${f.id_tenant}" target="_blank" rel="noopener">${esc(f.nf_nome)}</a>`
          : "—";
        const temComp = !!f.comprovante_nome;
        const comp = temComp
          ? `<span class="CfgBx_Comp"><a href="/configuracoes/comissoes-baixa/${f.id}/comprovante" target="_blank" rel="noopener">${esc(f.comprovante_nome)}</a>${
              f.status === "aguardando" ? `<button type="button" class="Cl_BtnAuxiliar" data-anexar="${f.id}">Trocar</button>` : ""
            }</span>`
          : `<button type="button" class="Cl_BtnAuxiliar" data-anexar="${f.id}">Anexar</button>`;
        const acao =
          f.status === "pago"
            ? `Pago em ${dataBr(f.pago_em)}`
            : `<button type="button" class="Cl_botaoprimario" data-baixa="${f.id}" data-nome="${esc(f.fornecedor)}" ${temComp ? "" : "disabled"}>Dar baixa</button>`;
        const pix = f.pix_chave
          ? `${esc(f.pix_chave)}<span class="CfgBx_Pix">${esc(f.pix_tipo || "PIX")}</span>`
          : "—";
        return `<tr>
          <td>${esc(f.fornecedor)}</td>
          <td>${dataBr(f.criado_em)}</td>
          <td>${dataBr(f.vencimento_em)}</td>
          <td>${brl(f.valor_centavos)}</td>
          <td>${pix}</td>
          <td>${nota}</td>
          <td>${comp}</td>
          <td>${acao}</td>
        </tr>`;
      })
      .join("");
  }

  async function carregar() {
    const r = await fetch(`/configuracoes/comissoes-baixa/dados?status=${aba}`, { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar.");
    render(j);
  }

  async function baixa(id, nome) {
    const conf = await Swal.fire({
      icon: "question",
      title: "Dar baixa neste pagamento?",
      text: nome ? `Depósito confirmado para ${nome}.` : "Confirme depois do depósito.",
      showCancelButton: true,
      confirmButtonText: "Baixar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
    });
    if (!conf.isConfirmed) return;
    const r = await fetch("/configuracoes/comissoes-baixa/baixa", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id_fechamento: id }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha na baixa.");
    await carregar();
    await Swal.fire({ icon: "success", title: "Pagamento baixado", confirmButtonColor: "#021F81" });
  }

  let anexarId = 0;
  const arquivo = document.getElementById("bx_arquivo");

  async function anexar(file) {
    if (!anexarId || !file) return;
    const fd = new FormData();
    fd.append("comprovante", file);
    Swal.fire({ title: "Anexando…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    const r = await fetch(`/configuracoes/comissoes-baixa/${anexarId}/comprovante`, {
      method: "POST",
      credentials: "same-origin",
      body: fd,
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao anexar.");
    await carregar();
    Swal.close();
  }

  tabs?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".CfgBx_Tab");
    if (!btn) return;
    aba = btn.dataset.aba || "aguardando";
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  tbody?.addEventListener("click", (ev) => {
    const anex = ev.target.closest("[data-anexar]");
    if (anex) {
      anexarId = Number(anex.dataset.anexar);
      if (arquivo) {
        arquivo.value = "";
        arquivo.click();
      }
      return;
    }
    const btn = ev.target.closest("[data-baixa]");
    if (!btn || btn.disabled) return;
    baixa(Number(btn.dataset.baixa), btn.dataset.nome || "").catch((e) => Swal.fire("Erro", e.message, "error"));
  });
  arquivo?.addEventListener("change", () => {
    const file = arquivo.files?.[0];
    if (!file) return;
    anexar(file).catch((e) => Swal.fire("Erro", e.message, "error"));
  });

  carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
})();
