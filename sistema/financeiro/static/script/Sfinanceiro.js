/**
 * Sfinanceiro.js — faturas e log Efi (DEV)
 */
(function () {
  "use strict";

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("fin_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
  }

  let pagina = 1;

  function badge(st) {
    const map = {
      pendente: ["Fin_Badge--warn", "Emitida"],
      pago: ["Fin_Badge--ok", "Paga"],
      vencido: ["Fin_Badge--danger", "Vencida"],
      cancelado: ["Fin_Badge--muted", "Cancelada"],
    };
    const [cls, lbl] = map[st] || ["Fin_Badge--muted", st || "—"];
    return '<span class="Fin_Badge ' + cls + '">' + lbl + "</span>";
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function fmtData(iso) {
    if (!iso) return "—";
    try {
      const p = iso.length === 10 ? iso + "T12:00:00" : iso;
      return new Date(p).toLocaleDateString("pt-BR");
    } catch {
      return iso;
    }
  }

  function acoes(f) {
    const parts = [];
    if (f.link_boleto && (f.status === "pendente" || f.status === "vencido")) {
      parts.push(
        '<a class="Cl_botaoFiltro" href="' +
          esc(f.link_boleto) +
          '" target="_blank" rel="noopener">Boleto</a>'
      );
    }
    if (f.pix_copia_cola && (f.status === "pendente" || f.status === "vencido")) {
      parts.push(
        '<button type="button" class="Cl_botaoFiltro" data-pix="' +
          esc(f.pix_copia_cola) +
          '">Copiar PIX</button>'
      );
    }
    if (f.link_pagamento && (f.status === "pendente" || f.status === "vencido")) {
      parts.push(
        '<a class="Cl_botaoFiltro" href="' +
          esc(f.link_pagamento) +
          '" target="_blank" rel="noopener">Pagar</a>'
      );
    }
    if (f.status === "pendente" || f.status === "vencido") {
      parts.push(
        '<button type="button" class="Cl_botaoFiltro" data-regen="' +
          f.id +
          '" data-valor="' +
          (f.valor_centavos || 0) +
          '">Gerar 2ª via</button>'
      );
    }
    return parts.length ? '<div class="Fin_Acoes">' + parts.join("") + "</div>" : "—";
  }

  async function carregar(page) {
    pagina = page || 1;
    const corpo = document.getElementById("fin_corpo");
    if (!corpo || !cfg.apiFaturas) return;
    try {
      const r = await fetch(cfg.apiFaturas + "?page=" + pagina, { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Erro");
      const lista = j.faturas || [];
      if (!lista.length) {
        corpo.innerHTML = '<tr><td colspan="7" class="Fin_Empty">Nenhuma fatura emitida ainda.</td></tr>';
      } else {
        corpo.innerHTML = lista
          .map(function (f) {
            return (
              "<tr><td>" +
              esc(f.referencia) +
              "</td><td>" +
              esc(f.plano_slug || "—") +
              "</td><td>" +
              esc(f.valor_formatado) +
              "</td><td>" +
              fmtData(f.vencimento_em) +
              "</td><td>" +
              esc(f.forma_pagamento) +
              "</td><td>" +
              badge(f.status) +
              "</td><td>" +
              acoes(f) +
              "</td></tr>"
            );
          })
          .join("");
      }
      const pag = document.getElementById("fin_paginacao");
      if (pag) {
        pag.hidden = !(j.total_paginas > 1);
        pag.textContent = "Página " + j.pagina + " de " + j.total_paginas;
      }
      corpo.querySelectorAll("[data-pix]").forEach(function (btn) {
        btn.addEventListener("click", async function () {
          try {
            await navigator.clipboard.writeText(btn.getAttribute("data-pix") || "");
            if (window.Swal) Swal.fire({ icon: "success", title: "PIX copiado", timer: 1500, showConfirmButton: false });
          } catch {
            if (window.Swal) Swal.fire("PIX", btn.getAttribute("data-pix") || "", "info");
          }
        });
      });
      corpo.querySelectorAll("[data-regen]").forEach(function (btn) {
        btn.addEventListener("click", function () {
          regenerar(+btn.getAttribute("data-regen"), +btn.getAttribute("data-valor") || 0);
        });
      });
    } catch (e) {
      corpo.innerHTML = '<tr><td colspan="7" class="Fin_Empty">' + esc(e.message || "Erro") + "</td></tr>";
    }
  }

  async function regenerar(id, valorCentavos) {
    if (typeof Swal === "undefined") {
      if (!confirm("Gerar 2ª via?")) return;
      await postRegenerar(id, { forma_pagamento: "boleto" });
      return;
    }

    const { value: forma } = await Swal.fire({
      title: "Gerar 2ª via",
      html:
        "<p>Escolha a forma da nova cobrança.</p>" +
        '<select id="fin_forma" class="swal2-select">' +
        '<option value="boleto">Boleto bancário</option>' +
        '<option value="cartao">Cartão de crédito</option>' +
        "</select>",
      showCancelButton: true,
      confirmButtonText: "Continuar",
      confirmButtonColor: "#021F81",
      preConfirm: function () {
        return document.getElementById("fin_forma")?.value || "boleto";
      },
    });
    if (!forma) return;

    const body = { forma_pagamento: forma };
    if (forma === "cartao") {
      if (!window.DropNexoEfi || !DropNexoEfi.promptCartao) {
        Swal.fire({
          icon: "error",
          title: "Cartão",
          text: "Script do cartão não carregou. Recarregue a página.",
          confirmButtonColor: "#021F81",
        });
        return;
      }
      const tok = await DropNexoEfi.promptCartao({
        payeeCode: cfg.efiPayeeCode || "",
        environment: cfg.efiEnvironment || "sandbox",
        valorCentavos: valorCentavos || 0,
        titulo: "Pagar 2ª via",
      });
      if (!tok) return;
      body.payment_token = tok.payment_token;
      body.installments = tok.installments || 1;
    }

    Swal.fire({ title: "Gerando cobrança…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    await postRegenerar(id, body);
  }

  async function postRegenerar(id, body) {
    try {
      const r = await fetch(cfg.apiRegenerarBase + "/" + id + "/regenerar", {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body || {}),
      });
      const j = await r.json();
      if (typeof Swal !== "undefined") {
        const fat = j.fatura || {};
        let extra = "";
        if (fat.link_boleto) {
          extra = '<p><a href="' + esc(fat.link_boleto) + '" target="_blank" rel="noopener">Abrir boleto</a></p>';
        }
        Swal.fire({
          icon: j.success ? "success" : "error",
          title: j.success ? "Cobrança regenerada" : "Erro",
          html: "<p>" + esc(j.message || "") + "</p>" + extra,
          confirmButtonColor: "#021F81",
        });
      }
      if (j.success) carregar(pagina);
    } catch (e) {
      if (typeof Swal !== "undefined") Swal.fire("Erro", e.message, "error");
    }
  }

  async function carregarLogs() {
    const box = document.getElementById("fin_logs");
    if (!box || !cfg.apiLogs) return;
    box.innerHTML = "<p>Carregando…</p>";
    try {
      const r = await fetch(cfg.apiLogs + "?page=1", { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Erro");
      const logs = j.logs || [];
      if (!logs.length) {
        box.innerHTML = '<p class="Fin_Empty">Nenhum log ainda.</p>';
        return;
      }
      box.innerHTML = logs
        .map(function (l) {
          return (
            '<div class="Fin_LogItem">' +
            '<div class="' +
            (l.ok ? "Fin_LogOk" : "Fin_LogFail") +
            '">#' +
            l.id +
            " · " +
            esc(l.criado_em) +
            " · " +
            esc(l.direcao) +
            "/" +
            esc(l.operacao) +
            " · tenant " +
            (l.id_tenant || "—") +
            " · charge " +
            esc(l.efi_charge_id || "—") +
            "</div>" +
            "<div>" +
            esc((l.request_resumo || "").slice(0, 500)) +
            "</div>" +
            "<div>" +
            esc((l.response_resumo || "").slice(0, 500)) +
            "</div></div>"
          );
        })
        .join("");
    } catch (e) {
      box.innerHTML = "<p>" + esc(e.message) + "</p>";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    carregar(1);
    document.getElementById("fin_btnLogs")?.addEventListener("click", carregarLogs);
  });
})();
