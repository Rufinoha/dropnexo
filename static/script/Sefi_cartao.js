/**
 * Sefi_cartao.js — formulário de cartão + tokenizador Efi Pay (payment-token-efi)
 *
 * Uso:
 *   const r = await DropNexoEfi.promptCartao({
 *     payeeCode, environment, valorCentavos, titulo
 *   });
 *   // r => { payment_token, installments, card_mask } | null
 */
(function (global) {
  "use strict";

  const CDN =
    "https://cdn.jsdelivr.net/npm/payment-token-efi/dist/payment-token-efi-umd.min.js";

  const BRAND_LABEL = {
    visa: "Visa",
    mastercard: "Mastercard",
    amex: "Amex",
    elo: "Elo",
    hipercard: "Hipercard",
  };

  let scriptPromise = null;

  function digits(s) {
    return String(s || "").replace(/\D/g, "");
  }

  function loadTokenizer() {
    if (global.EfiPay && global.EfiPay.CreditCard) {
      return Promise.resolve(global.EfiPay.CreditCard);
    }
    if (scriptPromise) return scriptPromise;
    scriptPromise = new Promise(function (resolve, reject) {
      const s = document.createElement("script");
      s.src = CDN;
      s.async = true;
      s.onload = function () {
        if (global.EfiPay && global.EfiPay.CreditCard) resolve(global.EfiPay.CreditCard);
        else reject(new Error("Biblioteca Efi não carregou."));
      };
      s.onerror = function () {
        scriptPromise = null;
        reject(new Error("Falha ao carregar o tokenizador Efi."));
      };
      document.head.appendChild(s);
    });
    return scriptPromise;
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
    const year = 2000 + parseInt(yy, 10);
    return { month: mm, year: String(year) };
  }

  function formHtml(opts) {
    const valor =
      opts.valorCentavos > 0
        ? (opts.valorCentavos / 100).toLocaleString("pt-BR", {
            style: "currency",
            currency: "BRL",
          })
        : "";
    return (
      '<div class="EfiCard">' +
      '<div class="EfiCard_Visual" aria-hidden="true">' +
      '<div class="EfiCard_Chip"></div>' +
      '<div class="EfiCard_Brand" id="efi_brand_lbl">Cartão</div>' +
      '<div class="EfiCard_Number" id="efi_preview_num">•••• •••• •••• ••••</div>' +
      '<div class="EfiCard_Footer">' +
      '<span id="efi_preview_name">NOME NO CARTÃO</span>' +
      '<span id="efi_preview_exp">MM/AA</span>' +
      "</div></div>" +
      (valor
        ? '<p class="EfiCard_Valor">Cobrança de <strong>' + valor + "</strong></p>"
        : "") +
      '<div class="EfiCard_Form">' +
      '<label class="EfiCard_Field EfiCard_Field--full">' +
      "<span>Número do cartão</span>" +
      '<input id="efi_number" inputmode="numeric" autocomplete="cc-number" maxlength="23" placeholder="0000 0000 0000 0000" />' +
      "</label>" +
      '<label class="EfiCard_Field EfiCard_Field--full">' +
      "<span>Nome impresso</span>" +
      '<input id="efi_holder" autocomplete="cc-name" maxlength="80" placeholder="Como está no cartão" />' +
      "</label>" +
      '<label class="EfiCard_Field">' +
      "<span>Validade</span>" +
      '<input id="efi_exp" inputmode="numeric" autocomplete="cc-exp" maxlength="5" placeholder="MM/AA" />' +
      "</label>" +
      '<label class="EfiCard_Field">' +
      "<span>CVV</span>" +
      '<input id="efi_cvv" inputmode="numeric" autocomplete="cc-csc" maxlength="4" placeholder="•••" />' +
      "</label>" +
      '<label class="EfiCard_Field EfiCard_Field--full">' +
      "<span>CPF/CNPJ do titular</span>" +
      '<input id="efi_doc" inputmode="numeric" maxlength="18" placeholder="Somente números" />' +
      "</label>" +
      '<label class="EfiCard_Field EfiCard_Field--full">' +
      "<span>Parcelas</span>" +
      '<select id="efi_installments"><option value="1">1x sem juros</option></select>' +
      "</label>" +
      '<p class="EfiCard_Hint" id="efi_hint">Os dados do cartão não passam pelo DropNexo — só o token seguro da Efi.</p>' +
      "</div></div>"
    );
  }

  function wirePreview(root) {
    const num = root.querySelector("#efi_number");
    const holder = root.querySelector("#efi_holder");
    const exp = root.querySelector("#efi_exp");
    const brandLbl = root.querySelector("#efi_brand_lbl");
    const prevNum = root.querySelector("#efi_preview_num");
    const prevName = root.querySelector("#efi_preview_name");
    const prevExp = root.querySelector("#efi_preview_exp");
    let brand = "";
    let brandTimer = null;

    num.addEventListener("input", function () {
      num.value = formatCardNumber(num.value);
      const d = digits(num.value);
      prevNum.textContent = d
        ? formatCardNumber(d.padEnd(Math.max(d.length, 16), "•")).slice(0, 23)
        : "•••• •••• •••• ••••";
      clearTimeout(brandTimer);
      if (d.length >= 6) {
        brandTimer = setTimeout(async function () {
          try {
            const CC = await loadTokenizer();
            const b = await CC.setCardNumber(d).verifyCardBrand();
            brand = (b || "").toLowerCase();
            brandLbl.textContent = BRAND_LABEL[brand] || brand || "Cartão";
            brandLbl.dataset.brand = brand;
          } catch {
            brand = "";
            brandLbl.textContent = "Cartão";
            brandLbl.dataset.brand = "";
          }
        }, 280);
      } else {
        brand = "";
        brandLbl.textContent = "Cartão";
        brandLbl.dataset.brand = "";
      }
    });

    holder.addEventListener("input", function () {
      const v = (holder.value || "").trim().toUpperCase();
      prevName.textContent = v || "NOME NO CARTÃO";
    });

    exp.addEventListener("input", function () {
      exp.value = formatExpiry(exp.value);
      prevExp.textContent = exp.value || "MM/AA";
    });

    return {
      getBrand: function () {
        return brand || (brandLbl.dataset.brand || "");
      },
    };
  }

  async function loadInstallments(opts, brand, selectEl) {
    if (!opts.valorCentavos || opts.valorCentavos < 100 || !brand || !opts.payeeCode) {
      selectEl.innerHTML = '<option value="1">1x sem juros</option>';
      return;
    }
    try {
      const CC = await loadTokenizer();
      const res = await CC.setAccount(opts.payeeCode)
        .setEnvironment(opts.environment || "sandbox")
        .setBrand(brand)
        .setTotal(opts.valorCentavos)
        .getInstallments();
      const list = (res && res.installments) || [];
      if (!list.length) {
        selectEl.innerHTML = '<option value="1">1x sem juros</option>';
        return;
      }
      selectEl.innerHTML = list
        .map(function (it) {
          const n = it.installment;
          const cur = it.currency || "";
          const juros = it.has_interest ? " com juros" : " sem juros";
          return (
            '<option value="' +
            n +
            '">' +
            n +
            "x de " +
            cur +
            juros +
            "</option>"
          );
        })
        .join("");
    } catch {
      selectEl.innerHTML = '<option value="1">1x sem juros</option>';
    }
  }

  /**
   * @param {object} opts
   * @param {string} opts.payeeCode
   * @param {string} [opts.environment]
   * @param {number} [opts.valorCentavos]
   * @param {string} [opts.titulo]
   * @returns {Promise<{payment_token:string, installments:number, card_mask:string}|null>}
   */
  async function promptCartao(opts) {
    opts = opts || {};
    if (!global.Swal) throw new Error("SweetAlert2 não disponível.");
    if (!opts.payeeCode) {
      await Swal.fire({
        icon: "warning",
        title: "Cartão indisponível",
        html:
          "Falta o <strong>Identificador de Conta</strong> da Efi no servidor " +
          "(EFI_PAYEE_CODE_DEV / EFI_PAYEE_CODE_PROD).<br>" +
          "Painel Efi → API → Introdução.",
        confirmButtonColor: "#021F81",
      });
      return null;
    }

    try {
      await loadTokenizer();
    } catch (e) {
      await Swal.fire({
        icon: "error",
        title: "Tokenizador",
        text: e.message || "Não foi possível carregar o JS da Efi.",
        confirmButtonColor: "#021F81",
      });
      return null;
    }

    let previewApi = null;
    const result = await Swal.fire({
      title: opts.titulo || "Cartão de crédito",
      html: formHtml(opts),
      width: 440,
      showCancelButton: true,
      confirmButtonText: "Pagar com cartão",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
      focusConfirm: false,
      customClass: { popup: "EfiCard_Swal" },
      didOpen: function () {
        const popup = Swal.getPopup();
        previewApi = wirePreview(popup);
        const num = popup.querySelector("#efi_number");
        const sel = popup.querySelector("#efi_installments");
        num.addEventListener("blur", async function () {
          const brand = previewApi.getBrand();
          if (brand) await loadInstallments(opts, brand, sel);
        });
        setTimeout(function () {
          num.focus();
        }, 50);
      },
      preConfirm: async function () {
        const popup = Swal.getPopup();
        const number = digits(popup.querySelector("#efi_number").value);
        const holder = (popup.querySelector("#efi_holder").value || "").trim();
        const exp = parseExpiry(popup.querySelector("#efi_exp").value);
        const cvv = digits(popup.querySelector("#efi_cvv").value);
        const doc = digits(popup.querySelector("#efi_doc").value);
        const installments = parseInt(popup.querySelector("#efi_installments").value || "1", 10) || 1;
        let brand = previewApi ? previewApi.getBrand() : "";

        if (number.length < 13 || number.length > 19) {
          Swal.showValidationMessage("Número do cartão inválido.");
          return false;
        }
        if (!holder || holder.length < 3) {
          Swal.showValidationMessage("Informe o nome impresso no cartão.");
          return false;
        }
        if (!exp) {
          Swal.showValidationMessage("Validade inválida (use MM/AA).");
          return false;
        }
        if (cvv.length < 3 || cvv.length > 4) {
          Swal.showValidationMessage("CVV inválido.");
          return false;
        }
        if (doc && doc.length !== 11 && doc.length !== 14) {
          Swal.showValidationMessage("CPF/CNPJ do titular inválido.");
          return false;
        }

        const confirmBtn = Swal.getConfirmButton();
        if (confirmBtn) {
          confirmBtn.disabled = true;
          confirmBtn.textContent = "Validando cartão…";
        }
        try {
          const CC = await loadTokenizer();
          if (!brand) {
            brand = ((await CC.setCardNumber(number).verifyCardBrand()) || "").toLowerCase();
          }
          if (!brand || brand === "undefined" || brand === "null") {
            Swal.showValidationMessage("Não foi possível identificar a bandeira do cartão.");
            return false;
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
          const tokenRes = await CC.setAccount(opts.payeeCode)
            .setEnvironment(opts.environment || "sandbox")
            .setCreditCardData(cardData)
            .getPaymentToken();

          const payment_token = tokenRes && tokenRes.payment_token;
          if (!payment_token) {
            Swal.showValidationMessage("Efi não retornou o token do cartão.");
            return false;
          }
          return {
            payment_token: payment_token,
            installments: installments,
            card_mask: (tokenRes && tokenRes.card_mask) || "",
            brand: brand,
          };
        } catch (err) {
          const msg =
            (err && (err.error_description || err.error || err.message)) ||
            "Falha ao tokenizar o cartão.";
          Swal.showValidationMessage(String(msg));
          return false;
        } finally {
          if (confirmBtn) {
            confirmBtn.disabled = false;
            confirmBtn.textContent = "Pagar com cartão";
          }
        }
      },
    });

    if (!result.isConfirmed) return null;
    return result.value || null;
  }

  global.DropNexoEfi = {
    loadTokenizer: loadTokenizer,
    promptCartao: promptCartao,
  };
})(window);
