(() => {
  "use strict";

  const API_DADOS = "/fornecedor/parametros/rede-visibilidade/dados";
  const API_SALVAR = "/fornecedor/parametros/rede-visibilidade";
  const chkRede = document.getElementById("fnParVisivelRede");
  const statusEl = document.getElementById("fnParRedeStatus");
  let salvando = false;

  function textoStatus(d) {
    const qtd = Number(d.qtd_produtos_ativos) || 0;
    if (!d.visivel_rede_vendedor) {
      return "Oculto — vendedores não encontram sua empresa na rede.";
    }
    if (qtd === 0) {
      return "Ativado, mas ainda sem produtos ativos — cadastre ao menos 1 produto ativo para aparecer.";
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

  async function carregarRede() {
    if (!chkRede) return;
    try {
      const r = await fetch(API_DADOS, { credentials: "same-origin", headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.success) return;
      chkRede.checked = !!j.visivel_rede_vendedor;
      renderStatus(j);
    } catch (e) {
      console.error(e);
    }
  }

  async function salvarRede(visivel) {
    if (salvando) return;
    salvando = true;
    try {
      const r = await fetch(API_SALVAR, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ visivel_rede_vendedor: visivel }),
      });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Não foi possível salvar.");
      renderStatus(j);
      if (window.Swal) {
        Swal.fire({
          icon: j.aparece_na_rede ? "success" : "info",
          title: "Salvo",
          text: j.message || "",
          timer: 2200,
          showConfirmButton: false,
        });
      }
    } catch (e) {
      chkRede.checked = !visivel;
      if (window.Swal) Swal.fire("Erro", e.message || "Falha ao salvar.", "error");
    } finally {
      salvando = false;
    }
  }

  chkRede?.addEventListener("change", () => {
    salvarRede(chkRede.checked);
  });

  document.getElementById("fnParGrid")?.addEventListener("click", (ev) => {
    const card = ev.target.closest("[data-card]");
    if (!card || !window.GlobalUtils?.abrirJanelaApoioModal) return;
    if (card.dataset.card === "precificacao") {
      GlobalUtils.abrirJanelaApoioModal({
        rota: "/fornecedor/parametros/precificacao",
        titulo: "Precificação",
        largura: 920,
        altura: 540,
        nivel: 2,
      });
    }
    if (card.dataset.card === "requisitos_vendedor") {
      GlobalUtils.abrirJanelaApoioModal({
        rota: "/fornecedor/parametros/requisitos-vendedor",
        titulo: "Requisitos para vendedores",
        largura: 980,
        altura: 640,
        nivel: 2,
      });
    }
  });

  carregarRede();
})();
