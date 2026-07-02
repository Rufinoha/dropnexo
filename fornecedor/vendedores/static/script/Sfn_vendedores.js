(function () {
  const lista = document.getElementById("vd_lista");
  const vazio = document.getElementById("vd_vazio");
  const modal = document.getElementById("vd_modal");
  const modalTitulo = document.getElementById("vd_modalTitulo");
  const modalBody = document.getElementById("vd_modalBody");
  const modalFooter = document.getElementById("vd_modalFooter");
  const fecharModal = document.getElementById("vd_fecharModal");

  if (!lista) return;

  let dadosCache = [];
  let vinculoAtual = null;

  const statusMap = {
    aguardando: { cls: "is-aguardando", label: "Aguardando aprovação" },
    ativo: { cls: "is-ativo", label: "Vínculo ativo" },
    recusado: { cls: "", label: "Recusado" },
    inativo: { cls: "", label: "Encerrado" },
  };

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function fmtData(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("pt-BR");
    } catch {
      return iso;
    }
  }

  function fechar() {
    if (!modal) return;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
    vinculoAtual = null;
  }

  function abrir() {
    if (!modal) return;
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
  }

  function renderCards(rows) {
    if (!rows.length) {
      lista.innerHTML = "";
      if (vazio) vazio.hidden = false;
      return;
    }
    if (vazio) vazio.hidden = true;
    lista.innerHTML = rows
      .map((v) => {
        const st = statusMap[v.status] || { cls: "", label: v.status };
        const loc = [v.cidade, v.uf].filter(Boolean).join(" / ") || "—";
        return `
        <article class="VdParceiros_Card ${st.cls}" data-id="${v.id}" tabindex="0" title="Clique duas vezes para detalhes">
          <h3 class="VdParceiros_CardNome">${esc(v.nome)}</h3>
          <p class="VdParceiros_CardMeta">${esc(loc)}</p>
          <p class="VdParceiros_CardMeta">Solicitado: ${fmtData(v.solicitado_em)}</p>
          <div class="VdParceiros_CardFoot">
            <span class="VdParceiros_Badge ${st.cls}">${esc(st.label)}</span>
            <button type="button" class="Cl_BtnLink VdParceiros_BtnDetalhe" data-acao="detalhe" data-id="${v.id}">Ver detalhes</button>
          </div>
        </article>`;
      })
      .join("");
  }

  function renderDetalhe(j) {
    const v = j.vendedor || {};
    const vin = j.vinculo || {};
    vinculoAtual = vin;
    if (modalTitulo) modalTitulo.textContent = v.nome || "Vendedor";

    modalBody.innerHTML = `
      <div class="VdParceiros_Secao">
        <h4>Resumo na plataforma</h4>
        <div class="VdParceiros_Stats">
          <span class="VdParceiros_Stat">${esc(v.tempo_plataforma)}</span>
          <span class="VdParceiros_Stat">${v.qtd_fornecedores_ativos || 0} fornecedor(es) ativo(s)</span>
          <span class="VdParceiros_Stat">${v.qtd_produtos_vitrine || 0} produto(s) na vitrine</span>
        </div>
      </div>
      <div class="VdParceiros_Secao">
        <h4>Dados básicos</h4>
        <dl class="VdParceiros_Dl">
          <dt>Nome</dt><dd>${esc(v.nome)}</dd>
          <dt>Razão social</dt><dd>${esc(v.razao_social || "—")}</dd>
          <dt>CPF / CNPJ</dt><dd>${esc(v.documento || "—")}</dd>
          <dt>Endereço</dt><dd>${esc(v.endereco || "—")}${v.cep ? " · CEP " + esc(v.cep) : ""}</dd>
          <dt>Cidade</dt><dd>${esc([v.cidade, v.uf].filter(Boolean).join(" / ") || "—")}</dd>
        </dl>
      </div>
      <div class="VdParceiros_Secao">
        <h4>Contato</h4>
        <dl class="VdParceiros_Dl">
          <dt>Responsável</dt><dd>${esc(v.contato_nome || "—")}</dd>
          <dt>E-mail</dt><dd>${v.email ? `<a href="mailto:${esc(v.email)}">${esc(v.email)}</a>` : "—"}</dd>
          <dt>Telefone</dt><dd>${esc(v.telefone || "—")}</dd>
          <dt>WhatsApp</dt><dd>${esc(v.whatsapp || "—")}</dd>
          <dt>Site</dt><dd>${v.site ? `<a href="${esc(v.site)}" target="_blank" rel="noopener">${esc(v.site)}</a>` : "—"}</dd>
        </dl>
      </div>
      ${
        v.faturamento_ultimo_ano || v.tamanho_empresa
          ? `<div class="VdParceiros_Secao"><h4>Perfil comercial</h4><dl class="VdParceiros_Dl">
          <dt>Faturamento</dt><dd>${esc(v.faturamento_ultimo_ano || "—")}</dd>
          <dt>Porte</dt><dd>${esc(v.tamanho_empresa || "—")}</dd>
        </dl></div>`
          : ""
      }
      ${
        vin.mensagem_solicitacao
          ? `<div class="VdParceiros_Secao"><h4>Mensagem do vendedor</h4><p>${esc(vin.mensagem_solicitacao)}</p></div>`
          : ""
      }
      ${
        v.aceite_requisitos
          ? `<div class="VdParceiros_Secao"><h4>Requisitos</h4><p style="font-size:0.9rem;color:#047857">Vendedor concordou com os requisitos comerciais na solicitação.</p></div>`
          : ""
      }`;

    if (modalFooter) {
      if (vin.status === "aguardando") {
        modalFooter.hidden = false;
        modalFooter.innerHTML = `
          <button type="button" class="Cl_BtnSalvar" id="vd_btnAprovar">Aprovar vínculo</button>
          <button type="button" class="Cl_BtnCancelar" id="vd_btnRecusar">Recusar</button>
          <div class="VdParceiros_RecusaBox" id="vd_recusaBox" hidden>
            <label for="vd_motivoRecusa">Motivo da recusa (será enviado ao vendedor)</label>
            <textarea id="vd_motivoRecusa" placeholder="Explique o motivo para o vendedor…"></textarea>
            <button type="button" class="Cl_BtnExcluir" id="vd_btnConfirmarRecusa" style="margin-top:8px">Confirmar recusa</button>
          </div>`;
      } else if (vin.status === "ativo") {
        modalFooter.hidden = false;
        modalFooter.innerHTML = `
          <button type="button" class="Cl_BtnLink" id="vd_btnInativar">Encerrar vínculo</button>`;
      } else {
        modalFooter.hidden = true;
        modalFooter.innerHTML = "";
        if (vin.mensagem_resposta) {
          modalBody.innerHTML += `<div class="VdParceiros_Secao"><h4>Resposta enviada</h4><p>${esc(vin.mensagem_resposta)}</p></div>`;
        }
      }
    }
    abrir();
  }

  async function carregarDetalhe(id) {
    modalBody.innerHTML = "<p>Carregando…</p>";
    if (modalFooter) modalFooter.hidden = true;
    abrir();
    const r = await fetch("/fornecedor/vendedores/detalhe/" + id, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      modalBody.innerHTML = "<p>" + esc(j.message || "Erro") + "</p>";
      return;
    }
    renderDetalhe(j);
  }

  async function responder(acao, mensagem) {
    if (!vinculoAtual) return;
    const r = await fetch("/fornecedor/vendedores/responder", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: vinculoAtual.id, acao, mensagem: mensagem || "" }),
    });
    const j = await r.json();
    if (window.Swal) Swal.fire(j.success ? "OK" : "Erro", j.message, j.success ? "success" : "error");
    else alert(j.message);
    if (j.success) {
      fechar();
      carregar();
    }
  }

  async function carregar() {
    const r = await fetch("/fornecedor/vendedores/dados", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      lista.textContent = j.message || "Erro";
      return;
    }
    dadosCache = j.dados || [];
    renderCards(dadosCache);
  }

  lista.addEventListener("click", (e) => {
    const btn = e.target.closest("[data-acao='detalhe']");
    if (!btn) return;
    e.preventDefault();
    e.stopPropagation();
    carregarDetalhe(btn.getAttribute("data-id"));
  });

  lista.addEventListener("dblclick", (e) => {
    const card = e.target.closest(".VdParceiros_Card");
    if (!card) return;
    carregarDetalhe(card.getAttribute("data-id"));
  });

  modalFooter?.addEventListener("click", (e) => {
    if (e.target.id === "vd_btnAprovar") responder("aprovar");
    if (e.target.id === "vd_btnRecusar") {
      const box = document.getElementById("vd_recusaBox");
      if (box) box.hidden = false;
    }
    if (e.target.id === "vd_btnConfirmarRecusa") {
      const txt = (document.getElementById("vd_motivoRecusa")?.value || "").trim();
      if (txt.length < 5) {
        Swal?.fire("Atenção", "Informe o motivo da recusa (mínimo 5 caracteres).", "warning");
        return;
      }
      responder("recusar", txt);
    }
    if (e.target.id === "vd_btnInativar") {
      Swal?.fire({
        title: "Encerrar vínculo?",
        text: "Produtos serão desativados e estoque zerado na vitrine.",
        icon: "warning",
        showCancelButton: true,
      }).then((c) => {
        if (c.isConfirmed) responder("inativar");
      });
    }
  });

  fecharModal?.addEventListener("click", fechar);
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) fechar();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && !modal.hidden) fechar();
  });

  carregar();
})();
