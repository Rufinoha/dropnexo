(function () {
  const btnImportar = document.getElementById("ol_btn_importar");
  const btnSair = document.getElementById("ol_btn_desconectar");

  async function postJson(url, corpo) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(corpo || {}),
    });
    const data = await r.json().catch(() => ({}));
    if (!r.ok || data.success === false) {
      throw new Error(data.message || "Não foi possível concluir.");
    }
    return data;
  }

  if (btnSair) {
    btnSair.addEventListener("click", async () => {
      const ok = await Swal.fire({
        title: "Desconectar o Olist?",
        text: "Os produtos já importados permanecem no catálogo.",
        icon: "warning",
        showCancelButton: true,
        confirmButtonText: "Desconectar",
        cancelButtonText: "Cancelar",
        confirmButtonColor: "#021F81",
      });
      if (!ok.isConfirmed) return;
      try {
        await postJson("/api/integracoes/olist/desconectar");
        window.location.reload();
      } catch (e) {
        Swal.fire({ icon: "error", title: "Olist", text: e.message, confirmButtonColor: "#021F81" });
      }
    });
  }

  if (!btnImportar) return;

  btnImportar.addEventListener("click", async () => {
    const ok = await Swal.fire({
      title: "Importar produtos do Olist?",
      text: "Entra em lotes curtos. A foto é baixada para o servidor, como no Bling.",
      icon: "question",
      showCancelButton: true,
      confirmButtonText: "Importar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#021F81",
    });
    if (!ok.isConfirmed) return;

    let offset = 0;
    let novos = 0;
    let atualizados = 0;
    let erros = [];
    Swal.fire({
      title: "Importando",
      html: "Buscando o primeiro lote…",
      allowOutsideClick: false,
      didOpen: () => Swal.showLoading(),
    });
    try {
      for (let i = 0; i < 400; i += 1) {
        const data = await postJson("/api/integracoes/olist/produtos/importar", { offset });
        novos += data.importados || 0;
        atualizados += data.atualizados || 0;
        if (Array.isArray(data.erros)) erros = erros.concat(data.erros);
        const el = Swal.getHtmlContainer();
        if (el) {
          el.textContent = `${novos + atualizados} produto(s) até agora.`;
        }
        if (data.fim) break;
        offset = data.proximo_offset || offset + 5;
      }
      const extra = erros.length ? ` ${erros.length} item(ns) ficaram de fora.` : "";
      await Swal.fire({
        icon: erros.length ? "warning" : "success",
        title: "Importação concluída",
        text: `${novos} novo(s), ${atualizados} atualizado(s).${extra}`,
        confirmButtonColor: "#021F81",
      });
      window.location.reload();
    } catch (e) {
      Swal.fire({ icon: "error", title: "Olist", text: e.message, confirmButtonColor: "#021F81" });
    }
  });
})();
