(function () {
  "use strict";

  function el(id) {
    return document.getElementById(id);
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
    const r = await fetch("/vendedor/notas/listar", { credentials: "same-origin" });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao listar.");
    const notas = j.notas || [];
    if (!notas.length) {
      tbody.innerHTML = `<tr><td colspan="7">Nenhuma nota emitida.</td></tr>`;
      return;
    }
    tbody.innerHTML = notas
      .map((n) => {
        const danfe = n.tem_danfe
          ? `<a class="Cl_BtnLink" href="/vendedor/notas/${n.id}/arquivo/pdf" target="_blank" rel="noopener">DANFE</a>`
          : "";
        const xml = n.tem_xml
          ? `<a class="Cl_BtnLink" href="/vendedor/notas/${n.id}/arquivo/xml">XML</a>`
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

  async function emitirAvulsa() {
    const cep = (el("nf_cep")?.value || "").replace(/\D/g, "");
    if (cep.length === 8 && !el("nf_ibge")?.value) {
      const via = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
      const end = await via.json();
      if (!end.erro) {
        if (el("nf_logr") && !el("nf_logr").value) el("nf_logr").value = end.logradouro || "";
        if (el("nf_bairro") && !el("nf_bairro").value) el("nf_bairro").value = end.bairro || "";
        if (el("nf_cidade")) el("nf_cidade").value = end.localidade || el("nf_cidade").value;
        if (el("nf_uf")) el("nf_uf").value = end.uf || el("nf_uf").value;
        if (el("nf_ibge")) el("nf_ibge").value = end.ibge || "";
      }
    }
    const body = {
      destinatario: {
        nome: el("nf_nome")?.value,
        documento: el("nf_doc")?.value,
        email: el("nf_email")?.value,
        indicador_ie: el("nf_ind")?.value,
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
    const r = await fetch("/vendedor/notas/emitir", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) throw new Error(j.message || "Falha ao emitir.");
    if (window.Swal) Swal.fire("Nota", j.nota?.status === "autorizado" ? "Nota autorizada." : "Nota enviada. Atualize o status em instantes.", "success");
    el("nf_form").hidden = true;
    await carregar();
  }

  el("nf_btnNova")?.addEventListener("click", () => {
    el("nf_form").hidden = false;
  });
  el("nf_btnFechar")?.addEventListener("click", () => {
    el("nf_form").hidden = true;
  });
  el("nf_btnEmitir")?.addEventListener("click", () => {
    emitirAvulsa().catch((e) => {
      if (window.Swal) Swal.fire("Nota", e.message || "Falha ao emitir.", "error");
    });
  });
  el("nf_tbody")?.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-atualizar]");
    if (!btn) return;
    fetch(`/vendedor/notas/${btn.dataset.atualizar}/atualizar`, { method: "POST", credentials: "same-origin" })
      .then((r) => r.json())
      .then((j) => {
        if (!j.success) throw new Error(j.message || "Falha ao atualizar.");
        return carregar();
      })
      .catch((e) => {
        if (window.Swal) Swal.fire("Nota", e.message || "Falha ao atualizar.", "error");
      });
  });

  carregar().catch((e) => {
    const tbody = el("nf_tbody");
    if (tbody) tbody.innerHTML = `<tr><td colspan="7">${esc(e.message || "Erro")}</td></tr>`;
  });
})();
