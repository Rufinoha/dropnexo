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
        altura: "auto",
        nivel: 2,
      });
    }
  });
})();
