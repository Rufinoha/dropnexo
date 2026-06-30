/**
 * Tela de aceite — solicitação de vínculo com fornecedor.
 */
(function () {
  "use strict";

  let idFornecedor = null;
  let temRequisitos = false;

  const el = {
    id: document.getElementById("id_fornecedor"),
    intro: document.getElementById("vincIntro"),
    secReq: document.getElementById("secRequisitos"),
    secSem: document.getElementById("secSemRequisitos"),
    listaReq: document.getElementById("vincListaReq"),
    secContato: document.getElementById("secContato"),
    contato: document.getElementById("vincContato"),
    wrapCheckReq: document.getElementById("wrapCheckReq"),
    checkReq: document.getElementById("vincCheckReq"),
    checkDados: document.getElementById("vincCheckDados"),
    checkApto: document.getElementById("vincCheckApto"),
    form: document.getElementById("formVinculoAceite"),
    btnCancel: document.getElementById("vincBtnCancelar"),
    btnConfirm: document.getElementById("vincBtnConfirmar"),
  };

  const fmtMoeda = (v) =>
    window.Util?.formatarMoeda
      ? Util.formatarMoeda(v)
      : "R$ " + Number(v || 0).toFixed(2).replace(".", ",");

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function montarItensRequisitos(req) {
    const itens = [];
    if (req.exige_cnpj) itens.push("Exige CNPJ (pessoa jurídica)");
    if (req.exige_nf) itens.push("Exige emissão de nota fiscal nas vendas");
    if (req.cobra_taxa_vinculo && Number(req.valor_taxa_vinculo) > 0) {
      itens.push(`Taxa única de vínculo: ${fmtMoeda(req.valor_taxa_vinculo)}`);
    } else if (req.cobra_taxa_vinculo) {
      itens.push("Cobra taxa única de vínculo");
    }
    if (req.cobra_taxa_mensal && Number(req.valor_taxa_mensal) > 0) {
      itens.push(`Taxa mensal recorrente: ${fmtMoeda(req.valor_taxa_mensal)}`);
    } else if (req.cobra_taxa_mensal) {
      itens.push("Cobra taxa mensal recorrente");
    }
    if (req.cobra_taxa_pedido && Number(req.valor_taxa_pedido) > 0) {
      itens.push(`Taxa por pedido: ${fmtMoeda(req.valor_taxa_pedido)}`);
    } else if (req.cobra_taxa_pedido) {
      itens.push("Cobra taxa por pedido");
    }
    if ((req.texto_adicional || "").trim()) {
      itens.push(req.texto_adicional.trim());
    }
    return itens;
  }

  function fecharApoio(cancelou) {
    const nivel = window.__nivelModal__ || 1;
    const alvo = window.parent?.GlobalUtils || window.GlobalUtils;
    if (cancelou && idFornecedor) {
      try {
        window.parent.postMessage(
          { grupo: "vinculoCancelado", id_fornecedor: idFornecedor },
          "*"
        );
      } catch {}
    }
    alvo?.fecharJanelaApoio?.(nivel);
  }

  function notificarSucesso() {
    try {
      window.parent.postMessage(
        { grupo: "vinculoSolicitado", id_fornecedor: idFornecedor },
        "*"
      );
    } catch {}
    fecharApoio(false);
  }

  function renderContato(c) {
    if (!c || (!c.nome && !c.email && !c.whatsapp)) return;
    el.secContato.hidden = false;
    el.contato.innerHTML = `
      <dt>Nome</dt><dd>${esc(c.nome || "—")}</dd>
      <dt>E-mail</dt><dd>${esc(c.email || "—")}</dd>
      <dt>WhatsApp</dt><dd>${esc(c.whatsapp || "—")}</dd>`;
  }

  async function carregar(id) {
    idFornecedor = id;
    if (el.id) el.id.value = String(id);

    const r = await fetch("/fornecedores/" + id + "/requisitos-vinculo", {
      credentials: "same-origin",
    });
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Erro ao carregar.");

    if (j.requisitos?.exige_cnpj && !j.vendedor_eh_pj) {
      throw new Error(
        "Este fornecedor exige CNPJ. Complete os dados em Minha conta → Minha empresa."
      );
    }

    const nome = j.fornecedor_nome || "Fornecedor";
    if (el.intro) {
      el.intro.innerHTML =
        "Revise as condições de <strong>" +
        esc(nome) +
        "</strong> antes de enviar sua solicitação de vínculo.";
    }

    temRequisitos = !!j.tem_requisitos;
    const itens = montarItensRequisitos(j.requisitos || {});

    if (itens.length) {
      temRequisitos = true;
      if (el.secReq) el.secReq.hidden = false;
      if (el.listaReq) {
        el.listaReq.innerHTML = itens.map((i) => "<li>" + esc(i) + "</li>").join("");
      }
      if (el.wrapCheckReq) el.wrapCheckReq.hidden = false;
    } else if (el.secSem) {
      el.secSem.hidden = false;
    }

    if (j.contato_fornecedor) renderContato(j.contato_fornecedor);
  }

  el.btnCancel?.addEventListener("click", () => fecharApoio(true));

  el.form?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    if (temRequisitos && !el.checkReq?.checked) {
      if (window.Util?.alertar) Util.alertar("Marque que leu as condições comerciais.", "warning");
      else alert("Marque que leu as condições comerciais.");
      return;
    }
    if (!el.checkDados?.checked) {
      if (window.Util?.alertar) Util.alertar("Autorize o acesso aos seus dados cadastrais.", "warning");
      else alert("Autorize o acesso aos seus dados cadastrais.");
      return;
    }
    if (!el.checkApto?.checked) {
      if (window.Util?.alertar) Util.alertar("Confirme que está apto a cumprir as condições.", "warning");
      else alert("Confirme que está apto a cumprir as condições.");
      return;
    }

    if (el.btnConfirm) el.btnConfirm.disabled = true;
    try {
      const r = await fetch("/fornecedores/solicitar-vinculo", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          id_fornecedor: idFornecedor,
          aceite_requisitos: temRequisitos,
          aceite_compartilhamento_dados: true,
          aceite_declaracao_apto: true,
        }),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Erro ao solicitar vínculo.");
      if (window.Util?.alertar) Util.alertar(j.message, "success");
      else if (window.Swal) await Swal.fire("Enviado", j.message, "success");
      notificarSucesso();
    } catch (e) {
      if (window.Swal) Swal.fire("Erro", e.message, "error");
      else if (window.Util?.alertar) Util.alertar(e.message, "error");
      else alert(e.message);
    } finally {
      if (el.btnConfirm) el.btnConfirm.disabled = false;
    }
  });

  function iniciar(id) {
    if (!id) {
      if (el.intro) el.intro.textContent = "Fornecedor não informado.";
      return;
    }
    carregar(id).catch((e) => {
      if (el.intro) el.intro.textContent = e.message || "Erro ao carregar.";
      if (window.Swal) Swal.fire("Erro", e.message, "error");
    });
  }

  if (window.GlobalUtils?.receberDadosApoio) {
    GlobalUtils.receberDadosApoio((id) => iniciar(id));
  } else {
    const qs = new URLSearchParams(window.location.search);
    iniciar(Number(qs.get("id")) || null);
  }
})();
