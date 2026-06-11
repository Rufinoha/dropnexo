/**
 * Smeu_perfil.js — Meu perfil do usuário logado
 */
(function () {
  "use strict";

  const cfg = window.OSB_MEU_PERFIL || {};

  function fmtData(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" });
    } catch {
      return iso;
    }
  }

  function iniciaisDe(nome) {
    const partes = String(nome || "")
      .trim()
      .split(/\s+/)
      .filter(Boolean);
    if (partes.length >= 2) {
      return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
    }
    if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
    return cfg.iniciaisPadrao || "OS";
  }

  function iniciaisAtuais() {
    const ini = document.getElementById("mp-iniciais");
    return (ini && ini.textContent.trim()) || cfg.iniciaisPadrao || "OS";
  }

  function fotoUrlPadrao() {
    return (
      cfg.fotoUrlPadrao ||
      (window.OSB_SHELL && window.OSB_SHELL.fotoUrlPadrao) ||
      "/static/imge/imguser/userpadrao.png"
    );
  }

  function syncHeaderAvatar() {
    const headerUrl =
      cfg.apiFotoUrl || (window.OSB_SHELL && window.OSB_SHELL.apiFotoUsuario);
    if (window.OsbAvatar && typeof window.OsbAvatar.sync === "function") {
      window.OsbAvatar.sync(headerUrl || fotoUrlPadrao(), iniciaisAtuais());
    }
  }

  /** @param {string} [url] — URL estática da foto (custom ou userpadrao.png) */
  /** @param {boolean} [temFotoCustom] — usuário enviou foto própria */
  function aplicarFoto(url, temFotoCustom) {
    const img = document.getElementById("mp-foto");
    const ini = document.getElementById("mp-iniciais");
    const btnRem = document.getElementById("mp-btn-remover-foto");
    if (!img) return;

    const urlExibir = url || fotoUrlPadrao();
    const bust = urlExibir + (urlExibir.indexOf("?") >= 0 ? "&" : "?") + "t=" + Date.now();
    img.src = bust;
    img.hidden = false;
    if (ini) ini.hidden = true;
    if (btnRem) btnRem.hidden = !temFotoCustom;
    syncHeaderAvatar();
  }

  function renderRegrasSenha() {
    const ul = document.getElementById("mp-regras-senha");
    const nova = document.getElementById("mp-senha-nova")?.value || "";
    const conf = document.getElementById("mp-senha-confirma")?.value || "";
    if (!ul) return;

    const regras = [
      { id: "min8", ok: nova.length >= 8, label: "Mínimo de 8 caracteres" },
      { id: "maiuscula", ok: /[A-Z]/.test(nova), label: "1 letra maiúscula" },
      { id: "minuscula", ok: /[a-z]/.test(nova), label: "1 letra minúscula" },
      { id: "numero", ok: /[0-9]/.test(nova), label: "1 número" },
      { id: "especial", ok: /[^A-Za-z0-9]/.test(nova), label: "1 caractere especial" },
      { id: "igual", ok: nova.length > 0 && nova === conf, label: "Senha e confirmação iguais" },
    ];

    ul.innerHTML = regras
      .map(function (r) {
        return (
          '<li class="' +
          (r.ok ? "ok" : "fail") +
          '" data-regra="' +
          r.id +
          '">' +
          r.label +
          "</li>"
        );
      })
      .join("");
  }

  async function carregarPerfil() {
    try {
      const r = await fetch(cfg.apiDados, { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.success || !j.perfil) {
        if (typeof Swal !== "undefined") Swal.fire("Erro", j.message || "Falha ao carregar.", "error");
        return;
      }

      const p = j.perfil;
      document.getElementById("mp-nome").value = p.nome || "";
      document.getElementById("mp-email").value = p.email || "";
      document.getElementById("mp-whatsapp").value = p.whatsapp || "";
      document.getElementById("mp-tenant").textContent = p.tenant_nome || "—";
      document.getElementById("mp-papel").textContent = p.papel_label || p.papel || "—";
      document.getElementById("mp-plano").textContent = (p.tenant_plano || "—").toString();
      document.getElementById("mp-ultimo-acesso").textContent = fmtData(p.ultimo_acesso_em);

      const ini = document.getElementById("mp-iniciais");
      if (ini) ini.textContent = iniciaisDe(p.nome);

      const nomeTop = document.querySelector(".fg-user-name");
      if (nomeTop && p.nome) nomeTop.textContent = p.nome;

      aplicarFoto(p.foto_url || p.foto_url_padrao, !!p.tem_foto);
    } catch (err) {
      if (typeof Swal !== "undefined") Swal.fire("Erro", err.message || "Falha de conexão.", "error");
    }
  }

  async function salvarDados(ev) {
    ev.preventDefault();
    const nome = (document.getElementById("mp-nome").value || "").trim();
    const whatsapp = (document.getElementById("mp-whatsapp").value || "").trim();

    if (nome.length < 2) {
      if (typeof Swal !== "undefined") Swal.fire("Atenção", "Informe o nome.", "warning");
      return;
    }

    try {
      const r = await fetch(cfg.apiSalvar, {
        method: "PUT",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify({ nome: nome, whatsapp: whatsapp || null }),
      });
      const j = await r.json();
      if (!j.success) {
        if (typeof Swal !== "undefined") Swal.fire("Erro", j.message || "Falha ao salvar.", "error");
        return;
      }

      const ini = document.getElementById("mp-iniciais");
      if (ini) ini.textContent = iniciaisDe(nome);
      const nomeTop = document.querySelector(".fg-user-name");
      if (nomeTop) nomeTop.textContent = nome;

      if (typeof Swal !== "undefined") Swal.fire("Salvo", j.message || "Dados atualizados.", "success");
    } catch (err) {
      if (typeof Swal !== "undefined") Swal.fire("Erro", err.message || "Falha.", "error");
    }
  }

  async function trocarSenha(ev) {
    ev.preventDefault();
    const body = {
      senha_atual: document.getElementById("mp-senha-atual")?.value || "",
      senha_nova: document.getElementById("mp-senha-nova")?.value || "",
      confirmar: document.getElementById("mp-senha-confirma")?.value || "",
    };

    try {
      const r = await fetch(cfg.apiSenha, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!j.success) {
        if (typeof Swal !== "undefined") Swal.fire("Erro", j.message || "Não foi possível alterar.", "error");
        return;
      }

      document.getElementById("form-senha").reset();
      renderRegrasSenha();
      if (typeof Swal !== "undefined") Swal.fire("Pronto", j.message || "Senha alterada.", "success");
    } catch (err) {
      if (typeof Swal !== "undefined") Swal.fire("Erro", err.message || "Falha.", "error");
    }
  }

  async function enviarFoto(arquivo) {
    if (!arquivo) return;

    const fd = new FormData();
    fd.append("arquivo", arquivo);

    if (typeof Swal !== "undefined") {
      Swal.fire({
        title: "Enviando foto…",
        allowOutsideClick: false,
        didOpen: function () {
          Swal.showLoading();
        },
      });
    }

    try {
      const r = await fetch(cfg.apiFotoUpload, { method: "POST", body: fd });
      const j = await r.json();
      if (typeof Swal !== "undefined") Swal.close();

      if (!j.success) {
        if (typeof Swal !== "undefined") Swal.fire("Erro", j.message || "Falha no envio.", "error");
        return;
      }

      aplicarFoto(j.foto_url, true);
      if (typeof Swal !== "undefined") Swal.fire("Pronto", j.message || "Foto atualizada.", "success");
    } catch (err) {
      if (typeof Swal !== "undefined") Swal.fire("Erro", err.message || "Falha.", "error");
    }
  }

  async function removerFoto() {
    const confirma =
      typeof Swal !== "undefined"
        ? await Swal.fire({
            title: "Remover foto?",
            icon: "warning",
            showCancelButton: true,
            confirmButtonText: "Sim",
            cancelButtonText: "Voltar",
          }).then(function (res) {
            return res.isConfirmed;
          })
        : confirm("Remover foto?");

    if (!confirma) return;

    try {
      const r = await fetch(cfg.apiFotoDelete, {
        method: "DELETE",
        headers: { Accept: "application/json" },
      });
      const j = await r.json();
      if (!j.success) {
        if (typeof Swal !== "undefined") Swal.fire("Erro", j.message || "Falha.", "error");
        return;
      }

      aplicarFoto(j.foto_url || fotoUrlPadrao(), false);
      const inp = document.getElementById("mp-input-foto");
      if (inp) inp.value = "";
    } catch (err) {
      if (typeof Swal !== "undefined") Swal.fire("Erro", err.message || "Falha.", "error");
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    carregarPerfil();

    document.getElementById("form-perfil")?.addEventListener("submit", salvarDados);
    document.getElementById("form-senha")?.addEventListener("submit", trocarSenha);

    document.getElementById("mp-btn-toggle-senha")?.addEventListener("click", function () {
      const panel = document.getElementById("mp-senha-panel");
      const expanded = this.getAttribute("aria-expanded") === "true";
      this.setAttribute("aria-expanded", expanded ? "false" : "true");
      if (panel) panel.hidden = expanded;
      if (!expanded) renderRegrasSenha();
    });

    ["mp-senha-nova", "mp-senha-confirma"].forEach(function (id) {
      document.getElementById(id)?.addEventListener("input", renderRegrasSenha);
    });

    document.getElementById("mp-input-foto")?.addEventListener("change", function () {
      const f = this.files && this.files[0];
      if (f) enviarFoto(f);
      this.value = "";
    });

    document.getElementById("mp-btn-remover-foto")?.addEventListener("click", removerFoto);

    renderRegrasSenha();
  });
})();
