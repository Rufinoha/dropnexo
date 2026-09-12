/**
 * Abre a tela de aceite antes de solicitar vínculo com fornecedor.
 */
window.VinculoRequisitos = (function () {
  function solicitarComRequisitos(idFornecedor, nomeFornecedor, opts) {
    const GU = window.parent?.GlobalUtils || window.GlobalUtils;
    if (!GU?.abrirJanelaApoioModal) {
      return Promise.reject(new Error("Modal de apoio indisponível."));
    }

    const baseNivel = window.__nivelModal__ || 0;
    const nivel = baseNivel + 1;
    const azf = opts && opts.id_armazem_fornecedor ? Number(opts.id_armazem_fornecedor) : null;
    let rota = "/fornecedores/solicitar-vinculo/apoio";
    if (azf) rota += "?azf=" + encodeURIComponent(String(azf));

    return new Promise((resolve) => {
      const onMsg = (ev) => {
        const id = Number(ev.data?.id_fornecedor);
        if (Number(idFornecedor) !== id) return;
        if (ev.data?.grupo === "vinculoSolicitado") {
          window.removeEventListener("message", onMsg);
          resolve(true);
        }
        if (ev.data?.grupo === "vinculoCancelado") {
          window.removeEventListener("message", onMsg);
          resolve(false);
        }
      };
      window.addEventListener("message", onMsg);

      GU.abrirJanelaApoioModal({
        rota,
        titulo: "Solicitar vínculo — " + (nomeFornecedor || "Fornecedor"),
        largura: 680,
        altura: 720,
        nivel,
        id: idFornecedor,
      });
    });
  }

  return { solicitarComRequisitos };
})();
