/**
 * Editor rico da descrição do produto (Quill + modo HTML com pré-visualização).
 */
(function () {
  const SPECIAL_CHARS = [
    "®", "©", "™", "°", "±", "½", "¼", "¾", "×", "÷",
    "→", "←", "↑", "↓", "•", "…", "“", "”", "‘", "’",
    "€", "£", "¥", "¹", "²", "³", "µ", "§", "¶", "★",
  ];

  let quill = null;
  let htmlMode = false;
  let previewTimer = null;

  const el = {};

  function $(id) {
    return document.getElementById(id);
  }

  function looksLikeHtml(value) {
    return /<[a-z][\s\S]*>/i.test(value || "");
  }

  function isEmptyHtml(html) {
    const stripped = (html || "")
      .replace(/<p><br><\/p>/gi, "")
      .replace(/<p>\s*<\/p>/gi, "")
      .trim();
    return !stripped;
  }

  function normalizeQuillHtml(html) {
    if (isEmptyHtml(html)) return "";
    return (html || "").trim();
  }

  function formatHtmlBasic(html) {
    if (!html) return "";
    return html
      .replace(/></g, ">\n<")
      .replace(/\n\s*\n/g, "\n")
      .trim();
  }

  function setQuillContent(value) {
    if (!quill) return;
    const v = (value || "").trim();
    if (!v) {
      quill.setText("");
      return;
    }
    if (looksLikeHtml(v)) {
      quill.clipboard.dangerouslyPasteHTML(v);
    } else {
      quill.setText(v);
    }
  }

  function updatePreview() {
    if (!el.preview || !el.htmlTextarea) return;
    const html = el.htmlTextarea.value.trim();
    el.preview.innerHTML = html;
    if (isEmptyHtml(html)) {
      el.preview.innerHTML = '<p class="Cat_DescPreviewEmpty">A pré-visualização aparece aqui conforme você edita o HTML.</p>';
    }
  }

  function schedulePreview() {
    clearTimeout(previewTimer);
    previewTimer = setTimeout(updatePreview, 120);
  }

  function closeSpecialChars() {
    el.charsPopover?.remove();
    el.charsPopover = null;
  }

  function insertSpecialChar(ch) {
    if (!quill || htmlMode) return;
    const range = quill.getSelection(true);
    const index = range ? range.index : quill.getLength();
    quill.insertText(index, ch, "user");
    quill.setSelection(index + ch.length, 0);
    closeSpecialChars();
  }

  function openSpecialChars(anchor) {
    closeSpecialChars();
    const pop = document.createElement("div");
    pop.className = "Cat_DescCharsPopover";
    pop.setAttribute("role", "menu");
    pop.innerHTML = SPECIAL_CHARS.map(
      (ch) => `<button type="button" class="Cat_DescCharBtn" data-char="${ch}">${ch}</button>`
    ).join("");
    pop.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-char]");
      if (!btn) return;
      insertSpecialChar(btn.getAttribute("data-char"));
    });
    anchor.closest(".Cat_DescToolbarWrap")?.appendChild(pop);
    el.charsPopover = pop;
    const onDoc = (ev) => {
      if (pop.contains(ev.target) || anchor.contains(ev.target)) return;
      closeSpecialChars();
      document.removeEventListener("mousedown", onDoc);
    };
    setTimeout(() => document.addEventListener("mousedown", onDoc), 0);
  }

  function addSpecialCharsButton() {
    const toolbar = el.visualPane?.querySelector(".ql-toolbar");
    if (!toolbar || toolbar.querySelector(".Cat_DescCharsTool")) return;
    const group = document.createElement("span");
    group.className = "ql-formats Cat_DescCharsTool";
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "Cat_DescToolbarExtra";
    btn.title = "Caracteres especiais";
    btn.setAttribute("aria-label", "Caracteres especiais");
    btn.innerHTML = "<span>Ω</span>";
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      openSpecialChars(btn);
    });
    group.appendChild(btn);
    toolbar.appendChild(group);
  }

  function enterHtmlMode() {
    if (!quill) return;
    const html = normalizeQuillHtml(quill.root.innerHTML);
    el.htmlTextarea.value = formatHtmlBasic(html);
    el.visualPane.hidden = true;
    el.htmlPane.hidden = false;
    el.btnToggle.innerHTML = ICON_EYE + " Ver editor visual";
    el.btnToggle.setAttribute("aria-pressed", "true");
    if (el.btnCopy) el.btnCopy.hidden = false;
    htmlMode = true;
    updatePreview();
    el.htmlTextarea.focus();
  }

  function enterVisualMode() {
    const html = (el.htmlTextarea?.value || "").trim();
    setQuillContent(html);
    el.visualPane.hidden = false;
    el.htmlPane.hidden = true;
    el.btnToggle.innerHTML = ICON_CODE + " Ver código HTML";
    el.btnToggle.setAttribute("aria-pressed", "false");
    if (el.btnCopy) el.btnCopy.hidden = true;
    htmlMode = false;
    closeSpecialChars();
    quill?.focus();
  }

  function toggleMode() {
    if (htmlMode) enterVisualMode();
    else enterHtmlMode();
  }

  async function copyHtml() {
    const html = (el.htmlTextarea?.value || "").trim();
    if (!html) {
      window.Swal?.fire("Nada para copiar", "O campo HTML está vazio.", "info");
      return;
    }
    try {
      await navigator.clipboard.writeText(html);
      window.Swal?.fire({ title: "Copiado!", text: "HTML copiado para a área de transferência.", icon: "success", timer: 1800, showConfirmButton: false });
    } catch {
      el.htmlTextarea.select();
      document.execCommand("copy");
      window.Swal?.fire({ title: "Copiado!", icon: "success", timer: 1800, showConfirmButton: false });
    }
  }

  const ICON_CODE = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/></svg>';
  const ICON_EYE = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
  const ICON_COPY = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>';

  function bindElements() {
    el.visualPane = $("descricaoVisualPane");
    el.htmlPane = $("descricaoHtmlPane");
    el.htmlTextarea = $("descricaoHtml");
    el.preview = $("descricaoPreview");
    el.btnToggle = $("btnDescModeToggle");
    el.btnCopy = $("btnDescCopyHtml");
    el.hiddenField = $("descricao");
  }

  function initQuill() {
    if (typeof Quill === "undefined") return;
    quill = new Quill("#descricaoEditor", {
      theme: "snow",
      placeholder: "Descrição do produto…",
      modules: {
        toolbar: [
          [{ header: [2, 3, false] }],
          ["bold", "italic", "underline", "strike"],
          [{ color: [] }, { background: [] }],
          [{ align: [] }],
          [{ list: "ordered" }, { list: "bullet" }],
          ["blockquote", "link"],
          ["clean"],
        ],
      },
    });
    quill.on("text-change", () => {
      if (!htmlMode && el.hiddenField) {
        el.hiddenField.value = normalizeQuillHtml(quill.root.innerHTML);
      }
    });
    addSpecialCharsButton();
  }

  function bindEvents() {
    el.btnToggle?.addEventListener("click", toggleMode);
    el.btnCopy?.addEventListener("click", copyHtml);
    el.htmlTextarea?.addEventListener("input", schedulePreview);
  }

  function init() {
    if (!$("descricaoEditor")) return false;
    bindElements();
    initQuill();
    bindEvents();
    if (el.btnToggle) {
      el.btnToggle.innerHTML = ICON_CODE + " Ver código HTML";
    }
    if (el.btnCopy) {
      el.btnCopy.innerHTML = ICON_COPY + " Copiar HTML";
      el.btnCopy.hidden = true;
    }
    return true;
  }

  function getValue() {
    let html = "";
    if (htmlMode) html = (el.htmlTextarea?.value || "").trim();
    else if (quill) html = normalizeQuillHtml(quill.root.innerHTML);
    else html = (el.hiddenField?.value || "").trim();
    if (el.hiddenField) el.hiddenField.value = html;
    return html;
  }

  function setValue(value) {
    const v = (value || "").trim();
    if (htmlMode) {
      if (el.htmlTextarea) el.htmlTextarea.value = formatHtmlBasic(v);
      updatePreview();
    } else {
      setQuillContent(v);
    }
    if (el.hiddenField) el.hiddenField.value = v;
  }

  function setReadOnly(readonly) {
    const ro = !!readonly;
    if (quill) quill.enable(!ro);
    if (el.htmlTextarea) {
      el.htmlTextarea.readOnly = ro;
      el.htmlTextarea.disabled = ro;
    }
    el.visualPane?.classList.toggle("is-readonly", ro);
    el.htmlPane?.classList.toggle("is-readonly", ro);
    el.btnToggle?.toggleAttribute("disabled", ro);
    if (el.btnCopy) el.btnCopy.toggleAttribute("disabled", ro);
  }

  window.CatDescricaoEditor = { init, getValue, setValue, setReadOnly };

  if (document.getElementById("descricaoEditor")) {
    init();
  }
})();
