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

  function iniciais(nome) {
    const p = String(nome || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (!p.length) return "?";
    if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
    return (p[0][0] + p[p.length - 1][0]).toUpperCase();
  }

  function fmtTel(raw) {
    const d = String(raw || "").replace(/\D/g, "");
    if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
    if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
    return String(raw || "").trim() || "—";
  }

  function fmtDataCurta(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleDateString("pt-BR", {
        day: "2-digit",
        month: "short",
        year: "numeric",
      });
    } catch {
      return iso;
    }
  }

  function siteHref(site) {
    const s = String(site || "").trim();
    if (!s) return "";
    return /^https?:\/\//i.test(s) ? s : "https://" + s;
  }

  function renderDetalhe(j) {
    const v = j.vendedor || {};
    const vin = j.vinculo || {};
    vinculoAtual = vin;
    const st = statusMap[vin.status] || { cls: "", label: vin.status || "—" };
    const nome = v.nome || "Vendedor";
    const loc = [v.cidade, v.uf].filter(Boolean).join(" / ");
    const waHref = v.whatsapp ? linkWhatsApp(v.whatsapp) : "";
    const siteUrl = siteHref(v.site);

    if (modalTitulo) {
      modalTitulo.innerHTML =
        `<span class="VdDet_HeadKicker">Solicitação de vínculo</span>` +
        `<span class="VdDet_HeadNome">${esc(nome)}</span>`;
    }

    const chips = [];
    if (v.email) {
      chips.push(`<a class="VdDet_Chip" href="mailto:${esc(v.email)}">E-mail</a>`);
    }
    if (waHref) {
      chips.push(
        `<a class="VdDet_Chip is-wa" href="${esc(waHref)}" target="_blank" rel="noopener">WhatsApp</a>`
      );
    }
    if (siteUrl) {
      chips.push(
        `<a class="VdDet_Chip" href="${esc(siteUrl)}" target="_blank" rel="noopener">Site</a>`
      );
    }

    const stats = [
      { label: "Na plataforma", value: v.tempo_plataforma || "—" },
      { label: "Fornecedores", value: String(v.qtd_fornecedores_ativos ?? "0") },
      { label: "Produtos", value: String(v.qtd_produtos_vitrine ?? "0") },
    ];
    if (v.tamanho_empresa) stats.push({ label: "Porte", value: v.tamanho_empresa });
    if (v.faturamento_ultimo_ano) stats.push({ label: "Faturamento", value: v.faturamento_ultimo_ano });

    modalBody.innerHTML = `
      <div class="VdDet">
        <section class="VdDet_Hero">
          <div class="VdDet_Avatar" aria-hidden="true">${esc(iniciais(nome))}</div>
          <div class="VdDet_HeroMain">
            <div class="VdDet_HeroTop">
              <span class="VdParceiros_Badge ${esc(st.cls)}">${esc(st.label)}</span>
              <span class="VdDet_Meta">Solicitado em ${esc(fmtDataCurta(vin.solicitado_em))}</span>
            </div>
            <h4 class="VdDet_Nome">${esc(nome)}</h4>
            <p class="VdDet_Loc">${esc(loc || "Localização não informada")}${
              v.documento ? ` · <span class="VdDet_Doc">${esc(v.documento)}</span>` : ""
            }</p>
            ${chips.length ? `<div class="VdDet_Quick">${chips.join("")}</div>` : ""}
          </div>
        </section>

        <section class="VdDet_Stats" aria-label="Indicadores">
          ${stats
            .map(
              (s) =>
                `<div class="VdDet_Stat"><span>${esc(s.label)}</span><strong>${esc(s.value)}</strong></div>`
            )
            .join("")}
        </section>

        <div class="VdDet_Grid">
          <section class="VdDet_Card">
            <h5>Empresa</h5>
            <dl class="VdDet_Dl">
              <div><dt>Razão social</dt><dd>${esc(v.razao_social || "—")}</dd></div>
              <div><dt>CPF / CNPJ</dt><dd>${esc(v.documento || "—")}</dd></div>
              <div><dt>Endereço</dt><dd>${esc(v.endereco || "—")}${
                v.cep ? `<br><span class="VdDet_Muted">CEP ${esc(v.cep)}</span>` : ""
              }</dd></div>
              <div><dt>Cidade</dt><dd>${esc(loc || "—")}</dd></div>
            </dl>
          </section>
          <section class="VdDet_Card">
            <h5>Contato</h5>
            <dl class="VdDet_Dl">
              <div><dt>Responsável</dt><dd>${esc(v.contato_nome || "—")}</dd></div>
              <div><dt>E-mail</dt><dd>${
                v.email
                  ? `<a href="mailto:${esc(v.email)}">${esc(v.email)}</a>`
                  : "—"
              }</dd></div>
              <div><dt>Telefone</dt><dd>${esc(fmtTel(v.telefone))}</dd></div>
              <div><dt>WhatsApp</dt><dd>${
                waHref
                  ? `<a class="VdDet_WaLink" href="${esc(waHref)}" target="_blank" rel="noopener">${esc(fmtTel(v.whatsapp))}</a>`
                  : "—"
              }</dd></div>
            </dl>
          </section>
        </div>

        ${
          vin.mensagem_solicitacao
            ? `<section class="VdDet_Note">
                <h5>Mensagem do vendedor</h5>
                <p>${esc(vin.mensagem_solicitacao)}</p>
              </section>`
            : ""
        }
        ${
          vin.motivo_status
            ? `<section class="VdDet_Note is-warn">
                <h5>Motivo da última ação</h5>
                <p>${esc(vin.motivo_status)}</p>
              </section>`
            : ""
        }
        ${
          vin.mensagem_resposta
            ? `<section class="VdDet_Note is-muted">
                <h5>Resposta enviada</h5>
                <p>${esc(vin.mensagem_resposta)}</p>
              </section>`
            : ""
        }
        ${
          v.aceite_requisitos
            ? `<section class="VdDet_Req is-ok">
                <span class="VdDet_ReqMark" aria-hidden="true">✓</span>
                <div>
                  <strong>Requisitos aceitos</strong>
                  <p>Vendedor concordou com os requisitos comerciais na solicitação.</p>
                </div>
              </section>`
            : `<section class="VdDet_Req">
                <span class="VdDet_ReqMark" aria-hidden="true">!</span>
                <div>
                  <strong>Requisitos</strong>
                  <p>Sem registro de aceite nesta solicitação.</p>
                </div>
              </section>`
        }
      </div>`;

    if (modalFooter) {
      if (vin.status === "aguardando") {
        modalFooter.hidden = false;
        modalFooter.innerHTML = `
          <div class="VdDet_FootLead">
            <strong>Decisão</strong>
            <span>Aprovar libera o catálogo; recusar envia o motivo ao vendedor.</span>
          </div>
          <div class="VdDet_FootBtns">
            <button type="button" class="Cl_BtnSalvar" id="vd_btnAprovar">Aprovar vínculo</button>
            <button type="button" class="Cl_BtnCancelar" id="vd_btnRecusar">Recusar</button>
          </div>
          <div class="VdParceiros_RecusaBox" id="vd_recusaBox" hidden>
            <label for="vd_motivoRecusa">Motivo da recusa (será enviado ao vendedor)</label>
            <textarea id="vd_motivoRecusa" placeholder="Explique o motivo para o vendedor…"></textarea>
            <button type="button" class="Cl_BtnExcluir" id="vd_btnConfirmarRecusa">Confirmar recusa</button>
          </div>`;
      } else if (vin.status === "ativo") {
        modalFooter.hidden = false;
        modalFooter.innerHTML = `
          <div class="VdDet_FootLead">
            <strong>Vínculo ativo</strong>
            <span>Pausar ou encerrar afeta a vitrine deste vendedor.</span>
          </div>
          <div class="VdDet_FootBtns">
            <button type="button" class="Cl_BtnCancelar" id="vd_btnPausar">Pausar vínculo</button>
            <button type="button" class="Cl_BtnExcluir" id="vd_btnInativar">Encerrar vínculo</button>
          </div>`;
      } else if (vin.status === "pausado") {
        modalFooter.hidden = false;
        modalFooter.innerHTML = `
          <div class="VdDet_FootLead">
            <strong>Vínculo pausado</strong>
            <span>${vin.pode_despausar ? "Você pode reativar ou encerrar." : "Somente quem pausou pode despausar."}</span>
          </div>
          <div class="VdDet_FootBtns">
            ${
              vin.pode_despausar
                ? '<button type="button" class="Cl_BtnSalvar" id="vd_btnDespausar">Despausar vínculo</button>'
                : ""
            }
            <button type="button" class="Cl_BtnExcluir" id="vd_btnInativar">Encerrar vínculo</button>
          </div>`;
      } else {
        modalFooter.hidden = true;
        modalFooter.innerHTML = "";
      }
    }
    abrir();
  }

  async function carregarDetalhe(id) {
    modalBody.innerHTML = '<div class="VdDet_Loading">Montando dossiê do vendedor…</div>';
    if (modalFooter) modalFooter.hidden = true;
    if (modalTitulo) {
      modalTitulo.innerHTML =
        `<span class="VdDet_HeadKicker">Solicitação de vínculo</span>` +
        `<span class="VdDet_HeadNome">Carregando…</span>`;
    }
    abrir();
    const r = await fetch("/fornecedor/vendedores/detalhe/" + id, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      modalBody.innerHTML = `<div class="VdDet_Loading is-err">${esc(j.message || "Erro")}</div>`;
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
