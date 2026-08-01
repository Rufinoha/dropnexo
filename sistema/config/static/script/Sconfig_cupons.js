(function () {
  "use strict";

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("cfg_cup_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
  }

  function util() {
    return window.Util || { gerarIconeTech: () => "…" };
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function fmtDesc(c) {
    if (c.tipo_desconto === "fixo") {
      return "R$ " + Number(c.valor_desconto || 0).toLocaleString("pt-BR", { minimumFractionDigits: 2 });
    }
    return Number(c.valor_desconto || 0) + "%";
  }

  function fmtEscopo(c) {
    const partes = [];
    if (c.publico_alvo === "vendedor") partes.push("Vendedores");
    else if (c.publico_alvo === "fornecedor") partes.push("Fornecedores");
    const nt = (c.ids_tenants || []).length;
    if (nt === 1) partes.push("1 tenant");
    else if (nt > 1) partes.push(nt + " tenants");
    const np = (c.planos_slug || []).length;
    if (np === 1) partes.push("1 plano");
    else if (np > 1) partes.push(np + " planos");
    return partes.length ? partes.join(" · ") : "Todos";
  }

  function abrirApoio(id) {
    if (!window.GlobalUtils?.abrirJanelaApoioModal) {
      alert("GlobalUtils indisponível.");
      return;
    }
    GlobalUtils.abrirJanelaApoioModal({
      rota: id ? cfg.rotaEditar : cfg.rotaIncluir,
      id: id || null,
      titulo: id ? "Editar cupom" : "Novo cupom",
      largura: 980,
      altura: 640,
      nivel: 1,
    });
  }

  async function desativar(id) {
    const c = await Swal.fire({
      title: "Desativar este cupom?",
      icon: "warning",
      showCancelButton: true,
      confirmButtonText: "Sim, desativar",
      cancelButtonText: "Cancelar",
    });
    if (!c.isConfirmed) return;
    const r = await fetch(cfg.apiExcluir, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify({ id: id }),
    });
    const j = await r.json();
    if (!r.ok || !j.success) throw new Error(j.message || "Erro ao desativar.");
    await Swal.fire("OK", j.message || "Cupom desativado.", "success");
    await carregar();
  }

  async function carregar() {
    const tbody = document.getElementById("cfg_cup_tbody");
    if (!tbody || !cfg.apiDados) return;
    try {
      const r = await fetch(cfg.apiDados, { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Erro");
      const lista = j.cupons || [];
      if (!lista.length) {
        tbody.innerHTML = '<tr><td colspan="8" class="CfgCup_Hint">Nenhum cupom ainda.</td></tr>';
        return;
      }
      const u = util();
      tbody.innerHTML = lista
        .map(function (c) {
          const usos =
            c.usos_max == null
              ? c.usos_count + " / ∞"
              : c.usos_count + " / " + c.usos_max;
          let badge = c.ativo
            ? '<span class="CfgCup_Badge CfgCup_Badge--ok">Ativo</span>'
            : '<span class="CfgCup_Badge CfgCup_Badge--off">Inativo</span>';
          if (c.esgotado) {
            badge = '<span class="CfgCup_Badge CfgCup_Badge--warn">Esgotado</span>';
          }
          const acoes =
            '<td class="Cl_TableActions">' +
            '<button type="button" class="Cl_BtnAcao btnEditar" data-id="' +
            c.id +
            '" title="Editar">' +
            u.gerarIconeTech("editar") +
            "</button>" +
            (c.ativo
              ? '<button type="button" class="Cl_BtnAcao btnInativar" data-id="' +
                c.id +
                '" title="Desativar">' +
                u.gerarIconeTech("excluir") +
                "</button>"
              : "") +
            "</td>";
          return (
            "<tr>" +
            "<td><strong>" +
            esc(c.codigo) +
            "</strong></td>" +
            "<td>" +
            esc(fmtDesc(c)) +
            "</td>" +
            "<td>" +
            esc(c.periodo) +
            "</td>" +
            "<td>" +
            esc(fmtEscopo(c)) +
            "</td>" +
            "<td>" +
            esc(c.valido_ate || "—") +
            "</td>" +
            "<td>" +
            esc(usos) +
            "</td>" +
            "<td>" +
            badge +
            "</td>" +
            acoes +
            "</tr>"
          );
        })
        .join("");
      window.lucide?.createIcons?.();
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="8" class="CfgCup_Hint">' + esc(e.message) + "</td></tr>";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("cfg_cup_novo")?.addEventListener("click", function () {
      abrirApoio(null);
    });
    document.getElementById("cfg_cup_tbody")?.addEventListener("click", function (ev) {
      const btn = ev.target.closest(".Cl_BtnAcao");
      if (!btn) return;
      const id = +btn.getAttribute("data-id");
      if (!id) return;
      if (btn.classList.contains("btnEditar")) {
        abrirApoio(id);
        return;
      }
      if (btn.classList.contains("btnInativar")) {
        desativar(id).catch(function (e) {
          Swal.fire("Erro", e.message, "error");
        });
      }
    });
    window.addEventListener("message", function (ev) {
      if (!ev.data?.grupo) return;
      if (ev.data.grupo === "atualizarTabela") carregar();
    });
    carregar();
  });
})();
