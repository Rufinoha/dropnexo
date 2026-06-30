(function () {
  const grid = document.getElementById("ob_gridFornecedores");
  const msgVazio = document.getElementById("ob_msgVazio");
  const contador = document.getElementById("ob_contador");
  const inpBusca = document.getElementById("ob_filtroBusca");
  const btnBuscar = document.getElementById("ob_btnBuscar");
  const listaSegmentos = document.getElementById("ob_listaSegmentos");
  const btnLimparSeg = document.getElementById("ob_limparSegmentos");

  if (!grid) return;

  const segmentosMarcados = new Set();

  const statusLabel = {
    nenhum: { cls: "", txt: "Não conectado", badge: "Não conectado" },
    aguardando: { cls: "is-pending", txt: "Aguardando aprovação", badge: "Aguardando" },
    ativo: { cls: "is-active", txt: "Conectado", badge: "Conectado" },
    recusado: { cls: "is-denied", txt: "Não aprovado", badge: "Recusado" },
    inativo: { cls: "is-denied", txt: "Vínculo encerrado", badge: "Inativo" },
  };

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function attrEsc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;");
  }

  function buildUrl() {
    const params = new URLSearchParams();
    const busca = (inpBusca && inpBusca.value.trim()) || "";
    if (busca) params.set("busca", busca);
    if (segmentosMarcados.size) params.set("segmentos", [...segmentosMarcados].join(","));
    const qs = params.toString();
    return "/fornecedores/rede" + (qs ? "?" + qs : "");
  }

  async function carregarSegmentos() {
    if (!listaSegmentos) return;
    const r = await fetch("/fornecedores/segmentos", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      listaSegmentos.innerHTML = '<p class="Forn_SidebarVazio">Erro ao carregar segmentos.</p>';
      return;
    }
    const lista = j.segmentos || [];
    if (!lista.length) {
      listaSegmentos.innerHTML = '<p class="Forn_SidebarVazio">Nenhum segmento disponível.</p>';
      return;
    }
    listaSegmentos.innerHTML = lista
      .map(
        (s) => `
      <label class="Forn_SidebarItem">
        <input type="checkbox" value="${s.id}" data-seg="${s.id}" />
        <span>${esc(s.nome)}</span>
        <span class="Forn_SidebarItemCount">${s.qtd_fornecedores}</span>
      </label>`
      )
      .join("");
  }

  function atualizarLimparSeg() {
    if (btnLimparSeg) btnLimparSeg.hidden = segmentosMarcados.size === 0;
  }

  async function carregar() {
    const r = await fetch(buildUrl(), { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      grid.innerHTML = "";
      if (msgVazio) {
        msgVazio.hidden = false;
        msgVazio.textContent = j.message || "Erro ao carregar.";
      }
      if (contador) contador.hidden = true;
      return;
    }
    const lista = j.fornecedores || [];
    if (contador) {
      contador.hidden = false;
      contador.textContent =
        lista.length === 1 ? "1 fornecedor encontrado" : `${lista.length} fornecedores encontrados`;
    }
    if (!lista.length) {
      grid.innerHTML = "";
      if (msgVazio) msgVazio.hidden = false;
      return;
    }
    if (msgVazio) msgVazio.hidden = true;
    grid.innerHTML = lista
      .map((f) => {
        const st = statusLabel[f.status_vinculo] || statusLabel.nenhum;
        const podeVinculo = !["ativo", "aguardando"].includes(f.status_vinculo || "nenhum");
        const chips = (f.segmentos || [])
          .map((s) => `<span class="Forn_Chip">${esc(s)}</span>`)
          .join("");
        const local = [f.cidade, f.uf].filter(Boolean).join(" / ") || "Local não informado";
        const iniciais = String(f.nome || "?")
          .split(/\s+/)
          .filter(Boolean)
          .slice(0, 2)
          .map((w) => w[0])
          .join("")
          .toUpperCase();
        const qtd = Number(f.qtd_produtos) || 0;
        return `
        <article class="Forn_Card ${st.cls}" data-id="${f.id}" data-nome="${attrEsc(f.nome)}"
          data-status="${f.status_vinculo || "nenhum"}" tabindex="0" role="button"
          aria-label="Abrir catálogo de ${esc(f.nome)}">
          <div class="Forn_CardTop">
            <div class="Forn_CardBrand">
              <span class="Forn_CardAvatar" aria-hidden="true">${esc(iniciais || "?")}</span>
              <div class="Forn_CardBrandText">
                <h3 class="Forn_CardNome">${esc(f.nome)}</h3>
                <p class="Forn_CardLocal">${esc(local)}</p>
              </div>
            </div>
            <span class="Forn_CardBadge">${esc(st.badge || st.txt)}</span>
          </div>
          <div class="Forn_CardChips">${chips || '<span class="Forn_Chip Forn_Chip--muted">Sem segmento</span>'}</div>
          <div class="Forn_CardStats">
            <span class="Forn_CardStat">
              <strong>${qtd}</strong> ${qtd === 1 ? "produto" : "produtos"}
            </span>
          </div>
          ${f.motivo_recusa ? `<p class="Forn_CardRecusa" title="${attrEsc(f.motivo_recusa)}">Motivo: ${esc(f.motivo_recusa)}</p>` : ""}
          <div class="Forn_CardFooter">
            <button type="button" class="Forn_CardBtn Forn_CardBtn--ghost" data-acao="loja">Ver catálogo</button>
            ${
              podeVinculo
                ? '<button type="button" class="Forn_CardBtn Forn_CardBtn--primary" data-acao="vinculo">Solicitar vínculo</button>'
                : ""
            }
          </div>
        </article>`;
      })
      .join("");
  }

  let clickTimer = null;

  function abrirLoja(id, nome) {
    if (!window.GlobalUtils?.abrirJanelaApoioModal) {
      window.location.href = "/fornecedores/loja?id=" + id;
      return;
    }
    window.GlobalUtils.abrirJanelaApoioModal({
      rota: "/fornecedores/loja",
      id,
      titulo: "Catálogo — " + (nome || "Fornecedor"),
      largura: 1280,
      altura: 860,
      nivel: 1,
    });
  }

  async function solicitarVinculoCard(card) {
    const id = Number(card.getAttribute("data-id"));
    const nome = card.getAttribute("data-nome");
    const st = card.getAttribute("data-status") || "nenhum";
    if (st === "ativo") {
      if (window.Util?.alertar) Util.alertar("Você já está conectado a este fornecedor.", "info");
      return;
    }
    if (st === "aguardando") {
      if (window.Util?.alertar) Util.alertar("Solicitação já enviada. Aguarde aprovação.", "info");
      return;
    }
    if (!window.VinculoRequisitos?.solicitarComRequisitos) {
      alert("Módulo de vínculo indisponível.");
      return;
    }
    try {
      const ok = await VinculoRequisitos.solicitarComRequisitos(id, nome);
      if (ok) carregar();
    } catch (e) {
      if (window.Swal) Swal.fire("Erro", e.message, "error");
      else if (window.Util?.alertar) Util.alertar(e.message, "error");
      else alert(e.message);
    }
  }

  grid.addEventListener("click", (e) => {
    const btnAcao = e.target.closest("[data-acao]");
    const card = e.target.closest(".Forn_Card");
    if (!card) return;

    if (btnAcao) {
      e.preventDefault();
      e.stopPropagation();
      clearTimeout(clickTimer);
      const acao = btnAcao.getAttribute("data-acao");
      const id = card.getAttribute("data-id");
      const nome = card.getAttribute("data-nome");
      if (acao === "vinculo") {
        solicitarVinculoCard(card);
        return;
      }
      if (acao === "loja" && id) {
        abrirLoja(id, nome);
        return;
      }
    }

    clearTimeout(clickTimer);
    clickTimer = setTimeout(() => {
      const id = card.getAttribute("data-id");
      const nome = card.getAttribute("data-nome");
      if (id) abrirLoja(id, nome);
    }, 260);
  });

  grid.addEventListener("dblclick", (e) => {
    const card = e.target.closest(".Forn_Card");
    if (!card || e.target.closest("[data-acao='loja']")) return;
    e.preventDefault();
    clearTimeout(clickTimer);
    solicitarVinculoCard(card);
  });

  grid.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const card = e.target.closest(".Forn_Card");
    if (!card) return;
    e.preventDefault();
    const id = card.getAttribute("data-id");
    const nome = card.getAttribute("data-nome");
    if (id) abrirLoja(id, nome);
  });

  listaSegmentos?.addEventListener("change", (e) => {
    const cb = e.target.closest('input[type="checkbox"]');
    if (!cb) return;
    const id = cb.value;
    if (cb.checked) segmentosMarcados.add(id);
    else segmentosMarcados.delete(id);
    atualizarLimparSeg();
    carregar();
  });

  btnLimparSeg?.addEventListener("click", () => {
    segmentosMarcados.clear();
    listaSegmentos?.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
      cb.checked = false;
    });
    atualizarLimparSeg();
    carregar();
  });

  if (btnBuscar) btnBuscar.addEventListener("click", carregar);
  if (inpBusca) {
    inpBusca.addEventListener("keydown", (e) => {
      if (e.key === "Enter") carregar();
    });
  }

  carregarSegmentos().then(carregar).catch(() => carregar());

  window.addEventListener("message", (ev) => {
    if (ev.data?.grupo === "vinculoSolicitado") carregar();
  });
})();
