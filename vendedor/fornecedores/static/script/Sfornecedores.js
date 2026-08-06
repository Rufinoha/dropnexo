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
  /** Contatos dos fornecedores conectados (id → contato). */
  const contatosPorId = new Map();

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

  function linkWhatsApp(raw) {
    let d = String(raw || "").replace(/\D/g, "");
    if (!d) return "";
    if (!d.startsWith("55") || d.length <= 11) d = "55" + d.replace(/^55/, "");
    return `https://wa.me/${d}`;
  }

  function siteHref(site) {
    const s = String(site || "").trim();
    if (!s) return "";
    return /^https?:\/\//i.test(s) ? s : "https://" + s;
  }

  function fmtTel(raw) {
    const d = String(raw || "").replace(/\D/g, "");
    if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
    if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
    return String(raw || "").trim() || "—";
  }

  function iniciaisNome(nome) {
    const p = String(nome || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (!p.length) return "?";
    if (p.length === 1) return p[0].slice(0, 2).toUpperCase();
    return (p[0][0] + p[p.length - 1][0]).toUpperCase();
  }

  function svgIcon(tipo) {
    const common = 'xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"';
    if (tipo === "mail") {
      return `<svg ${common}><rect width="20" height="16" x="2" y="4" rx="2"/><path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7"/></svg>`;
    }
    if (tipo === "wa") {
      return `<svg ${common}><path d="M21 11.5a8.38 8.38 0 0 1-.9 3.8 8.5 8.5 0 0 1-7.6 4.7 8.38 8.38 0 0 1-3.8-.9L3 21l1.9-5.7a8.38 8.38 0 0 1-.9-3.8 8.5 8.5 0 0 1 4.7-7.6 8.38 8.38 0 0 1 3.8-.9h.5a8.48 8.48 0 0 1 8 8v.5z"/></svg>`;
    }
    if (tipo === "phone") {
      return `<svg ${common}><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.12.9.36 1.77.7 2.61a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.84.34 1.71.58 2.61.7A2 2 0 0 1 22 16.92z"/></svg>`;
    }
    if (tipo === "globe") {
      return `<svg ${common}><circle cx="12" cy="12" r="10"/><path d="M12 2a14.5 14.5 0 0 0 0 20 14.5 14.5 0 0 0 0-20"/><path d="M2 12h20"/></svg>`;
    }
    if (tipo === "user") {
      return `<svg ${common}><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2"/><circle cx="12" cy="7" r="4"/></svg>`;
    }
    if (tipo === "pin") {
      return `<svg ${common}><path d="M20 10c0 4.993-5.539 10.193-7.399 11.799a1 1 0 0 1-1.202 0C9.539 20.193 4 14.993 4 10a8 8 0 0 1 16 0"/><circle cx="12" cy="10" r="3"/></svg>`;
    }
    return "";
  }

  function abrirContatoFornecedor(card) {
    const id = Number(card.getAttribute("data-id"));
    const nome = card.getAttribute("data-nome") || "Fornecedor";
    const local = card.getAttribute("data-local") || "";
    const c = contatosPorId.get(id) || {};
    const email = (c.email || "").trim();
    const wa = (c.whatsapp || "").trim();
    const tel = (c.telefone || "").trim();
    const site = (c.site || "").trim();
    const resp = (c.responsavel || "").trim();
    const waHref = wa ? linkWhatsApp(wa) : "";
    const siteUrl = siteHref(site);
    const telDigits = tel.replace(/\D/g, "");
    const telHref = telDigits
      ? `tel:+${telDigits.startsWith("55") ? telDigits : "55" + telDigits}`
      : "";

    const acoes = [];
    if (email) {
      acoes.push(`
        <a class="FornContato_Acao is-mail" href="mailto:${esc(email)}">
          <span class="FornContato_AcaoIcon">${svgIcon("mail")}</span>
          <span class="FornContato_AcaoTxt">
            <strong>Enviar e-mail</strong>
            <small>${esc(email)}</small>
          </span>
        </a>`);
    }
    if (waHref) {
      acoes.push(`
        <a class="FornContato_Acao is-wa" href="${esc(waHref)}" target="_blank" rel="noopener">
          <span class="FornContato_AcaoIcon">${svgIcon("wa")}</span>
          <span class="FornContato_AcaoTxt">
            <strong>WhatsApp</strong>
            <small>${esc(fmtTel(wa))}</small>
          </span>
        </a>`);
    }
    if (telHref) {
      acoes.push(`
        <a class="FornContato_Acao is-tel" href="${esc(telHref)}">
          <span class="FornContato_AcaoIcon">${svgIcon("phone")}</span>
          <span class="FornContato_AcaoTxt">
            <strong>Ligar</strong>
            <small>${esc(fmtTel(tel))}</small>
          </span>
        </a>`);
    }
    if (siteUrl) {
      acoes.push(`
        <a class="FornContato_Acao is-site" href="${esc(siteUrl)}" target="_blank" rel="noopener">
          <span class="FornContato_AcaoIcon">${svgIcon("globe")}</span>
          <span class="FornContato_AcaoTxt">
            <strong>Abrir site</strong>
            <small>${esc(site)}</small>
          </span>
        </a>`);
    }

    const linhas = [
      {
        icon: "user",
        label: "Responsável",
        value: resp ? esc(resp) : '<span class="FornContato_Empty">Não informado</span>',
      },
      {
        icon: "mail",
        label: "E-mail",
        value: email
          ? `<a href="mailto:${esc(email)}">${esc(email)}</a>
             <button type="button" class="FornContato_Copy" data-copy="${attrEsc(email)}" title="Copiar">Copiar</button>`
          : '<span class="FornContato_Empty">Não informado</span>',
      },
      {
        icon: "wa",
        label: "WhatsApp",
        value: waHref
          ? `<a class="is-wa" href="${esc(waHref)}" target="_blank" rel="noopener">${esc(fmtTel(wa))}</a>`
          : '<span class="FornContato_Empty">Não informado</span>',
      },
      {
        icon: "phone",
        label: "Telefone",
        value: tel
          ? telHref
            ? `<a href="${esc(telHref)}">${esc(fmtTel(tel))}</a>`
            : esc(fmtTel(tel))
          : '<span class="FornContato_Empty">Não informado</span>',
      },
      {
        icon: "globe",
        label: "Site",
        value: siteUrl
          ? `<a href="${esc(siteUrl)}" target="_blank" rel="noopener">${esc(site)}</a>`
          : '<span class="FornContato_Empty">Não informado</span>',
      },
    ];

    const html = `
      <div class="FornContato">
        <header class="FornContato_Hero">
          <div class="FornContato_Avatar" aria-hidden="true">${esc(iniciaisNome(nome))}</div>
          <div class="FornContato_HeroMain">
            <div class="FornContato_HeroTop">
              <span class="FornContato_Badge">Conectado</span>
              ${
                local
                  ? `<span class="FornContato_Pin">${svgIcon("pin")}<span>${esc(local)}</span></span>`
                  : ""
              }
            </div>
            <h3 class="FornContato_Nome">${esc(nome)}</h3>
            <p class="FornContato_Lead">Canal direto com o dono da conta — fale com quem decide.</p>
          </div>
        </header>

        ${
          acoes.length
            ? `<section class="FornContato_Acoes" aria-label="Ações rápidas">${acoes.join("")}</section>`
            : `<p class="FornContato_Vazio">Este fornecedor ainda não disponibilizou canais de contato.</p>`
        }

        <section class="FornContato_Painel">
          <h4>Dados do dono</h4>
          <ul class="FornContato_Lista">
            ${linhas
              .map(
                (l) => `<li class="FornContato_Item">
                  <span class="FornContato_ItemIcon">${svgIcon(l.icon)}</span>
                  <div class="FornContato_ItemBody">
                    <span class="FornContato_ItemLabel">${esc(l.label)}</span>
                    <div class="FornContato_ItemValue">${l.value}</div>
                  </div>
                </li>`
              )
              .join("")}
          </ul>
        </section>
      </div>`;

    if (window.Swal) {
      Swal.fire({
        html,
        width: 560,
        showConfirmButton: true,
        confirmButtonText: "Fechar",
        showDenyButton: true,
        denyButtonText: "Ver catálogo",
        customClass: {
          popup: "FornContatoSwal",
          htmlContainer: "FornContatoSwal__html",
          actions: "FornContatoSwal__actions",
          confirmButton: "FornContatoSwal__confirm",
          denyButton: "FornContatoSwal__deny",
        },
        buttonsStyling: false,
        didOpen: (popup) => {
          popup.querySelectorAll("[data-copy]").forEach((btn) => {
            btn.addEventListener("click", async (ev) => {
              ev.preventDefault();
              const txt = btn.getAttribute("data-copy") || "";
              if (!txt || !navigator.clipboard?.writeText) return;
              try {
                await navigator.clipboard.writeText(txt);
                const prev = btn.textContent;
                btn.textContent = "Copiado!";
                btn.classList.add("is-ok");
                setTimeout(() => {
                  btn.textContent = prev || "Copiar";
                  btn.classList.remove("is-ok");
                }, 1200);
              } catch {
                /* ignore */
              }
            });
          });
        },
      }).then((res) => {
        if (res.isDenied) abrirLoja(String(id), nome);
      });
      return;
    }
    alert(
      [nome, email && `E-mail: ${email}`, wa && `WhatsApp: ${wa}`, tel && `Telefone: ${tel}`, site && `Site: ${site}`]
        .filter(Boolean)
        .join("\n") || "Sem contatos disponíveis."
    );
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
    contatosPorId.clear();
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
        if (conectado && f.contato) contatosPorId.set(Number(f.id), f.contato);
        let acoesVinculo = "";
        if (conectado) {
          acoesVinculo =
            '<button type="button" class="Forn_CardBtn Forn_CardBtn--primary" data-acao="contato">Contatar</button>' +
            '<button type="button" class="Forn_CardBtn Forn_CardBtn--ghost" data-acao="pausar">Pausar</button>' +
            '<button type="button" class="Forn_CardBtn Forn_CardBtn--danger" data-acao="encerrar">Encerrar</button>';
        } else if (pausado) {
          if (f.pode_despausar) {
            acoesVinculo =
              '<button type="button" class="Forn_CardBtn Forn_CardBtn--primary" data-acao="despausar">Despausar</button>';
          }
          acoesVinculo +=
            '<button type="button" class="Forn_CardBtn Forn_CardBtn--danger" data-acao="encerrar">Encerrar</button>';
        }
        const aria = conectado
          ? `Contatar ${esc(f.nome)}`
          : `Abrir catálogo de ${esc(f.nome)}`;
        return `
        <article class="Forn_Card ${st.cls}" data-id="${f.id}" data-nome="${attrEsc(f.nome)}"
          data-status="${stVin}" data-local="${attrEsc(local)}" data-qtd-vitrine="${qtdVitrine}"
          tabindex="0" role="button" aria-label="${aria}">
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
    const st = card.getAttribute("data-status") || "nenhum";
    const conectado = st === "ativo";

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
      if (acao === "contato") {
        abrirContatoFornecedor(card);
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
      if (conectado) abrirContatoFornecedor(card);
      else {
        const id = card.getAttribute("data-id");
        const nome = card.getAttribute("data-nome");
        if (id) abrirLoja(id, nome);
      }
    }, 260);
  });

  grid.addEventListener("dblclick", (e) => {
    const card = e.target.closest(".Forn_Card");
    if (!card || e.target.closest("[data-acao]")) return;
    e.preventDefault();
    clearTimeout(clickTimer);
    const st = card.getAttribute("data-status") || "nenhum";
    if (st === "ativo") abrirContatoFornecedor(card);
    else solicitarVinculoCard(card);
  });

  grid.addEventListener("keydown", (e) => {
    if (e.key !== "Enter" && e.key !== " ") return;
    const card = e.target.closest(".Forn_Card");
    if (!card) return;
    e.preventDefault();
    const st = card.getAttribute("data-status") || "nenhum";
    if (st === "ativo") {
      abrirContatoFornecedor(card);
      return;
    }
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
