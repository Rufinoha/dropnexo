(function () {
  const elTipo = document.getElementById("pxm_tipo");
  const elChave = document.getElementById("pxm_chave");
  const elNome = document.getElementById("pxm_nome");
  const elCidade = document.getElementById("pxm_cidade");
  const elAtivo = document.getElementById("pxm_ativo");
  const elMsg = document.getElementById("pxm_msg");
  const elBadge = document.getElementById("pxm_status_badge");

  function mostrarMsg(txt, erro) {
    if (!elMsg) return;
    elMsg.textContent = txt;
    elMsg.hidden = !txt;
    elMsg.classList.toggle("is-erro", !!erro);
  }

  async function carregar() {
    const r = await fetch("/api/integracoes/pix-manual/status", { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    if (elTipo) elTipo.value = j.tipo_chave || "aleatoria";
    if (elChave) elChave.value = j.chave_pix || "";
    if (elNome) elNome.value = j.nome_beneficiario || "";
    if (elCidade) elCidade.value = j.cidade_beneficiario || "";
    if (elAtivo) elAtivo.checked = !!j.ativo;
    if (elBadge) {
      elBadge.textContent = j.conectado ? "Ativo" : "Inativo";
      elBadge.classList.toggle("is-on", !!j.conectado);
      elBadge.classList.toggle("is-off", !j.conectado);
    }
  }

  async function salvar() {
    mostrarMsg("");
    const body = {
      ativo: !!elAtivo?.checked,
      tipo_chave: elTipo?.value || "aleatoria",
      chave_pix: elChave?.value?.trim() || "",
      nome_beneficiario: elNome?.value?.trim() || "",
      cidade_beneficiario: elCidade?.value?.trim() || "",
    };
    const r = await fetch("/api/integracoes/pix-manual/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!j.success) {
      mostrarMsg(j.message || "Erro ao salvar.", true);
      return;
    }
    mostrarMsg(j.message || "Salvo.");
    await carregar();
  }

  async function desativar() {
    if (!confirm("Desativar PIX manual?")) return;
    await fetch("/api/integracoes/pix-manual/desativar", {
      method: "POST",
      credentials: "same-origin",
    });
    await carregar();
    mostrarMsg("PIX manual desativado.");
  }

  document.getElementById("pxm_btn_salvar")?.addEventListener("click", salvar);
  document.getElementById("pxm_btn_desativar")?.addEventListener("click", desativar);
  carregar();
})();
