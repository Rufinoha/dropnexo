(function () {
  const form = document.getElementById("form-cadastro");
  if (!form) return;

  const apiUrl = window.OSB_CADASTRO_API || "/api/cadastro/novo";
  const msgEl = document.getElementById("msg-cad");
  const inpDoc = document.getElementById("documento");
  const inpCep = document.getElementById("cep");
  const inpWhatsapp = form.querySelector('[name="whatsapp"]');
  const radiosTipo = form.querySelectorAll('input[name="tipo_pessoa"]');

  const lblDoc = document.getElementById("lbl-documento");
  const lblNomeCompleto = document.getElementById("lbl-nome-completo");
  const lblNomeConta = document.getElementById("lbl-nome-conta");

  function soDigitos(v) {
    return String(v || "").replace(/\D/g, "");
  }

  function mascaraCpf(v) {
    const d = soDigitos(v).slice(0, 11);
    return d
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d)/, "$1.$2")
      .replace(/(\d{3})(\d{1,2})$/, "$1-$2");
  }

  function mascaraCnpj(v) {
    const d = soDigitos(v).slice(0, 14);
    return d
      .replace(/^(\d{2})(\d)/, "$1.$2")
      .replace(/^(\d{2})\.(\d{3})(\d)/, "$1.$2.$3")
      .replace(/\.(\d{3})(\d)/, ".$1/$2")
      .replace(/(\d{4})(\d)/, "$1-$2");
  }

  function mascaraCep(v) {
    const d = soDigitos(v).slice(0, 8);
    return d.length > 5 ? `${d.slice(0, 5)}-${d.slice(5)}` : d;
  }

  function mascaraTelefone(v) {
    const d = soDigitos(v).slice(0, 11);
    if (d.length <= 10) {
      return d
        .replace(/^(\d{2})(\d)/, "($1) $2")
        .replace(/(\d{4})(\d)/, "$1-$2");
    }
    return d
      .replace(/^(\d{2})(\d)/, "($1) $2")
      .replace(/(\d{5})(\d)/, "$1-$2");
  }

  function tipoAtual() {
    const r = form.querySelector('input[name="tipo_pessoa"]:checked');
    return r ? r.value : "F";
  }

  function aplicarTipoPessoa() {
    const j = tipoAtual() === "J";
    lblDoc.textContent = j ? "CNPJ" : "CPF";
    lblNomeCompleto.textContent = j ? "Razão social" : "Nome completo";
    lblNomeConta.textContent = j
      ? "Nome fantasia (exibição no sistema)"
      : "Nome no sistema (apelido)";
    inpDoc.value = j ? mascaraCnpj(inpDoc.value) : mascaraCpf(inpDoc.value);
    inpDoc.placeholder = j ? "00.000.000/0000-00" : "000.000.000-00";
  }

  function normalizarSlug(val) {
    return String(val || "")
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9\-]+/g, "-")
      .replace(/-+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 64);
  }

  function mostrarMsg(texto, ok) {
    msgEl.textContent = texto;
    msgEl.className = ok ? "form-msg is-ok" : "form-msg is-error";
    msgEl.hidden = false;
  }

  radiosTipo.forEach((r) => r.addEventListener("change", aplicarTipoPessoa));

  inpDoc.addEventListener("input", () => {
    const j = tipoAtual() === "J";
    inpDoc.value = j ? mascaraCnpj(inpDoc.value) : mascaraCpf(inpDoc.value);
  });

  inpCep.addEventListener("input", () => {
    inpCep.value = mascaraCep(inpCep.value);
  });

  inpWhatsapp.addEventListener("input", () => {
    inpWhatsapp.value = mascaraTelefone(inpWhatsapp.value);
  });

  const slugInput = form.querySelector('[name="slug"]');
  if (slugInput) {
    slugInput.addEventListener("blur", () => {
      slugInput.value = normalizarSlug(slugInput.value);
    });
  }

  document.getElementById("btn-buscar-cep")?.addEventListener("click", async () => {
    const cep = soDigitos(inpCep.value);
    if (cep.length !== 8) {
      mostrarMsg("Informe um CEP válido com 8 dígitos.", false);
      return;
    }
    try {
      const r = await fetch(`https://viacep.com.br/ws/${cep}/json/`);
      const j = await r.json();
      if (j.erro) {
        mostrarMsg("CEP não encontrado.", false);
        return;
      }
      document.getElementById("logradouro").value = j.logradouro || "";
      document.getElementById("bairro").value = j.bairro || "";
      document.getElementById("cidade").value = j.localidade || "";
      document.getElementById("uf").value = (j.uf || "").toUpperCase();
      msgEl.hidden = true;
    } catch {
      mostrarMsg("Não foi possível consultar o CEP.", false);
    }
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    msgEl.hidden = true;

    const fd = new FormData(form);
    const tipo = tipoAtual();
    const tipoNegocio = (document.getElementById("tipo_negocio")?.value || "").trim();
    const body = {
      tipo_negocio: tipoNegocio,
      tipo_pessoa: tipo,
      documento: soDigitos(fd.get("documento")),
      nome_completo: String(fd.get("nome_completo") || "").trim(),
      nome: String(fd.get("nome") || "").trim(),
      slug: normalizarSlug(fd.get("slug")),
      nome_usuario: String(fd.get("nome_usuario") || "").trim(),
      email: String(fd.get("email") || "").trim().toLowerCase(),
      whatsapp: soDigitos(fd.get("whatsapp")),
      cep: soDigitos(fd.get("cep")),
      logradouro: String(fd.get("logradouro") || "").trim(),
      numero: String(fd.get("numero") || "").trim(),
      complemento: String(fd.get("complemento") || "").trim(),
      bairro: String(fd.get("bairro") || "").trim(),
      cidade: String(fd.get("cidade") || "").trim(),
      uf: String(fd.get("uf") || "").trim().toUpperCase(),
    };

    const btn = document.getElementById("btn-cadastrar");
    btn.disabled = true;

    try {
      const r = await fetch(apiUrl, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j.success) {
        mostrarMsg(j.message || "Cadastro realizado.", true);
        form.reset();
        aplicarTipoPessoa();
        if (j.redirect) {
          setTimeout(() => {
            window.location.href = j.redirect;
          }, 2000);
        }
        return;
      }
      mostrarMsg(j.message || "Não foi possível concluir o cadastro.", false);
    } catch {
      mostrarMsg("Falha na comunicação com o servidor.", false);
    } finally {
      btn.disabled = false;
    }
  });

  aplicarTipoPessoa();
})();
