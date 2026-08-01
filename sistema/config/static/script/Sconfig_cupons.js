(function () {
  "use strict";

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("cfg_cup_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
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
            '<td><button type="button" class="Cl_botaoFiltro" data-edit="' +
            c.id +
            '">Editar</button> ' +
            (c.ativo
              ? '<button type="button" class="Cl_botaoFiltro" data-off="' + c.id + '">Desativar</button>'
              : "") +
            "</td></tr>"
          );
        })
        .join("");

      tbody.querySelectorAll("[data-edit]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          abrirApoio(+btn.getAttribute("data-edit"));
        });
      });
      tbody.querySelectorAll("[data-off]").forEach(function (btn) {
        btn.addEventListener("click", async function () {
          const id = +btn.getAttribute("data-off");
          if (!confirm("Desativar este cupom?")) return;
          const r = await fetch(cfg.apiExcluir, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({ id: id }),
          });
          const j = await r.json();
          if (window.Swal) {
            Swal.fire(j.success ? "OK" : "Erro", j.message || "", j.success ? "success" : "error");
          }
          if (j.success) carregar();
        });
      });
    } catch (e) {
      tbody.innerHTML = '<tr><td colspan="8" class="CfgCup_Hint">' + esc(e.message) + "</td></tr>";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("cfg_cup_novo")?.addEventListener("click", function () {
      abrirApoio(null);
    });
    window.addEventListener("message", function (ev) {
      if (!ev.data?.grupo) return;
      if (ev.data.grupo === "atualizarTabela") carregar();
    });
    carregar();
  });
})();
