(function () {
  "use strict";

  function el(id) {
    return document.getElementById(id);
  }

  function nfBase() {
    const n = document.querySelector("[data-nf-base]");
    return ((n && n.getAttribute("data-nf-base")) || "/vendedor").replace(/\/$/, "");
  }

  function esc(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function moeda(v) {
    return Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
  }

  function dataBr(v) {
    if (!v) return "—";
    const d = new Date(v);
    if (Number.isNaN(d.getTime())) return "—";
    return d.toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
  }

  async function carregar() {
    const tbody = el("nf_tbody");
    const r = await fetch(`${nfBase()}/notas/listar`, { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao listar.");
    const notas = j.notas || [];
    if (!notas.length) {
      tbody.innerHTML = `<tr><td colspan="7" class="Fin_Empty">Nenhuma nota emitida.</td></tr>`;
      return;
    }
    tbody.innerHTML = notas
      .map((n) => {
        const danfe = n.tem_danfe
          ? `<a class="Cl_BtnLink" href="${nfBase()}/notas/${n.id}/arquivo/pdf" target="_blank" rel="noopener">DANFE</a>`
          : "";
        const xml = n.tem_xml
          ? `<a class="Cl_BtnLink" href="${nfBase()}/notas/${n.id}/arquivo/xml">XML</a>`
          : "";
        return `<tr>
          <td>${esc(n.numero || "—")}</td>
          <td>${esc(n.destinatario_nome || "—")}</td>
          <td>${esc(moeda(n.valor_total))}</td>
          <td title="${esc(n.mensagem || "")}">${esc(n.status || "—")}</td>
          <td>${n.id_pedido ? esc(n.id_pedido) : "—"}</td>
          <td>${esc(dataBr(n.criado_em))}</td>
          <td class="col-acoes">
            <button type="button" class="Cl_botaoFiltro" data-atualizar="${n.id}">Atualizar</button>
            ${danfe} ${xml}
          </td>
        </tr>`;
      })
      .join("");
  }

  function ligarSidebar(root) {
    root?.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-nf-tab]");
      if (!btn || !root.contains(btn)) return;
      const nome = btn.dataset.nfTab;
      root.querySelectorAll("[data-nf-tab]").forEach((b) => b.classList.toggle("is-active", b === btn));
      root.querySelectorAll("[data-nf-pane]").forEach((p) => {
        p.hidden = p.dataset.nfPane !== nome;
      });
    });
  }

  function irCertificado() {
    abrirAba("parametros");
    el("nf_par_shell")?.querySelector("[data-nf-tab='cert']")?.click();
    const url = new URL(window.location.href);
    url.searchParams.set("aba", "parametros");
    window.history.replaceState(null, "", url);
    el("nf_aba_parametros")?.scrollIntoView({ block: "start" });
  }

  async function avisoEscolha(texto, acao) {
    if (!window.Swal) return false;
    const escolha = await Swal.fire({
      icon: "info",
      title: "Nota fiscal",
      text: texto,
      showCancelButton: true,
      reverseButtons: true,
      cancelButtonText: "OK",
      confirmButtonText: acao,
      confirmButtonColor: "#021F81",
      cancelButtonColor: "#64748b",
    });
    return !!escolha.isConfirmed;
  }

  async function aoNovaNota() {
    const raiz = document.querySelector("[data-nf-base]");
    const planos = raiz?.getAttribute("data-nf-planos") || "";
    const checaCert = !!planos || raiz?.hasAttribute("data-nf-checa-cert");
    if (!checaCert) {
      abrirModal();
      return;
    }
    const r = await fetch(`${nfBase()}/notas/pode-emitir`, { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao verificar a nota.");
    if (planos && !j.plano_ok) {
      const quer = await avisoEscolha(
        "A emissão de nota começa no plano Crescer.",
        "Mostrar plano"
      );
      if (quer) window.location.href = planos;
      return;
    }
    if (!j.tem_certificado) {
      const quer = await avisoEscolha(
        "Não há certificado A1 cadastrado. Envie o arquivo para emitir a nota.",
        "Incluir certificado"
      );
      if (quer) irCertificado();
      return;
    }
    abrirModal();
  }

  function abrirModal() {
    const modal = el("nf_modal");
    if (!modal) return;
    modal.hidden = false;
    document.body.style.overflow = "hidden";
    const shell = el("nf_modal_shell");
    shell?.querySelector("[data-nf-tab='cliente']")?.click();
    el("nf_nome")?.focus();
  }

  function fecharModal() {
    const modal = el("nf_modal");
    if (modal) modal.hidden = true;
    document.body.style.overflow = "";
  }

  async function buscarCep() {
    const cep = (el("nf_cep")?.value || "").replace(/\D/g, "");
    if (cep.length !== 8) {
      if (window.Swal) Swal.fire("CEP", "Informe um CEP com 8 dígitos.", "warning");
      return false;
    }
    const btn = el("nf_btnCep");
    if (btn) btn.disabled = true;
    try {
      const via = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
      const end = await via.json();
      if (!via.ok || end.erro) throw new Error("CEP não encontrado.");
      if (el("nf_logr")) el("nf_logr").value = end.logradouro || "";
      if (el("nf_bairro")) el("nf_bairro").value = end.bairro || "";
      if (el("nf_cidade")) el("nf_cidade").value = end.localidade || "";
      if (el("nf_uf")) el("nf_uf").value = end.uf || "";
      if (el("nf_ibge")) el("nf_ibge").value = end.ibge || "";
      el("nf_num")?.focus();
    } catch (e) {
      if (window.Swal) Swal.fire("CEP", e.message || "Não foi possível buscar o CEP.", "error");
      return false;
    } finally {
      if (btn) btn.disabled = false;
    }
    return true;
  }

  async function emitirAvulsa() {
    const cep = (el("nf_cep")?.value || "").replace(/\D/g, "");
    if (cep.length === 8 && !el("nf_ibge")?.value) {
      const ok = await buscarCep();
      if (!ok) return;
    }
    const body = {
      destinatario: {
        nome: el("nf_nome")?.value,
        documento: el("nf_doc")?.value,
        email: el("nf_email")?.value,
        indicador_ie: el("nf_ind_ie")?.value,
        ie: el("nf_ie")?.value,
        cep: el("nf_cep")?.value,
        logradouro: el("nf_logr")?.value,
        numero: el("nf_num")?.value,
        bairro: el("nf_bairro")?.value,
        municipio: el("nf_cidade")?.value,
        uf: el("nf_uf")?.value,
        codigo_municipio: el("nf_ibge")?.value,
      },
      itens: [
        {
          descricao: el("nf_desc")?.value,
          ncm: el("nf_ncm")?.value,
          quantidade: Number(el("nf_qtd")?.value || 1),
          valor_unitario: Number(el("nf_valor")?.value || 0),
          codigo: "AVULSO",
          unidade: "UN",
          origem: "0",
        },
      ],
    };
    if (window.Swal) Swal.fire({ title: "Emitindo…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    const r = await fetch(`${nfBase()}/notas/emitir`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao emitir.");
    if (window.Swal) Swal.fire("Nota", j.nota?.status === "autorizado" ? "Nota autorizada." : "Nota enviada. Atualize o status em instantes.", "success");
    fecharModal();
    await carregar();
  }

  el("nf_btnNova")?.addEventListener("click", () => {
    aoNovaNota().catch((e) => {
      if (window.Swal) Swal.fire("Nota", e.message || "Falha ao abrir a nota.", "error");
    });
  });
  el("nf_btnFechar")?.addEventListener("click", fecharModal);
  el("nf_btnFechar2")?.addEventListener("click", fecharModal);
  el("nf_btnCep")?.addEventListener("click", () => {
    buscarCep().catch((e) => {
      if (window.Swal) Swal.fire("CEP", e.message || "Não foi possível buscar o CEP.", "error");
    });
  });
  el("nf_modal")?.addEventListener("click", (ev) => {
    if (ev.target === el("nf_modal")) fecharModal();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && el("nf_modal") && !el("nf_modal").hidden) fecharModal();
  });
  ligarSidebar(el("nf_par_shell"));
  ligarSidebar(el("nf_modal_shell"));
  el("nf_btnEmitir")?.addEventListener("click", () => {
    emitirAvulsa().catch((e) => {
      if (window.Swal) Swal.fire("Nota", e.message || "Falha ao emitir.", "error");
    });
  });
  el("nf_tbody")?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-atualizar]");
    if (!btn) return;
    fetch(`${nfBase()}/notas/${btn.dataset.atualizar}/atualizar`, { method: "POST", credentials: "same-origin" })
      .then((r) => r.json())
      .then((j) => {
        if (!j.success) throw new Error(j.message || "Falha ao atualizar.");
        return carregar();
      })
      .catch((e) => {
        if (window.Swal) Swal.fire("Nota", e.message || "Falha ao atualizar.", "error");
      });
  });

  function abrirAba(nome) {
    document.querySelectorAll(".Fin_Tab").forEach((btn) => {
      btn.classList.toggle("is-active", btn.dataset.aba === nome);
    });
    const notas = el("nf_aba_notas");
    const param = el("nf_aba_parametros");
    if (notas) notas.hidden = nome !== "notas";
    if (param) param.hidden = nome !== "parametros";
    if (nome !== "notas") fecharModal();
  }

  document.querySelectorAll(".Fin_Tab").forEach((btn) => {
    btn.addEventListener("click", () => abrirAba(btn.dataset.aba || "notas"));
  });
  if (new URLSearchParams(window.location.search).get("aba") === "parametros") abrirAba("parametros");

  carregar().catch((e) => {
    const tbody = el("nf_tbody");
    if (tbody) tbody.innerHTML = `<tr><td colspan="7">${esc(e.message || "Erro")}</td></tr>`;
  });
})();
