(() => {
  "use strict";
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
})();
