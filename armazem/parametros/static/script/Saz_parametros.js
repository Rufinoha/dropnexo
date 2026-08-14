(() => {
  "use strict";

  const API_DADOS = "/armazem/parametros/dados";
  const API_SALVAR = "/armazem/parametros/salvar";
  const chkRede = document.getElementById("azParVisivelRede");
  const statusEl = document.getElementById("azParRedeStatus");
  const modoA = document.getElementById("az_par_modo_a");
  const modoB = document.getElementById("az_par_modo_b");
  let salvando = false;
  let modoAtual = "armazem";

  function textoStatus(d) {
    const qtd = Number(d.qtd_produtos_ativos) || 0;
    if (!d.visivel_rede_vendedor) {
      return "Oculto — vendedores não encontram o armazém na rede.";
    }
    if (qtd === 0) {
      return "Ativado, mas ainda sem produtos publicados — publique ao menos 1 produto para aparecer.";
    }
    if (d.aparece_na_rede) {
      return `Visível na rede — ${qtd} produto(s) ativo(s) no catálogo.`;
    }
    return `Produtos ativos: ${qtd}.`;
  }

  function renderStatus(d) {
    if (!statusEl || !d) return;
    statusEl.textContent = textoStatus(d);
    statusEl.hidden = false;
    statusEl.classList.toggle("is-on", !!d.aparece_na_rede);
    statusEl.classList.toggle("is-warn", !!d.visivel_rede_vendedor && !d.aparece_na_rede);
  }

  function aplicarModoUI(modo) {
    modoAtual = modo === "fornecedores" ? "fornecedores" : "armazem";
    if (modoAtual === "fornecedores") modoB.checked = true;
    else modoA.checked = true;
  }

  async function carregar() {
    try {
      const r = await fetch(API_DADOS, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      const j = await r.json();
      if (!j.success) return;
      const p = j.parametros || {};
      if (chkRede) chkRede.checked = !!p.visivel_rede_vendedor;
      aplicarModoUI(p.modo_vitrine || "armazem");
      renderStatus({
        visivel_rede_vendedor: !!p.visivel_rede_vendedor,
        qtd_produtos_ativos: j.qtd_produtos_ativos,
        aparece_na_rede: !!j.aparece_na_rede,
      });
    } catch (e) {
      console.error(e);
    }
  }

  async function salvar(partial) {
    if (salvando) return;
    salvando = true;
    const body = {
      visivel_rede_vendedor: !!chkRede?.checked,
      modo_vitrine: modoB?.checked ? "fornecedores" : "armazem",
      ...partial,
    };
    try {
      const r = await fetch(API_SALVAR, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Não foi possível salvar.");
      const p = j.parametros || {};
      if (chkRede) chkRede.checked = !!p.visivel_rede_vendedor;
      aplicarModoUI(p.modo_vitrine || body.modo_vitrine);
      renderStatus({
        visivel_rede_vendedor: !!p.visivel_rede_vendedor,
        qtd_produtos_ativos: j.qtd_produtos_ativos,
        aparece_na_rede: !!j.aparece_na_rede,
      });
      if (window.Swal) {
        Swal.fire({
          icon: j.aparece_na_rede || !p.visivel_rede_vendedor ? "success" : "info",
          title: "Salvo",
          text: j.message || "",
          timer: 2200,
          showConfirmButton: false,
        });
      }
    } catch (e) {
      if (partial && "visivel_rede_vendedor" in partial && chkRede) {
        chkRede.checked = !partial.visivel_rede_vendedor;
      }
      if (partial && "modo_vitrine" in partial) aplicarModoUI(modoAtual);
      if (window.Swal) Swal.fire("Erro", e.message || "Falha ao salvar.", "error");
    } finally {
      salvando = false;
    }
  }

  chkRede?.addEventListener("change", () => {
    salvar({ visivel_rede_vendedor: chkRede.checked });
  });

  modoA?.addEventListener("change", () => {
    if (modoA.checked) salvar({ modo_vitrine: "armazem" });
  });
  modoB?.addEventListener("change", () => {
    if (modoB.checked) salvar({ modo_vitrine: "fornecedores" });
  });

  document.getElementById("azParGrid")?.addEventListener("click", (ev) => {
    const card = ev.target.closest("[data-card]");
    if (!card || !window.GlobalUtils?.abrirJanelaApoioModal) return;
    if (card.dataset.card === "precificacao") {
      GlobalUtils.abrirJanelaApoioModal({
        rota: "/armazem/parametros/precificacao",
        titulo: "Precificação",
        largura: 920,
        altura: 540,
        nivel: 2,
      });
    }
    if (card.dataset.card === "requisitos_vendedor") {
      GlobalUtils.abrirJanelaApoioModal({
        rota: "/armazem/parametros/requisitos-vendedor",
        titulo: "Requisitos para vendedores",
        largura: 980,
        altura: 640,
        nivel: 2,
      });
    }
  });

  carregar();
})();
