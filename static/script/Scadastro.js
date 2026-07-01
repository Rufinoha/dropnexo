(function () {
  const form = document.getElementById("form-cadastro");
  if (!form) return;

  const apiUrl = window.OSB_CADASTRO_API || "/api/cadastro/novo";
  const apiSegmentos = window.OSB_CADASTRO_SEGMENTOS_API || "/api/cadastro/segmentos";
  const apiCnpjUrl = window.OSB_CADASTRO_CNPJ_API || "/api/cadastro/cnpj";
  const tipoNegocioCadastro = (window.OSB_CADASTRO_TIPO || "").toLowerCase();
  const ehFornecedor = tipoNegocioCadastro === "fornecedor";
  const msgEl = document.getElementById("msg-cad");
  const inpDoc = document.getElementById("documento");
  const inpCep = document.getElementById("cep");
  const inpWhatsapp = form.querySelector('[name="whatsapp"]');

  const MSG_SUCESSO_FORNECEDOR =
    "Cadastro realizado com sucesso! Você receberá um e-mail para finalizar o cadastro e poderá efetuar login na plataforma após definir sua senha.";

  function urlLoginPosCadastro(redirect) {
    return redirect || window.OSB_LOGIN_URL || "/login";
  }

  async function concluirCadastroSucesso(j, { titulo = "Cadastro realizado!", texto = "" } = {}) {
    const destino = urlLoginPosCadastro(j.redirect);
    const mensagem = texto || j.message || MSG_SUCESSO_FORNECEDOR;
    form.reset();
    if (window.Swal) {
      await Swal.fire({
        title: titulo,
        text: mensagem,
        icon: "success",
        confirmButtonColor: "#021f81",
        confirmButtonText: "Ir para login",
      });
      window.location.href = destino;
      return;
    }
    mostrarMsg(mensagem, true);
    setTimeout(() => {
      window.location.href = destino;
    }, 2500);
  }

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
    if (!msgEl) return;
    msgEl.textContent = texto;
    msgEl.className = ok ? "form-msg is-ok" : "form-msg is-error";
    msgEl.hidden = false;
    if (!ok) msgEl.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }

  inpCep?.addEventListener("input", () => {
    inpCep.value = mascaraCep(inpCep.value);
  });

  inpWhatsapp?.addEventListener("input", () => {
    inpWhatsapp.value = mascaraTelefone(inpWhatsapp.value);
  });

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
      if (msgEl) msgEl.hidden = true;
    } catch {
      mostrarMsg("Não foi possível consultar o CEP.", false);
    }
  });

  if (ehFornecedor) {
    inpDoc?.addEventListener("input", () => {
      inpDoc.value = mascaraCnpj(inpDoc.value);
    });

    document.getElementById("btn-buscar-cnpj")?.addEventListener("click", async () => {
      const doc = soDigitos(inpDoc?.value);
      if (doc.length !== 14) {
        mostrarMsg("Informe o CNPJ completo com 14 dígitos.", false);
        return;
      }
      const btn = document.getElementById("btn-buscar-cnpj");
      btn.disabled = true;
      try {
        const r = await fetch(`${apiCnpjUrl}?cnpj=${encodeURIComponent(doc)}`, {
          headers: { Accept: "application/json" },
        });
        let j;
        try {
          j = await r.json();
        } catch {
          throw new Error("Resposta inválida do servidor ao consultar CNPJ.");
        }
        if (!r.ok || !j.success) {
          throw new Error(j.message || "Erro na consulta do CNPJ.");
        }
        const d = j.dados || {};
        const elRazao = document.getElementById("nome_completo");
        const elNome = document.getElementById("nome");
        if (elRazao) elRazao.value = d.razao_social || "";
        if (elNome) elNome.value = d.nome_fantasia || d.razao_social || "";
        if (d.cep) {
          inpCep.value = mascaraCep(d.cep);
        }
        if (d.logradouro) document.getElementById("logradouro").value = d.logradouro;
        if (d.numero) form.querySelector('[name="numero"]').value = d.numero;
        if (d.complemento) form.querySelector('[name="complemento"]').value = d.complemento;
        if (d.bairro) document.getElementById("bairro").value = d.bairro;
        if (d.cidade) document.getElementById("cidade").value = d.cidade;
        if (d.uf) document.getElementById("uf").value = d.uf;
        if (msgEl) msgEl.hidden = true;
        if (window.Swal) {
          await Swal.fire({
            title: "Dados carregados",
            text: "Razão social, fantasia e endereço foram preenchidos com base no CNPJ.",
            icon: "success",
            confirmButtonColor: "#021f81",
          });
        }
      } catch (err) {
        const texto = err.message || "Não foi possível consultar o CNPJ.";
        mostrarMsg(texto, false);
        if (window.Swal) {
          await Swal.fire({
            title: "Consulta CNPJ",
            text: texto,
            icon: "warning",
            confirmButtonColor: "#021f81",
          });
        }
      } finally {
        btn.disabled = false;
      }
    });

    async function carregarSegmentosCombobox() {
      const sel = document.getElementById("cad-segmento");
      if (!sel) return;
      try {
        const r = await fetch(apiSegmentos, { headers: { Accept: "application/json" } });
        const j = await r.json();
        if (!j.success || !Array.isArray(j.segmentos)) return;
        j.segmentos.forEach((seg) => {
          const opt = document.createElement("option");
          opt.value = String(seg.id);
          opt.textContent = seg.nome || seg.titulo || `Segmento ${seg.id}`;
          sel.appendChild(opt);
        });
      } catch (err) {
        console.error(err);
      }
    }

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (msgEl) msgEl.hidden = true;

      const fd = new FormData(form);
      const idSegmento = String(fd.get("id_segmento") || "").trim();
      if (!idSegmento) {
        mostrarMsg("Selecione o segmento do marketplace.", false);
        return;
      }

      const body = {
        tipo_negocio: "fornecedor",
        tipo_pessoa: "J",
        documento: soDigitos(fd.get("documento")),
        nome_completo: String(fd.get("nome_completo") || "").trim(),
        nome: String(fd.get("nome") || "").trim(),
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
        ids_segmentos_nichos: [parseInt(idSegmento, 10)],
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
          await concluirCadastroSucesso(j);
          return;
        }
        mostrarMsg(j.message || "Não foi possível concluir o cadastro.", false);
      } catch {
        mostrarMsg("Falha na comunicação com o servidor.", false);
      } finally {
        btn.disabled = false;
      }
    });

    carregarSegmentosCombobox();
    return;
  }

  const radiosTipo = form.querySelectorAll('input[name="tipo_pessoa"]');
  const lblDoc = document.getElementById("lbl-documento");
  const lblNomeCompleto = document.getElementById("lbl-nome-completo");
  const wrapNomeUsuario = document.getElementById("wrap-nome-usuario");
  const legendResponsavel = document.getElementById("legend-responsavel");
  const inpNomeUsuario = form.querySelector('[name="nome_usuario"]');

  const inpNomeCompleto = form.querySelector('[name="nome_completo"]');

  function tipoAtual() {
    const r = form.querySelector('input[name="tipo_pessoa"]:checked');
    return r ? r.value : "F";
  }

  function sincronizarNomeUsuarioPf() {
    if (tipoAtual() !== "F" || !inpNomeUsuario || !inpNomeCompleto) return;
    inpNomeUsuario.value = String(inpNomeCompleto.value || "").trim();
  }

  function aplicarTipoPessoa() {
    const j = tipoAtual() === "J";
    if (lblDoc) lblDoc.textContent = j ? "CNPJ" : "CPF";
    if (lblNomeCompleto) lblNomeCompleto.textContent = j ? "Razão social" : "Nome completo";
    if (wrapNomeUsuario) wrapNomeUsuario.hidden = !j;
    if (legendResponsavel) legendResponsavel.textContent = j ? "Responsável (dono)" : "Contato";
    if (inpNomeUsuario) {
      inpNomeUsuario.required = j;
      if (j) {
        inpNomeUsuario.value = "";
      } else {
        sincronizarNomeUsuarioPf();
      }
    }
    if (inpDoc) {
      inpDoc.value = j ? mascaraCnpj(inpDoc.value) : mascaraCpf(inpDoc.value);
      inpDoc.placeholder = j ? "00.000.000/0000-00" : "000.000.000-00";
    }
  }

  radiosTipo.forEach((r) => r.addEventListener("change", aplicarTipoPessoa));

  inpNomeCompleto?.addEventListener("input", sincronizarNomeUsuarioPf);

  inpDoc?.addEventListener("input", () => {
    const j = tipoAtual() === "J";
    inpDoc.value = j ? mascaraCnpj(inpDoc.value) : mascaraCpf(inpDoc.value);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (msgEl) msgEl.hidden = true;

    const fd = new FormData(form);
    const tipo = tipoAtual();
    const tipoNegocio = (document.getElementById("tipo_negocio")?.value || "").trim();
    const nomeCompleto = String(fd.get("nome_completo") || "").trim();
    const body = {
      tipo_negocio: tipoNegocio,
      tipo_pessoa: tipo,
      documento: soDigitos(fd.get("documento")),
      nome_completo: nomeCompleto,
      nome_usuario:
        tipo === "F"
          ? nomeCompleto
          : String(fd.get("nome_usuario") || "").trim(),
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

    if (tipo === "J" && body.nome_usuario.length < 2) {
      mostrarMsg("Informe o nome do responsável.", false);
      return;
    }

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
        await concluirCadastroSucesso(j, { texto: j.message || "Cadastro realizado." });
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
