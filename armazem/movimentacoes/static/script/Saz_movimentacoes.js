(function () {
  const BASE = "/armazem/movimentacoes";
  const lista = document.getElementById("az_mov_lista");
  const vazio = document.getElementById("az_mov_vazio");
  const modal = document.getElementById("az_mov_modal");
  const form = document.getElementById("az_mov_form");
  const elProd = document.getElementById("az_mov_prod");
  const elDep = document.getElementById("az_mov_dep");
  const elTipo = document.getElementById("az_mov_tipo");
  const elQtd = document.getElementById("az_mov_qtd");
  const elQtdLbl = document.getElementById("az_mov_qtd_lbl");
  const elObs = document.getElementById("az_mov_obs");

  if (!lista) return;

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  const LABEL = { entrada: "Entrada", saida: "Saída", ajuste: "Ajuste" };

  async function combos() {
    const r = await fetch(`${BASE}/combos`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    elProd.innerHTML =
      '<option value="">Selecione…</option>' +
      (j.produtos || []).map((p) => `<option value="${p.id}">${esc(p.nome)}</option>`).join("");
    elDep.innerHTML =
      '<option value="">Selecione…</option>' +
      (j.depositos || []).map((d) => `<option value="${d.id}">${esc(d.nome)}</option>`).join("");
  }

  async function carregar() {
    const r = await fetch(`${BASE}/dados`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const rows = j.dados || [];
    if (!rows.length) {
      lista.innerHTML = "";
      vazio.hidden = false;
      return;
    }
    vazio.hidden = true;
    lista.innerHTML = rows
      .map(
        (m) => `
      <article class="AzMov_Card AzMov_Card--${esc(m.tipo)}">
        <div>
          <strong>${LABEL[m.tipo] || m.tipo}</strong>
          <span>${esc(m.produto)}</span>
          <small>${esc(m.deposito)}${m.fornecedor ? " · " + esc(m.fornecedor) : ""}</small>
        </div>
        <div class="AzMov_Qtd">
          <b>${m.tipo === "saida" ? "-" : m.tipo === "entrada" ? "+" : "="}${m.quantidade}</b>
          <small>saldo ${m.saldo_apos}</small>
        </div>
      </article>`
      )
      .join("");
  }

  function abrir() {
    form.reset();
    elTipo.value = "entrada";
    elQtdLbl.textContent = "Quantidade";
    modal.hidden = false;
  }
  function fechar() {
    modal.hidden = true;
  }

  elTipo?.addEventListener("change", () => {
    elQtdLbl.textContent = elTipo.value === "ajuste" ? "Novo saldo no depósito" : "Quantidade";
  });

  document.getElementById("az_mov_btnNovo")?.addEventListener("click", abrir);
  document.getElementById("az_mov_fechar")?.addEventListener("click", fechar);
  document.getElementById("az_mov_cancelar")?.addEventListener("click", fechar);

  form?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = {
      tipo: elTipo.value,
      id_produto: Number(elProd.value),
      id_deposito: Number(elDep.value),
      quantidade: Number(elQtd.value),
      observacao: elObs.value,
    };
    const r = await fetch(`${BASE}/lancar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (window.Util?.alertar) Util.alertar(j.message || (j.success ? "OK" : "Erro"), j.success ? "success" : "error");
    else if (window.Swal) Swal.fire(j.success ? "OK" : "Erro", j.message, j.success ? "success" : "error");
    if (j.success) {
      fechar();
      carregar();
    }
  });

  combos().then(carregar);
})();
