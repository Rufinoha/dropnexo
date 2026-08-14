(function () {
  const grid = document.getElementById("az_forn_grid");
  const vazio = document.getElementById("az_forn_vazio");
  const modal = document.getElementById("az_forn_modal");
  const form = document.getElementById("az_forn_form");
  const titulo = document.getElementById("az_forn_titulo");
  const busca = document.getElementById("az_forn_busca");
  const BASE = "/armazem/fornecedores";

  const el = {
    id: document.getElementById("az_forn_id"),
    nome: document.getElementById("az_forn_nome"),
    fantasia: document.getElementById("az_forn_fantasia"),
    doc: document.getElementById("az_forn_doc"),
    email: document.getElementById("az_forn_email"),
    tel: document.getElementById("az_forn_tel"),
    wa: document.getElementById("az_forn_wa"),
    obs: document.getElementById("az_forn_obs"),
    btnExcluir: document.getElementById("az_forn_btnExcluir"),
    logoImg: document.getElementById("az_forn_logo_img"),
    logoPh: document.getElementById("az_forn_logo_ph"),
    logoInput: document.getElementById("az_forn_logo_input"),
  };

  let logoPendente = null;

  if (!grid || !modal) return;

  function esc(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function setLogoPreview(url) {
    if (url && el.logoImg) {
      el.logoImg.src = url;
      el.logoImg.hidden = false;
      if (el.logoPh) el.logoPh.hidden = true;
    } else {
      if (el.logoImg) {
        el.logoImg.removeAttribute("src");
        el.logoImg.hidden = true;
      }
      if (el.logoPh) el.logoPh.hidden = false;
    }
  }

  function abrirModal(dados) {
    logoPendente = null;
    if (el.logoInput) el.logoInput.value = "";
    el.id.value = dados?.id || "";
    el.nome.value = dados?.nome || "";
    el.fantasia.value = dados?.nome_fantasia || "";
    el.doc.value = dados?.documento || "";
    el.email.value = dados?.email || "";
    el.tel.value = dados?.telefone || "";
    el.wa.value = dados?.whatsapp || "";
    el.obs.value = dados?.observacoes || "";
    titulo.textContent = dados?.id ? "Editar fornecedor" : "Novo fornecedor";
    el.btnExcluir.hidden = !dados?.id;
    const logoUrl = dados?.logo_url
      ? dados.logo_url + (dados.logo_url.includes("?") ? "&" : "?") + "t=" + Date.now()
      : "";
    setLogoPreview(logoUrl);
    modal.hidden = false;
    modal.setAttribute("aria-hidden", "false");
  }

  function fecharModal() {
    logoPendente = null;
    modal.hidden = true;
    modal.setAttribute("aria-hidden", "true");
  }

  async function uploadLogo(idFornecedor, file) {
    const fd = new FormData();
    fd.append("arquivo", file);
    const r = await fetch(`${BASE}/${idFornecedor}/logo`, {
      method: "POST",
      credentials: "same-origin",
      body: fd,
    });
    return r.json();
  }

  async function carregar() {
    const q = (busca?.value || "").trim();
    const url = q ? `${BASE}/dados?busca=${encodeURIComponent(q)}` : `${BASE}/dados`;
    const r = await fetch(url, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    const lista = j.dados || [];
    if (!lista.length) {
      grid.innerHTML = "";
      if (vazio) vazio.hidden = false;
      return;
    }
    if (vazio) vazio.hidden = true;
    grid.innerHTML = lista
      .map((f) => {
        const logo = f.logo_url
          ? `<img class="AzForn_CardLogo" src="${esc(f.logo_url)}?t=${Date.now()}" alt="" />`
          : `<span class="AzForn_CardLogoPh" aria-hidden="true"></span>`;
        return `
      <article class="AzForn_Card" data-id="${f.id}">
        ${logo}
        <div class="AzForn_CardBody">
          <strong>${esc(f.nome_fantasia || f.nome)}</strong>
          <span>${esc(f.nome_fantasia && f.nome_fantasia !== f.nome ? f.nome : "")}</span>
          <span class="AzForn_Meta">${esc(f.documento || "Sem documento")}${f.email ? " · " + esc(f.email) : ""}</span>
        </div>
      </article>`;
      })
      .join("");
  }

  document.getElementById("az_forn_btnIncluir")?.addEventListener("click", () => abrirModal(null));
  document.getElementById("az_forn_btnFechar")?.addEventListener("click", fecharModal);
  document.getElementById("az_forn_btnCancelar")?.addEventListener("click", fecharModal);

  el.logoInput?.addEventListener("change", async () => {
    const f = el.logoInput.files?.[0];
    if (!f) return;
    if (f.size > 2 * 1024 * 1024) {
      if (window.Util?.alertar) Util.alertar("O logotipo deve ter no máximo 2 MB.", "warning");
      else alert("O logotipo deve ter no máximo 2 MB.");
      el.logoInput.value = "";
      return;
    }
    setLogoPreview(URL.createObjectURL(f));
    if (el.id.value) {
      const up = await uploadLogo(Number(el.id.value), f);
      if (up.success) {
        logoPendente = null;
        if (up.logo_url) setLogoPreview(up.logo_url);
        if (window.Util?.alertar) Util.alertar(up.message || "Logotipo atualizado.", "success");
      } else {
        logoPendente = f;
        if (window.Util?.alertar) Util.alertar(up.message || "Erro ao enviar logo.", "error");
      }
    } else {
      logoPendente = f;
    }
  });

  grid.addEventListener("dblclick", async (e) => {
    const card = e.target.closest("[data-id]");
    if (!card) return;
    const r = await fetch(`${BASE}/apoio`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: Number(card.dataset.id) }),
    });
    const j = await r.json();
    if (j.success) abrirModal(j.dados);
  });

  form?.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = {
      id: el.id.value ? Number(el.id.value) : null,
      nome: el.nome.value,
      nome_fantasia: el.fantasia.value,
      documento: el.doc.value,
      email: el.email.value,
      telefone: el.tel.value,
      whatsapp: el.wa.value,
      observacoes: el.obs.value,
      ativo: true,
    };
    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.success) {
      if (window.Util?.alertar) Util.alertar(j.message || "Erro", "error");
      else if (window.Swal) Swal.fire("Erro", j.message, "error");
      return;
    }
    if (logoPendente && j.id) {
      const up = await uploadLogo(j.id, logoPendente);
      logoPendente = null;
      if (!up.success) {
        if (window.Util?.alertar) Util.alertar(up.message || "Fornecedor salvo, mas o logo falhou.", "warning");
        else if (window.Swal) Swal.fire("Atenção", up.message || "Fornecedor salvo, mas o logo falhou.", "warning");
      } else if (window.Util?.alertar) {
        Util.alertar(j.message || "Salvo", "success");
      }
    } else if (window.Util?.alertar) {
      Util.alertar(j.message || "Salvo", "success");
    } else if (window.Swal) {
      Swal.fire("Salvo", j.message, "success");
    }
    fecharModal();
    carregar();
  });

  el.btnExcluir?.addEventListener("click", async () => {
    if (!el.id.value) return;
    const ok = window.Swal
      ? (
          await Swal.fire({
            icon: "warning",
            title: "Excluir fornecedor?",
            showCancelButton: true,
            confirmButtonText: "Excluir",
            confirmButtonColor: "#b91c1c",
          })
        ).isConfirmed
      : confirm("Excluir fornecedor?");
    if (!ok) return;
    const r = await fetch(`${BASE}/excluir`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: Number(el.id.value) }),
    });
    const j = await r.json();
    if (window.Util?.alertar) Util.alertar(j.message, j.success ? "success" : "error");
    if (j.success) {
      fecharModal();
      carregar();
    }
  });

  let t = null;
  busca?.addEventListener("input", () => {
    clearTimeout(t);
    t = setTimeout(carregar, 280);
  });

  carregar();
})();
