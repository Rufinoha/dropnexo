(function () {
  const BASE = "/configuracoes/manutencao-tenant";
  let nivelModal = 1;
  let idTenant = 0;
  let tipoOriginal = "";
  let slugAtual = "";
  let protegido = false;
  let ehSessao = false;

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
    counts: document.getElementById("counts"),
    warn: document.getElementById("warn"),
    btnSalvar: document.getElementById("btnSalvar"),
    btnExcluir: document.getElementById("btnExcluir"),
  };

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
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
    if (el.btnExcluir) {
      el.btnExcluir.disabled = protegido || ehSessao || !idTenant;
      el.btnExcluir.title = protegido
        ? "Tenant protegido"
        : ehSessao
          ? "Não exclua o tenant da sessão atual"
          : "Excluir tenant e dados ligados";
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

  async function excluir() {
    if (!idTenant || !slugAtual) {
      await Swal.fire("Atenção", "Nada para excluir.", "info");
      return;
    }
    if (protegido || ehSessao) {
      await Swal.fire(
        "Bloqueado",
        protegido
          ? "Tenant protegido."
          : "Troque de tenant na sessão DEV antes de excluir este.",
        "warning"
      );
      return;
    }
    const c1 = await Swal.fire({
      icon: "warning",
      title: "Excluir tenant permanentemente?",
      html:
        `Remove <strong>${esc(el.nome?.value || slugAtual)}</strong> (#${idTenant}) e todos os dados ligados.` +
        `<br><br><small>Irreversível — só para testes.</small>`,
      showCancelButton: true,
      confirmButtonText: "Continuar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
    });
    if (!c1.isConfirmed) return;

    const c2 = await Swal.fire({
      icon: "warning",
      title: "Confirme digitando o slug",
      html: `Digite <strong>${esc(slugAtual)}</strong> para confirmar.`,
      input: "text",
      inputPlaceholder: slugAtual,
      showCancelButton: true,
      confirmButtonText: "Excluir de vez",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
      preConfirm: (v) => {
        if ((v || "").trim().toLowerCase() !== String(slugAtual).toLowerCase()) {
          Swal.showValidationMessage("Slug não confere.");
          return false;
        }
        return (v || "").trim();
      },
    });
    if (!c2.isConfirmed) return;

    Swal.fire({
      title: "Excluindo…",
      text: "Removendo dados em cascata…",
      allowOutsideClick: false,
      didOpen: () => Swal.showLoading(),
    });
    const r = await fetch(`${BASE}/excluir`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idTenant, confirm_slug: c2.value }),
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
  el.btnSalvar?.addEventListener("click", () =>
    salvar().catch((e) => Swal.fire("Erro", e.message, "error"))
  );
  el.btnExcluir?.addEventListener("click", () =>
    excluir().catch((e) => Swal.fire("Erro", e.message, "error"))
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
