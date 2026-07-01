console.log("Global Utils - Carregado!")

// ------------------------------
// CONFIGURAÇÕES
// ------------------------------
window.App = window.App || {};
window.Util = window.Util || {};
window.GlobalUtils = window.GlobalUtils || {};


// --------------------------------------------------------
// SweetAlert padrão para todo o sistema
// --------------------------------------------------------
(function initTechSwal() {
  const applyMixin = () => {
    if (!window.Swal || typeof window.Swal.mixin !== "function") return false;

    window.Swal = window.Swal.mixin({
      confirmButtonColor: '#c8a25e',
      cancelButtonColor:  '#ccc',
      confirmButtonText:  'OK',
      cancelButtonText:   'Cancelar',
      didOpen: () => {
        const c = document.querySelector(".swal2-container");
        if (c) c.style.zIndex = "20000";
      }
    });


    return true;
  };

  if (!applyMixin()) {
    document.addEventListener('DOMContentLoaded', applyMixin, { once: true });
    window.addEventListener('load', applyMixin, { once: true });
  }
})();

/** Feedback ao usuário — sempre SweetAlert2 quando disponível. */
window.Util.alertar = function (mensagem, tipo) {
  const msg = mensagem == null ? "" : String(mensagem);
  const map = {
    success: ["Sucesso", "success"],
    error: ["Erro", "error"],
    warning: ["Atenção", "warning"],
    info: ["Atenção", "info"],
  };
  const [titulo, icon] = map[tipo] || map.info;
  if (window.Swal && typeof window.Swal.fire === "function") {
    return window.Swal.fire(titulo, msg, icon);
  }
  window.alert(msg ? titulo + ": " + msg : titulo);
  return Promise.resolve();
};

/** Confirmação — retorna Promise<boolean>. */
window.Util.confirmar = function (titulo, texto) {
  if (window.Swal && typeof window.Swal.fire === "function") {
    return window.Swal.fire({
      title: titulo || "Confirmar?",
      text: texto || "",
      icon: "warning",
      showCancelButton: true,
    }).then((r) => !!r.isConfirmed);
  }
  const t = [titulo, texto].filter(Boolean).join("\n");
  return Promise.resolve(window.confirm(t || "Confirmar?"));
};


// --------------------------------------------------------
// Carregador de scripts via CDN (com cache simples)
// --------------------------------------------------------
// Inicialização global do Lucide (compatível com CSP, sem inline)
GlobalUtils.refreshIcons = function () {
  if (window.lucide && typeof window.lucide.createIcons === "function") {
    window.lucide.createIcons();
  }
};

// Desenhar ícones assim que o DOM estiver pronto (sem inline)
if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", GlobalUtils.refreshIcons, { once: true });
} else {
  GlobalUtils.refreshIcons();
}







/******************** MODAL - Usado para abrir janelas de Apoio via MODAL *************************** */
GlobalUtils.abrirJanelaApoioModal = function ({
  rota,
  titulo = "Apoio",
  largura = 1000,
  altura = 600,   // número (px) OU "auto"
  nivel = 1,
  modulo = null,   // ✅ NOVO (opcional)
  id = null
}) {
  GlobalUtils.fecharJanelaApoio(nivel, true);

  const overlayId = `modalApoioOverlay_nivel${nivel}`;
  const janelaId  = `modalApoioJanela_nivel${nivel}`;

  if (document.getElementById(overlayId)) {
    console.warn(`Já existe um modal no nível ${nivel}.`);
    return;
  }

  // Overlay
  const overlay = document.createElement("div");
  overlay.id = overlayId;
  overlay.style.cssText = `
    position: fixed; inset: 0;
    background: rgba(0,0,0,0.4);
    z-index: ${9998 + nivel * 2};
    display: flex; align-items: center; justify-content: center;
  `;

  // Modal
  const modal = document.createElement("div");
  modal.id = janelaId;

  const isAuto = String(altura).toLowerCase() === "auto";
  const cssW = `min(${Number(largura) || 1000}px, 96vw)`;
  const cssH = isAuto ? `92vh` : `min(${Number(altura) || 600}px, 92vh)`;

  modal.style.cssText = `
    background: #ffffff;
    border-radius: 10px;
    overflow: hidden;
    width: ${cssW};
    height: ${cssH};
    position: relative;
    display: flex;
    flex-direction: column;
    box-shadow: 0 0 20px rgba(0,0,0,0.4);
  `;

  // ✅ HEADER DO MODAL PAI (é aqui que vai aparecer o titulo)
  const header = document.createElement("div");
  header.style.cssText = `
    background: linear-gradient(135deg, #021f81 0%, #2c6bf3 100%); color: #fff;
    padding: 12px 18px;
    font-weight: 700;
    display: flex; align-items: center; justify-content: space-between;
    font-size: 17px;
    flex: 0 0 auto;
    letter-spacing: 0.01em;
  `;
  header.innerHTML = `
    <span class="apoio-modal-titulo"></span>
    <button type="button" data-fechar-nivel="${nivel}"
      style="background:none;border:none;color:white;font-size:20px;cursor:pointer">✖</button>
  `;
  header.querySelector(".apoio-modal-titulo").textContent = String(titulo || "Apoio");

  // Iframe
  const iframe = document.createElement("iframe");
  iframe.src = rota;
  iframe.style.cssText = `
    border: none;
    flex: 1 1 auto;
    display: block;
    width: 100%;
    height: 100%;
    background: transparent;
  `;
  iframe.setAttribute("data-apoio", "iframe");

  // Monta
  modal.appendChild(header);
  modal.appendChild(iframe);
  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  // Fechar no X
  header.querySelector("button").onclick = () => {
    GlobalUtils.fecharJanelaApoio(nivel);
  };

  // Fechar clicando fora
  overlay.addEventListener("mousedown", (ev) => {
    if (ev.target === overlay) GlobalUtils.fecharJanelaApoio(nivel);
  });

  // Fechar no ESC
  const escHandler = (ev) => {
    if (ev.key !== "Escape") return;
    if (document.getElementById(overlayId)) GlobalUtils.fecharJanelaApoio(nivel);
  };
  document.addEventListener("keydown", escHandler);

  // Remove listener ESC quando fechar
  const observerClose = new MutationObserver(() => {
    if (!document.getElementById(overlayId)) {
      try { document.removeEventListener("keydown", escHandler); } catch {}
      try { observerClose.disconnect(); } catch {}
    }
  });
  observerClose.observe(document.body, { childList: true, subtree: true });

  // ✅ Ajustes dentro do iframe: transparente + esconde header interno (pra não duplicar)
  function ajustarIframeInterno() {
    try {
      const doc = iframe.contentDocument || iframe.contentWindow?.document;
      if (!doc) return;

      doc.documentElement.style.background = "transparent";
      doc.body.style.background = "transparent";
      doc.body.style.margin = "0";

      // Esconde o header interno da tela (título fica só no modal pai — padrão BARACAT)
      const hd = doc.querySelector(".imp-header, .ch-apoio-header, .Cl_Header");
      if (hd) hd.style.display = "none";

      // Também remove o backdrop interno se existir (caso alguém tenha deixado modal interno)
      const bd = doc.querySelector(".imp-backdrop");
      if (bd) bd.style.display = "none";

      // Garantir que o container principal não crie "modal dentro do modal"
      const root = doc.querySelector("#impModal");
      if (root) {
        root.style.height = "100%";
        root.style.minHeight = "100vh";
        root.style.display = "flex";
        root.style.flexDirection = "column";
      }

      const dialog = doc.querySelector("#impModal .imp-dialog");
      if (dialog) {
        dialog.style.flex = "1 1 auto";
        dialog.style.height = "100%";
        dialog.style.display = "flex";
        dialog.style.flexDirection = "column";
      }

      const body = doc.querySelector("#impModal .imp-body");
      if (body) {
        body.style.flex = "1 1 auto";
        body.style.minHeight = "0";
        body.style.overflow = "auto";
        body.style.display = "flex";
        body.style.flexDirection = "column";
      }
    } catch {
      // se virar cross-origin no futuro, não dá pra mexer no DOM interno
    }
  }

  iframe.onload = () => {
    // aplica em ondas (DOM do iframe monta em fases)
    ajustarIframeInterno();
    setTimeout(ajustarIframeInterno, 0);
    setTimeout(ajustarIframeInterno, 80);
    setTimeout(ajustarIframeInterno, 250);

    // mantém protocolo (caso você ainda use do lado do apoio)
    setTimeout(() => {
      try {
        iframe.contentWindow.postMessage(
          {
            grupo: "apoioPronto",
            nivel,
            titulo,
            id,
            modulo: (modulo == null || String(modulo).trim() === "" ? null : String(modulo).trim())
          },
          "*"
        );

      } catch {}
    }, 120);
  };
};



