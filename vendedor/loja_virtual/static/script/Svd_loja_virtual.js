(function () {
  const chipsEl = document.getElementById("lv_chips");
  const btn = document.getElementById("lv_btnInteresse");
  const btnEditar = document.getElementById("lv_btnEditar");
  const painel = document.getElementById("lv_painelInteresse");
  const painelOk = document.getElementById("lv_painelOk");
  const social = document.getElementById("lv_social");
  const socialOk = document.getElementById("lv_socialOk");
  const priosOk = document.getElementById("lv_priosOk");
  const card = document.getElementById("lv_card");

  if (!chipsEl || !btn) return;

  const MAX = 3;
  let opcoes = {};
  let selecionadas = [];
  let inscrito = false;
  let totalInteressados = 0;

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function textoSocial(total) {
    const n = Number(total) || 0;
    if (n <= 0) return "Seja um dos primeiros a reservar prioridade.";
    if (n === 1) return "1 vendedor já entrou na lista de prioridade.";
    return `${n} vendedores já entraram na lista de prioridade.`;
  }

  function syncBtn() {
    btn.disabled = selecionadas.length < 1;
    btn.textContent =
      selecionadas.length < 1
        ? "Escolha ao menos 1 prioridade"
        : inscrito
          ? "Atualizar minhas prioridades"
          : "Quero prioridade de acesso";
  }

  function renderChips() {
    chipsEl.innerHTML = Object.entries(opcoes)
      .map(([key, label]) => {
        const on = selecionadas.includes(key);
        const bloqueado = !on && selecionadas.length >= MAX;
        return `<button type="button" class="LvSoon_Chip${on ? " is-on" : ""}" data-key="${esc(key)}"${
          bloqueado ? " disabled" : ""
        } aria-pressed="${on ? "true" : "false"}">${esc(label)}</button>`;
      })
      .join("");
    syncBtn();
  }

  function mostrarOk(st) {
    inscrito = true;
    totalInteressados = Number(st.total_interessados) || totalInteressados;
    selecionadas = Array.isArray(st.prioridades) ? st.prioridades.slice(0, MAX) : selecionadas;
    const labels = st.prioridades_labels || selecionadas.map((k) => opcoes[k] || k);
    if (priosOk) {
      priosOk.innerHTML = labels.map((l) => `<li>${esc(l)}</li>`).join("");
    }
    if (socialOk) socialOk.textContent = textoSocial(totalInteressados);
    if (painel) painel.hidden = true;
    if (painelOk) painelOk.hidden = false;
    card?.classList.add("is-ok");
  }

  function mostrarForm(st) {
    if (painel) painel.hidden = false;
    if (painelOk) painelOk.hidden = true;
    card?.classList.remove("is-ok");
    if (st) {
      selecionadas = Array.isArray(st.prioridades) ? st.prioridades.slice(0, MAX) : selecionadas;
      if (st.total_interessados != null) totalInteressados = Number(st.total_interessados) || 0;
    }
    if (social) social.textContent = textoSocial(totalInteressados);
    renderChips();
  }

  chipsEl.addEventListener("click", (e) => {
    const chip = e.target.closest(".LvSoon_Chip");
    if (!chip || chip.disabled) return;
    const key = chip.getAttribute("data-key");
    if (!key) return;
    if (selecionadas.includes(key)) {
      selecionadas = selecionadas.filter((k) => k !== key);
    } else if (selecionadas.length < MAX) {
      selecionadas.push(key);
    }
    renderChips();
  });

  btn.addEventListener("click", async () => {
    if (selecionadas.length < 1) return;
    btn.disabled = true;
    const prev = btn.textContent;
    btn.textContent = "Reservando…";
    try {
      const r = await fetch("/vendedor/loja-virtual/interesse", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prioridades: selecionadas }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Não foi possível salvar.");
      mostrarOk(j);
      if (window.Swal) {
        Swal.fire({
          icon: "success",
          title: "Prioridade reservada",
          text: j.message || "Você entrou na lista.",
          timer: 2200,
          showConfirmButton: false,
        });
      }
    } catch (err) {
      btn.disabled = false;
      btn.textContent = prev;
      if (window.Swal) Swal.fire("Atenção", err.message || "Falha", "warning");
      else alert(err.message || "Falha");
      syncBtn();
    }
  });

  btnEditar?.addEventListener("click", () => {
    mostrarForm({ prioridades: selecionadas, total_interessados: totalInteressados });
  });

  async function carregar() {
    try {
      const r = await fetch("/vendedor/loja-virtual/interesse", { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Erro");
      opcoes = j.opcoes || {};
      totalInteressados = Number(j.total_interessados) || 0;
      selecionadas = Array.isArray(j.prioridades) ? j.prioridades.slice(0, MAX) : [];
      inscrito = !!j.inscrito;
      if (j.inscrito) mostrarOk(j);
      else mostrarForm(j);
    } catch (err) {
      if (social) social.textContent = err.message || "Não foi possível carregar.";
      opcoes = {
        dominio: "Domínio próprio",
        vitrine: "Vitrine e categorias",
        checkout: "Carrinho e checkout",
        marca: "Identidade da marca",
        pedidos: "Pedidos integrados",
        mobile: "Loja no celular",
      };
      renderChips();
    }
  }

  carregar();
})();
