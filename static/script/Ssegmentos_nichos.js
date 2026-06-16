/**
 * Ssegmentos_nichos.js — seleção de segmentos marketplace (pills + Swal ajuda)
 */
(function (global) {
  "use strict";

  function escapeHtml(s) {
    return String(s || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function listaHtml(itens) {
    if (!itens || !itens.length) return "<p class=\"SegSwal_Desc\">—</p>";
    return "<ul>" + itens.map((i) => "<li>" + escapeHtml(i) + "</li>").join("") + "</ul>";
  }

  function abrirAjudaSegmento(seg) {
    if (typeof Swal === "undefined") {
      alert((seg.descricao || seg.nome) + "\n\n" + (seg.aplicacao || ""));
      return;
    }
    const obs = seg.observacao
      ? '<p class="SegSwal_Obs"><strong>Observação:</strong> ' + escapeHtml(seg.observacao) + "</p>"
      : "";
    Swal.fire({
      title: seg.nome,
      icon: "info",
      width: "36rem",
      confirmButtonColor: "#021F81",
      customClass: { popup: "swal-seg-nicho", htmlContainer: "swal-seg-html" },
      html:
        '<p class="SegSwal_Desc">' +
        escapeHtml(seg.descricao) +
        "</p>" +
        '<div class="SegSwal_Block"><h4>Exemplos de categorias</h4>' +
        listaHtml(seg.exemplos_categorias) +
        "</div>" +
        '<div class="SegSwal_Block"><h4>Exemplos de fornecedores</h4>' +
        listaHtml(seg.exemplos_fornecedores) +
        "</div>" +
        (seg.aplicacao
          ? '<div class="SegSwal_Block"><h4>Aplicação</h4><p class="SegSwal_Aplic">' +
            escapeHtml(seg.aplicacao) +
            "</p></div>"
          : "") +
        obs,
    });
  }

  function render(container, segmentos, selecionados) {
    if (!container) return;
    const sel = new Set((selecionados || []).map((id) => Number(id)));
    container.innerHTML = (segmentos || [])
      .map((s) => {
        const on = sel.has(Number(s.id)) || s.selecionado;
        return (
          '<div class="SegNichos_Item" data-seg-id="' +
          s.id +
          '">' +
          '<button type="button" class="SegNichos_Pill' +
          (on ? " is-on" : "") +
          '" data-id="' +
          s.id +
          '" data-on="' +
          (on ? "1" : "0") +
          '">' +
          '<span class="SegNichos_PillText">' +
          escapeHtml(s.nome) +
          "</span>" +
          '<span class="SegNichos_Help" role="button" tabindex="0" data-help-id="' +
          s.id +
          '" title="O que é este segmento?" aria-label="Ajuda: ' +
          escapeHtml(s.nome) +
          '">?</span>' +
          "</button></div>"
        );
      })
      .join("");
    container._segmentosCache = segmentos || [];
  }

  function idsSelecionados(container) {
    if (!container) return [];
    return Array.from(container.querySelectorAll(".SegNichos_Pill.is-on")).map((b) =>
      Number(b.getAttribute("data-id"))
    );
  }

  function bind(container, opts) {
    if (!container || container._segNichosBound) return;
    container._segNichosBound = true;
    const onChange = opts && opts.onChange ? opts.onChange : null;

    container.addEventListener("click", (e) => {
      const help = e.target.closest(".SegNichos_Help");
      if (help) {
        e.preventDefault();
        e.stopPropagation();
        const id = Number(help.getAttribute("data-help-id"));
        const seg = (container._segmentosCache || []).find((s) => Number(s.id) === id);
        if (seg) abrirAjudaSegmento(seg);
        return;
      }
      const pill = e.target.closest(".SegNichos_Pill");
      if (!pill) return;
      const on = pill.classList.toggle("is-on");
      pill.setAttribute("data-on", on ? "1" : "0");
      const err = container.parentElement?.querySelector(".SegNichos_Erro");
      if (err) err.hidden = true;
      if (onChange) onChange(idsSelecionados(container));
    });
  }

  function validarMinimo(container, msg) {
    const ids = idsSelecionados(container);
    const errEl = container?.parentElement?.querySelector(".SegNichos_Erro");
    if (ids.length > 0) {
      if (errEl) errEl.hidden = true;
      return true;
    }
    if (errEl) {
      errEl.textContent = msg || "Selecione ao menos um segmento.";
      errEl.hidden = false;
    }
    return false;
  }

  global.SegNichos = {
    render,
    bind,
    idsSelecionados,
    validarMinimo,
    abrirAjuda: abrirAjudaSegmento,
  };
})(window);
