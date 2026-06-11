(function () {
  let idUsuario = null;
  let nivelModal = 1;

  const el = {
    id: document.getElementById("id"),
    email: document.getElementById("email"),
    nome: document.getElementById("nome"),
    whatsapp: document.getElementById("whatsapp"),
    id_perfil: document.getElementById("id_perfil"),
    status: document.getElementById("status"),
    enviar_convite: document.getElementById("enviar_convite"),
    wrapEnviarConvite: document.getElementById("wrapEnviarConvite"),
    conviteHint: document.getElementById("conviteHint"),
    btnSalvar: document.getElementById("btnSalvar"),
    btnReenviar: document.getElementById("btnReenviar"),
  };
  if (!el.email) return;

  const BASE = "/fornecedor/usuarios";

  async function carregarPerfis() {
    const r = await fetch(`${BASE}/combos`);
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar perfis.");
    el.id_perfil.innerHTML = "";
    (j.perfis || []).forEach((p) => {
      const o = document.createElement("option");
      o.value = p.id;
      o.textContent = `${p.nome} (${p.codigo})`;
      el.id_perfil.appendChild(o);
    });
  }

  function hintConvite(status) {
    const map = {
      PENDENTE: "Convite pendente — o usuário ainda não definiu a senha.",
      ACEITO: "Usuário já ativou o acesso.",
      EXPIRADO: "Convite expirado — use Reenviar convite.",
      SEM_CONVITE: "Sem convite enviado.",
    };
    el.conviteHint.textContent = map[status] || "";
  }

  async function carregarApoio(id) {
    const r = await fetch(`${BASE}/apoio`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao carregar.");
    const d = j.dados;
    el.email.value = d.email || "";
    el.email.readOnly = true;
    el.nome.value = d.nome || "";
    el.whatsapp.value = d.whatsapp || "";
    el.id_perfil.value = d.id_perfil || "";
    el.status.checked = !!d.status;
    el.wrapEnviarConvite.style.display = "none";
    el.btnReenviar.style.display =
      d.convite_status === "PENDENTE" || d.convite_status === "EXPIRADO" ? "inline-block" : "none";
    hintConvite(d.convite_status);
  }

  async function salvar() {
    const body = {
      id: idUsuario,
      email: (el.email.value || "").trim(),
      nome: (el.nome.value || "").trim(),
      whatsapp: (el.whatsapp.value || "").trim(),
      id_perfil: el.id_perfil.value ? Number(el.id_perfil.value) : null,
      status: !!el.status.checked,
      enviar_convite: !!el.enviar_convite?.checked,
    };
    const r = await fetch(`${BASE}/salvar`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao salvar.");
    await Swal.fire("Sucesso", j.message, "success");
    window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    window.GlobalUtils?.fecharJanelaApoio(nivelModal);
  }

  async function reenviar() {
    if (!idUsuario) return;
    const r = await fetch(`${BASE}/reenviar-convite`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id: idUsuario }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro.");
    await Swal.fire("Sucesso", j.message, "success");
    await carregarApoio(idUsuario);
  }

  el.btnSalvar?.addEventListener("click", () =>
    salvar().catch((e) => Swal.fire("Erro", e.message, "error"))
  );
  el.btnReenviar?.addEventListener("click", () =>
    reenviar().catch((e) => Swal.fire("Erro", e.message, "error"))
  );

  let combosProntos = false;
  let idPendente = null;

  async function aplicarId(id, nivel) {
    idUsuario = id ? Number(id) : null;
    nivelModal = nivel || 1;
    if (el.id) el.id.value = idUsuario ? String(idUsuario) : "";
    if (!idUsuario) {
      el.email.readOnly = false;
      el.wrapEnviarConvite.style.display = "";
      el.btnReenviar.style.display = "none";
      el.conviteHint.textContent = "Um e-mail de convite será enviado para definir a senha.";
      return;
    }
    if (!combosProntos) {
      idPendente = idUsuario;
      return;
    }
    await carregarApoio(idUsuario);
  }

  if (window.GlobalUtils?.receberDadosApoio) {
    window.GlobalUtils.receberDadosApoio((id, nivel) => aplicarId(id, nivel));
  }

  carregarPerfis()
    .then(() => {
      combosProntos = true;
      if (idPendente != null) {
        const id = idPendente;
        idPendente = null;
        return carregarApoio(id);
      }
    })
    .catch((e) => Swal.fire("Erro", e.message, "error"));
})();
