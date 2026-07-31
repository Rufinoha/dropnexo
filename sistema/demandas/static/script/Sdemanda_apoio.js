(function () {
  "use strict";

  let nivelModal = 1;

  function el(id) {
    return document.getElementById(id);
  }

  async function salvar() {
    const titulo = (el("dem_apoio_titulo")?.value || "").trim();
    const mensagem = (el("dem_apoio_mensagem")?.value || "").trim();
    const categoria = el("dem_apoio_categoria")?.value || "duvida";
    const prioridade = el("dem_apoio_prioridade")?.value || "normal";
    const modulo = (el("dem_apoio_modulo")?.value || "").trim();
    const tela = (el("dem_apoio_tela")?.value || "").trim();
    const arquivos = el("dem_apoio_anexos")?.files ? Array.from(el("dem_apoio_anexos").files) : [];

    if (titulo.length < 3) {
      Swal.fire("Atenção", "Informe um assunto com pelo menos 3 caracteres.", "warning");
      return;
    }
    if (mensagem.length < 5) {
      Swal.fire("Atenção", "Descreva sua demanda com pelo menos 5 caracteres.", "warning");
      return;
    }

    Swal.fire({ title: "Enviando...", allowOutsideClick: false, didOpen: () => Swal.showLoading() });

    try {
      let r;
      if (arquivos.length) {
        const fd = new FormData();
        fd.append("titulo", titulo);
        fd.append("mensagem", mensagem);
        fd.append("categoria", categoria);
        fd.append("prioridade", prioridade);
        fd.append("url", "/demandas");
        if (modulo) fd.append("modulo", modulo);
        if (tela) fd.append("tela", tela);
        arquivos.forEach((f) => fd.append("anexos", f, f.name));
        r = await fetch("/api/demandas/abrir", { method: "POST", credentials: "include", body: fd });
      } else {
        r = await fetch("/api/demandas/abrir", {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            titulo,
            mensagem,
            categoria,
            prioridade,
            modulo,
            tela,
            url: "/demandas",
          }),
        });
      }

      const j = await r.json().catch(() => ({}));
      Swal.close();

      if (!r.ok || !j.success) {
        Swal.fire("Erro", j.message || `Falha ao abrir chamado (${r.status}).`, "error");
        return;
      }

      const proto = j.chamado?.protocolo ? ` Protocolo: ${j.chamado.protocolo}.` : "";
      await Swal.fire("Sucesso", (j.message || "Chamado aberto com sucesso.") + proto, "success");

      window.parent.postMessage(
        { grupo: "atualizarTabela", nivel: nivelModal, uuid: j.chamado?.uuid || "" },
        window.location.origin
      );

      if (window.GlobalUtils?.fecharJanelaApoio) {
        GlobalUtils.fecharJanelaApoio(nivelModal);
      }
    } catch (e) {
      try {
        Swal.close();
      } catch (_) {}
      Swal.fire("Erro", e.message || "Falha ao enviar chamado.", "error");
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    el("dem_apoio_btnSalvar")?.addEventListener("click", salvar);
    if (window.GlobalUtils?.receberDadosApoio) {
      GlobalUtils.receberDadosApoio((_id, nivel) => {
        if (nivel) nivelModal = nivel;
      });
    }
  });
})();