/******************** MODAL - Usado no apoio para Receber informações da janela principal *************************** */
GlobalUtils.receberDadosApoio = function (callback) {
  window.addEventListener("message", (event) => {
    if (!event.data?.grupo) {
      console.warn("⚠️ Mensagem ignorada: sem 'grupo' definido.");
      return;
    }

    // Só a abertura do modal envia contexto (id/nivel). Outros grupos (ex.: atualizarTabela)
    // são tratados por listeners locais com whitelist — não devem resetar o apoio.
    if (event.data.grupo !== "apoioPronto") return;

    const nivel = event.data.nivel !== undefined ? event.data.nivel : 1;
    window.__nivelModal__ = nivel;

    // NOVO: deixa o módulo disponível para qualquer JS da tela (apoio)
    // - se vier vazio, vira null e não quebra
    const modulo = (event.data.modulo == null || String(event.data.modulo).trim() === "")
      ? null
      : String(event.data.modulo).trim();

    // contexto padrão do apoio (pode crescer no futuro)
    window.__apoioContexto__ = window.__apoioContexto__ || {};
    window.__apoioContexto__.nivel  = nivel;
    window.__apoioContexto__.grupo  = event.data.grupo;
    window.__apoioContexto__.modulo = modulo;

    // backward compatible: callback(null, nivel)
    // se seu callback quiser, ele pode ler window.__apoioContexto__.modulo
    const id = event.data.id !== undefined ? event.data.id : null;

    window.__apoioContexto__.id = id;

    callback(id, nivel);

  });
}; 


/*************************** MODAL Função padrão para FECHAR o apoio  ***********************************/
GlobalUtils.fecharJanelaApoio = function (nivel, quiet = false) {
  const fecharEm = (doc, alvoNivel) => {
    if (!doc) return false;

    const overlays = Array.from(doc.querySelectorAll('[id^="modalApoioOverlay_nivel"]'));
    if (!overlays.length) return false;

    let alvos = [];
    if (alvoNivel == null) {
      // fecha o de maior nível (topo)
      alvos = overlays.sort((a, b) => {
        const na = Number(a.id.replace(/\D/g, "")) || 0;
        const nb = Number(b.id.replace(/\D/g, "")) || 0;
        return nb - na;
      }).slice(0, 1);
    } else {
      alvos = overlays.filter(el => el.id === `modalApoioOverlay_nivel${alvoNivel}`);
    }

    alvos.forEach((overlay) => {
      const iframe = overlay.querySelector('iframe[data-apoio="iframe"]');
      try {
        iframe?.contentWindow?.postMessage({ grupo: "__dispose__" }, "*");
        if (iframe) iframe.src = "about:blank";
      } catch {}
      overlay.remove();
    });

    return !!alvos.length;
  };

  const fechouAqui   = fecharEm(document, nivel);
  const fechouParent = fecharEm(window.parent?.document, nivel);

  if (!fechouAqui && !fechouParent) {
    if (!quiet) {
      console.warn(`⚠️ Nenhum modal encontrado no nível ${nivel ?? "(topo)"}`);
    }
  }
};




// --------------------------------------------------------
// DOCUMENTAÇÕES (CEP, CPF, CNPJ) — versão robusta e simples
// --------------------------------------------------------

// Helpers internos (simples)
window.Util = window.Util || {};

function _onlyDigits(v) {
  return String(v || "").replace(/\D/g, "");
}

function _getInputEl(inputOrSelector) {
  if (!inputOrSelector) return null;
  if (typeof inputOrSelector === "string") {
    return document.querySelector(inputOrSelector);
  }
  return inputOrSelector; // assume elemento
}

// CPF
// --------------------------------------------------------
window.Util.limparMascaraCPF = function (cpf) {
  return _onlyDigits(cpf);
};

window.Util.formatarCPF = function (cpf) {
  const v = _onlyDigits(cpf);
  if (!v) return "";
  // formata progressivo (não exige 11)
  if (v.length <= 3) return v;
  if (v.length <= 6) return v.replace(/(\d{3})(\d+)/, "$1.$2");
  if (v.length <= 9) return v.replace(/(\d{3})(\d{3})(\d+)/, "$1.$2.$3");
  return v.slice(0, 11).replace(/(\d{3})(\d{3})(\d{3})(\d{2})/, "$1.$2.$3-$4");
};

window.Util.validarCPF = function (cpf) {
  const v = _onlyDigits(cpf);
  if (v.length !== 11) return false;
  if (/^(\d)\1+$/.test(v)) return false;

  let soma = 0;
  for (let i = 0; i < 9; i++) soma += Number(v.charAt(i)) * (10 - i);
  let d1 = (soma * 10) % 11;
  if (d1 === 10) d1 = 0;
  if (d1 !== Number(v.charAt(9))) return false;

  soma = 0;
  for (let i = 0; i < 10; i++) soma += Number(v.charAt(i)) * (11 - i);
  let d2 = (soma * 10) % 11;
  if (d2 === 10) d2 = 0;

  return d2 === Number(v.charAt(10));
};

// CNPJ
// --------------------------------------------------------
window.Util.limparMascaraCNPJ = function (texto) {
  return _onlyDigits(texto);
};

window.Util.formatarCNPJ = function (texto) {
  const v = _onlyDigits(texto);
  if (!v) return "";
  // progressivo (não exige 14)
  if (v.length <= 2) return v;
  if (v.length <= 5) return v.replace(/(\d{2})(\d+)/, "$1.$2");
  if (v.length <= 8) return v.replace(/(\d{2})(\d{3})(\d+)/, "$1.$2.$3");
  if (v.length <= 12) return v.replace(/(\d{2})(\d{3})(\d{3})(\d+)/, "$1.$2.$3/$4");
  return v.slice(0, 14).replace(/(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})/, "$1.$2.$3/$4-$5");
};

window.Util.validarCNPJ = function (cnpj) {
  const v = _onlyDigits(cnpj);
  if (v.length !== 14) return false;
  if (/^(\d)\1{13}$/.test(v)) return false;

  const calc = (nums) => {
    let n = 0;
    let y = nums.length - 7;
    for (let i = 0; i < nums.length; i++) {
      n += nums[i] * y--;
      if (y < 2) y = 9;
    }
    return (n % 11) < 2 ? 0 : 11 - (n % 11);
  };

  const nums = v.substring(0, 12).split("").map(Number);
  const d1 = calc(nums);
  const d2 = calc([...nums, d1]);

  return d1 === Number(v.charAt(12)) && d2 === Number(v.charAt(13));
};

