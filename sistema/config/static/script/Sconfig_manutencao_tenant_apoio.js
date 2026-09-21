(function () {
  const BASE = "/configuracoes/manutencao-tenant";
  let nivelModal = 1;
  let idTenant = 0;
  let tipoOriginal = "";
  let slugAtual = "";
  let protegido = false;
  let ehSessao = false;
  let temRelacionamento = false;

  const el = {
    id: document.getElementById("id"),
    nome: document.getElementById("nome"),
    slug: document.getElementById("slug"),
    tipo: document.getElementById("tipo_negocio"),
    plano: document.getElementById("plano"),
    documento: document.getElementById("documento"),
    ativo: document.getElementById("ativo"),
    limparSeg: document.getElementById("limpar_segmentos"),
    wrapLimpar: document.getElementById("wrap_limpar_seg"),
    contato: document.getElementById("contato"),
    linkWhatsapp: document.getElementById("link_whatsapp"),
    whatsappVazio: document.getElementById("whatsapp_vazio"),
    linkEmail: document.getElementById("link_email"),
    emailVazio: document.getElementById("email_vazio"),
    counts: document.getElementById("counts"),
    warn: document.getElementById("warn"),
    btnSalvar: document.getElementById("btnSalvar"),
    btnExcluir: document.getElementById("btnExcluir"),
    btnDesativar: document.getElementById("btnDesativar"),
    tabs: document.getElementById("cfg_mt_tabs"),
    paneTenant: document.getElementById("cfg_pane_tenant"),
    paneDono: document.getElementById("cfg_pane_dono"),
    donoVazio: document.getElementById("dono_vazio"),
    donoDados: document.getElementById("dono_dados"),
    donoId: document.getElementById("dono_id"),
    donoNome: document.getElementById("dono_nome"),
    donoEmail: document.getElementById("dono_email"),
    donoWhatsapp: document.getElementById("dono_whatsapp"),
    donoPerfil: document.getElementById("dono_perfil"),
    donoAtivo: document.getElementById("dono_ativo"),
    donoVinculo: document.getElementById("dono_vinculo"),
    donoDev: document.getElementById("dono_dev"),
    donoCriado: document.getElementById("dono_criado"),
    donoAcesso: document.getElementById("dono_acesso"),
  };

  function pickTab(tab) {
    const t = tab === "dono" ? "dono" : "tenant";
    el.tabs?.querySelectorAll(".CfgMt_Tab").forEach((b) => {
      b.classList.toggle("is-active", b.dataset.tab === t);
    });
    if (el.paneTenant) el.paneTenant.hidden = t !== "tenant";
    if (el.paneDono) el.paneDono.hidden = t !== "dono";
    if (el.btnSalvar) el.btnSalvar.hidden = t !== "tenant";
  }

  function formatarDataHora(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) {
      const s = String(iso).replace("T", " ");
      return s.length >= 16 ? s.slice(0, 16) : s;
    }
    const pad = (n) => String(n).padStart(2, "0");
    return (
      `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ` +
      `${pad(d.getHours())}:${pad(d.getMinutes())}`
    );
  }

  function simNao(v) {
    if (v === true) return "Sim";
    if (v === false) return "Não";
    return "—";
  }

  function preencherDono(t) {
    const d = t?.dono && typeof t.dono === "object" ? t.dono : null;
    const tem = !!(d && d.id);
    if (el.donoVazio) el.donoVazio.hidden = tem;
    if (el.donoDados) el.donoDados.hidden = !tem;
    if (!tem) return;
    if (el.donoId) el.donoId.value = String(d.id);
    if (el.donoNome) el.donoNome.value = d.nome || "";
    if (el.donoEmail) el.donoEmail.value = d.email || "";
    if (el.donoWhatsapp) {
      el.donoWhatsapp.value = formatarWhatsappExibicao(d.whatsapp) || d.whatsapp || "";
    }
    if (el.donoPerfil) {
      const cod = (d.perfil_codigo || "").trim();
      const nome = (d.perfil_nome || "").trim();
      el.donoPerfil.value = nome && cod ? `${nome} (${cod})` : nome || cod || "dono";
    }
    if (el.donoAtivo) el.donoAtivo.value = simNao(d.ativo);
    if (el.donoVinculo) el.donoVinculo.value = simNao(d.vinculo_ativo);
    if (el.donoDev) el.donoDev.value = simNao(!!d.eh_desenvolvedor);
    if (el.donoCriado) el.donoCriado.value = formatarDataHora(d.criado_em);
    if (el.donoAcesso) el.donoAcesso.value = formatarDataHora(d.ultimo_acesso_em);
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function soDigitos(s) {
    return String(s || "").replace(/\D+/g, "");
  }

  function formatarWhatsappExibicao(raw) {
    const d = soDigitos(raw);
    if (!d) return "";
    if (window.Util?.formatarTelefone) return window.Util.formatarTelefone(d) || d;
    return d;
  }

  function linkWhatsapp(raw) {
    let d = soDigitos(raw);
    if (!d) return "";
    if (d.length >= 10 && d.length <= 11) d = "55" + d;
    return `https://wa.me/${d}`;
  }

  function preencherContato(t) {
    if (el.contato) el.contato.hidden = false;
    const wa = (t.whatsapp || "").trim();
    const email = (t.email || t.email_comercial || "").trim();

    if (el.linkWhatsapp && el.whatsappVazio) {
      const href = linkWhatsapp(wa);
      if (href) {
        el.linkWhatsapp.hidden = false;
        el.whatsappVazio.hidden = true;
        el.linkWhatsapp.href = href;
        el.linkWhatsapp.textContent = formatarWhatsappExibicao(wa) || wa;
        el.linkWhatsapp.title = "Abrir WhatsApp";
      } else {
        el.linkWhatsapp.hidden = true;
        el.linkWhatsapp.removeAttribute("href");
        el.whatsappVazio.hidden = false;
      }
    }

    if (el.linkEmail && el.emailVazio) {
      if (email && email.includes("@")) {
        el.linkEmail.hidden = false;
        el.emailVazio.hidden = true;
        el.linkEmail.href = `mailto:${email}`;
        el.linkEmail.textContent = email;
        el.linkEmail.title = "Abrir e-mail";
      } else {
        el.linkEmail.hidden = true;
        el.linkEmail.removeAttribute("href");
        el.emailVazio.hidden = false;
      }
    }
  }

  function atualizarLimparSeg() {
    const vaiVendedor = (el.tipo?.value || "") === "vendedor";
    const mudou = (el.tipo?.value || "") !== tipoOriginal;
    if (el.wrapLimpar) el.wrapLimpar.hidden = !(vaiVendedor && mudou);
    if (el.limparSeg && !(vaiVendedor && mudou)) el.limparSeg.checked = false;
    if (el.limparSeg && vaiVendedor && mudou && tipoOriginal === "fornecedor") {
      el.limparSeg.checked = true;
    }
  }

  function preencher(t) {
    idTenant = Number(t.id || 0) || 0;
    tipoOriginal = t.tipo_negocio || "vendedor";
    slugAtual = (t.slug || "").trim();
    protegido = !!t.protegido;
    ehSessao = !!t.eh_tenant_sessao;
    if (el.id) el.id.value = String(idTenant || "");
    if (el.nome) el.nome.value = t.nome || "";
    if (el.slug) el.slug.value = t.slug || "";
    if (el.tipo) el.tipo.value = t.tipo_negocio || "vendedor";
    if (el.plano) {
      el.plano.value = ["starter", "professional", "scale", "enterprise"].includes(t.plano)
        ? t.plano
        : "starter";
    }
    if (el.documento) el.documento.value = t.documento || "";
    if (el.ativo) el.ativo.checked = !!t.ativo;
    preencherContato(t);
    preencherDono(t);

    const c = t.contagens || {};
    if (el.counts) {
      el.counts.hidden = false;
      el.counts.innerHTML = `
        <span>Produtos: <strong>${c.produtos || 0}</strong></span>
        <span>Segmentos forn.: <strong>${c.segmentos || 0}</strong></span>
        <span>Vínculos (forn.): <strong>${c.vinculos_como_fornecedor || 0}</strong></span>
        <span>Vínculos (vend.): <strong>${c.vinculos_como_vendedor || 0}</strong></span>
        <span>Pedidos (forn.): <strong>${c.pedidos_como_fornecedor || 0}</strong></span>
        <span>Pedidos (vend.): <strong>${c.pedidos_como_vendedor || 0}</strong></span>
      `;
    }
    const risco =
      (c.produtos || 0) +
        (c.vinculos_como_fornecedor || 0) +
        (c.pedidos_como_fornecedor || 0) >
      0;
    if (el.warn) {
      el.warn.hidden = !risco;
      el.warn.textContent = risco
        ? "Este tenant já tem dados de fornecedor (produtos/vínculos/pedidos). Ao virar Armazém, isso permanece e a visibilidade na rede é copiada para os parâmetros do armazém. Confira após sair e entrar de novo."
        : "";
    }
    temRelacionamento = !!t.tem_relacionamento;
    const bloqueado = protegido || ehSessao || !idTenant;
    if (el.btnExcluir) {
      el.btnExcluir.hidden = temRelacionamento || bloqueado;
      el.btnExcluir.disabled = bloqueado;
    }
    if (el.btnDesativar) {
      el.btnDesativar.hidden = !temRelacionamento || bloqueado || !t.ativo;
      el.btnDesativar.disabled = bloqueado;
    }
    atualizarLimparSeg();
  }

  async function carregarApoio(id) {
    const r = await fetch(`${BASE}/apoio`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao carregar tenant.");
    preencher(j.tenant || {});
  }

  async function salvar() {
    if (!idTenant) {
      await Swal.fire("Atenção", "Nenhum tenant carregado.", "warning");
      return;
    }
    const body = {
      id: idTenant,
      nome: (el.nome?.value || "").trim(),
      slug: (el.slug?.value || "").trim(),
      tipo_negocio: el.tipo?.value || "vendedor",
      plano: el.plano?.value || "starter",
      documento: (el.documento?.value || "").trim(),
      ativo: !!el.ativo?.checked,
      limpar_segmentos_fornecedor: !!el.limparSeg?.checked,
    };
    if (!body.nome || body.nome.length < 2) {
      await Swal.fire("Atenção", "Informe o nome do tenant.", "warning");
      return;
    }
    if (body.tipo_negocio !== tipoOriginal) {
      const conf = await Swal.fire({
        icon: "warning",
        title: "Alterar tipo de negócio?",
        html: `De <strong>${esc(tipoOriginal)}</strong> para <strong>${esc(body.tipo_negocio)}</strong>.<br><small>O usuário precisará sair e entrar de novo.</small>`,
        showCancelButton: true,
        confirmButtonText: "Sim, alterar",
        cancelButtonText: "Cancelar",
        confirmButtonColor: "#021F81",
      });
      if (!conf.isConfirmed) return;
    }

    Swal.fire({
      title: "Salvando…",
      allowOutsideClick: false,
      didOpen: () => Swal.showLoading(),
    });
    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao salvar.");

    tipoOriginal = body.tipo_negocio;
    slugAtual = body.slug;
    let texto = j.message || "Salvo.";
    if (j.avisos?.length) texto += " " + j.avisos.join(" ");
    await Swal.fire({
      icon: "success",
      title: "Atualizado",
      text: texto,
      confirmButtonColor: "#021F81",
    });
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  async function desativar() {
    if (!idTenant) return;
    const c1 = await Swal.fire({
      icon: "warning",
      title: "Desativar tenant?",
      html: "Há vínculo ou pedido. A conta sai do ar e o histórico fica.",
      showCancelButton: true,
      confirmButtonText: "Desativar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b45309",
    });
    if (!c1.isConfirmed) return;
    const r = await fetch(`${BASE}/desativar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idTenant }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao desativar.");
    await Swal.fire({ icon: "success", title: "Desativado", text: j.message || "Concluído.", confirmButtonColor: "#021F81" });
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  async function excluir() {
    if (!idTenant) {
      await Swal.fire("Atenção", "Nada para excluir.", "info");
      return;
    }
    if (temRelacionamento) {
      await Swal.fire("Atenção", "Este tenant tem vínculo ou pedido. Use Desativar.", "warning");
      return;
    }
    if (protegido || ehSessao) {
      await Swal.fire("Bloqueado", protegido ? "Tenant protegido." : "Troque de tenant na sessão DEV antes.", "warning");
      return;
    }
    const c1 = await Swal.fire({
      icon: "warning",
      title: "Excluir de vez?",
      html: `Remove <strong>${esc(el.nome?.value || slugAtual)}</strong> e os dados só dele. Sem vínculo e sem pedido.`,
      showCancelButton: true,
      confirmButtonText: "Excluir",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
    });
    if (!c1.isConfirmed) return;

    Swal.fire({
      title: "Excluindo…",
      allowOutsideClick: false,
      didOpen: () => Swal.showLoading(),
    });
    const r = await fetch(`${BASE}/excluir`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idTenant }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao excluir.");
    await Swal.fire({
      icon: "success",
      title: "Tenant excluído",
      text: j.message || "Concluído.",
      confirmButtonColor: "#021F81",
    });
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  el.tipo?.addEventListener("change", atualizarLimparSeg);
  el.tabs?.addEventListener("click", (ev) => {
    const btn = ev.target.closest(".CfgMt_Tab");
    if (!btn) return;
    pickTab(btn.dataset.tab || "tenant");
  });
  el.btnSalvar?.addEventListener("click", () =>
    salvar().catch((e) => Swal.fire("Erro", e.message, "error"))
  );
  el.btnExcluir?.addEventListener("click", () =>
    excluir().catch((e) => Swal.fire("Erro", e.message, "error"))
  );
  el.btnDesativar?.addEventListener("click", () =>
    desativar().catch((e) => Swal.fire("Erro", e.message, "error"))
  );

  if (window.GlobalUtils?.receberDadosApoio) {
    window.GlobalUtils.receberDadosApoio((id, nivel) => {
      nivelModal = Number(nivel || 1) || 1;
      const tid = Number(id || 0) || 0;
      if (!tid) {
        Swal.fire("Atenção", "Selecione um tenant na lista para editar.", "info").then(() => {
          window.GlobalUtils?.fecharJanelaApoio(nivelModal);
        });
        return;
      }
      carregarApoio(tid).catch((e) => Swal.fire("Erro", e.message, "error"));
    });
  }
})();
