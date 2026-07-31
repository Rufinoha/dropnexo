(function () {
  "use strict";

  let cfg = {};
  let tenantsCache = [];
  let tenantsSelecionadosIds = new Set();
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
    const n = (c.ids_tenants || []).length;
    if (n === 1) partes.push("1 tenant");
    else if (n > 1) partes.push(n + " tenants");
    return partes.length ? partes.join(" · ") : "Todos";
  }

  function syncSelecaoDoSelect() {
    const sel = document.getElementById("cfg_cup_tenants");
    if (!sel) return;
    const visiveis = new Set(Array.from(sel.options).map(function (o) { return +o.value; }));
    // Remove só os visíveis desmarcados; mantém os ocultos pelo filtro.
    visiveis.forEach(function (id) {
      tenantsSelecionadosIds.delete(id);
    });
    Array.from(sel.selectedOptions).forEach(function (o) {
      tenantsSelecionadosIds.add(+o.value);
    });
  }

  function tenantsSelecionados() {
    return Array.from(tenantsSelecionadosIds);
  }

  function renderTenantsSelect(selecionados) {
    const sel = document.getElementById("cfg_cup_tenants");
    const filtro = (document.getElementById("cfg_cup_tenant_filtro")?.value || "")
      .trim()
      .toLowerCase();
    if (!sel) return;
    if (selecionados) {
      tenantsSelecionadosIds = new Set(selecionados.map(Number));
    }
    const lista = tenantsCache.filter(function (t) {
      if (!filtro) return true;
      const blob = ("#" + t.id + " " + (t.nome || "") + " " + (t.slug || "") + " " + (t.tipo_negocio || "")).toLowerCase();
      return blob.includes(filtro);
    });
    sel.innerHTML = lista
      .map(function (t) {
        const label =
          "#" +
          t.id +
          " — " +
          (t.nome || t.slug || "Tenant") +
          " (" +
          (t.tipo_negocio || "?") +
          ")";
        return (
          '<option value="' +
          t.id +
          '"' +
          (tenantsSelecionadosIds.has(+t.id) ? " selected" : "") +
          ">" +
          esc(label) +
          "</option>"
        );
      })
      .join("");
  }

  function limparForm() {
    document.getElementById("cfg_cup_id").value = "";
    document.getElementById("cfg_cup_codigo").value = "";
    document.getElementById("cfg_cup_desc").value = "";
    document.getElementById("cfg_cup_tipo").value = "percentual";
    document.getElementById("cfg_cup_valor").value = "10";
    document.getElementById("cfg_cup_periodo").value = "mensal";
    document.getElementById("cfg_cup_publico").value = "";
    const filtro = document.getElementById("cfg_cup_tenant_filtro");
    if (filtro) filtro.value = "";
    renderTenantsSelect([]);
    document.getElementById("cfg_cup_valido").value = "";
    document.getElementById("cfg_cup_usos").value = "";
    document.getElementById("cfg_cup_ativo").checked = true;
    document.getElementById("cfg_cup_form_title").textContent = "Novo cupom";
    syncValorLabel();
  }

  function syncValorLabel() {
    const tipo = document.getElementById("cfg_cup_tipo").value;
    document.getElementById("cfg_cup_valor_lbl").textContent =
      tipo === "fixo" ? "Valor (R$)" : "Valor (%)";
  }

  function preencher(c) {
    document.getElementById("cfg_cup_id").value = c.id || "";
    document.getElementById("cfg_cup_codigo").value = c.codigo || "";
    document.getElementById("cfg_cup_desc").value = c.descricao || "";
    document.getElementById("cfg_cup_tipo").value = c.tipo_desconto || "percentual";
    document.getElementById("cfg_cup_valor").value = c.valor_desconto ?? 0;
    document.getElementById("cfg_cup_periodo").value = c.periodo || "mensal";
    document.getElementById("cfg_cup_publico").value = c.publico_alvo || "";
    const filtro = document.getElementById("cfg_cup_tenant_filtro");
    if (filtro) filtro.value = "";
    renderTenantsSelect(c.ids_tenants || []);
    document.getElementById("cfg_cup_valido").value = c.valido_ate || "";
    document.getElementById("cfg_cup_usos").value = c.usos_max == null ? "" : c.usos_max;
    document.getElementById("cfg_cup_ativo").checked = !!c.ativo;
    document.getElementById("cfg_cup_form_title").textContent = "Editar cupom";
    syncValorLabel();
  }

  async function carregar() {
    const tbody = document.getElementById("cfg_cup_tbody");
    if (!tbody || !cfg.apiDados) return;
    try {
      const r = await fetch(cfg.apiDados, { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Erro");
      tenantsCache = j.tenants || [];
      renderTenantsSelect(tenantsSelecionados());
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
          const id = +btn.getAttribute("data-edit");
          const c = lista.find(function (x) {
            return x.id === id;
          });
          if (c) preencher(c);
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
    document.getElementById("cfg_cup_tipo")?.addEventListener("change", syncValorLabel);
    document.getElementById("cfg_cup_novo")?.addEventListener("click", limparForm);
    document.getElementById("cfg_cup_cancelar")?.addEventListener("click", limparForm);
    document.getElementById("cfg_cup_tenant_filtro")?.addEventListener("input", function () {
      syncSelecaoDoSelect();
      renderTenantsSelect();
    });
    document.getElementById("cfg_cup_tenants")?.addEventListener("change", syncSelecaoDoSelect);
    document.getElementById("cfg_cup_form")?.addEventListener("submit", async function (e) {
      e.preventDefault();
      syncSelecaoDoSelect();
      const body = {
        id: document.getElementById("cfg_cup_id").value || null,
        codigo: document.getElementById("cfg_cup_codigo").value,
        descricao: document.getElementById("cfg_cup_desc").value,
        tipo_desconto: document.getElementById("cfg_cup_tipo").value,
        valor_desconto: document.getElementById("cfg_cup_valor").value,
        periodo: document.getElementById("cfg_cup_periodo").value,
        publico_alvo: document.getElementById("cfg_cup_publico").value || "",
        ids_tenants: tenantsSelecionados(),
        valido_ate: document.getElementById("cfg_cup_valido").value || null,
        usos_max: document.getElementById("cfg_cup_usos").value || null,
        ativo: document.getElementById("cfg_cup_ativo").checked,
      };
      try {
        const r = await fetch(cfg.apiSalvar, {
          method: "POST",
          headers: { "Content-Type": "application/json", Accept: "application/json" },
          body: JSON.stringify(body),
        });
        const j = await r.json();
        if (window.Swal) {
          Swal.fire(j.success ? "Salvo" : "Erro", j.message || "", j.success ? "success" : "error");
        }
        if (j.success) {
          limparForm();
          carregar();
        }
      } catch (err) {
        if (window.Swal) Swal.fire("Erro", err.message, "error");
      }
    });
    syncValorLabel();
    carregar();
  });
})();
