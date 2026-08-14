(function () {
  const form = document.getElementById("az_par_form");
  if (!form) return;
  const el = {
    visivel: document.getElementById("az_par_visivel"),
    modoA: document.getElementById("az_par_modo_a"),
    modoB: document.getElementById("az_par_modo_b"),
    auto: document.getElementById("az_par_aprovacao_auto"),
    texto: document.getElementById("az_par_texto"),
  };

  function preencher(p) {
    if (!p) return;
    el.visivel.checked = !!p.visivel_rede_vendedor;
    el.auto.checked = !!p.aprovacao_automatica;
    el.texto.value = p.texto_adicional || "";
    const modo = (p.modo_vitrine || "armazem").toLowerCase();
    if (modo === "fornecedores") el.modoB.checked = true;
    else el.modoA.checked = true;
  }

  async function carregar() {
    const r = await fetch("/armazem/parametros/dados", { credentials: "same-origin" });
    const j = await r.json();
    if (j.success) preencher(j.parametros);
  }

  form.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const body = {
      visivel_rede_vendedor: !!el.visivel.checked,
      modo_vitrine: el.modoB.checked ? "fornecedores" : "armazem",
      aprovacao_automatica: !!el.auto.checked,
      texto_adicional: (el.texto.value || "").trim(),
    };
    const r = await fetch("/armazem/parametros/salvar", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const j = await r.json();
    if (window.Util?.alertar) Util.alertar(j.message || (j.success ? "Salvo" : "Erro"), j.success ? "success" : "error");
    else if (window.Swal) Swal.fire(j.success ? "Salvo" : "Erro", j.message, j.success ? "success" : "error");
    if (j.success && j.parametros) preencher(j.parametros);
  });

  carregar();
})();