window.Util.aplicarMascaraCNPJ = function (inputOrSelector) {
  const input = _getInputEl(inputOrSelector);
  if (!input) return;

  if (input.dataset.maskCnpj === "1") return; // evita listener duplicado
  input.dataset.maskCnpj = "1";

  input.addEventListener("input", () => {
    input.value = window.Util.formatarCNPJ(input.value);
  });
};

// CEP
// --------------------------------------------------------
window.Util.limparMascaraCEP = function (texto) {
  return _onlyDigits(texto);
};

window.Util.formatarCEP = function (texto) {
  const v = _onlyDigits(texto);
  if (!v) return "";
  if (v.length <= 5) return v;
  return `${v.substring(0, 5)}-${v.substring(5, 8)}`;
};

window.Util.validarCEP = function (texto) {
  const v = _onlyDigits(texto);
  return v.length === 8;
};

window.Util.aplicarMascaraCEP = function (inputOrSelector) {
  const input = _getInputEl(inputOrSelector);
  if (!input) return;

  if (input.dataset.maskCep === "1") return; // evita listener duplicado
  input.dataset.maskCep = "1";

  input.addEventListener("input", () => {
    input.value = window.Util.formatarCEP(input.value);
  });
};



// --------------------------------------------------------
// Telefone
// --------------------------------------------------------
window.Util = window.Util || {};

function _onlyDigits(v) {
  return String(v || "").replace(/\D/g, "");
}

function _getInputEl(inputOrSelector) {
  if (!inputOrSelector) return null;
  if (typeof inputOrSelector === "string") {
    return document.querySelector(inputOrSelector);
  }
  return inputOrSelector;
}

window.Util.limparMascaraTelefone = function (texto) {
  return _onlyDigits(texto);
};

window.Util.formatarTelefone = function (texto) {
  const v = _onlyDigits(texto);
  if (!v) return "";

  // progressivo
  if (v.length <= 2) return `(${v}`;
  if (v.length <= 6) return `(${v.slice(0,2)}) ${v.slice(2)}`;
  if (v.length <= 10) {
    return `(${v.slice(0,2)}) ${v.slice(2,6)}-${v.slice(6)}`;
  }
  // 11 dígitos (celular)
  return `(${v.slice(0,2)}) ${v.slice(2,7)}-${v.slice(7,11)}`;
};

window.Util.validarTelefone = function (texto) {
  const v = _onlyDigits(texto);
  return v.length === 10 || v.length === 11;
};

window.Util.aplicarMascaraTelefone = function (inputOrSelector) {
  const input = _getInputEl(inputOrSelector);
  if (!input) return;

  // evita múltiplos listeners
  if (input.dataset.maskTelefone === "1") return;
  input.dataset.maskTelefone = "1";

  input.addEventListener("input", () => {
    input.value = window.Util.formatarTelefone(input.value);
  });
};







