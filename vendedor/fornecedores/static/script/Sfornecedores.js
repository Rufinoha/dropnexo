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
    pausado: { cls: "is-pending", txt: "Vínculo pausado", badge: "Pausado" },
    recusado: { cls: "is-denied", txt: "Não aprovado", badge: "Recusado" },
    inativo: { cls: "is-denied", txt: "Vínculo encerrado", badge: "Encerrado" },
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
        const stVin = f.status_vinculo || "nenhum";
        const podeVinculo = !["ativo", "aguardando", "pausado"].includes(stVin);
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
        const qtdVitrine = Number(f.qtd_produtos_vitrine) || 0;
        const conectado = stVin === "ativo";
        const pausado = stVin === "pausado";
        let acoesVinculo = "";
        if (conectado) {
          acoesVinculo =
            '<button type="button" class="Forn_CardBtn Forn_CardBtn--primary" data-acao="pausar">Pausar</button>' +
            '<button type="button" class="Forn_CardBtn Forn_CardBtn--danger" data-acao="encerrar">Encerrar</button>';
        } else if (pausado) {
          if (f.pode_despausar) {
            acoesVinculo =
              '<button type="button" class="Forn_CardBtn Forn_CardBtn--primary" data-acao="despausar">Despausar</button>';
          }
          acoesVinculo +=
            '<button type="button" class="Forn_CardBtn Forn_CardBtn--danger" data-acao="encerrar">Encerrar</button>';
        }
        return `
        <article class="Forn_Card ${st.cls}" data-id="${f.id}" data-nome="${attrEsc(f.nome)}"
          data-status="${stVin}" data-qtd-vitrine="${qtdVitrine}" tabindex="0" role="button"
          aria-label="Abrir catálogo de ${esc(f.nome)}">
          <div class="Forn_CardTop">
            <div class="Forn_CardBrand">
              <span class="Forn_CardAvatar" aria-hidden="true">${esc(iniciais || "?")}</span>
              <div class="Forn_CardBrandText">
                <h3 class="Forn_CardNome">${esc(f.nome)}</h3>
                <p class="Forn_CardLocal">${esc(local)}</p>
              </div>
            </div>
          </div>
          <div class="Forn_CardChips">${chips || '<span class="Forn_Chip Forn_Chip--muted">Sem segmento</span>'}</div>
          ${f.motivo_recusa ? `<p class="Forn_CardRecusa" title="${attrEsc(f.motivo_recusa)}">Motivo: ${esc(f.motivo_recusa)}</p>` : ""}
          ${f.motivo_status && (pausado || stVin === "inativo") ? `<p class="Forn_CardRecusa" title="${attrEsc(f.motivo_status)}">Motivo: ${esc(f.motivo_status)}</p>` : ""}
          <div class="Forn_CardMetaRow">
            <span class="Forn_CardStat">
              <strong>${qtd}</strong> ${qtd === 1 ? "produto" : "produtos"}
            </span>
            <span class="Forn_CardBadge">${esc(st.badge || st.txt)}</span>
          </div>
          <div class="Forn_CardFooter">
            <button type="button" class="Forn_CardBtn Forn_CardBtn--ghost" data-acao="loja">Ver catálogo</button>
            ${acoesVinculo}
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

  async function pedirMotivoVinculo({ title, htmlInfo, confirmText, confirmColor }) {
    if (!window.Swal) {
      const m = prompt((title || "") + "\nMotivo (obrigatório):");
      if (!m || m.trim().length < 5) return null;
      return m.trim();
    }
    const r = await Swal.fire({
      title,
      width: 520,
      html: `
        <div class="VdVinculoSwal">
          <div class="VdVinculoSwal__info">${htmlInfo}</div>
          <label class="VdVinculoSwal__label" for="fn_motivoVinculo">Motivo <span>*</span></label>
          <textarea id="fn_motivoVinculo" class="VdVinculoSwal__textarea" rows="4" placeholder="Explique o motivo com clareza…"></textarea>
        </div>`,
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: confirmText || "Confirmar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: confirmColor || "#b91c1c",
      cancelButtonColor: "#94a3b8",
      focusConfirm: false,
      customClass: {
        popup: "VdVinculoSwalPopup",
        title: "VdVinculoSwalTitle",
        htmlContainer: "VdVinculoSwalHtml",
        actions: "VdVinculoSwalActions",
        confirmButton: "VdVinculoSwalConfirm",
        cancelButton: "VdVinculoSwalCancel",
      },
      preConfirm: () => {
        const txt = (document.getElementById("fn_motivoVinculo")?.value || "").trim();
        if (txt.length < 5) {
          Swal.showValidationMessage("Informe o motivo com pelo menos 5 caracteres.");
          return false;
        }
        return txt;
      },
    });
    return r.isConfirmed ? r.value : null;
  }

  async function acaoVinculo(card, acao) {
    const id = Number(card.getAttribute("data-id"));
    const nome = card.getAttribute("data-nome") || "fornecedor";
    if (!id) return;

    if (acao === "despausar") {
      const ok = window.Swal
        ? (
            await Swal.fire({
              title: "Despausar vínculo?",
              html: `<p style="text-align:left;margin:0;line-height:1.45">Retomar operação com <strong>${esc(nome)}</strong>? Estoques voltam conforme a sincronização.</p>`,
              icon: "question",
              showCancelButton: true,
              confirmButtonText: "Despausar",
            })
          ).isConfirmed
        : confirm("Despausar vínculo?");
      if (!ok) return;
      try {
        const r = await fetch("/fornecedores/vinculo-acao", {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ id_fornecedor: id, acao: "despausar" }),
        });
        const j = await r.json();
        if (!j.success) throw new Error(j.message || "Falha ao despausar.");
        if (window.Swal) await Swal.fire("OK", j.message, "success");
        else alert(j.message);
        carregar();
      } catch (e) {
        if (window.Swal) Swal.fire("Erro", e.message, "error");
        else alert(e.message);
      }
      return;
    }

    const configs = {
      pausar: {
        title: "Pausar vínculo?",
        confirmText: "Pausar vínculo",
        confirmColor: "#b45309",
        htmlInfo:
          `<p class="VdVinculoSwal__lead">Com ${esc(nome)}</p><ul>` +
          "<li>O vínculo <strong>não é desfeito</strong></li>" +
          "<li>Estoques são <strong>zerados</strong> (produtos ficam visíveis com 0)</li>" +
          "<li>Novos produtos ficam bloqueados até despausar</li>" +
          "<li>O fornecedor recebe e-mail e aviso</li></ul>",
      },
      encerrar: {
        title: "Encerrar vínculo?",
        confirmText: "Encerrar vínculo",
        confirmColor: "#b91c1c",
        htmlInfo:
          `<p class="VdVinculoSwal__lead">Com ${esc(nome)}</p><ul>` +
          "<li>O vínculo é <strong>encerrado</strong></li>" +
          "<li>Para voltar, será preciso <strong>solicitar e ser aprovado</strong> de novo</li>" +
          "<li>Estoques são <strong>zerados</strong> (produtos ficam visíveis com 0)</li>" +
          "<li>O fornecedor recebe e-mail e aviso</li></ul>",
      },
    };
    const cfg = configs[acao];
    if (!cfg) return;
    const motivo = await pedirMotivoVinculo(cfg);
    if (!motivo) return;
    try {
      const r = await fetch("/fornecedores/vinculo-acao", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_fornecedor: id, acao, motivo }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha na operação.");
      if (window.Swal) await Swal.fire("OK", j.message, "success");
      else alert(j.message);
      carregar();
    } catch (e) {
      if (window.Swal) Swal.fire("Erro", e.message, "error");
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
      if (acao === "pausar" || acao === "despausar" || acao === "encerrar") {
        acaoVinculo(card, acao);
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
