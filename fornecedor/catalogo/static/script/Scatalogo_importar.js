(function () {
  const elArquivo = document.getElementById("arquivo_csv");
  const elBtn = document.getElementById("btnImportar");
  const elResult = document.getElementById("resultado_import");
  if (!elBtn) return;

  elBtn.addEventListener("click", async () => {
    const file = elArquivo?.files?.[0];
    if (!file) {
      await Swal.fire("Atenção", "Selecione um arquivo CSV.", "warning");
      return;
    }
    const fd = new FormData();
    fd.append("arquivo", file);
    try {
      elBtn.disabled = true;
      const r = await fetch("/catalogos/importar", { method: "POST", body: fd });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Erro na importação.");

      let txt = `${j.message}\nInseridos: ${j.inseridos || 0}\nAtualizados: ${j.atualizados || 0}`;
      if (j.total_erros) {
        txt += `\nErros: ${j.total_erros}`;
        (j.erros || []).forEach((e) => {
          txt += `\n  Linha ${e.linha}: ${e.erro}`;
        });
      }
      if (elResult) {
        elResult.hidden = false;
        elResult.textContent = txt;
      }
      await Swal.fire("Importação", j.message, j.total_erros ? "warning" : "success");
      window.parent.postMessage({ grupo: "atualizarTabela" }, "*");
    } catch (e) {
      await Swal.fire("Erro", e.message, "error");
    } finally {
      elBtn.disabled = false;
    }
  });
})();