// --------------------------------------------------------
// DATAS E HORAS (data e hora) — versão TOP (simples, robusta, sem redundância)
// --------------------------------------------------------
(function () {
  const pad2 = (n) => String(n).padStart(2, "0");

  // ✅ Parser único e previsível
  // Aceita:
  // - Date
  // - "HH:MM" ou "HH:MM:SS"
  // - "YYYY-MM-DD"
  // - "YYYY-MM-DDTHH:MM..." (ISO datetime)
  // - "DD/MM/YYYY"
  // - "DD/MM/YYYY HH:MM"
  // - timestamp number (ms) ou string numérica
  function parseDate(valor) {
    try {
      if (valor == null || valor === "") return null;
      if (valor instanceof Date) return isNaN(valor.getTime()) ? null : valor;

      // number: timestamp (ms) ou excel serial? (não misturar aqui)
      if (typeof valor === "number") {
        const d = new Date(valor);
        return isNaN(d.getTime()) ? null : d;
      }

      const str = String(valor).trim();
      if (!str) return null;

      // string numérica → timestamp ms
      if (/^\d+$/.test(str)) {
        const n = Number(str);
        const d = new Date(n);
        return isNaN(d.getTime()) ? null : d;
      }

      // Hora pura "H:MM" / "HH:MM" / com segundos
      if (/^\d{1,2}:\d{2}(:\d{2})?$/.test(str)) {
        const hoje = new Date();
        const [h, m, s] = str.split(":");
        hoje.setHours(Number(h), Number(m), Number(s || 0), 0);
        return isNaN(hoje.getTime()) ? null : hoje;
      }

      // ISO datetime (mantém nativo)
      if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(str)) {
        const d = new Date(str);
        return isNaN(d.getTime()) ? null : d;
      }

      // ISO date "YYYY-MM-DD" (cria data local, sem risco de timezone do Date.parse)
      if (/^\d{4}-\d{2}-\d{2}$/.test(str)) {
        const [y, mo, da] = str.split("-").map(Number);
        const d = new Date(y, mo - 1, da);
        return isNaN(d.getTime()) ? null : d;
      }

      // BR completo "DD/MM/YYYY HH:MM"
      if (/^\d{2}\/\d{2}\/\d{4}\s+\d{2}:\d{2}$/.test(str)) {
        const [dataPart, horaPart] = str.split(/\s+/);
        const [da, mo, y] = dataPart.split("/").map(Number);
        const [h, mi] = horaPart.split(":").map(Number);
        const d = new Date(y, mo - 1, da, h, mi, 0, 0);
        return isNaN(d.getTime()) ? null : d;
      }

      // BR "DD/MM/YYYY"
      if (/^\d{2}\/\d{2}\/\d{4}$/.test(str)) {
        const [da, mo, y] = str.split("/").map(Number);
        const d = new Date(y, mo - 1, da);
        return isNaN(d.getTime()) ? null : d;
      }

      // fallback (aceita formatos adicionais)
      const tentativa = new Date(str);
      return isNaN(tentativa.getTime()) ? null : tentativa;
    } catch {
      return null;
    }
  }

  // Expor como API interna (mantém seu nome para compatibilidade)
  window.Util._parseData = parseDate;

  // ----------------------------------------
  // FORMATADORES (todos reaproveitam parseDate)
  // ----------------------------------------
  window.Util.paraDataBR = function (valor) { // DD/MM/AAAA
    const d = parseDate(valor);
    if (!d) return "";
    return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()}`;
  };

  window.Util.paraDataISO = function (valor) { // AAAA-MM-DD
    if (valor == null || valor === "") return "";

    // ✅ se já vier ISO datetime, corta (performance + previsibilidade)
    if (typeof valor === "string" && /^\d{4}-\d{2}-\d{2}T/.test(valor)) {
      return valor.slice(0, 10);
    }

    // ✅ se já vier ISO date, devolve (sem mexer)
    if (typeof valor === "string" && /^\d{4}-\d{2}-\d{2}$/.test(valor)) {
      return valor;
    }

    // ✅ se vier BR, converte sem Date (evita timezone e é mais rápido)
    if (typeof valor === "string" && /^\d{2}\/\d{2}\/\d{4}$/.test(valor.trim())) {
      const [dd, mm, aaaa] = valor.trim().split("/");
      return `${aaaa}-${mm}-${dd}`;
    }

    const d = parseDate(valor);
    if (!d) return "";
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  };

  window.Util.paraDataBR_completo = function (valor) { // DD/MM/AAAA HH:MM
    const d = parseDate(valor);
    if (!d) return "";
    return `${pad2(d.getDate())}/${pad2(d.getMonth() + 1)}/${d.getFullYear()} ${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  };

  window.Util.paraHoraBR = function (valor) { // HH:MM
    const d = parseDate(valor);
    if (!d) return "";
    return `${pad2(d.getHours())}:${pad2(d.getMinutes())}`;
  };

  window.Util.paraHoraISO = function (valor) { // HH:MM:SS
    const d = parseDate(valor);
    if (!d) return "";
    return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`;
  };

  // ----------------------------------------
  // EXCEL (mantido, mas com conversão mais segura)
  // ----------------------------------------
  window.Util.converterExcelParaData = function (excelDate) {
    const n = Number(excelDate);
    if (!Number.isFinite(n)) return "";

    // Excel serial: dias desde 1899-12-30 (compatível com seu cálculo atual)
    const base = new Date(1899, 11, 30);
    base.setDate(base.getDate() + Math.floor(n));

    // mantém pt-BR por padrão (simples)
    return `${pad2(base.getDate())}/${pad2(base.getMonth() + 1)}/${base.getFullYear()}`;
  };

  window.Util.converterExcelParaHora = function (excelDate) {
    const n = Number(excelDate);
    if (!Number.isFinite(n)) return "";

    const frac = ((n % 1) + 1) % 1; // garante 0..1 mesmo se vier negativo
    const totalSegundos = Math.round(frac * 24 * 60 * 60);

    const horas = Math.floor(totalSegundos / 3600) % 24;
    const minutos = Math.floor((totalSegundos % 3600) / 60);

    return `${pad2(horas)}:${pad2(minutos)}`;
  };

  window.Util.hojeISO = function () { // AAAA-MM-DD
    const d = new Date();
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  };
})();







/* ===================================================================
 * FORMATAÇÃO E PARSE DE VALORES NUMÉRICOS (PADRÃO BARACAT)
 * ===================================================================
 * - Todas as funções trabalham com padrão pt-BR
 * - Separador de milhar: .
 * - Separador decimal: ,
 * - Retornam string para UI ou number para backend
 * =================================================================== */
/**
 * Formata valor numérico para pt-BR
 * @param {number|string} valor
 * @param {Object} opcoes
 * @param {number} opcoes.decimais - número de casas decimais
 * @param {boolean} opcoes.truncar - se true, não arredonda
 * @returns {string}
 */
GlobalUtils.formatarValorBR = function (valor, opcoes) {
  if (valor === null || valor === undefined || valor === "") return "";

  const num = Number(valor);
  if (!Number.isFinite(num)) return "";

  const cfg = Object.assign(
    {
      decimais: 2,
      truncar: false
    },
    opcoes || {}
  );

  let v = num;

  if (cfg.truncar) {
    const fator = Math.pow(10, cfg.decimais);
    v = Math.trunc(v * fator) / fator;
  }

  return new Intl.NumberFormat("pt-BR", {
    minimumFractionDigits: cfg.decimais,
    maximumFractionDigits: cfg.decimais
  }).format(v);
};

/**
 * Remove formatação pt-BR e converte para number
 * @param {string|number} texto
 * @returns {number|null}
 */
GlobalUtils.parseValorBR = function (texto) {
  if (texto === null || texto === undefined || texto === "") return null;

  if (typeof texto === "number") {
    return Number.isFinite(texto) ? texto : null;
  }

  const limpo = String(texto)
    .replace(/\./g, "")
    .replace(",", ".");

  const num = Number(limpo);
  return Number.isFinite(num) ? num : null;
};

/* FUNÇÕES DE ATALHO (SEMÂNTICAS)
 * =================================================================== */

/**
 * Monetário padrão (2 casas, arredonda)
 */
GlobalUtils.formatarMoeda = function (valor) {
  return GlobalUtils.formatarValorBR(valor, { decimais: 2, truncar: false });
};

/**
 * Monetário truncado (2 casas, SEM arredondar)
 */
GlobalUtils.formatarMoedaTruncada = function (valor) {
  return GlobalUtils.formatarValorBR(valor, { decimais: 2, truncar: true });
};

/**
 * Valor inteiro (sem casas decimais)
 */
GlobalUtils.formatarInteiro = function (valor) {
  return GlobalUtils.formatarValorBR(valor, { decimais: 0 });
};

/**
 * Quantidade (4 casas decimais, comum em volume/estoque)
 */
GlobalUtils.formatarQuantidade = function (valor) {
  return GlobalUtils.formatarValorBR(valor, { decimais: 4 });
};







// --------------------------------------------------------------------------
// Util.localstorage(campo, padrao)
// Camada de leitura padronizada do localStorage (BARACAT)
// --------------------------------------------------------------------------
window.Util.localstorage = function (campo, padrao = null) {

  const MAPA = {

    // ======================================================
    // USUÁRIO (usuarioLogado) — fase 1
    // ======================================================
    "id_usuario":              { chave: "usuarioLogado", path: "id_usuario", toInt: true },
    "nome":                    { chave: "usuarioLogado", path: "nome" },
    "imagem":                  { chave: "usuarioLogado", path: "imagem" },
    "grupo":                   { chave: "usuarioLogado", path: "grupo" },
    "id_ultima_novidade_lida": { chave: "usuarioLogado", path: "id_ultima_novidade_lida", toInt: true },

    // ======================================================
    // pack (packAtivo) — fase 2 (OBRIGATÓRIO p/ negócio)
    // ======================================================
    "id_pack":              { chave: "packAtivo", path: "id_pack", toInt: true },
    "pack_nome":            { chave: "packAtivo", path: "nome" },
    "pack_responsavel":     { chave: "packAtivo", path: "responsavel" },
    "pack_codigo":          { chave: "packAtivo", path: "codigo_publico" },
    "pack_imagem":          { chave: "packAtivo", path: "imagem" },

    // ======================================================
    // META
    // ======================================================
    "horaLogin":               { chave: "horaLogin", path: null }
  };

  const definicao = MAPA[campo];
  if (!definicao) return padrao;

  // valor simples
  if (definicao.path === null) {
    const bruto = localStorage.getItem(definicao.chave);
    return bruto !== null ? bruto : padrao;
  }

  // valor JSON
  let objeto;
  try {
    objeto = JSON.parse(localStorage.getItem(definicao.chave) || "{}");
  } catch {
    objeto = {};
  }

  let valor = objeto[definicao.path];

  if (definicao.toInt) {
    const n = Number(valor);
    return Number.isInteger(n) ? n : padrao;
  }

  return (valor !== undefined && valor !== null) ? valor : padrao;
};




// ============================ COMBOBOX PADRÃO BARACAT ============================
// Debug global opcional
window.__DEBUG_COMBOBUSCA = window.__DEBUG_COMBOBUSCA ?? false;
const _cbLog = (...args) => { if (window.__DEBUG_COMBOBUSCA) console.log("ComboBusca:", ...args); };

// Namespaces globais
window.GlobalUtils = window.GlobalUtils || {};
window.Util = window.Util || {};

// === [GlobalUtils.ComboboxBusca] MÓDULO GLOBAL ===
(function () {
  const KEY = { UP: 38, DOWN: 40, ENTER: 13, ESC: 27, TAB: 9 };

  const DEFAULTS = {
    // Seletores (obrigatórios)
    wrapSel: null,
    displaySel: null,
    panelSel: null,
    searchSel: null,
    listSel: null,
    statusSel: null,

    // Comportamento
    minChars: 3,
    limite: 20,
    debounceMs: 280,
    cache: true,

    // Linhas exibidas (até 5)
    linhas: [],

    // Valor inicial (opcional)
    valorInicial: null, // { id, label }

    // Hooks
    onSelect: null,
    onOpen: null,
    onClose: null,

    // Busca
    fetchFn: null,       // async (termo, {signal}) => ({itens:[...]}) OU {itens:[...], msg}
    rota: null,          // alternativa: POST JSON
    queryBuilder: null,  // (termo) => payload

    // Hidden para guardar item.id
    campoOcultoId: null,

    // Textos
    placeholderBuscar: null, // se null, vira "Digite X caracteres ou mais..."
    msgMinChars: null        // se null, vira "Digite X+ para pesquisar"
  };

  function debounce(fn, ms) {
    let t;
    return function (...args) {
      clearTimeout(t);
      t = setTimeout(() => fn.apply(this, args), ms);
    };
  }

  function highlight(texto, termo) {
    if (!termo) return String(texto);
    try {
      const rx = new RegExp(`(${String(termo).replace(/[.*+?^${}()|[\\]\\\\]/g, '\\$&')})`, "ig");
      return String(texto).replace(rx, "<mark>$1</mark>");
    } catch {
      return String(texto);
    }
  }

  function renderItemHTML(item, termo, linhas) {
    const partes = [];

    for (let i = 0; i < Math.min(linhas.length, 5); i++) {
      const def = linhas[i];
      if (!def || !def.campo) continue;

      let valor = item?.[def.campo];
      if (valor === undefined || valor === null || valor === "") continue;

      if (typeof def.formatter === "function") {
        try { valor = def.formatter(valor, item); } catch {}
      }

      const rotuloHTML = def.rotulo ? `<span class="Cl_Item__rotulo">${String(def.rotulo)}</span>` : "";
      const clsLinha = `Cl_Item__linha Cl_Item__linha--${i + 1}`;

      const linhaHTML = (i === 0)
        ? `<div class="${clsLinha}">${highlight(String(valor), termo)}</div>`
        : `<div class="${clsLinha}">${rotuloHTML}<span class="Cl_Match">${highlight(String(valor), termo)}</span></div>`;

      partes.push(linhaHTML);
    }

    if (partes.length === 0) {
      const label = item?.label ?? item?.nome ?? "(sem dados)";
      partes.push(`<div class="Cl_Item__linha Cl_Item__linha--1">${highlight(String(label), termo)}</div>`);
    }

    return `<div class="Cl_Item" role="option" data-id="${item?.id ?? ""}">${partes.join("")}</div>`;
  }

  // Descobre ancestrais roláveis para reposicionar o painel ao rolar
  function getScrollParents(el) {
    const parents = [];
    let p = el && el.parentNode;

    while (p && p !== document.body) {
      const s = p instanceof Element ? window.getComputedStyle(p) : null;
      if (s) {
        const ov = `${s.overflow} ${s.overflowX} ${s.overflowY}`;
        if (/(auto|scroll|overlay)/.test(ov)) parents.push(p);
      }
      p = p.parentNode;
    }
    parents.push(window);
    return parents;
  }

  function attach(userCfg) {
    const cfg = { ...DEFAULTS, ...userCfg };

    if (!cfg.wrapSel || !cfg.displaySel || !cfg.panelSel || !cfg.searchSel || !cfg.listSel) {
      console.error("ComboBusca: config inválida (seletor ausente).", cfg);
      return null;
    }

    const $wrap = document.querySelector(cfg.wrapSel);
    const $display = document.querySelector(cfg.displaySel);
    const $panel = document.querySelector(cfg.panelSel);
    const $search = document.querySelector(cfg.searchSel);
    const $list = document.querySelector(cfg.listSel);
    const $status = cfg.statusSel ? document.querySelector(cfg.statusSel) : null;
    const $hidden = cfg.campoOcultoId ? document.getElementById(cfg.campoOcultoId) : null;

    if (!$wrap || !$display || !$panel || !$search || !$list) {
      console.error("ComboBusca: elementos não encontrados.", cfg);
      return null;
    }

    // Anti-autocomplete agressivo
    $search.setAttribute("autocomplete", "new-password");
    $search.setAttribute("autocapitalize", "off");
    $search.setAttribute("autocorrect", "off");
    $search.setAttribute("spellcheck", "false");
    $search.setAttribute("name", `cb_search_${Date.now()}_${Math.random().toString(16).slice(2)}`);

    const minChars = Number.isFinite(cfg.minChars) ? cfg.minChars : 3;
    const placeholderBuscar = cfg.placeholderBuscar ?? `Digite ${minChars} caracteres ou mais...`;
    const msgMinChars = cfg.msgMinChars ?? `Digite ${minChars}+ para pesquisar`;

    let itens = [];
    let selIndex = -1;
    let aberto = false;
    let aborter = null;
    const cache = new Map();

    let floating = false;
    let scrollParents = [];

    function positionPanel() {
      const rect = $display.getBoundingClientRect();
      const vh = window.innerHeight;
      const gap = 6;

      if (!floating) {
        document.body.appendChild($panel);
        $panel.classList.add("is-floating");
        floating = true;
      }

      // sempre para BAIXO
      const maxDown = Math.max(80, vh - rect.bottom - gap - 8);
      const desiredH = Math.min($panel.scrollHeight, 280, maxDown);

      const width = Math.round(rect.width);
      const left = Math.round(rect.left);
      const top = Math.round(rect.bottom + gap);

      $panel.style.left = `${left}px`;
      $panel.style.top = `${top}px`;
      $panel.style.width = `${width}px`;
      $panel.style.maxHeight = `${desiredH}px`;
    }

    function attachScrollListeners() {
      scrollParents = getScrollParents($wrap);
      scrollParents.forEach(p => p.addEventListener("scroll", positionPanel, { passive: true }));
      window.addEventListener("resize", positionPanel, { passive: true });
    }

    function detachScrollListeners() {
      scrollParents.forEach(p => p.removeEventListener("scroll", positionPanel));
      window.removeEventListener("resize", positionPanel);
      scrollParents = [];
    }

    function unfloat() {
      if (!floating) return;
      $wrap.appendChild($panel);
      $panel.classList.remove("is-floating");
      $panel.style.left = $panel.style.top = $panel.style.width = "";
      $panel.style.maxHeight = "";
      floating = false;
    }

    function setStatus(txt) {
      if ($status) $status.textContent = txt ?? "";
    }

    function limparListaComMsgMin() {
      itens = [];
      selIndex = -1;
      $list.innerHTML = "";
      setStatus(msgMinChars);
      positionPanel();
    }

    function abrir() {
      if (aberto) return;
      $wrap.classList.add("open");
      $panel.setAttribute("aria-hidden", "false");
      aberto = true;

      // placeholder / status iguais ao esperado nas imagens
      $search.placeholder = placeholderBuscar;
      if (!$search.value || ($search.value.trim().length < minChars)) {
        setStatus(msgMinChars);
      }

      attachScrollListeners();
      positionPanel();

      // Evita popup de histórico no primeiro foco
      $search.setAttribute("readonly", "readonly");
      setTimeout(() => {
        $search.removeAttribute("readonly");
        $search.focus();
      }, 30);

      if (typeof cfg.onOpen === "function") cfg.onOpen();
    }

    function fechar() {
      if (!aberto) return;
      $wrap.classList.remove("open");
      $panel.setAttribute("aria-hidden", "true");
      aberto = false;
      selIndex = -1;

      detachScrollListeners();
      unfloat();

      if (typeof cfg.onClose === "function") cfg.onClose();
    }

    function syncSelVisual() {
      const nodes = $list.querySelectorAll(".Cl_Item");
      nodes.forEach((n, i) => n.classList.toggle("Cl_sel", i === selIndex));
    }

    function desenharLista(termo) {
      $list.innerHTML = itens.map(it => renderItemHTML(it, termo, cfg.linhas || [])).join("");
      selIndex = (itens.length > 0) ? 0 : -1;
      syncSelVisual();
      positionPanel();
    }

    function mover(direcao) {
      if (!itens.length) return;
      selIndex = (selIndex + direcao + itens.length) % itens.length;
      syncSelVisual();

      const alvo = $list.querySelectorAll(".Cl_Item")[selIndex];
      if (alvo) {
        const top = alvo.offsetTop;
        const bot = top + alvo.offsetHeight;
        if (top < $list.scrollTop) $list.scrollTop = top;
        else if (bot > $list.scrollTop + $list.clientHeight) $list.scrollTop = bot - $list.clientHeight;
      }
    }

    function aplicarSelecao(item) {
      // display guarda SOMENTE linha 1 (campo da primeira coluna)
      const campoL1 = cfg.linhas?.[0]?.campo;
      const labelDisplay =
        (campoL1 ? item?.[campoL1] : null) ??
        item?.label ??
        item?.nome ??
        "";

      $display.value = String(labelDisplay || "").trim();
      if ($hidden) $hidden.value = item?.id ?? "";

      if (typeof cfg.onSelect === "function") cfg.onSelect(item);
      fechar();
    }

    function selecionarAtual() {
      if (selIndex < 0 || selIndex >= itens.length) return;
      aplicarSelecao(itens[selIndex]);
    }

    async function buscar(termo) {
      const t = (termo ?? "").trim();

      if (t.length < minChars) {
        limparListaComMsgMin();
        return;
      }

      const cacheKey = cfg.cache ? `${cfg.rota || "customFn"}::${minChars}::${t}` : null;
      if (cfg.cache && cacheKey && cache.has(cacheKey)) {
        itens = cache.get(cacheKey) || [];
        desenharLista(t);
        setStatus(itens.length ? `${itens.length} encontrado(s)` : "Sem resultados");
        return;
      }

      if (aborter) aborter.abort();
      aborter = new AbortController();

      try {
        setStatus("Carregando...");

        let resposta;
        if (typeof cfg.fetchFn === "function") {
          resposta = await cfg.fetchFn(t, { signal: aborter.signal });
        } else if (cfg.rota) {
          const payload = (typeof cfg.queryBuilder === "function")
            ? cfg.queryBuilder(t)
            : { filtro: t, limitar: cfg.limite };

          const resp = await fetch(cfg.rota, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
            signal: aborter.signal
          });
          if (!resp.ok) throw new Error("HTTP " + resp.status);
          resposta = await resp.json();
        } else {
          throw new Error("Sem rota ou fetchFn");
        }

        const itensBrutos = Array.isArray(resposta?.itens)
          ? resposta.itens
          : (Array.isArray(resposta) ? resposta : []);

        itens = itensBrutos;
        if (cfg.cache && cacheKey) cache.set(cacheKey, itens);

        desenharLista(t);
        setStatus(itens.length ? `${itens.length} encontrado(s)` : "Sem resultados");
      } catch (e) {
        _cbLog("erro busca:", e);
        itens = [];
        $list.innerHTML = "";
        setStatus("Erro ao carregar");
      }
    }

    const buscarDebounced = debounce((v) => buscar(v), cfg.debounceMs);

    // ===== Listeners (para poder limpar no dispose) =====
    const onDisplayClick = () => { if (!$display.disabled) abrir(); };

    const onSearchInput = (e) => {
      const termo = e.target.value ?? "";
      buscarDebounced(termo);
    };

    const onSearchKeydown = (e) => {
      switch (e.keyCode) {
        case KEY.DOWN: e.preventDefault(); mover(+1); break;
        case KEY.UP: e.preventDefault(); mover(-1); break;
        case KEY.ENTER: e.preventDefault(); selecionarAtual(); break;
        case KEY.ESC: e.preventDefault(); fechar(); break;
        default: break;
      }
    };

    const onListMouseMove = (e) => {
      const el = e.target.closest(".Cl_Item");
      if (!el) return;
      const idx = Array.from($list.querySelectorAll(".Cl_Item")).indexOf(el);
      if (idx >= 0) { selIndex = idx; syncSelVisual(); }
    };

    const onListClick = (e) => {
      const el = e.target.closest(".Cl_Item");
      if (!el) return;
      const idx = Array.from($list.querySelectorAll(".Cl_Item")).indexOf(el);
      if (idx >= 0) { selIndex = idx; selecionarAtual(); }
    };

    const onDocMouseDown = (e) => {
      const clicouDentro = $wrap.contains(e.target) || $panel.contains(e.target);
      if (!clicouDentro) fechar();
    };

    $display.addEventListener("click", onDisplayClick);
    $search.addEventListener("input", onSearchInput);
    $search.addEventListener("keydown", onSearchKeydown);
    $list.addEventListener("mousemove", onListMouseMove);
    $list.addEventListener("click", onListClick);
    document.addEventListener("mousedown", onDocMouseDown);

    // valor inicial
    if (cfg.valorInicial && (cfg.valorInicial.label || cfg.valorInicial.id)) {
      $display.value = cfg.valorInicial.label ?? "";
      if ($hidden) $hidden.value = cfg.valorInicial.id ?? "";
    }

    function dispose() {
      try { if (aborter) aborter.abort(); } catch {}
      $display.removeEventListener("click", onDisplayClick);
      $search.removeEventListener("input", onSearchInput);
      $search.removeEventListener("keydown", onSearchKeydown);
      $list.removeEventListener("mousemove", onListMouseMove);
      $list.removeEventListener("click", onListClick);
      document.removeEventListener("mousedown", onDocMouseDown);
      detachScrollListeners();
      unfloat();
      _cbLog("disposed", cfg.wrapSel);
    }

    _cbLog("iniciado", cfg.wrapSel);
    return { abrir, fechar, buscar, dispose, aplicarSelecao };
  }

  window.GlobalUtils.ComboboxBusca = { attach };
})();

// === [Util.combobox_personalisado] API “TOP” ===
(function () {
  function parseRotulo(rot, campo) {
    if (rot === false || rot === null || rot === undefined || rot === "") return null;
    if (rot === true) return String(campo);
    if (typeof rot === "string") return rot;
    return null;
  }

  function parseCol(col) {
    // Aceita:
    // 1) "campo"
    // 2) { campo: "cnpj", rotulo: true|false|"Rótulo" , formatter?: fn }
    // 3) [ "campo", true|false|"Rótulo" ]
    if (!col) return null;

    if (typeof col === "string") {
      return { campo: col, rotulo: null };
    }

    if (Array.isArray(col)) {
      const campo = col[0];
      const rotulo = col.length >= 2 ? col[1] : null;
      if (!campo) return null;
      return { campo, rotulo: parseRotulo(rotulo, campo) };
    }

    if (typeof col === "object" && col.campo) {
      return {
        campo: col.campo,
        rotulo: parseRotulo(col.rotulo, col.campo),
        formatter: (typeof col.formatter === "function") ? col.formatter : undefined
      };
    }

    return null;
  }

  /**
   * Util.combobox_personalisado({
   *   seletor: "#combo_pack",
   *   caracteres: 3,
   *   rota: "/combo/packs",
   *   limite: 20,
   *   campoOcultoId: "pack_id",
   *   col_l1: ["apelido", false],
   *   col_l2: ["cnpj", "CNPJ"],
   *   col_l3: ["responsavel", true],
   *   col_l4: null,
   *   col_l5: null,
   *   onSelect: (item) => {}
   * })
   */
  window.Util.combobox_personalisado = function combobox_personalisado(opts) {
    if (!window.GlobalUtils?.ComboboxBusca?.attach) {
      throw new Error("GlobalUtils.ComboboxBusca.attach não encontrado (carregue global_util.js).");
    }

    const seletor = opts?.seletor;
    if (!seletor) throw new Error("Informe 'seletor' (ex: '#combo_pack').");

    const minChars = Number.isFinite(opts.caracteres) ? opts.caracteres : 3;
    const limite = Number.isFinite(opts.limite) ? opts.limite : 20;

    const cols = [opts.col_l1, opts.col_l2, opts.col_l3, opts.col_l4, opts.col_l5]
      .map(parseCol)
      .filter(Boolean);

    if (cols.length === 0) {
      throw new Error("Informe ao menos col_l1 (ex: col_l1: ['apelido', false]).");
    }

    const cfg = {
      wrapSel: seletor,
      displaySel: `${seletor} .Cl_SelectDisplay`,
      panelSel: `${seletor} .Cl_ComboPanel`,
      searchSel: `${seletor} .Cl_ComboSearchInput`,
      listSel: `${seletor} .Cl_ComboLista`,
      statusSel: `${seletor} .Cl_ComboStatus`,

      minChars,
      limite,
      cache: opts.cache ?? true,
      debounceMs: opts.debounceMs ?? 280,

      linhas: cols,

      campoOcultoId: opts.campoOcultoId || null,

      // Mensagens iguais ao “esperado”
      placeholderBuscar: opts.placeholderBuscar ?? `Digite ${minChars} caracteres ou mais...`,
      msgMinChars: opts.msgMinChars ?? `Digite ${minChars}+ para pesquisar`,

      // Busca: padrão GET (mais simples p/ combobox)
      fetchFn: async (termo, { signal } = {}) => {
        if (!opts.rota) throw new Error("Informe 'rota' (ex: '/combo/packs').");
        const params = new URLSearchParams({
          filtro: termo || "",
          limitar: String(limite)
        });

        const resp = await fetch(`${opts.rota}?${params.toString()}`, { method: "GET", signal });
        const json = await resp.json();

        if (!json?.sucesso) throw new Error(json?.mensagem || "Falha ao buscar.");
        return { itens: json.dados || [] };
      },

      onSelect: (item) => {
        if (typeof opts.onSelect === "function") opts.onSelect(item);
      }
    };

    return window.GlobalUtils.ComboboxBusca.attach(cfg);
  };
})();






/**
 * Util.mesAnoPicker.attach("#picker_mesano", {
 *   storageKey: "mesano_ativo",   // opcional
 *   onChange: ({mes, ano, label}) => {}
 * })
 */
window.Util.mesAnoPicker = (function () {
  const MESES = [
    { n: 1,  sigla: "JAN" }, { n: 2,  sigla: "FEV" }, { n: 3,  sigla: "MAR" },
    { n: 4,  sigla: "ABR" }, { n: 5,  sigla: "MAI" }, { n: 6,  sigla: "JUN" },
    { n: 7,  sigla: "JUL" }, { n: 8,  sigla: "AGO" }, { n: 9,  sigla: "SET" },
    { n: 10, sigla: "OUT" }, { n: 11, sigla: "NOV" }, { n: 12, sigla: "DEZ" }
  ];

  function pad2(n){ return String(n).padStart(2, "0"); }
  function label(mes, ano){ return `${MESES[mes-1]?.sigla ?? "---"}/${String(ano).slice(-2)}`; }

  function attach(rootSel, opts = {}) {
    const root = document.querySelector(rootSel);
    if (!root) return null;

    const btnDisplay = root.querySelector(".Cl_MesAno__display");
    const txt = root.querySelector(".Cl_MesAno__text");
    const panel = root.querySelector(".Cl_MesAno__panel");
    const elAno = root.querySelector("#picker_mesano_ano");
    const grid = root.querySelector("#picker_mesano_meses");
    const msg = root.querySelector("#picker_mesano_msg");
    const hiddenMes = root.querySelector("#mes_ativo");
    const hiddenAno = root.querySelector("#ano_ativo");

    const storageKey = opts.storageKey || "baracat_mesano_ativo";

    let anoVisivel;
    let selecionadoTemp = { mes: null, ano: null };
    let confirmado = { mes: null, ano: null };

    function setMsg(t){ if (msg) msg.textContent = t || ""; }

    function renderMeses() {
      grid.innerHTML = MESES.map(m => (
        `<button type="button" class="Cl_MesAno__mes" data-mes="${m.n}">${m.sigla}</button>`
      )).join("");
    }

    function syncSelVisual() {
      grid.querySelectorAll(".Cl_MesAno__mes").forEach(b => {
        const m = parseInt(b.getAttribute("data-mes"), 10);
        b.classList.toggle("is-sel", selecionadoTemp.mes === m && selecionadoTemp.ano === anoVisivel);
      });
    }

    function setAnoVisivel(n) {
      anoVisivel = n;
      if (elAno) elAno.textContent = String(anoVisivel);
      // se a pessoa já escolheu um mês, mantém seleção no mesmo ano visível
      if (selecionadoTemp.mes) selecionadoTemp.ano = anoVisivel;
      syncSelVisual();
    }

    function aplicarConfirmado(mes, ano) {
      confirmado = { mes, ano };
      if (hiddenMes) hiddenMes.value = pad2(mes);
      if (hiddenAno) hiddenAno.value = String(ano);
      if (txt) txt.textContent = label(mes, ano);

      // persiste (pra abrir o sistema já preenchido)
      try {
        localStorage.setItem(storageKey, JSON.stringify({ mes, ano }));
      } catch {}

      if (typeof opts.onChange === "function") {
        opts.onChange({ mes, ano, label: label(mes, ano) });
      }

      // evento global (opcional, útil pra dashboard)
      window.dispatchEvent(new CustomEvent("baracat:mesano-alterado", { detail: { mes, ano } }));
    }

    function abrir() {
      panel.setAttribute("aria-hidden", "false");
      btnDisplay.setAttribute("aria-expanded", "true");
      setMsg("");

      // ao abrir, clona o confirmado para temp
      selecionadoTemp = { ...confirmado };
      setAnoVisivel(selecionadoTemp.ano ?? new Date().getFullYear());
      syncSelVisual();
    }

    function fechar() {
      panel.setAttribute("aria-hidden", "true");
      btnDisplay.setAttribute("aria-expanded", "false");
      setMsg("");
    }

    // ===== Init: definir mês/ano atual (ou restaurar do storage) =====
    (function initDefault(){
      let mes = new Date().getMonth() + 1;
      let ano = new Date().getFullYear();

      try {
        const raw = localStorage.getItem(storageKey);
        if (raw) {
          const j = JSON.parse(raw);
          if (j && Number.isFinite(j.mes) && Number.isFinite(j.ano)) {
            mes = j.mes; ano = j.ano;
          }
        }
      } catch {}

      renderMeses();
      aplicarConfirmado(mes, ano);
      setAnoVisivel(ano);
    })();

    // ===== Listeners =====
    btnDisplay.addEventListener("click", () => {
      const aberto = panel.getAttribute("aria-hidden") === "false";
      if (aberto) fechar(); else abrir();
    });

    panel.addEventListener("click", (e) => {
      const anoBtn = e.target.closest(".Cl_MesAno__anoBtn");
      if (anoBtn) {
        const acao = anoBtn.getAttribute("data-acao");
        if (acao === "menos") setAnoVisivel(anoVisivel - 1);
        if (acao === "mais")  setAnoVisivel(anoVisivel + 1);
        return;
      }

      const mesBtn = e.target.closest(".Cl_MesAno__mes");
      if (mesBtn) {
        const mes = parseInt(mesBtn.getAttribute("data-mes"), 10);
        selecionadoTemp = { mes, ano: anoVisivel };
        setMsg("");
        syncSelVisual();
        return;
      }

      const acaoBtn = e.target.closest(".Cl_MesAno__btn");
      if (acaoBtn) {
        const acao = acaoBtn.getAttribute("data-acao");
        if (acao === "cancelar") {
          fechar();
          return;
        }
        if (acao === "ok") {
          if (!selecionadoTemp.mes || !selecionadoTemp.ano) {
            setMsg("Selecione um mês e um ano.");
            return;
          }
          aplicarConfirmado(selecionadoTemp.mes, selecionadoTemp.ano);
          fechar();
          return;
        }
      }
    });

    document.addEventListener("mousedown", (e) => {
      if (!root.contains(e.target)) fechar();
    });

    return {
      abrir,
      fechar,
      get: () => ({ ...confirmado, label: label(confirmado.mes, confirmado.ano) })
    };
  }

  return { attach };
})();






// --------------------------------------------------
// AUXILIA NO BLOQUEIO A TELAS QUE EXIGEM APROVADORES
// --------------------------------------------------
(function () {
  function getRotaFromEl(el) {
    const acao = (el.dataset.acao || el.dataset.action || "").trim();
    const rota = (el.dataset.rota || "").trim();
    if (rota) return rota;
    if (!acao) return null;
    return `/${acao}`;
  }

  async function validarAprovadorAntesDeNavegar(rota) {
    const resp = await fetch(rota, {
      method: "GET",
      headers: { "X-Requested-With": "XMLHttpRequest" }
    });

    if (resp.status === 200) return { ok: true };

    if (resp.status === 401) return { ok: false, tipo: "401" };

    if (resp.status === 403) {
      let msg = "Acesso restrito.";
      try {
        const json = await resp.json();
        msg = json.message || msg;
      } catch {}
      return { ok: false, tipo: "403", msg };
    }

    return { ok: false, tipo: "erro" };
  }

  function bindAcoesProtegidas() {
    const seletor = 'button[data-acao], button[data-action]';

    document.querySelectorAll(seletor).forEach((btn) => {
      if (btn.dataset._aprovadorBound === "1") return;
      btn.dataset._aprovadorBound = "1";

      btn.addEventListener("click", async (ev) => {
        // Só intercepta se estiver marcado como aprovador
        if (String(btn.dataset.aprovador || "") !== "1") return;

        ev.preventDefault();
        ev.stopPropagation();

        const rota = getRotaFromEl(btn);
        if (!rota) {
          Swal.fire("Erro", "Ação sem rota definida.", "error");
          return;
        }

        try {
          const v = await validarAprovadorAntesDeNavegar(rota);

          if (v.ok) {
            window.location.href = rota;
            return;
          }

          if (v.tipo === "401") {
            Swal.fire("Sessão expirada", "Faça login novamente.", "warning").then(() => {
              window.location.href = "/login?force=1";
            });
            return;
          }

          if (v.tipo === "403") {
            Swal.fire("Sem permissão", v.msg, "warning");
            return;
          }

          Swal.fire("Erro", "Não foi possível validar o acesso.", "error");

        } catch (e) {
          Swal.fire("Erro", e.message || "Falha ao validar acesso.", "error");
        }
      }, true); // capture=true para ganhar de handlers existentes
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", bindAcoesProtegidas, { once: true });
  } else {
    bindAcoesProtegidas();
  }
})();





// -----------------------------------------------------------------------------------------
// ÍCONES TECH (Lucide) — tudo em UMA função, compatível com CSP e com uso antigo
// -----------------------------------------------------------------------------------------
window.Util.gerarIconeTech = (function () {
  // mapa privado (minúsculo)
const MAP = {
  adm_bens: "building",
  adiantamento_viagem: "plane",
  apresentacao: "doc_ppt",
  adicionar: "plus",
  ajuda: "help-circle",
  agenda: "calendar",
  anexo: "paperclip",
  assinatura: "pen-tool",
  baixar: "download",
  cancelar: "x-circle",
  categorias: "list",
  calendario: "calendar",
  chamado: "life-buoy",
  checklist: "check-square",
  comercio: "store",
  compras: "shopping-cart",
  configuracoes: "settings",
  corporativo: "briefcase-business",
  departamentos: "building",
  detalhe: "search",
  detalhes: "list-details",
  periodo: "calendar-range",
  eventos: "history",
  intervalo: "calendar-range",
  vigencia: "calendar-range",
  ver_detalhe: "list-details",
  doc_excel: "file-spreadsheet", 
  copia_seguranca: "archive-restore",
  doc_word: "file-text",
  doc_ppt: "presentation",     
  doc_pdf: "file-archive",
  documentacao: "book-open",
  documento: "files",
  download: "download",
  editar: "pencil",
  seta_dir: "chevron-right",
  seta_esq: "chevron-left",
  seta_baixo: "chevron-down",
  seta_cima: "chevron-up",
  cobrar: "bell",


  email: "mail",
  email_aberto: "mail-open",
  email_enviado: "send",
  email_erro: "alert-circle",
  empresa: "building-2",
  enviar: "upload",
  estoque: "boxes",
  etiqueta: "tag",
  etiquetas: "tag",
  excluir: "trash-2",
  favorecidos: "users",
  financeiro: "wallet",
  grupo_acesso: "user-cog",
  industria: "factory",
  info: "info",
  livro_diario: "banknote",
  mais: "plus",
  menos: "minus",
  nf_hub: "receipt-text",
  nivel_acesso: "badge-check",
  novidades: "newspaper",
  nucleo: "network",
  rede: "globe-2",
  ocultar: "eye-off",
  //padrao: "star",
  padrao: "badge-check",
  perfil: "user",
  pj: "building-2",
  plano_contas: "folder-tree",
  principal: "layout-dashboard",
  packs: "layout-dashboard",
  reembolso: "receipt",
  relatorio: "doc_pdf",
  sair: "log-out",
  saude: "hospital",
  salvar: "check-circle",
  servicos: "wrench",
  seta_dir: "chevron-right",
  seta_esq: "chevron-left",
  suporte: "life-buoy",
  terceiro_setor: "hand-heart",
  upload: "upload",
  usuarios: "users",
  vincular_clientes: "link-2",
  visualizar: "eye",
  visualizar_clientes_outro: "users"
};


  let booted = false;

  function refresh() {
    if (window.lucide && typeof window.lucide.createIcons === "function") {
      window.lucide.createIcons();
    }
  }

  function ensureBoot() {
    if (booted) return;
    booted = true;
    if (document.readyState === "loading") {
      document.addEventListener("DOMContentLoaded", refresh, { once: true });
    } else {
      refresh();
    }
  }

  function makeHTML(nome) {
    if (nome == null) return "";
    const key = String(nome).trim().toLowerCase();
    if (!key) return "";
    const icon = MAP[key];
    if (!icon) {
      console.warn(`Ícone TECH não encontrado para: ${nome}`);
      return "";
    }
    const el = document.createElement("i");
    el.setAttribute("data-lucide", icon);
    el.className = "icon-tech";
    return el.outerHTML;
  }

  function apply(dest, nome, modo = "replace") {
    if (!dest) return;
    const html = makeHTML(nome);
    if (!html) { dest.innerHTML = ""; return; }
    if (modo === "append") dest.insertAdjacentHTML("beforeend", html);
    else if (modo === "prepend") dest.insertAdjacentHTML("afterbegin", html);
    else dest.innerHTML = html;
    refresh();
  }

  // ===== API única =====
  // - string => retorna HTML (compatível com uso antigo)
  // - objeto => aplica no destino { dest|destino|el|element, nome|key, modo? }
  function api(arg, maybeDest) {
    ensureBoot();

    if (typeof arg === "string" || arg == null) {
      return makeHTML(arg);
    }

    if (typeof arg === "object") {
      const { dest, destino, el, element, nome, key, modo } = arg;
      const target = dest || destino || el || element || maybeDest || null;
      if (!target) return makeHTML(nome ?? key ?? "");
      apply(target, (nome ?? key ?? ""), modo);
      return target;
    }

    return "";
  }

  // opcional: permitir forçar redesenho manual quando quiser
  api.refresh = refresh;

  return api;
})();
