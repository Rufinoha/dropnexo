(function () {
  const form = document.getElementById("form-espera-fundador");
  if (!form) return;
  const api = window.OSB_ESPERA_FUNDADOR_API || "/api/lista-espera-fundador";
  const msgEl = document.getElementById("msg-espera");
  const inpWa = form.querySelector('[name="whatsapp"]');

  function soDigitos(v) {
    return String(v || "").replace(/\D/g, "");
  }
  function mascaraTelefone(v) {
    const d = soDigitos(v).slice(0, 11);
    if (d.length <= 10) {
      return d.replace(/^(\d{2})(\d)/, "($1) $2").replace(/(\d{4})(\d)/, "$1-$2");
    }
    return d.replace(/^(\d{2})(\d)/, "($1) $2").replace(/(\d{5})(\d)/, "$1-$2");
  }
  inpWa?.addEventListener("input", () => {
    inpWa.value = mascaraTelefone(inpWa.value);
  });

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (msgEl) msgEl.hidden = true;
    const fd = new FormData(form);
    const body = {
      nome: String(fd.get("nome") || "").trim(),
      whatsapp: soDigitos(fd.get("whatsapp")),
      segmento: String(fd.get("segmento") || "").trim(),
      email: String(fd.get("email") || "").trim(),
      empresa: String(fd.get("empresa") || "").trim(),
      comentarios: String(fd.get("comentarios") || "").trim(),
    };
    const btn = form.querySelector('[type="submit"]');
    btn.disabled = true;
    try {
      const r = await fetch(api, {
        method: "POST",
        headers: { "Content-Type": "application/json", Accept: "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (j.success) {
        form.reset();
        if (window.Swal) {
          await Swal.fire({ title: "Recebido!", text: j.message || "Entraremos em contato.", icon: "success" });
        } else if (msgEl) {
          msgEl.textContent = j.message || "Enviado.";
          msgEl.className = "form-msg is-ok";
          msgEl.hidden = false;
        }
        return;
      }
      if (msgEl) {
        msgEl.textContent = j.message || "Não foi possível enviar.";
        msgEl.className = "form-msg is-error";
        msgEl.hidden = false;
      }
    } catch {
      if (msgEl) {
        msgEl.textContent = "Falha na comunicação.";
        msgEl.className = "form-msg is-error";
        msgEl.hidden = false;
      }
    } finally {
      btn.disabled = false;
    }
  });
})();
