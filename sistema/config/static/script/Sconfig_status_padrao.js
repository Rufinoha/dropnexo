(function () {
  "use strict";

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("cfg_isp_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function abrirApoio(id) {
    if (!window.GlobalUtils?.abrirJanelaApoioModal) {
      alert("GlobalUtils indisponível.");
      return;
    }
    GlobalUtils.abrirJanelaApoioModal({
      rota: id ? cfg.rotaEditar : cfg.rotaIncluir,
      id: id || null,
      titulo: id ? "Editar status padrão" : "Novo status padrão",
      largura: 820,
      altura: 620,
      nivel: 1,
    });
  }

  async function excluir(id) {
    const c = await Swal.fire({
      title: "Excluir este mapeamento?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, excluir",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;
    const r = await fetch(cfg.apiExcluir, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao excluir.");
    await Swal.fire("OK", j.message || "Removido.", "success");
    await carregar();
  }

  async function carregar() {
    const tbody = document.getElementById("cfg_isp_tbody");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="9" class="CfgIsp_Hint">Carregando…</td></tr>`;
    const app = document.getElementById("cfg_isp_filtro_app")?.value || "";
    const ctx = document.getElementById("cfg_isp_filtro_ctx")?.value || "";
    const qs = new URLSearchParams();
    if (app) qs.set("aplicacao", app);
    if (ctx) qs.set("contexto", ctx);
    qs.set("todos", "1");
    const r = await fetch(`${cfg.apiDados}?${qs}`, { headers: { Accept: "application/json" } });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao listar.");
    const lista = j.linhas || [];
    if (!lista.length) {
      tbody.innerHTML = `<tr><td colspan="9" class="CfgIsp_Hint">Nenhum registro.</td></tr>`;
      return;
    }
    tbody.innerHTML = lista
      .map((row) => {
        const st = row.ativo
          ? `<span class="CfgIsp_On">Ativo</span>`
          : `<span class="CfgIsp_Off">Inativo</span>`;
        return `<tr>
          <td>${esc(row.aplicacao)}</td>
          <td>${esc(row.contexto)}</td>
          <td><strong>${esc(row.status_dn_label)}</strong><br><small>${esc(row.status_dn)}</small></td>
          <td>${esc(row.evento)}</td>
          <td>${esc(row.status_externo)}</td>
          <td>${esc(row.direcao)}</td>
          <td>${esc(row.ordem)}</td>
          <td>${st}</td>
          <td class="Cl_TableActions">
            <button type="button" class="Cl_BtnLink cfg-isp-editar" data-id="${row.id}">Editar</button>
            <button type="button" class="Cl_BtnLink cfg-isp-excluir" data-id="${row.id}">Excluir</button>
          </td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll(".cfg-isp-editar").forEach((btn) => {
      btn.addEventListener("click", () => abrirApoio(Number(btn.dataset.id)));
    });
    tbody.querySelectorAll(".cfg-isp-excluir").forEach((btn) => {
      btn.addEventListener("click", () =>
        excluir(Number(btn.dataset.id)).catch((e) => Swal.fire("Erro", e.message, "error"))
      );
    });
  }

  document.getElementById("cfg_isp_novo")?.addEventListener("click", () => abrirApoio(null));
  document.getElementById("cfg_isp_filtro_app")?.addEventListener("change", () =>
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"))
  );
  document.getElementById("cfg_isp_filtro_ctx")?.addEventListener("change", () =>
    carregar().catch((e) => Swal.fire("Erro", e.message, "error"))
  );

  window.addEventListener("message", (ev) => {
    if (ev?.data?.grupo === "atualizarTabela") {
      carregar().catch(() => {});
    }
  });

  carregar().catch((e) => {
    const tbody = document.getElementById("cfg_isp_tbody");
    if (tbody) tbody.innerHTML = `<tr><td colspan="9" class="CfgIsp_Hint">${esc(e.message)}</td></tr>`;
  });
})();
