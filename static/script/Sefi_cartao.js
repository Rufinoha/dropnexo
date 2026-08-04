/**
 * DropNexo Pay — checkout único (cartão / boleto / PIX em breve) + tokenizador Efi.
 *
 * EfiPay.CreditCard é Proxy: nunca retornar CreditCard de Promise/async.
 *
 *   const r = await DropNexoEfi.openCheckout({
 *     payeeCode, environment, valorCentavos, planoNome, titulo
 *   });
 *   // { forma, payment_token?, installments? } | null
 */
(function (global) {
  "use strict";

  const CDN =
    "https://cdn.jsdelivr.net/npm/payment-token-efi@3.2.1/dist/payment-token-efi-umd.min.js";

  const BRAND_LABEL = {
    visa: "Visa",
    mastercard: "Mastercard",
    amex: "Amex",
    elo: "Elo",
    hipercard: "Hipercard",
  };

  let scriptPromise = null;
  let envReady = "";
  let activeRoot = null;

  function digits(s) {
    return String(s || "").replace(/\D/g, "");
  }

  function efi() {
    return global.EfiPay.CreditCard;
  }

  function ensureScript() {
    if (global.EfiPay && global.EfiPay.CreditCard) return Promise.resolve(true);
    if (scriptPromise) return scriptPromise;
    scriptPromise = new Promise(function (resolve, reject) {
      const s = document.createElement("script");
      s.src = CDN;
      s.async = true;
      s.onload = function () {
        if (global.EfiPay && global.EfiPay.CreditCard) resolve(true);
        else {
          scriptPromise = null;
          reject(new Error("Biblioteca Efi não carregou."));
        }
      };
      s.onerror = function () {
        scriptPromise = null;
        reject(new Error("Falha ao carregar o tokenizador Efi."));
      };
      document.head.appendChild(s);
    });
    return scriptPromise;
  }

  function setEnv(environment) {
    const env = environment === "production" ? "production" : "sandbox";
    if (envReady !== env) {
      efi().setEnvironment(env);
      envReady = env;
    }
  }

  function runEfi(environment, fn) {
    return ensureScript().then(function () {
      setEnv(environment);
      return fn(efi());
    });
  }

  function formatCardNumber(raw) {
    const d = digits(raw).slice(0, 19);
    return d.replace(/(\d{4})(?=\d)/g, "$1 ").trim();
  }

  function formatExpiry(raw) {
    const d = digits(raw).slice(0, 4);
    if (d.length <= 2) return d;
    return d.slice(0, 2) + "/" + d.slice(2);
  }

  function parseExpiry(val) {
    const d = digits(val);
    if (d.length !== 4) return null;
    const mm = d.slice(0, 2);
    const yy = d.slice(2);
    const month = parseInt(mm, 10);
    if (month < 1 || month > 12) return null;
    return { month: mm, year: String(2000 + parseInt(yy, 10)) };
  }

  function money(centavos) {
    return ((centavos || 0) / 100).toLocaleString("pt-BR", {
      style: "currency",
      currency: "BRL",
    });
  }

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function destroyCheckout() {
    if (!activeRoot) return;
    activeRoot.classList.remove("is-open");
    const node = activeRoot;
    activeRoot = null;
    setTimeout(function () {
      if (node && node.parentNode) node.parentNode.removeChild(node);
    }, 280);
    document.body.style.overflow = "";
  }

  function buildMarkup(opts) {
    const plano = esc(opts.planoNome || "Plano DropNexo");
    const titulo = esc(opts.titulo || "Finalizar pagamento");
    const valor = money(opts.valorCentavos);
    return (
      '<div class="DnPay" id="dnpay_root" aria-hidden="true">' +
      '<div class="DnPay_Scrim" data-dnpay-close="1"></div>' +
      '<div class="DnPay_Panel" role="dialog" aria-modal="true" aria-labelledby="dnpay_title">' +
      '<button type="button" class="DnPay_Close" data-dnpay-close="1" aria-label="Fechar">×</button>' +
      '<aside class="DnPay_Aside">' +
      '<p class="DnPay_Brand">DropNexo Pay</p>' +
      '<p class="DnPay_Kicker" id="dnpay_title">' +
      titulo +
      "</p>" +
      '<h2 class="DnPay_Plan">' +
      plano +
      "</h2>" +
      '<div class="DnPay_Price"><strong id="dnpay_valor_final">' +
      esc(valor) +
      '</strong><span id="dnpay_valor_sufixo">/ mês</span></div>' +
      '<p class="DnPay_AsideNote" id="dnpay_aside_note">Escolha o ciclo, cupom (opcional) e a forma de pagamento.</p>' +
      '<p class="DnPay_AsideFoot" id="dnpay_aside_break">—</p>' +
      "</aside>" +
      '<main class="DnPay_Main">' +
      '<div class="DnPay_Body">' +
      '<div class="DnPay_Periodo" role="group" aria-label="Periodicidade">' +
      '<button type="button" class="DnPay_PeriodoBtn is-active" data-periodo="mensal">Mensal</button>' +
      '<button type="button" class="DnPay_PeriodoBtn" data-periodo="semestral">Semestral<small>−10%</small></button>' +
      '<button type="button" class="DnPay_PeriodoBtn" data-periodo="anual">Anual<small>−20%</small></button>' +
      "</div>" +
      '<div class="DnPay_Cupom">' +
      '<label class="DnPay_CupomField"><span>Cupom de desconto</span>' +
      '<div class="DnPay_CupomRow">' +
      '<input id="dnpay_cupom" maxlength="40" placeholder="Código do cupom" autocomplete="off" />' +
      '<button type="button" class="DnPay_CupomBtn" id="dnpay_cupom_aplicar">Aplicar</button>' +
      "</div></label>" +
      '<p class="DnPay_CupomMsg" id="dnpay_cupom_msg"></p>' +
      "</div>" +
      '<div class="DnPay_Tabs" role="tablist">' +
      '<button type="button" class="DnPay_Tab is-active" data-tab="cartao" role="tab">Cartão</button>' +
      '<button type="button" class="DnPay_Tab" data-tab="boleto" role="tab">Boleto</button>' +
      '<button type="button" class="DnPay_Tab is-soon" data-tab="pix" role="tab">PIX<small>em breve</small></button>' +
      "</div>" +
      '<section class="DnPay_Pane is-active" data-pane="cartao">' +
      '<p class="DnPay_PaneTitle">Cartão de crédito</p>' +
      '<p class="DnPay_PaneDesc">Tokenização na Efí — os dados do cartão não passam pelo DropNexo.</p>' +
      '<div class="EfiCard">' +
      '<div class="EfiCard_Visual" aria-hidden="true">' +
      '<div class="EfiCard_Chip"></div>' +
      '<div class="EfiCard_Brand" id="efi_brand_lbl">Cartão</div>' +
      '<div class="EfiCard_Number" id="efi_preview_num">•••• •••• •••• ••••</div>' +
      '<div class="EfiCard_Footer">' +
      '<span id="efi_preview_name">NOME NO CARTÃO</span>' +
      '<span id="efi_preview_exp">MM/AA</span>' +
      "</div></div>" +
      '<div class="EfiCard_Form">' +
      '<label class="EfiCard_Field EfiCard_Field--full"><span>Número do cartão</span>' +
      '<input id="efi_number" inputmode="numeric" autocomplete="cc-number" maxlength="23" placeholder="0000 0000 0000 0000" /></label>' +
      '<label class="EfiCard_Field EfiCard_Field--full"><span>Nome impresso</span>' +
      '<input id="efi_holder" autocomplete="cc-name" maxlength="80" placeholder="Como está no cartão" /></label>' +
      '<label class="EfiCard_Field"><span>Validade</span>' +
      '<input id="efi_exp" inputmode="numeric" autocomplete="cc-exp" maxlength="5" placeholder="MM/AA" /></label>' +
      '<label class="EfiCard_Field"><span>CVV</span>' +
      '<input id="efi_cvv" inputmode="numeric" autocomplete="cc-csc" maxlength="4" placeholder="•••" /></label>' +
      '<label class="EfiCard_Field EfiCard_Field--full"><span>CPF/CNPJ do titular</span>' +
      '<input id="efi_doc" inputmode="numeric" maxlength="18" placeholder="Somente números" /></label>' +
      '<label class="EfiCard_Field EfiCard_Field--full"><span>Parcelas</span>' +
      '<select id="efi_installments"><option value="1">1x sem juros</option></select></label>' +
      '<p class="EfiCard_Hint">Ambiente ' +
      esc(opts.environment === "production" ? "produção" : "homologação") +
      "</p>" +
      "</div></div></section>" +
      '<section class="DnPay_Pane" data-pane="boleto">' +
      '<p class="DnPay_PaneTitle">Boleto bancário</p>' +
      '<p class="DnPay_PaneDesc">Geramos a cobrança agora. Você recebe o boleto para pagar no banco ou app.</p>' +
      '<div class="DnPay_Boleto">' +
      '<div class="DnPay_Barcode" aria-hidden="true"></div>' +
      "<ul>" +
      "<li>O plano é liberado assim que o boleto é gerado.</li>" +
      "<li>Sem pagamento em até 7 dias úteis, a conta volta ao Explorar.</li>" +
      "<li>Acompanhe status e 2ª via em Financeiro.</li>" +
      "</ul></div></section>" +
      '<section class="DnPay_Pane" data-pane="pix">' +
      '<div class="DnPay_Soon">' +
      '<div class="DnPay_SoonMark">PIX</div>' +
      "<h4>Quase lá</h4>" +
      "<p>PIX estará disponível em breve neste mesmo checkout.<br>Por agora, use cartão ou boleto.</p>" +
      "</div></section>" +
      '<section class="DnPay_Pane" data-pane="cortesia">' +
      '<div class="DnPay_Cortesia">' +
      '<div class="DnPay_CortesiaMark" aria-hidden="true">0</div>' +
      "<h4>Plano por cortesia</h4>" +
      "<p>Cupom aplicado com 100% de desconto. Não há cobrança neste ciclo — confirme para ativar o plano.</p>" +
      "</div></section>" +
      "</div>" +
      '<p class="DnPay_Error" id="dnpay_error" aria-live="polite"></p>' +
      '<div class="DnPay_Actions">' +
      '<button type="button" class="DnPay_Btn DnPay_Btn--primary" id="dnpay_submit">Pagar com cartão</button>' +
      '<button type="button" class="DnPay_Btn DnPay_Btn--ghost" data-dnpay-close="1">Cancelar</button>' +
      '<p class="DnPay_Secure">Conexão segura · dados sensíveis só na Efí</p>' +
      "</div></main></div></div>"
    );
  }

  function wireCard(root, opts, getBrandRef) {
    const num = root.querySelector("#efi_number");
    const holder = root.querySelector("#efi_holder");
    const exp = root.querySelector("#efi_exp");
    const brandLbl = root.querySelector("#efi_brand_lbl");
    const prevNum = root.querySelector("#efi_preview_num");
    const prevName = root.querySelector("#efi_preview_name");
    const prevExp = root.querySelector("#efi_preview_exp");
    const sel = root.querySelector("#efi_installments");
    let brand = "";
    let brandTimer = null;

    function setBrand(b) {
      brand = String(b || "").toLowerCase();
      brandLbl.textContent = BRAND_LABEL[brand] || brand || "Cartão";
      brandLbl.dataset.brand = brand;
      getBrandRef.current = brand;
    }

    num.addEventListener("input", function () {
      num.value = formatCardNumber(num.value);
      const d = digits(num.value);
      prevNum.textContent = d
        ? formatCardNumber(d.padEnd(Math.max(d.length, 16), "•")).slice(0, 23)
        : "•••• •••• •••• ••••";
      clearTimeout(brandTimer);
      if (d.length < 6) {
        setBrand("");
        return;
      }
      brandTimer = setTimeout(function () {
        runEfi(opts.environment, function (api) {
          return api.setCardNumber(d).verifyCardBrand();
        })
          .then(setBrand)
          .catch(function () {
            setBrand("");
          });
      }, 280);
    });

    function valorParaParcelas() {
      if (typeof opts.getValorFinal === "function") {
        return parseInt(opts.getValorFinal(), 10) || 0;
      }
      return parseInt(opts.valorCentavos, 10) || 0;
    }

    function carregarParcelas() {
      const total = valorParaParcelas();
      if (!getBrandRef.current || !total || !opts.payeeCode) return;
      runEfi(opts.environment, function (api) {
        return api
          .setAccount(opts.payeeCode)
          .setBrand(getBrandRef.current)
          .setTotal(total)
          .getInstallments();
      })
        .then(function (res) {
          const list = (res && res.installments) || [];
          if (!list.length) {
            sel.innerHTML = '<option value="1">1x sem juros</option>';
            return;
          }
          sel.innerHTML = list
            .map(function (it) {
              const n = it.installment;
              const cur = it.currency || "";
              const juros = it.has_interest ? " com juros" : " sem juros";
              return '<option value="' + n + '">' + n + "x de " + cur + juros + "</option>";
            })
            .join("");
        })
        .catch(function () {
          sel.innerHTML = '<option value="1">1x sem juros</option>';
        });
    }

    num.addEventListener("blur", carregarParcelas);
    opts.refreshInstallments = carregarParcelas;

    holder.addEventListener("input", function () {
      prevName.textContent = (holder.value || "").trim().toUpperCase() || "NOME NO CARTÃO";
    });

    exp.addEventListener("input", function () {
      exp.value = formatExpiry(exp.value);
      prevExp.textContent = exp.value || "MM/AA";
    });
  }

  function tokenizeCard(root, opts, brandHint) {
    const number = digits(root.querySelector("#efi_number").value);
    const holder = (root.querySelector("#efi_holder").value || "").trim();
    const exp = parseExpiry(root.querySelector("#efi_exp").value);
    const cvv = digits(root.querySelector("#efi_cvv").value);
    const doc = digits(root.querySelector("#efi_doc").value);
    const installments =
      parseInt(root.querySelector("#efi_installments").value || "1", 10) || 1;

    if (!opts.payeeCode) {
      return Promise.reject(
        new Error("Falta o Identificador de Conta da Efi (EFI_PAYEE_CODE) no servidor.")
      );
    }
    if (number.length < 13 || number.length > 19) {
      return Promise.reject(new Error("Número do cartão inválido."));
    }
    if (!holder || holder.length < 3) {
      return Promise.reject(new Error("Informe o nome impresso no cartão."));
    }
    if (!exp) return Promise.reject(new Error("Validade inválida (use MM/AA)."));
    if (cvv.length < 3 || cvv.length > 4) {
      return Promise.reject(new Error("CVV inválido."));
    }
    if (doc && doc.length !== 11 && doc.length !== 14) {
      return Promise.reject(new Error("CPF/CNPJ do titular inválido."));
    }

    const brandStep = brandHint
      ? Promise.resolve(brandHint)
      : runEfi(opts.environment, function (api) {
          return api.setCardNumber(number).verifyCardBrand();
        }).then(function (b) {
          return String(b || "").toLowerCase();
        });

    return brandStep.then(function (brand) {
      if (!brand || brand === "undefined" || brand === "null") {
        throw new Error("Não foi possível identificar a bandeira do cartão.");
      }
      const cardData = {
        brand: brand,
        number: number,
        cvv: cvv,
        expirationMonth: exp.month,
        expirationYear: exp.year,
        holderName: holder,
        reuse: false,
      };
      if (doc) cardData.holderDocument = doc;
      return runEfi(opts.environment, function (api) {
        return api.setAccount(opts.payeeCode).setCreditCardData(cardData).getPaymentToken();
      }).then(function (tokenRes) {
        const payment_token = tokenRes && tokenRes.payment_token;
        if (!payment_token) throw new Error("Efi não retornou o token do cartão.");
        return {
          forma: "cartao",
          payment_token: payment_token,
          installments: installments,
          card_mask: (tokenRes && tokenRes.card_mask) || "",
          brand: brand,
        };
      });
    });
  }

  /**
   * @param {object} opts
   * @returns {Promise<{forma:string, payment_token?:string, installments?:number}|null>}
   */
  function openCheckout(opts) {
    opts = opts || {};
    destroyCheckout();

    return ensureScript()
      .catch(function () {
        // Boleto/cupom ainda funcionam sem o tokenizador
        return false;
      })
      .then(function (ok) {
        if (ok !== false) {
          try {
            setEnv(opts.environment);
          } catch (_) {
            /* ignore */
          }
        }

        const wrap = document.createElement("div");
        wrap.innerHTML = buildMarkup(opts);
        const root = wrap.firstElementChild;
        document.body.appendChild(root);
        document.body.style.overflow = "hidden";
        activeRoot = root;
        requestAnimationFrame(function () {
          root.classList.add("is-open");
          root.setAttribute("aria-hidden", "false");
        });

        const brandRef = { current: "" };
        const state = {
          periodo: "mensal",
          cupom: "",
          valorFinal: opts.valorCentavos || 0,
          preco: null,
        };
        const optsCard = Object.assign({}, opts);
        optsCard.getValorFinal = function () {
          return state.valorFinal;
        };
        wireCard(root, optsCard, brandRef);

        let tab = "cartao";
        const errEl = root.querySelector("#dnpay_error");
        const submitBtn = root.querySelector("#dnpay_submit");
        const cupomMsg = root.querySelector("#dnpay_cupom_msg");
        const labels = {
          cartao: "Pagar com cartão",
          boleto: "Gerar boleto",
          pix: "PIX em breve",
        };

        function syncCortesiaUI() {
          const isCortesia = state.valorFinal <= 0;
          root.classList.toggle("is-cortesia", isCortesia);
          if (isCortesia) {
            labels.cartao = "Aceitar cortesia";
            labels.boleto = "Aceitar cortesia";
            labels.pix = "Aceitar cortesia";
            submitBtn.textContent = "Aceitar cortesia";
            submitBtn.disabled = false;
            root.querySelectorAll(".DnPay_Pane").forEach(function (pane) {
              pane.classList.toggle(
                "is-active",
                pane.getAttribute("data-pane") === "cortesia"
              );
            });
            return;
          }
          labels.cartao = "Pagar com cartão";
          labels.boleto = "Gerar boleto";
          labels.pix = "PIX em breve";
          root.querySelectorAll(".DnPay_Pane").forEach(function (pane) {
            const name = pane.getAttribute("data-pane");
            pane.classList.toggle("is-active", name === tab);
          });
          submitBtn.textContent = labels[tab] || "Continuar";
          submitBtn.disabled = tab === "pix";
        }

        function aplicarPreco(preco) {
          state.preco = preco;
          state.valorFinal = int(preco.valor_final_centavos);
          const elV = root.querySelector("#dnpay_valor_final");
          const elS = root.querySelector("#dnpay_valor_sufixo");
          const elN = root.querySelector("#dnpay_aside_note");
          const elB = root.querySelector("#dnpay_aside_break");
          if (elV) elV.textContent = preco.valor_final_formatado || money(state.valorFinal);
          if (elS) {
            elS.textContent =
              preco.meses_cobertos > 1 ? " / " + preco.meses_cobertos + " meses" : "/ mês";
          }
          if (elN) {
            if (state.valorFinal <= 0) {
              elN.textContent = "Cupom de cortesia — sem cobrança neste ciclo.";
            } else {
              elN.textContent = preco.periodo_rotulo
                ? "Ciclo: " + preco.periodo_rotulo
                : "Escolha o ciclo e a forma de pagamento.";
            }
          }
          if (elB) {
            const parts = [];
            if (preco.desconto_periodo_centavos > 0) {
              parts.push("−" + money(preco.desconto_periodo_centavos) + " ciclo");
            }
            if (preco.desconto_cupom_centavos > 0) {
              parts.push("−" + money(preco.desconto_cupom_centavos) + " cupom");
            }
            elB.textContent = parts.length
              ? "De " + (preco.valor_cheio_formatado || "") + " · " + parts.join(" · ")
              : "Pagamento processado com segurança pela Efí.";
          }
          syncCortesiaUI();
          if (typeof optsCard.refreshInstallments === "function") {
            optsCard.refreshInstallments();
          }
        }

        function int(n) {
          return parseInt(n, 10) || 0;
        }

        function atualizarPreco() {
          if (!opts.apiPreview || !opts.planoSlug) {
            aplicarPreco({
              valor_final_centavos: opts.valorCentavos || 0,
              valor_final_formatado: money(opts.valorCentavos || 0),
              meses_cobertos: state.periodo === "anual" ? 12 : state.periodo === "semestral" ? 6 : 1,
              periodo_rotulo: state.periodo,
              desconto_periodo_centavos: 0,
              desconto_cupom_centavos: 0,
            });
            return Promise.resolve();
          }
          return fetch(opts.apiPreview, {
            method: "POST",
            headers: { "Content-Type": "application/json", Accept: "application/json" },
            body: JSON.stringify({
              plano_slug: opts.planoSlug,
              periodicidade: state.periodo,
              cupom: state.cupom || null,
            }),
          })
            .then(function (r) {
              return r.json();
            })
            .then(function (j) {
              if (!j.success) throw new Error(j.message || "Falha ao calcular preço");
              aplicarPreco(j);
              if (cupomMsg) {
                if (state.cupom && j.desconto_cupom_centavos > 0) {
                  cupomMsg.textContent = "Cupom aplicado: −" + money(j.desconto_cupom_centavos);
                  cupomMsg.className = "DnPay_CupomMsg is-ok";
                } else if (state.cupom) {
                  cupomMsg.textContent = "Cupom sem desconto neste cálculo.";
                  cupomMsg.className = "DnPay_CupomMsg";
                } else {
                  cupomMsg.textContent = "";
                  cupomMsg.className = "DnPay_CupomMsg";
                }
              }
            })
            .catch(function (e) {
              if (cupomMsg && state.cupom) {
                cupomMsg.textContent = e.message || "Cupom inválido";
                cupomMsg.className = "DnPay_CupomMsg is-err";
                state.cupom = "";
              }
              return fetch(opts.apiPreview, {
                method: "POST",
                headers: { "Content-Type": "application/json", Accept: "application/json" },
                body: JSON.stringify({
                  plano_slug: opts.planoSlug,
                  periodicidade: state.periodo,
                  cupom: null,
                }),
              })
                .then(function (r) {
                  return r.json();
                })
                .then(function (j) {
                  if (j.success) aplicarPreco(j);
                });
            });
        }

        function setTab(next) {
          if (state.valorFinal <= 0) return;
          tab = next;
          root.querySelectorAll(".DnPay_Tab").forEach(function (btn) {
            btn.classList.toggle("is-active", btn.getAttribute("data-tab") === next);
          });
          root.querySelectorAll(".DnPay_Pane").forEach(function (pane) {
            pane.classList.toggle("is-active", pane.getAttribute("data-pane") === next);
          });
          submitBtn.textContent = labels[next] || "Continuar";
          submitBtn.disabled = next === "pix";
          errEl.textContent = "";
          if (next === "cartao") {
            const n = root.querySelector("#efi_number");
            if (n) setTimeout(function () {
              n.focus();
            }, 40);
          }
        }

        root.querySelectorAll(".DnPay_Tab").forEach(function (btn) {
          btn.addEventListener("click", function () {
            setTab(btn.getAttribute("data-tab"));
          });
        });

        root.querySelectorAll(".DnPay_PeriodoBtn").forEach(function (btn) {
          btn.addEventListener("click", function () {
            state.periodo = btn.getAttribute("data-periodo") || "mensal";
            root.querySelectorAll(".DnPay_PeriodoBtn").forEach(function (b) {
              b.classList.toggle("is-active", b === btn);
            });
            atualizarPreco();
          });
        });

        root.querySelector("#dnpay_cupom_aplicar")?.addEventListener("click", function () {
          state.cupom = (root.querySelector("#dnpay_cupom")?.value || "").trim().toUpperCase();
          atualizarPreco();
        });
        root.querySelector("#dnpay_cupom")?.addEventListener("keydown", function (e) {
          if (e.key !== "Enter") return;
          e.preventDefault();
          root.querySelector("#dnpay_cupom_aplicar")?.click();
        });

        atualizarPreco();

        return new Promise(function (resolve) {
          let settled = false;
          function finish(value) {
            if (settled) return;
            settled = true;
            destroyCheckout();
            resolve(value);
          }

          root.querySelectorAll("[data-dnpay-close]").forEach(function (el) {
            el.addEventListener("click", function () {
              finish(null);
            });
          });

          function onKey(e) {
            if (e.key === "Escape") {
              document.removeEventListener("keydown", onKey);
              finish(null);
            }
          }
          document.addEventListener("keydown", onKey);

          function payloadBase(extra) {
            return Object.assign(
              {
                forma: "boleto",
                periodicidade: state.periodo,
                cupom: state.cupom || null,
                valor_final_centavos: state.valorFinal,
              },
              extra || {}
            );
          }

          submitBtn.addEventListener("click", function () {
            errEl.textContent = "";
            // Cortesia 100%: ativa sem meio de pagamento
            if (state.valorFinal <= 0) {
              finish(payloadBase({ forma: "boleto" }));
              return;
            }
            if (tab === "pix") return;
            // Boleto: sem tokenizar cartão
            if (tab === "boleto") {
              finish(payloadBase({ forma: "boleto" }));
              return;
            }
            submitBtn.disabled = true;
            submitBtn.textContent = "Validando cartão…";
            tokenizeCard(root, optsCard, brandRef.current)
              .then(function (result) {
                document.removeEventListener("keydown", onKey);
                finish(payloadBase(result));
              })
              .catch(function (err) {
                errEl.textContent =
                  (err && (err.error_description || err.error || err.message)) ||
                  "Falha ao tokenizar o cartão.";
                submitBtn.disabled = false;
                submitBtn.textContent = labels.cartao;
              });
          });
        });
      });
  }

  /** Compat: abre checkout já na aba cartão */
  function promptCartao(opts) {
    return openCheckout(opts).then(function (r) {
      if (!r) return null;
      if (r.forma !== "cartao") return null;
      return r;
    });
  }

  global.DropNexoEfi = {
    openCheckout: openCheckout,
    promptCartao: promptCartao,
  };
})(window);
