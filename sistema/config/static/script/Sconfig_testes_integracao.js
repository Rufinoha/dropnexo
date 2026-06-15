(function () {
  const container = document.getElementById("ti-hub-container");
  if (!container) return;

  const cfg = window.CFG_TESTES || {};

  const cards = [
    {
      titulo: "Bling ERP",
      texto: "Homologação técnica da API v3: GET, POST, PUT, PATCH e DELETE em produtos.",
      rota: "/configuracoes/testes-integracao/bling",
      logo: cfg.blingIcon,
    },
  ];

  container.innerHTML = cards
    .map(
      (card) => `
    <article class="Cl_CardItem Ti_HubCard" role="button" tabindex="0" data-rota="${card.rota || ""}">
      <div class="card-topo">
        ${
          card.logo
            ? `<img src="${card.logo}" alt="" class="Ti_HubLogo" width="28" height="28" />`
            : ""
        }
        <span class="card-titulo">${card.titulo}</span>
      </div>
      <p class="card-texto">${card.texto}</p>
    </article>`
    )
    .join("");

  const abrirCard = (el) => {
    if (!el) return;
    const rota = el.getAttribute("data-rota");
    if (rota) window.location.href = rota;
  };

  container.addEventListener("click", (e) => {
    abrirCard(e.target.closest(".Cl_CardItem"));
  });

  container.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const el = e.target.closest(".Cl_CardItem");
    if (!el) return;
    e.preventDefault();
    abrirCard(el);
  });
})();
