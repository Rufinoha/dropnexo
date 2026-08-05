(function () {
  const lista = document.getElementById("vd_lista");
  const vazio = document.getElementById("vd_vazio");
  const modal = document.getElementById("vd_modal");
  const modalTitulo = document.getElementById("vd_modalTitulo");
  const modalBody = document.getElementById("vd_modalBody");
  const modalFooter = document.getElementById("vd_modalFooter");
  const fecharModal = document.getElementById("vd_fecharModal");
  const fNome = document.getElementById("vd_fNome");
  const fRazao = document.getElementById("vd_fRazao");
  const fDoc = document.getElementById("vd_fDoc");
  const fStatus = document.getElementById("vd_fStatus");
  const btnFiltrar = document.getElementById("vd_btnFiltrar");
  const btnLimpar = document.getElementById("vd_btnLimparFiltro");

  if (!lista) return;

  let dadosCache = [];
  let vinculoAtual = null;

  const STATUS_VISIVEIS = ["pausado", "aguardando", "ativo"];
  const ORDEM_STATUS = { pausado: 0, aguardando: 1, ativo: 2 };

  const statusMap = {
    aguardando: { cls: "is-aguardando", label: "Aguardando aprovação" },
    ativo: { cls: "is-ativo", label: "Vinculado" },
    pausado: { cls: "is-pausado", label: "Pausado" },
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

  async function pedirMotivoEConfirmar({ title, htmlInfo, confirmText, confirmColor }) {
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
          <label class="VdVinculoSwal__label" for="vd_motivoAcao">Motivo <span>*</span></label>
          <textarea id="vd_motivoAcao" class="VdVinculoSwal__textarea" rows="4" placeholder="Explique o motivo com clareza…"></textarea>
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
        const txt = (document.getElementById("vd_motivoAcao")?.value || "").trim();
        if (txt.length < 5) {
          Swal.showValidationMessage("Informe o motivo com pelo menos 5 caracteres.");
          return false;
        }
        return txt;
      },
    });
    return r.isConfirmed ? r.value : null;
  }

  function soDigitos(s) {
    return String(s || "").replace(/\D/g, "");
  }

  function contem(hay, needle) {
    if (!needle) return true;
    return String(hay || "")
      .toLowerCase()
      .includes(String(needle).toLowerCase());
  }

  function ordenarCards(rows) {
    return rows.slice().sort((a, b) => {
      const oa = ORDEM_STATUS[a.status] ?? 9;
      const ob = ORDEM_STATUS[b.status] ?? 9;
      if (oa !== ob) return oa - ob;
      const da = a.solicitado_em || "";
      const db = b.solicitado_em || "";
      return db.localeCompare(da);
    });
  }

  function aplicarFiltros() {
    const nomeQ = (fNome?.value || "").trim();
    const razaoQ = (fRazao?.value || "").trim();
    const docQ = soDigitos(fDoc?.value || "");
    const stQ = (fStatus?.value || "").trim();

    const filtrados = dadosCache.filter((v) => {
      if (!STATUS_VISIVEIS.includes(v.status)) return false;
      if (stQ && v.status !== stQ) return false;
      if (nomeQ) {
        const okNome = contem(v.nome, nomeQ) || contem(v.responsavel, nomeQ);
        if (!okNome) return false;
      }
      if (razaoQ && !contem(v.razao_social, razaoQ)) return false;
      if (docQ && !soDigitos(v.documento).includes(docQ)) return false;
      return true;
    });

    renderCards(ordenarCards(filtrados));
  }

  function renderCards(rows) {
    if (!rows.length) {
      lista.innerHTML = "";
      if (vazio) {
        vazio.hidden = false;
        vazio.textContent = dadosCache.length
          ? "Nenhum resultado para os filtros informados."
          : "Nenhuma solicitação ou vínculo.";
      }
      return;
    }
    if (vazio) vazio.hidden = true;
    lista.innerHTML = rows
      .map((v) => {
        const st = statusMap[v.status] || { cls: "", label: v.status };
        const loc = [v.cidade, v.uf].filter(Boolean).join(" / ") || "—";
        const resp = (v.responsavel || "").trim();
        return `
        <article class="VdParceiros_Card ${st.cls}" data-id="${v.id}" tabindex="0" title="Clique duas vezes para detalhes">
          <h3 class="VdParceiros_CardNome">${esc(v.nome)}</h3>
          ${resp ? `<p class="VdParceiros_CardMeta">Responsável: ${esc(resp)}</p>` : ""}
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

  function linkWhatsApp(raw) {
    let d = String(raw || "").replace(/\D/g, "");
    if (!d) return "";
    if (!d.startsWith("55") || d.length <= 11) d = "55" + d.replace(/^55/, "");
    return `https://wa.me/${d}`;
  }

  function htmlWhatsApp(raw) {
    const txt = String(raw || "").trim();
    if (!txt) return "—";
    const href = linkWhatsApp(txt);
    if (!href) return esc(txt);
    return `<a href="${esc(href)}" target="_blank" rel="noopener">${esc(txt)}</a>`;
  }

  function renderDetalhe(j) {
    const v = j.vendedor || {};
    const vin = j.vinculo || {};
    vinculoAtual = vin;
    if (modalTitulo) modalTitulo.textContent = v.nome || "Vendedor";

    modalBody.innerHTML = `
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
          <dt>WhatsApp</dt><dd>${htmlWhatsApp(v.whatsapp)}</dd>
          <dt>Site</dt><dd>${v.site ? `<a href="${esc(v.site)}" target="_blank" rel="noopener">${esc(v.site)}</a>` : "—"}</dd>
        </dl>
      </div>
      ${
        vin.motivo_status
          ? `<div class="VdParceiros_Secao"><h4>Motivo da última ação</h4><p>${esc(vin.motivo_status)}</p></div>`
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
          <button type="button" class="Cl_BtnCancelar" id="vd_btnPausar">Pausar vínculo</button>
          <button type="button" class="Cl_BtnExcluir" id="vd_btnInativar">Encerrar vínculo</button>`;
      } else if (vin.status === "pausado") {
        modalFooter.hidden = false;
        modalFooter.innerHTML = `
          ${
            vin.pode_despausar
              ? '<button type="button" class="Cl_BtnSalvar" id="vd_btnDespausar">Despausar vínculo</button>'
              : '<span class="Asf_Hint" style="align-self:center">Somente quem pausou pode despausar.</span>'
          }
          <button type="button" class="Cl_BtnExcluir" id="vd_btnInativar">Encerrar vínculo</button>`;
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
      body: JSON.stringify({ id: vinculoAtual.id, acao, mensagem: mensagem || "", motivo: mensagem || "" }),
    });
    let j = {};
    try {
      j = await r.json();
    } catch (_) {
      j = { success: false, message: "Erro no servidor (" + r.status + "). Tente novamente." };
    }
    if (window.Swal) Swal.fire(j.success ? "OK" : "Erro", j.message || "Falha", j.success ? "success" : "error");
    else alert(j.message || "Falha");
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
    aplicarFiltros();
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

  modalFooter?.addEventListener("click", async (e) => {
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
    if (e.target.id === "vd_btnPausar") {
      const motivo = await pedirMotivoEConfirmar({
        title: "Pausar vínculo?",
        htmlInfo:
          "<p class='VdVinculoSwal__lead'>O que acontece</p><ul>" +
          "<li>O vínculo <strong>não é desfeito</strong> (não precisa solicitar de novo)</li>" +
          "<li>Estoques deste vendedor são <strong>zerados</strong></li>" +
          "<li>Produtos ficam visíveis com estoque 0</li>" +
          "<li>Novos produtos ficam bloqueados até despausar</li>" +
          "<li>O vendedor recebe e-mail e aviso na plataforma</li></ul>",
        confirmText: "Pausar vínculo",
        confirmColor: "#b45309",
      });
      if (motivo) responder("pausar", motivo);
    }
    if (e.target.id === "vd_btnDespausar") {
      const ok = window.Swal
        ? (
            await Swal.fire({
              title: "Despausar vínculo?",
              text: "A operação volta ao normal. Estoques serão atualizados conforme a sincronização.",
              icon: "question",
              showCancelButton: true,
              confirmButtonText: "Despausar",
            })
          ).isConfirmed
        : confirm("Despausar vínculo?");
      if (ok) responder("despausar");
    }
    if (e.target.id === "vd_btnInativar") {
      const motivo = await pedirMotivoEConfirmar({
        title: "Encerrar vínculo?",
        htmlInfo:
          "<p class='VdVinculoSwal__lead'>O que acontece</p><ul>" +
          "<li>O vínculo é <strong>encerrado</strong></li>" +
          "<li>Para voltar, o vendedor precisa <strong>solicitar e ser aprovado</strong> de novo</li>" +
          "<li>Estoques são <strong>zerados</strong>; produtos ficam visíveis com estoque 0</li>" +
          "<li>O vendedor recebe e-mail e aviso na plataforma</li></ul>",
        confirmText: "Encerrar vínculo",
        confirmColor: "#b91c1c",
      });
      if (motivo) responder("inativar", motivo);
    }
  });

  fecharModal?.addEventListener("click", fechar);
  modal?.addEventListener("click", (e) => {
    if (e.target === modal) fechar();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && modal && !modal.hidden) fechar();
  });

  btnFiltrar?.addEventListener("click", aplicarFiltros);
  btnLimpar?.addEventListener("click", () => {
    if (fNome) fNome.value = "";
    if (fRazao) fRazao.value = "";
    if (fDoc) fDoc.value = "";
    if (fStatus) fStatus.value = "";
    aplicarFiltros();
  });
  [fNome, fRazao, fDoc].forEach((el) => {
    el?.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        aplicarFiltros();
      }
    });
  });
  fStatus?.addEventListener("change", aplicarFiltros);

  carregar();
})();
