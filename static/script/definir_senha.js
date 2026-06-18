(function () {
  "use strict";

  const form = document.getElementById("ds-form");
  const statusEl = document.getElementById("ds-status");
  const leadEl = document.getElementById("ds-lead");
  const msgEl = document.getElementById("msg-senha");
  const regrasEl = document.getElementById("ds-regras");
  const btnSubmit = document.getElementById("btn-submit");
  const inpSenha = document.getElementById("input-senha");
  const inpConfirmar = document.getElementById("input-confirmar");
  const fieldToken = document.getElementById("field-token");

  if (!form) return;

  const validarUrl = form.dataset.validarUrl || "/api/auth/validar-token";
  const salvarUrl = form.dataset.salvarUrl || "/api/auth/definir-senha";

  const REGRAS = [
    { id: "min8", test: (s) => s.length >= 8, label: "Mínimo de 8 caracteres" },
    { id: "maiuscula", test: (s) => /[A-Z]/.test(s), label: "1 letra maiúscula" },
    { id: "minuscula", test: (s) => /[a-z]/.test(s), label: "1 letra minúscula" },
    { id: "numero", test: (s) => /[0-9]/.test(s), label: "1 número" },
    { id: "especial", test: (s) => /[^A-Za-z0-9]/.test(s), label: "1 caractere especial" },
    { id: "igual", test: (s, c) => s.length > 0 && s === c, label: "Senha e confirmação iguais" },
  ];

  function tokenDaUrl() {
    return new URLSearchParams(window.location.search).get("token") || "";
  }

  function setStatus(texto, erro) {
    if (!statusEl) return;
    statusEl.textContent = texto;
    statusEl.classList.toggle("is-error", !!erro);
  }

  function mostrarMsg(texto, erro) {
    if (!msgEl) return;
    msgEl.textContent = texto;
    msgEl.hidden = !texto;
    msgEl.classList.toggle("is-error", !!erro);
  }

  function avaliarSenha() {
    const senha = inpSenha?.value || "";
    const conf = inpConfirmar?.value || "";
    let todasOk = true;

    if (regrasEl) {
      const html = ['<p class="ds-regras-titulo">Requisitos da senha</p>'];
      REGRAS.forEach((r) => {
        const ok = r.id === "igual" ? r.test(senha, conf) : r.test(senha);
        if (!ok) todasOk = false;
        html.push(
          `<div class="ds-regra${ok ? " is-ok" : ""}" data-regra="${r.id}">` +
            `<span class="ds-regra-icon" aria-hidden="true">${ok ? "✓" : ""}</span>` +
            `<span>${r.label}</span>` +
          `</div>`
        );
      });
      regrasEl.innerHTML = html.join("");
      regrasEl.classList.toggle("is-all-ok", todasOk);
    }

    if (btnSubmit) btnSubmit.disabled = !todasOk;
    return todasOk;
  }

  function bindToggleVisibilidade() {
    document.querySelectorAll(".ds-toggle-vis").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-target");
        const inp = id ? document.getElementById(id) : null;
        if (!inp) return;
        const visivel = inp.type === "text";
        inp.type = visivel ? "password" : "text";
        btn.textContent = visivel ? "Mostrar" : "Ocultar";
        btn.setAttribute("aria-pressed", visivel ? "false" : "true");
      });
    });
  }

  async function validarToken(token) {
    const r = await fetch(`${validarUrl}?token=${encodeURIComponent(token)}`, {
      headers: { Accept: "application/json" },
    });
    const j = await r.json();
    if (!r.ok || !j.valido) {
      throw new Error(j.message || "Link inválido ou expirado.");
    }
    return j;
  }

  async function salvarSenha(token) {
    const r = await fetch(salvarUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({
        token,
        senha: inpSenha?.value || "",
        confirmar: inpConfirmar?.value || "",
      }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) {
      throw new Error(j.message || "Não foi possível salvar a senha.");
    }
    return j;
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    mostrarMsg("", false);
    if (!avaliarSenha()) {
      mostrarMsg("A senha não atende a todos os requisitos.", true);
      return;
    }

    const token = fieldToken?.value || tokenDaUrl();
    if (btnSubmit) btnSubmit.disabled = true;

    try {
      const j = await salvarSenha(token);
      setStatus("Senha definida com sucesso! Redirecionando…", false);
      form.hidden = true;
      window.setTimeout(() => {
        window.location.href = j.redirect || "/login";
      }, 1200);
    } catch (err) {
      mostrarMsg(err.message || "Erro ao salvar.", true);
      if (btnSubmit) btnSubmit.disabled = false;
      avaliarSenha();
    }
  });

  inpSenha?.addEventListener("input", avaliarSenha);
  inpConfirmar?.addEventListener("input", avaliarSenha);

  bindToggleVisibilidade();
  avaliarSenha();

  (async function init() {
    const token = tokenDaUrl();
    if (!token) {
      setStatus("Link inválido: token ausente.", true);
      return;
    }

    try {
      const dados = await validarToken(token);
      if (fieldToken) fieldToken.value = token;
      if (leadEl && dados.nome) {
        leadEl.innerHTML =
          `Olá, <strong>${String(dados.nome).replace(/</g, "&lt;")}</strong>. ` +
          "Defina uma senha segura para ativar seu acesso.";
      }
      setStatus("", false);
      statusEl.hidden = true;
      form.hidden = false;
      inpSenha?.focus();
    } catch (err) {
      setStatus(err.message || "Link inválido ou expirado.", true);
    }
  })();
})();
