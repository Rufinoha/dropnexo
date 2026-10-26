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
  let planoAtual = null;

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

  function fecharMenus() {
    document.querySelectorAll(".Fin_MenuLista").forEach(function (n) {
      n.remove();
    });
  }

  function acoes(f) {
    const aberto = f.status === "pendente" || f.status === "vencido";
    const pago = f.status === "pago";
    if (!aberto && !pago) return "—";
    return (
      '<button type="button" class="Fin_MenuBtn" data-menu="' +
      f.id +
      '" data-status="' +
      esc(f.status) +
      '" data-link="' +
      esc(f.link_boleto || f.link_pagamento || "") +
      '" data-valor="' +
      (f.valor_centavos || 0) +
      '" data-plano="' +
      esc(f.plano_slug || "Plano") +
      '" aria-label="Ações">⋮</button>'
    );
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
      corpo.querySelectorAll("[data-menu]").forEach(function (btn) {
        btn.addEventListener("click", function (ev) {
          ev.stopPropagation();
          abrirMenu(btn);
        });
      });
    } catch (e) {
      corpo.innerHTML = '<tr><td colspan="7" class="Fin_Empty">' + esc(e.message || "Erro") + "</td></tr>";
    }
  }

  async function regenerar(id, valorCentavos, planoNome) {
    if (!window.DropNexoEfi || !DropNexoEfi.openCheckout) {
      if (!confirm("Gerar 2ª via em boleto?")) return;
      await postRegenerar(id, { forma_pagamento: "boleto" });
      return;
    }

    const pay = await DropNexoEfi.openCheckout({
      payeeCode: cfg.efiPayeeCode || "",
      environment: cfg.efiEnvironment || "sandbox",
      valorCentavos: valorCentavos || 0,
      planoNome: planoNome || "Fatura DropNexo",
      titulo: "Gerar 2ª via",
    });
    if (!pay) return;

    const body = {
      forma_pagamento: pay.forma,
      payment_token: pay.payment_token || null,
      installments: pay.installments || 1,
    };
    if (window.Swal) {
      Swal.fire({ title: "Gerando cobrança…", allowOutsideClick: false, didOpen: () => Swal.showLoading() });
    }
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

  function abrirMenu(btn) {
    fecharMenus();
    const status = btn.getAttribute("data-status");
    const link = btn.getAttribute("data-link") || "";
    const id = btn.getAttribute("data-menu");
    const box = document.createElement("div");
    box.className = "Fin_MenuLista";
    if (status === "pendente" || status === "vencido") {
      const pagar = document.createElement("button");
      pagar.type = "button";
      pagar.textContent = "Pagar agora";
      pagar.addEventListener("click", function () {
        fecharMenus();
        if (link) window.open(link, "_blank", "noopener");
        else
          regenerar(
            +id,
            +btn.getAttribute("data-valor") || 0,
            btn.getAttribute("data-plano") || "Fatura"
          );
      });
      box.appendChild(pagar);
    }
    if (status === "pago") {
      const nota = document.createElement("button");
      nota.type = "button";
      nota.textContent = "Baixar nota fiscal";
      nota.addEventListener("click", async function () {
        fecharMenus();
        try {
          const r = await fetch(cfg.apiRegenerarBase + "/" + id + "/nota", { headers: { Accept: "application/json" } });
          const j = await r.json();
          if (j.success && j.url) window.open(j.url, "_blank", "noopener");
          else if (window.Swal) Swal.fire("Nota fiscal", j.message || "Ainda não disponível.", "info");
        } catch (e) {
          if (window.Swal) Swal.fire("Nota fiscal", e.message || "Ainda não disponível.", "info");
        }
      });
      box.appendChild(nota);
    }
    document.body.appendChild(box);
    const r = btn.getBoundingClientRect();
    box.style.top = r.bottom + 4 + "px";
    box.style.left = Math.max(8, r.right - box.offsetWidth) + "px";
  }

  async function postTroca(body) {
    const r = await fetch(cfg.apiTrocarForma, {
      method: "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body: JSON.stringify(body || {}),
    });
    const j = await r.json();
    if (window.Swal) {
      Swal.fire(j.success ? "Forma de pagamento" : "Erro", j.message || "", j.success ? "success" : "error");
    }
    if (j.success) {
      carregarPlano();
      carregar(pagina);
    }
  }

  async function pedirCartao(opts) {
    if (!window.DropNexoEfi || !DropNexoEfi.openCheckout) {
      if (window.Swal) Swal.fire("Cartão", "O pagamento com cartão não carregou nesta página.", "error");
      return null;
    }
    return DropNexoEfi.openCheckout(
      Object.assign(
        {
          payeeCode: cfg.efiPayeeCode || "",
          environment: cfg.efiEnvironment || "sandbox",
          somenteCartao: true,
        },
        opts || {}
      )
    );
  }

  async function trocarForma() {
    const p = planoAtual || {};
    const proximas = !!p.pode_trocar_proximas;
    const esta = !!p.pode_pagar_esta;
    if (!proximas && !esta) return;
    let escopo = proximas ? "proximas" : "fatura";
    if (proximas && esta && window.Swal) {
      const escolha = await Swal.fire({
        title: "Trocar forma de pagamento",
        text: "Daqui pra frente muda as próximas cobranças. Só esta fatura paga a que está em boleto no cartão e deixa as próximas no boleto.",
        showDenyButton: true,
        showCancelButton: true,
        confirmButtonText: "Daqui pra frente",
        denyButtonText: "Só esta fatura no cartão",
        cancelButtonText: "Voltar",
        confirmButtonColor: "#021F81",
      });
      if (escolha.isDenied) escopo = "fatura";
      else if (!escolha.isConfirmed) return;
    }
    if (escopo === "fatura") {
      const fat = p.fatura_aberta || {};
      const pay = await pedirCartao({
        valorCentavos: fat.valor_centavos || 0,
        planoNome: fat.referencia || "Fatura em aberto",
        titulo: "Pagar esta fatura no cartão",
        nota: "As próximas cobranças continuam no boleto.",
        sufixo: "",
        rotuloBotao: "Pagar esta fatura",
      });
      if (!pay || pay.forma !== "cartao" || !pay.payment_token) return;
      await postTroca({
        escopo: "fatura",
        id_fatura: fat.id,
        payment_token: pay.payment_token,
        installments: pay.installments || 1,
      });
      return;
    }
    let forma = "cartao";
    if (window.Swal) {
      const formaDlg = await Swal.fire({
        title: "Próximas cobranças",
        text: "A fatura que já está em aberto continua como está.",
        input: "radio",
        inputOptions: { cartao: "Cartão de crédito", boleto: "Boleto" },
        inputValue: p.forma_pagamento === "boleto" ? "boleto" : "cartao",
        inputValidator: function (v) {
          if (!v) return "Escolha boleto ou cartão.";
        },
        showCancelButton: true,
        confirmButtonText: "Continuar",
        cancelButtonText: "Voltar",
        confirmButtonColor: "#021F81",
      });
      if (!formaDlg.isConfirmed) return;
      forma = formaDlg.value;
    }
    if (forma === "boleto") {
      await postTroca({ escopo: "proximas", forma: "boleto" });
      return;
    }
    const pay = await pedirCartao({
      valorCentavos: p.valor_centavos || (p.fatura_aberta && p.fatura_aberta.valor_centavos) || 0,
      planoNome: p.plano_nome || "Plano",
      titulo: "Cartão das próximas cobranças",
      nota: "As próximas cobranças usam este cartão. A fatura já em aberto não muda.",
      sufixo: "",
      semParcelas: true,
      rotuloBotao: "Usar este cartão",
    });
    if (!pay || pay.forma !== "cartao" || !pay.payment_token) return;
    await postTroca({
      escopo: "proximas",
      forma: "cartao",
      payment_token: pay.payment_token,
    });
  }

  async function carregarPlano() {
    const box = document.getElementById("fin_plano_corpo");
    if (!box || !cfg.apiMeuPlano) return;
    try {
      const r = await fetch(cfg.apiMeuPlano, { headers: { Accept: "application/json" } });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Erro");
      const p = j.plano || {};
      planoAtual = p;
      const status = p.assinatura_status === "cancelada" ? "Cancelada" : p.recorrencia_efi ? "Ativa na Efí" : "Sem recorrência na Efí";
      const aberta = p.fatura_aberta;
      box.innerHTML =
        "<p><strong>" + esc(p.plano_nome || p.plano_slug || "Explorar") + "</strong></p>" +
        "<p>Ciclo: " + esc(p.periodicidade || "—") + "</p>" +
        "<p>Forma: " + esc(p.forma_pagamento || "—") + "</p>" +
        "<p>Valor do plano: " + esc(p.valor_formatado || "—") + "</p>" +
        "<p>Recorrência: " + esc(status) + "</p>" +
        (p.dia_vencimento ? "<p>Dia de vencimento: " + esc(p.dia_vencimento) + "</p>" : "") +
        (aberta
          ? "<p>Fatura em aberto: " + esc(aberta.referencia) + " · boleto · " + esc(aberta.valor_formatado) + "</p>"
          : "");
      const btn = document.getElementById("fin_btnCancelarPlano");
      if (btn) btn.hidden = !p.pode_cancelar;
      const troca = document.getElementById("fin_btnTrocarForma");
      if (troca) troca.hidden = !(p.pode_trocar_proximas || p.pode_pagar_esta);
    } catch (e) {
      box.innerHTML = '<p class="Fin_Empty">' + esc(e.message || "Erro") + "</p>";
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    carregar(1);
    document.getElementById("fin_btnLogs")?.addEventListener("click", carregarLogs);
    function abrirAba(nome) {
      document.querySelectorAll("[data-fin-tab]").forEach(function (t) {
        t.classList.toggle("is-active", t.getAttribute("data-fin-tab") === nome);
      });
      document.querySelectorAll("[data-fin-panel]").forEach(function (p) {
        p.hidden = p.getAttribute("data-fin-panel") !== nome;
      });
      if (nome === "plano") carregarPlano();
    }
    document.querySelectorAll("[data-fin-tab]").forEach(function (tab) {
      tab.addEventListener("click", function () {
        abrirAba(tab.getAttribute("data-fin-tab"));
      });
    });
    if ((location.hash || "").replace("#", "") === "plano") abrirAba("plano");
    document.getElementById("fin_btnTrocarForma")?.addEventListener("click", trocarForma);
    document.getElementById("fin_btnCancelarPlano")?.addEventListener("click", async function () {
      const ok = window.Swal
        ? await Swal.fire({
            icon: "warning",
            title: "Cancelar o plano atual?",
            text: "Não haverá novas cobranças. O período já pago continua até o fim.",
            showCancelButton: true,
            confirmButtonText: "Cancelar plano",
            cancelButtonText: "Voltar",
            confirmButtonColor: "#021F81",
          })
        : { isConfirmed: confirm("Cancelar o plano atual?") };
      if (!ok || !ok.isConfirmed) return;
      const r = await fetch(cfg.apiCancelar, { method: "POST", headers: { Accept: "application/json" } });
      const j = await r.json();
      if (window.Swal) Swal.fire(j.success ? "Plano cancelado" : "Erro", j.message || "", j.success ? "success" : "error");
      if (j.success) carregarPlano();
    });
    document.addEventListener("click", fecharMenus);
    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape") fecharMenus();
    });
  });
})();
