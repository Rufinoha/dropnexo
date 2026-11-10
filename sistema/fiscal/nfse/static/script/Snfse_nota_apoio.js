(function () {
  let perfis = [], notaId = null, statusNota = null, ambiente = "homologacao", carga = 0;
  let chaveNota = "", numeroNfseNota = "";
  let prestadorLocal = "Cadastre o município do prestador em Empresa fiscal.";
  let totalTributos = "Não informado.";
  let tomadorModo = "cadastrado";
  let tomadorModoManual = false;
  let initEmAndamento = false;
  let buscandoCnpj = false, buscandoCep = false, ultimoCnpj = "", ultimoCep = "";
  const $ = id => document.getElementById(id);
  const digitos = v => String(v || "").replace(/\D/g, "");
  function numeroDaChave(chave) {
    const d = digitos(chave);
    if (d.length !== 50 || d[8] !== "2") return "";
    const bruto = d.slice(23, 36);
    if (!/^\d+$/.test(bruto)) return "";
    const n = parseInt(bruto, 10);
    return n > 0 ? String(n) : "";
  }
  const camposAvulso = ["tomaDoc","tomaNome","tomaCep","tomaFone","tomaEnd","tomaNum","tomaComp","tomaBairro","tomaCidade","tomaUf"];
  const camposTravaveis = ["perfil","tomador","destinatario","intermediario","competencia","valor","observacoes", ...camposAvulso];

  async function json(url, opts={}) {
    const r = await GlobalUtils.requestJSON({url, method: opts.method || "GET", payload: opts.payload});
    return r;
  }
  function aviso(titulo, texto, icon="info") { return GlobalUtils.swalFire({title:titulo, text:texto, icon}); }
  function toast(titulo) {
    return GlobalUtils.swalFire({ toast: true, position: "top-end", icon: "success", title: titulo, showConfirmButton: false, timer: 1800 });
  }
  function formatarDoc(v) {
    const d = digitos(v).slice(0, 14);
    if (d.length <= 11) return window.Util.formatarCPF(d);
    return window.Util.formatarCNPJ(d);
  }
  function formatarCEP(v) {
    return window.Util && Util.formatarCEP ? Util.formatarCEP(v) : String(v || "");
  }
  function temDadosAvulso() {
    return !!(digitos($("tomaDoc").value) || $("tomaNome").value.trim());
  }
  function setModoTomador(modo, {manual=false}={}) {
    tomadorModo = modo === "avulso" ? "avulso" : "cadastrado";
    if (manual) tomadorModoManual = true;
    $("tabTomadorCad").classList.toggle("is-on", tomadorModo === "cadastrado");
    $("tabTomadorAvulso").classList.toggle("is-on", tomadorModo === "avulso");
    $("tabTomadorCad").setAttribute("aria-selected", tomadorModo === "cadastrado" ? "true" : "false");
    $("tabTomadorAvulso").setAttribute("aria-selected", tomadorModo === "avulso" ? "true" : "false");
    $("painelTomadorCad").classList.toggle("is-on", tomadorModo === "cadastrado");
    $("painelTomadorCad").hidden = tomadorModo !== "cadastrado";
    $("painelTomadorAvulso").classList.toggle("is-on", tomadorModo === "avulso");
    $("painelTomadorAvulso").hidden = tomadorModo !== "avulso";
    atualizarHintAvulso();
  }
  function limparAvulso() {
    camposAvulso.forEach(id => { $(id).value = ""; });
    ultimoCnpj = "";
    ultimoCep = "";
  }
  function atualizarHintAvulso() {
    const d = digitos($("tomaDoc").value);
    $("hintTomadorAvulso").textContent = d.length === 11
      ? "Pessoa física: informe o CEP para preencher o endereço automaticamente."
      : "CNPJ preenche automaticamente os dados. Em CPF, digite o CEP para completar o endereço.";
  }
  function modoTomadorEfetivo() {
    // Aba avulso (ou dados digitados nela) manda — nunca usa o select oculto nesse caso.
    if (tomadorModo === "avulso" || temDadosAvulso()) return "avulso";
    return "cadastrado";
  }
  function payloadTomador() {
    if (modoTomadorEfetivo() === "cadastrado") {
      return { tomador_modo: "cadastrado", id_tomador_empresa: $("tomador").value || null };
    }
    return {
      tomador_modo: "avulso",
      id_tomador_empresa: null,
      tomador_cnpj_cpf: digitos($("tomaDoc").value),
      tomador_razao_social: $("tomaNome").value.trim().toLocaleUpperCase("pt-BR"),
      tomador_cep: digitos($("tomaCep").value),
      tomador_telefone: digitos($("tomaFone").value),
      tomador_logradouro: $("tomaEnd").value.trim(),
      tomador_numero: $("tomaNum").value.trim(),
      tomador_complemento: $("tomaComp").value.trim(),
      tomador_bairro: $("tomaBairro").value.trim(),
      tomador_cidade: $("tomaCidade").value.trim(),
      tomador_uf: $("tomaUf").value.trim().toUpperCase(),
    };
  }
  function errosAntesDeSalvar() {
    const erros = [];
    if (!$("perfil").value) erros.push(perfis.length ? "Perfil de nota" : "Perfil de nota (cadastre em Parâmetros)");
    if (!$("competencia").value) erros.push("Competência");
    if ($("valor").value === "" || $("valor").value == null) erros.push("Valor do serviço");
    const modo = modoTomadorEfetivo();
    if (modo === "cadastrado") {
      if (!$("tomador").value) erros.push("Tomador cadastrado (empresa)");
    } else {
      const doc = digitos($("tomaDoc").value);
      const nome = $("tomaNome").value.trim();
      if (!nome) erros.push("Nome / Razão social do tomador");
      if (doc.length !== 11 && doc.length !== 14) erros.push("CPF ou CNPJ do tomador");
      else if (doc.length === 11 && window.Util?.validarCPF && !Util.validarCPF(doc)) erros.push("CPF do tomador inválido");
      else if (doc.length === 14 && window.Util?.validarCNPJ && !Util.validarCNPJ(doc)) erros.push("CNPJ do tomador inválido");
      const cep = digitos($("tomaCep").value);
      if (cep && cep.length !== 8) erros.push("CEP do tomador (8 dígitos)");
      const uf = $("tomaUf").value.trim();
      if (uf && uf.length !== 2) erros.push("UF do tomador (2 letras)");
    }
    return erros;
  }
  function mensagemErroSalvar(r) {
    const j = r?.json || {};
    const partes = [];
    if (j.message || j.mensagem) partes.push(j.message || j.mensagem);
    if (Array.isArray(j.erros) && j.erros.length) partes.push(j.erros.join("\n"));
    if (j.detalhe) partes.push(j.detalhe);
    if (!partes.length) partes.push(r?.status ? `Falha HTTP ${r.status}.` : "Verifique os campos e tente de novo.");
    return partes.join("\n");
  }
  function aplicarAvulso(n) {
    $("tomaDoc").value = formatarDoc(n.tomador_cnpj_cpf || "");
    $("tomaNome").value = (n.tomador_razao_social || "").toLocaleUpperCase("pt-BR");
    $("tomaCep").value = formatarCEP(n.tomador_cep || "");
    $("tomaFone").value = digitos(n.tomador_telefone || "");
    $("tomaEnd").value = n.tomador_logradouro || "";
    $("tomaNum").value = n.tomador_numero || "";
    $("tomaComp").value = n.tomador_complemento || "";
    $("tomaBairro").value = n.tomador_bairro || "";
    $("tomaCidade").value = n.tomador_cidade || "";
    $("tomaUf").value = (n.tomador_uf || "").toUpperCase();
    atualizarHintAvulso();
  }
  async function buscarCNPJAuto() {
    const cnpj = digitos($("tomaDoc").value);
    if (cnpj.length !== 14 || buscandoCnpj || cnpj === ultimoCnpj) return;
    if (window.Util.validarCNPJ && !Util.validarCNPJ(cnpj)) {
      return aviso("CNPJ inválido", "Confira os dígitos do CNPJ informado.", "warning");
    }
    buscandoCnpj = true;
    ultimoCnpj = cnpj;
    try {
      const res = await fetch("/clientes/empresa/consulta-cnpj", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Requested-With": "XMLHttpRequest" },
        body: JSON.stringify({ cnpj }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.erro || "Falha na consulta.");
      if (data.razao_social) $("tomaNome").value = String(data.razao_social).toLocaleUpperCase("pt-BR");
      if (data.telefone) $("tomaFone").value = digitos(data.telefone);
      if (data.cep) {
        $("tomaCep").value = formatarCEP(data.cep);
        ultimoCep = digitos(data.cep);
      }
      if (data.endereco) $("tomaEnd").value = data.endereco;
      if (data.numero) $("tomaNum").value = data.numero;
      if (data.complemento) $("tomaComp").value = data.complemento;
      if (data.bairro) $("tomaBairro").value = data.bairro;
      if (data.cidade) $("tomaCidade").value = data.cidade;
      if (data.uf) $("tomaUf").value = data.uf;
      marcarAlterado();
      toast("CNPJ preenchido");
    } catch (err) {
      ultimoCnpj = "";
      aviso("Consulta CNPJ", err.message || String(err), "warning");
    } finally {
      buscandoCnpj = false;
    }
  }
  async function buscarCEPAuto() {
    const cep = digitos($("tomaCep").value);
    if (cep.length !== 8 || buscandoCep || cep === ultimoCep) return;
    buscandoCep = true;
    ultimoCep = cep;
    try {
      const res = await fetch("/clientes/empresa/consulta-cep?cep=" + encodeURIComponent(cep), {
        headers: { "X-Requested-With": "XMLHttpRequest" },
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.erro || "Falha na consulta.");
      $("tomaCep").value = formatarCEP(data.cep || cep);
      if (data.logradouro) $("tomaEnd").value = data.logradouro;
      if (data.complemento) $("tomaComp").value = data.complemento;
      if (data.bairro) $("tomaBairro").value = data.bairro;
      if (data.municipio) $("tomaCidade").value = data.municipio;
      if (data.uf) $("tomaUf").value = data.uf;
      marcarAlterado();
      toast("CEP preenchido");
    } catch (err) {
      ultimoCep = "";
      aviso("Consulta CEP", err.message || String(err), "warning");
    } finally {
      buscandoCep = false;
    }
  }
  function mostrarSecao(nome) {
    document.querySelectorAll("[data-secao]").forEach(btn => {
      const on = btn.dataset.secao === nome;
      btn.classList.toggle("is-on", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll("[data-painel]").forEach(painel => {
      const on = painel.dataset.painel === nome;
      painel.classList.toggle("is-on", on);
      painel.hidden = !on;
    });
  }
  function secaoOk() {
    const geral = !!($("perfil").value && $("competencia").value && $("valor").value !== "" && $("valor").value != null);
    let tomador = false;
    if (modoTomadorEfetivo() === "cadastrado") tomador = !!$("tomador").value;
    else {
      const doc = digitos($("tomaDoc").value);
      tomador = !!$("tomaNome").value.trim() && (doc.length === 11 || doc.length === 14);
    }
    return { geral, tomador, campos: !!$("perfil").value };
  }
  function atualizarSide() {
    const ok = secaoOk();
    $("sideOkGeral")?.closest("button")?.classList.toggle("is-ok", ok.geral);
    $("sideOkTomador")?.closest("button")?.classList.toggle("is-ok", ok.tomador);
    $("sideOkCampos")?.closest("button")?.classList.toggle("is-ok", ok.campos);
  }
  function etapaEmissao() {
    if (!notaId || !statusNota) return "salvar";
    if (statusNota === "validado") return "emitir";
    if (statusNota === "rascunho" || statusNota === "rejeitada") return "validar";
    return "salvar";
  }
  function pintarPasso(id, estado, numero) {
    const btn = $(id);
    if (!btn) return;
    btn.classList.toggle("is-agora", estado === "agora");
    btn.classList.toggle("is-feito", estado === "feito");
    btn.classList.toggle("is-espera", estado === "espera");
    btn.disabled = estado !== "agora";
    const bola = btn.querySelector(".nfse-passo__n");
    if (bola) bola.textContent = estado === "feito" ? "✓" : String(numero);
  }
  function atualizarAcoes() {
    const travada = ["autorizada", "cancelada", "processando"].includes(statusNota);
    $("formNota").classList.toggle("is-travada", travada);
    camposTravaveis.forEach(id => { const el = $(id); if (el) el.disabled = travada; });
    $("tabTomadorCad").disabled = travada;
    $("tabTomadorAvulso").disabled = travada;
    $("btnDanfse").hidden = !["autorizada", "cancelada"].includes(statusNota);
    $("btnCancelarNota").hidden = statusNota !== "autorizada";
    $("acoesRascunho").hidden = travada;
    $("acoesAutorizada").hidden = !["autorizada", "cancelada"].includes(statusNota);
    if ($("acoesProcessando")) $("acoesProcessando").hidden = statusNota !== "processando";
    const etapa = etapaEmissao();
    const ordem = ["salvar", "validar", "emitir"];
    const atual = ordem.indexOf(etapa);
    const estado = (qual) => {
      const i = ordem.indexOf(qual);
      if (i < atual) return "feito";
      if (i === atual) return "agora";
      return "espera";
    };
    pintarPasso("btnSalvar", travada ? "espera" : estado("salvar"), 1);
    pintarPasso("btnValidar", travada ? "espera" : estado("validar"), 2);
    pintarPasso("btnEmitir", travada ? "espera" : estado("emitir"), 3);
    const dicas = {
      salvar: {
        agora: "Salva a DPS para liberar a validação.",
        feito: "Rascunho salvo. Altere um campo para salvar de novo.",
      },
      validar: {
        agora: "Confere a DPS neste computador, sem enviar à Sefin.",
        espera: "Disponível depois de salvar o rascunho.",
        feito: "Validação concluída.",
      },
      emitir: {
        agora: "Transmite a NFS-e para a Sefin.",
        espera: "Disponível somente após a validação.",
      },
    };
    $("btnSalvar").title = dicas.salvar[estado("salvar")] || "";
    $("btnValidar").title = dicas.validar[estado("validar")] || "";
    $("btnEmitir").title = dicas.emitir[estado("emitir")] || "";
    const legendas = {
      salvar: "Passo 1 de 3 — salve o rascunho.",
      validar: "Passo 2 de 3 — valide antes de emitir.",
      emitir: "Passo 3 de 3 — pronto para transmitir.",
    };
    if ($("passoLegenda")) $("passoLegenda").textContent = legendas[etapa] || "";
    atualizarSide();
    const avisoEl = $("avisoTravada");
    if (statusNota === "autorizada") avisoEl.textContent = "NFS-e autorizada. Os dados não podem ser alterados.";
    else if (statusNota === "cancelada") avisoEl.textContent = "NFS-e cancelada. Os dados não podem ser alterados.";
    else if (statusNota === "processando") {
      avisoEl.textContent = "Transmissão em processamento ou resultado incerto. Não reemitir — sincronize com a Sefin.";
    }
    avisoEl.hidden = !travada;
    const titulos = window.parent?.document?.querySelectorAll(".apoio-modal-titulo");
    const titulo = titulos && titulos[titulos.length - 1];
    if (titulo) {
      titulo.textContent = statusNota === "autorizada" ? "NFS-e autorizada"
        : statusNota === "cancelada" ? "NFS-e cancelada"
        : statusNota === "processando" ? "NFS-e em processamento"
        : (notaId ? "Editar rascunho DPS" : "Nova DPS");
    }
  }
  async function reconciliarComChave(chaveInicial) {
    if (!notaId) return;
    const pedido = await GlobalUtils.swalFire({
      title: "Chave de acesso da NFS-e",
      html: "Cole a <strong>chave de acesso</strong> (50 dígitos). O sistema busca o <strong>XML completo</strong> na Sefin para preencher número e DANFSe.",
      input: "text",
      inputValue: chaveInicial || chaveNota || "",
      inputPlaceholder: "3527… (50 dígitos)",
      showCancelButton: true,
      confirmButtonText: "Buscar XML e reconciliar",
      cancelButtonText: "Cancelar",
      inputValidator: (v) => {
        const d = digitos(v);
        if (d.length !== 50) return "A chave deve ter exatamente 50 dígitos.";
        return null;
      },
    });
    if (!pedido?.isConfirmed) return;
    const chave = digitos(pedido.value);
    const sugerido = numeroDaChave(chave) || numeroNfseNota || "";
    const num = await GlobalUtils.swalFire({
      title: "Número da NFS-e",
      text: "Confirmado pela chave quando possível. Ajuste se o portal mostrar outro número.",
      input: "text",
      inputValue: sugerido,
      inputPlaceholder: "Ex.: 33",
      showCancelButton: true,
      confirmButtonText: "Continuar",
      cancelButtonText: "Usar só a chave",
    });
    const numero = num?.isConfirmed ? String(num.value || "").trim() : sugerido;
    const nivel = window.__nivelModal__ || 1;
    GlobalUtils.bloquearFecharApoio(nivel, true, "Baixando XML na Sefin…");
    const progresso = GlobalUtils.swalProgress({
      title: "Reconciliando NFS-e",
      steps: ["Consultando XML na Sefin…", "Gravando número e chave…", "Atualizando o painel…"],
    });
    let r = null;
    try {
      r = await GlobalUtils.requestJSON({
        url: `/nfse/api/notas/${notaId}/reconciliar`,
        method: "POST",
        payload: { chave_nfse: chave, numero_nfse: numero || null },
        timeoutMs: 90000,
      });
    } finally {
      try { await progresso.finish(!!r?.ok); } catch (_) {}
      GlobalUtils.bloquearFecharApoio(nivel, false);
    }
    if (!r?.ok) {
      return aviso("Reconciliação não concluída", r?.json?.message || "Não foi possível atualizar a nota.", "error");
    }
    await carregarNota(notaId);
    window.parent.postMessage({grupo:"nfse:salvo", id:notaId}, "*");
    await aviso("Nota reconciliada", r.json?.message || "Status atualizado.", "success");
  }
  async function sincronizarComSefin() {
    if (!notaId) return;
    const nivel = window.__nivelModal__ || 1;
    GlobalUtils.bloquearFecharApoio(nivel, true, "Sincronizando com a Sefin…");
    const progresso = GlobalUtils.swalProgress({
      title: "Sincronizando com a Sefin",
      steps: ["Consultando DF-e no Ambiente Nacional…", "Reconciliando esta DPS…", "Atualizando o painel…"],
    });
    let r = null;
    try {
      r = await GlobalUtils.requestJSON({
        url: "/nfse/api/notas/importar",
        method: "POST",
        payload: {},
        timeoutMs: 180000,
      });
    } finally {
      try { await progresso.finish(!!r?.ok); } catch (_) {}
      GlobalUtils.bloquearFecharApoio(nivel, false);
    }
    if (!r) return;
    if (!r.ok) {
      const msg = r.json?.message || "A Sefin não devolveu as notas.";
      const adnInscricao = /InscricaoCertificado|ADN_INSCRICAO|distribuição DF-e/i.test(msg);
      await aviso("Sincronização não concluída", msg, "error");
      if (adnInscricao || r.status === 502) {
        const seguir = await GlobalUtils.swalFire({
          title: "Usar chave do portal?",
          text: "O ADN rejeitou a consulta automática. Se a nota já está autorizada no portal, informe a chave de acesso para atualizar o painel.",
          icon: "question",
          showCancelButton: true,
          confirmButtonText: "Informar chave",
          cancelButtonText: "Agora não",
        });
        if (seguir?.isConfirmed) await reconciliarComChave("");
      }
      return;
    }
    await carregarNota(notaId);
    window.parent.postMessage({grupo:"nfse:salvo", id:notaId}, "*");
    if (statusNota === "autorizada" || statusNota === "cancelada") {
      await aviso("Status atualizado", r.json?.message || "Nota reconciliada com a Sefin.", "success");
      return;
    }
    const seguir = await GlobalUtils.swalFire({
      title: "Ainda em processamento",
      text: (r.json?.message || "Consulta encerrada.")
        + " Se a nota já aparece no portal, informe a chave de acesso para reconciliar agora.",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Informar chave do portal",
      cancelButtonText: "Deixar para depois",
    });
    if (seguir?.isConfirmed) await reconciliarComChave("");
  }
  function marcarAlterado() {
    if (["autorizada", "cancelada", "processando"].includes(statusNota)) return;
    if (notaId) statusNota = null;
    atualizarAcoes();
  }
  function preview() {
    const p = perfis.find(x => String(x.id) === $("perfil").value);
    $("pvServico").textContent = p?.codigo_servico || "—";
    $("pvTributacao").textContent = p?.codigo_tributacao_nacional || "—";
    $("pvNbs").textContent = p?.codigo_nbs || "—";
    const descricaoNota = $("observacoes").value.trim() || p?.descricao_servico || "";
    $("pvDescricao").textContent = descricaoNota || "Selecione um perfil.";
    $("pvLocal").textContent = prestadorLocal;
    if ($("pvTotTrib")) $("pvTotTrib").textContent = totalTributos;
    if (!p) return $("pvTributos").textContent = "—";
    const trib = [`ISS ${Number(p.aliquota_iss||0)}%${p.iss_retido?" retido":""}`];
    ["pis","cofins","inss","ir","csll"].forEach(t => trib.push(`${t.toUpperCase()} ${Number(p[`aliquota_${t}`]||0)}%${p[`${t}_retido`]?" retido":""}`));
    $("pvTributos").textContent = trib.join(" · ");
    atualizarSide();
  }
  async function carregarCombos() {
    const prev = {
      perfil: $("perfil").value,
      tomador: $("tomador").value,
      destinatario: $("destinatario").value,
      intermediario: $("intermediario").value,
    };
    const [rp, rt, rc] = await Promise.all([json("/nfse/api/perfis?ativos=1"), json("/nfse/api/tomadores?filtro="), json("/nfse/api/config")]);
    if (!rp?.ok || !rt?.ok || !rc?.ok) return;
    perfis = rp.json.dados;
    const cfg = rc.json.dados || {};
    ambiente = cfg.ambiente || "homologacao";
    const cidade = [cfg.municipio_nome, cfg.uf].filter(Boolean).join(" / ");
    prestadorLocal = cidade
      ? cidade + (cfg.municipio_ibge_codigo ? " · " + cfg.municipio_ibge_codigo : "")
      : "Cadastre o município do prestador em Empresa fiscal.";
    const percentual = String(cfg.percentual_tributos_sn ?? "").trim();
    totalTributos = cfg.optante_simples && percentual && Number(String(percentual).replace(",", ".")) > 0
      ? "Simples Nacional · " + percentual.replace(".", ",") + "%"
      : "Não informado.";
    const opcoesEmpresa = rt.json.dados.map(t=>`<option value="${t.id}">${t.razao_social}${t.cnpj?" · "+t.cnpj:""}</option>`).join("");
    $("perfil").innerHTML = '<option value="">Selecione...</option>' + perfis.map(p=>`<option value="${p.id}">${p.nome}</option>`).join("");
    $("tomador").innerHTML = '<option value="">Selecione...</option>' + opcoesEmpresa;
    $("destinatario").innerHTML = '<option value="">Não informado</option>' + opcoesEmpresa;
    $("intermediario").innerHTML = '<option value="">Não informado</option>' + opcoesEmpresa;
    if (prev.perfil) $("perfil").value = prev.perfil;
    if (prev.tomador) $("tomador").value = prev.tomador;
    if (prev.destinatario) $("destinatario").value = prev.destinatario;
    if (prev.intermediario) $("intermediario").value = prev.intermediario;
    preview();
  }
  async function carregarNota(id) {
    if (!id) return false;
    const r = await json(`/nfse/api/notas/${id}`);
    if (!r?.ok) {
      aviso("Nota não aberta", r?.json?.message || "Não foi possível carregar os dados desta nota.", "error");
      return false;
    }
    const n=r.json.dados; notaId=n.id; statusNota=n.status; $("notaId").value=n.id;
    chaveNota = digitos(n.chave_nfse || "");
    numeroNfseNota = String(n.numero_nfse || numeroDaChave(chaveNota) || "");
    $("perfil").value=n.id_perfil||"";
    $("destinatario").value=n.id_destinatario_empresa||"";
    $("intermediario").value=n.id_intermediario_empresa||"";
    $("competencia").value=String(n.competencia||"").slice(0,10); $("valor").value=n.valor_servico||0;
    $("observacoes").value=n.observacoes||"";
    tomadorModoManual = false;
    if (n.id_tomador_empresa) {
      setModoTomador("cadastrado");
      $("tomador").value = n.id_tomador_empresa;
      limparAvulso();
    } else {
      setModoTomador("avulso");
      $("tomador").value = "";
      aplicarAvulso(n);
      ultimoCnpj = digitos(n.tomador_cnpj_cpf || "");
      ultimoCep = digitos(n.tomador_cep || "");
    }
    atualizarAcoes(); preview();
    if (n.status === "rejeitada" && n.erro_mensagem) aviso("Emissão não concluída", n.erro_mensagem, "error");
    return true;
  }
  async function salvar() {
    if (modoTomadorEfetivo() === "avulso") {
      setModoTomador("avulso", {manual:true});
    }
    const pendencias = errosAntesDeSalvar();
    if (pendencias.length) {
      const faltaTomador = pendencias.some(e => /tomador/i.test(e));
      mostrarSecao(faltaTomador ? "tomador" : "geral");
      return aviso("Campos pendentes", pendencias.map(e => "• " + e).join("\n"), "warning");
    }
    const payload = {
      id:notaId,
      id_perfil:$("perfil").value,
      id_destinatario_empresa:$("destinatario").value || null,
      id_intermediario_empresa:$("intermediario").value || null,
      competencia:$("competencia").value,
      valor_servico:$("valor").value,
      observacoes:$("observacoes").value,
      ...payloadTomador(),
    };
    const r=await json("/nfse/api/notas/salvar",{method:"POST",payload});
    if(!r?.ok) return aviso("Não foi possível salvar", mensagemErroSalvar(r), "error");
    notaId=r.json.id; statusNota="rascunho"; $("notaId").value=notaId;
    await carregarNota(notaId);
    toast("Rascunho salvo. Agora valide.");
    window.parent.postMessage({grupo:"nfse:salvo",id:notaId},"*");
  }
  async function validar() {
    const r=await json(`/nfse/api/notas/${notaId}/validar`,{method:"POST",payload:{}});
    if(!r?.ok) return aviso("Pendências",(r?.json?.erros||[r?.json?.message]).join("\n"),"warning");
    statusNota="validado"; atualizarAcoes();
    toast("Validado. Agora pode emitir.");
  }
  async function emitir() {
    const confirmacao = await GlobalUtils.swalFire({
      title: "Confirmar transmissão?",
      text: ambiente === "producao"
        ? "ATENÇÃO: esta DPS será enviada ao ambiente de PRODUÇÃO e poderá gerar documento fiscal."
        : "A DPS será assinada e enviada ao ambiente de HOMOLOGAÇÃO (produção restrita).",
      icon: ambiente === "producao" ? "warning" : "question",
      showCancelButton: true,
      confirmButtonText: "Sim, transmitir",
      cancelButtonText: "Cancelar"
    });
    if (!confirmacao?.isConfirmed) return;
    const nivel = window.__nivelModal__ || 1;
    const motivoBloqueio = "Transmissão em andamento. Não feche esta janela.";
    GlobalUtils.bloquearFecharApoio(nivel, true, motivoBloqueio);
    $("btnEmitir").disabled = true;
    $("btnFechar").disabled = true;
    statusNota = "processando";
    atualizarAcoes();
    window.parent.postMessage({grupo:"nfse:salvo", id:notaId}, "*");
    const progresso = GlobalUtils.swalProgress({
      title: "Transmitindo NFS-e",
      steps: [
        "Assinando a DPS…",
        "Enviando à Sefin Nacional…",
        "Aguardando autorização…",
        "Finalizando no painel…",
      ],
    });
    let r = null;
    try {
      r = await GlobalUtils.requestJSON({
        url: `/nfse/api/notas/${notaId}/emitir`,
        method: "POST",
        payload: {},
        timeoutMs: 120000,
      });
    } finally {
      try { await progresso.finish(!!r?.ok); } catch (_) {}
      GlobalUtils.bloquearFecharApoio(nivel, false);
      $("btnFechar").disabled = false;
    }
    if (r?.ok) {
      statusNota = "autorizada";
      atualizarAcoes();
      await aviso("NFS-e autorizada", r.json.message, "success");
      window.parent.postMessage({grupo:"nfse:salvo", id:notaId}, "*");
      return;
    }
    const incerto = !!(r?.json?.resultado_incerto) || !r || r.status === 0 || r.status === 503;
    statusNota = incerto ? "processando" : (r?.status === 422 ? "rejeitada" : "validado");
    atualizarAcoes();
    window.parent.postMessage({grupo:"nfse:salvo", id:notaId}, "*");
    if (incerto) {
      await aviso(
        "Resultado incerto",
        (r?.json?.message || "A transmissão pode ter concluído na Sefin, mas o painel não confirmou.")
          + "\n\nUse Importar notas na lista para reconciliar. Não reemitir esta DPS.",
        "warning"
      );
      return;
    }
    aviso("Emissão não concluída", r?.json?.message || "Falha na transmissão.", "error");
  }
  async function danfse() {
    const resposta = await fetch(`/nfse/api/notas/${notaId}/danfse`);
    if (!resposta.ok) {
      let mensagem = "Não foi possível gerar a DANFSe.";
      try { mensagem = (await resposta.json()).message || mensagem; } catch (e) {}
      return aviso("DANFSe", mensagem, "error");
    }
    const blob = await resposta.blob();
    const url = URL.createObjectURL(blob);
    window.open(url, "_blank");
  }
  async function cancelarNota() {
    const escolha = await GlobalUtils.swalFire({
      title: "Cancelar NFS-e?",
      input: "select",
      inputOptions: {"1": "Erro na emissão", "2": "Serviço não prestado", "9": "Outros"},
      inputValue: "1",
      showCancelButton: true,
      confirmButtonText: "Continuar",
      cancelButtonText: "Voltar"
    });
    if (!escolha?.isConfirmed) return;
    const texto = await GlobalUtils.swalFire({
      title: "Justificativa",
      input: "textarea",
      inputPlaceholder: "Descreva o motivo, com pelo menos 15 caracteres.",
      showCancelButton: true,
      confirmButtonText: "Cancelar nota",
      cancelButtonText: "Voltar"
    });
    if (!texto?.isConfirmed) return;
    const motivo = String(texto.value || "").trim();
    if (motivo.length < 15) return aviso("Justificativa curta", "Descreva o motivo com pelo menos 15 caracteres.", "warning");
    const r = await json(`/nfse/api/notas/${notaId}/cancelar`, {method:"POST", payload:{codigo: escolha.value, motivo}});
    if (!r?.ok) return aviso("Cancelamento não concluído", r?.json?.message || "A Sefin não cancelou a nota.", "error");
    statusNota = "cancelada";
    atualizarAcoes();
    aviso("NFS-e cancelada", r.json.message, "success");
    window.parent.postMessage({grupo:"nfse:salvo", id:notaId}, "*");
  }
  async function init(id) {
    const daUrl = Number(new URLSearchParams(location.search).get("id") || 0);
    const escolhido = Number(id) > 0 ? Number(id) : (daUrl > 0 ? daUrl : 0);
    if (initEmAndamento) return;
    if (!escolhido && carga) return;
    if (escolhido && Number(notaId) === escolhido && carga) return;
    initEmAndamento = true;
    const pedido = ++carga;
    try {
      await carregarCombos();
      if (pedido !== carga) return;
      if (escolhido) {
        const ok = await carregarNota(escolhido);
        if (!ok || pedido !== carga) return;
      } else {
        if (!$("competencia").value) {
          $("competencia").value = new Date().toISOString().slice(0, 10);
        }
        // Não sobrescreve a aba se o usuário já escolheu "sem cadastro" enquanto os combos carregavam.
        if (!tomadorModoManual && !temDadosAvulso()) {
          setModoTomador("cadastrado");
        }
      }
      if (pedido !== carga) return;
      atualizarAcoes();
    } finally {
      if (pedido === carga) initEmAndamento = false;
    }
  }
  $("perfil").onchange=()=>{
    if (!["autorizada", "cancelada", "processando"].includes(statusNota)) {
      const escolhido = perfis.find(x => String(x.id) === $("perfil").value);
      $("observacoes").value = (escolhido?.descricao_servico || "").trim();
    }
    preview();
    marcarAlterado();
  };
  $("tabTomadorCad").onclick = () => { setModoTomador("cadastrado", {manual:true}); marcarAlterado(); };
  $("tabTomadorAvulso").onclick = () => { setModoTomador("avulso", {manual:true}); marcarAlterado(); };
  function marcarAvulsoEditado() {
    tomadorModoManual = true;
    if (tomadorModo !== "avulso") setModoTomador("avulso", {manual:true});
    marcarAlterado();
  }
  $("tomaDoc").addEventListener("input", e => {
    e.target.value = formatarDoc(e.target.value);
    atualizarHintAvulso();
    marcarAvulsoEditado();
    const d = digitos(e.target.value);
    if (d.length === 14) buscarCNPJAuto();
    else ultimoCnpj = "";
  });
  $("tomaCep").addEventListener("input", e => {
    e.target.value = formatarCEP(e.target.value);
    marcarAvulsoEditado();
    const cep = digitos(e.target.value);
    if (cep.length === 8) buscarCEPAuto();
    else ultimoCep = "";
  });
  $("tomaUf").addEventListener("input", e => {
    e.target.value = e.target.value.replace(/[^a-zA-Z]/g, "").toUpperCase().slice(0, 2);
    marcarAvulsoEditado();
  });
  ["tomador","destinatario","intermediario","competencia","valor","observacoes"].forEach(id=>$(id).addEventListener("change",marcarAlterado));
  $("tomaNome").addEventListener("input", e => {
    const inicio = e.target.selectionStart;
    const fim = e.target.selectionEnd;
    e.target.value = e.target.value.toLocaleUpperCase("pt-BR");
    try { e.target.setSelectionRange(inicio, fim); } catch (_) {}
    marcarAvulsoEditado();
  });
  $("tomaNome").addEventListener("change", marcarAvulsoEditado);
  ["tomaFone","tomaEnd","tomaNum","tomaComp","tomaBairro","tomaCidade"].forEach(id=>{
    $(id).addEventListener("input", marcarAvulsoEditado);
    $(id).addEventListener("change", marcarAvulsoEditado);
  });
  $("observacoes").addEventListener("input", () => { preview(); marcarAlterado(); });
  document.querySelectorAll("[data-secao]").forEach(btn => {
    btn.addEventListener("click", () => mostrarSecao(btn.dataset.secao));
  });
  $("btnSalvar").onclick=salvar; $("btnValidar").onclick=validar; $("btnEmitir").onclick=emitir;
  $("btnFechar").onclick=()=>GlobalUtils.fecharJanelaApoio(window.__nivelModal__||1);
  $("btnDanfse").onclick=danfse; $("btnCancelarNota").onclick=cancelarNota;
  if ($("btnSincronizar")) $("btnSincronizar").onclick = sincronizarComSefin;
  if ($("btnInformarChave")) $("btnInformarChave").onclick = () => reconciliarComChave(chaveNota);
  if ($("btnAtualizarXml")) $("btnAtualizarXml").onclick = () => reconciliarComChave(chaveNota);
  GlobalUtils.receberDadosApoio(id=>init(id));
  const queryId=Number(new URLSearchParams(location.search).get("id")||0);
  setTimeout(() => { if (!carga) init(queryId || null); }, 150);
})();
