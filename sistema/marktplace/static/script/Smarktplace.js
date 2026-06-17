(function () {
  const grid = document.getElementById("mk_grid");
  const modal = document.getElementById("mk_modal");
  if (!grid) return;

  const CAT_LABEL = {
    modulo: "Módulo",
    armazenamento: "Armazenamento",
    treinamento: "Treinamento",
    suporte: "Suporte",
    geral: "Serviço",
  };

  let produtos = [];
  let atual = null;

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s || "";
    return d.innerHTML;
  }

  function renderCard(p) {
    return `
      <article class="Mk_Card" data-id="${p.id}">
        <div class="Mk_CardTopo" style="background:${esc(p.cor_topo)}"></div>
        <div class="Mk_CardBody">
          <span class="Mk_CardCat">${esc(CAT_LABEL[p.categoria] || p.categoria)}</span>
          <h3 class="Mk_CardTitulo">${esc(p.titulo)}</h3>
          <p class="Mk_CardResumo">${esc(p.resumo)}</p>
          <div class="Mk_CardFoot">
            <span class="Mk_Preco">${esc(p.preco_label)}</span>
            <button type="button" class="Mk_BtnGhost" data-mk-detalhe="${p.id}">Saiba mais</button>
          </div>
        </div>
      </article>`;
  }

  function abrirModal(p) {
    atual = p;
    document.getElementById("mk_modal_topo").style.background = p.cor_topo || "#5b57f5";
    document.getElementById("mk_modal_titulo").textContent = p.titulo || "";
    document.getElementById("mk_modal_resumo").textContent = p.resumo || "";
    document.getElementById("mk_modal_desc").innerHTML = p.descricao || "<p>Sem descrição detalhada.</p>";
    document.getElementById("mk_modal_preco").textContent = p.preco_label || "";
    modal.hidden = false;
    document.body.style.overflow = "hidden";
  }

  function fecharModal() {
    modal.hidden = true;
    document.body.style.overflow = "";
    atual = null;
  }

  async function carregar() {
    try {
      const r = await fetch("/marktplace/catalogo", { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao carregar");
      produtos = j.produtos || [];
      if (!produtos.length) {
        grid.innerHTML = '<p class="Mk_Empty">Nenhum item disponível para sua conta no momento.</p>';
        return;
      }
      grid.innerHTML = produtos.map(renderCard).join("");
    } catch (e) {
      grid.innerHTML = `<p class="Mk_Empty">${esc(e.message || "Erro ao carregar catálogo.")}</p>`;
    }
  }

  grid.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-mk-detalhe]");
    if (!btn) return;
    const id = Number(btn.getAttribute("data-mk-detalhe"));
    const p = produtos.find((x) => x.id === id);
    if (p) abrirModal(p);
  });

  modal?.addEventListener("click", (e) => {
    if (e.target.matches("[data-mk-close]")) fecharModal();
  });

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && !modal.hidden) fecharModal();
  });

  document.getElementById("mk_btnContratar")?.addEventListener("click", () => {
    const titulo = atual?.titulo || "este item";
    if (window.Swal) {
      Swal.fire({
        icon: "info",
        title: "Em breve",
        html: `A contratação de <strong>${esc(titulo)}</strong> estará disponível aqui em breve.<br>Enquanto isso, fale com o comercial se precisar antecipar.`,
        confirmButtonText: "Entendi",
        confirmButtonColor: "#5b57f5",
      });
      return;
    }
    alert("Contratação em breve. Fale com o comercial se precisar antecipar.");
  });

  carregar();
})();
