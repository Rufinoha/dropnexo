(function () {
  const container = document.getElementById("config-container");
  if (!container) return;

  const cards = [
    {
      titulo: "Fornecedores na plataforma",
      texto: "Cadastro PJ, ativação e depósitos dos tenants fornecedor (somente desenvolvedor).",
      rota: "/configuracoes/fornecedores-plataforma",
      iconeTech: "fornecedores",
    },
    {
      titulo: "Segmentos",
      texto: "Nichos oficiais da plataforma (Moda, Calçados, Joias…). Fornecedores só escolhem os que atendem.",
      rota: "/configuracoes/segmentos-plataforma",
      iconeTech: "configuracoes",
    },
    {
      titulo: "Testes de integração",
      texto: "Homologação e validação técnica de ERPs e APIs antes de solicitar aprovação nos parceiros.",
      rota: "/configuracoes/testes-integracao",
      iconeTech: "checklist",
    },
    {
      titulo: "Usuários",
      texto: "Gerencie contas e permissões do sistema.",
      rota: "/configuracoes/usuarios",
      iconeTech: "favorecidos",
    },
    {
      titulo: "Perfil de Usuário",
      texto: "Gerencie os menus de cada perfil de acesso.",
      rota: "/configuracoes/perfis",
      iconeTech: "nivel_acesso",
    },
    {
      titulo: "Novidades",
      texto: "Gerencie os cards exibidos na lateral do sistema.",
      rota: "/configuracoes/novidades",
      iconeTech: "novidades",
    },
    {
      titulo: "Itens de Menu",
      texto: "Configure os menus e submenus do sistema.",
      rota: "/configuracoes/itens-menu",
      iconeTech: "configuracoes",
    },
  ];

  const gerarIcone = (chave) =>
    (window.Util && typeof window.Util.gerarIconeTech === "function"
      ? window.Util.gerarIconeTech(chave || "configuracoes")
      : "") || "";

  container.innerHTML = cards
    .map(
      (card) => `
    <article class="Cl_CardItem" role="button" tabindex="0" data-rota="${card.rota || ""}">
      <div class="card-topo">
        ${gerarIcone(card.iconeTech)}
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
