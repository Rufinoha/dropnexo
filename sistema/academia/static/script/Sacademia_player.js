/* Player Academia DropNexo — abre em modal */

(function () {
  "use strict";

  if (window.HubAcademiaPlayer) return;

  function getIdFromQuery() {
    try {
      const id = Number(new URLSearchParams(window.location.search).get("id") || 0);
      return id > 0 ? id : 0;
    } catch {
      return 0;
    }
  }

  window.HubAcademiaPlayer = {
    idVideo: 0,

    init: async function () {
      HubAcademiaPlayer.bind();

      if (window.GlobalUtils?.receberDadosApoio) {
        GlobalUtils.receberDadosApoio(async (id) => {
          const vid = Number(id || 0) || 0;
          if (!(vid > 0)) return;
          if (HubAcademiaPlayer.idVideo === vid) return;
          HubAcademiaPlayer.idVideo = vid;
          await HubAcademiaPlayer.carregarContextoEPlay(vid);
        });

        const idq = getIdFromQuery();
        if (idq > 0) {
          HubAcademiaPlayer.idVideo = idq;
          await HubAcademiaPlayer.carregarContextoEPlay(idq);
        }
        return;
      }

      const idq = getIdFromQuery();
      HubAcademiaPlayer.idVideo = idq;
      await HubAcademiaPlayer.carregarContextoEPlay(idq);
    },

    bind: function () {
      document.querySelector("#ob_btnFechar")?.addEventListener("click", () => {
        HubAcademiaPlayer.fechar();
      });

      document.querySelector("#ob_btnFullscreen")?.addEventListener("click", async () => {
        await HubAcademiaPlayer.fullscreen();
      });

      document.addEventListener("keydown", (ev) => {
        if (ev.key !== "Escape") return;
        if (document.fullscreenElement) {
          document.exitFullscreen().catch(() => {});
          return;
        }
        HubAcademiaPlayer.fechar();
      });
    },

    fechar: function () {
      try {
        window.parent?.GlobalUtils?.fecharJanelaApoio(1);
      } catch {
        try {
          window.close();
        } catch (_) {}
      }
    },

    fullscreen: async function () {
      const v = document.querySelector("#ob_video");
      if (!v) return;
      try {
        if (!document.fullscreenElement) await v.requestFullscreen();
        else await document.exitFullscreen();
      } catch {
        Swal.fire("Atenção", "Seu navegador bloqueou o modo tela cheia.", "warning");
      }
    },

    carregarContextoEPlay: async function (id) {
      if (!(Number(id) > 0)) {
        return Swal.fire("Erro", "Vídeo não encontrado.", "error");
      }

      const r = await GlobalUtils.requestJSON({
        url: "/academia/dados",
        method: "POST",
        payload: { categoria: "__TODOS__", q: "" },
      });

      if (!r) return;
      if (!r.ok) {
        return Swal.fire("Erro", r.json?.message || "Falha ao carregar.", "error");
      }

      const itens = r.json?.itens || [];
      const mv = r.json?.mais_vistos || [];
      const atual = itens.find((x) => Number(x.id) === Number(id));
      if (!atual) {
        return Swal.fire("Erro", "Vídeo não encontrado.", "error");
      }

      HubAcademiaPlayer.renderAtual(atual);
      HubAcademiaPlayer.renderMaisVistos(mv, id);
      HubAcademiaPlayer.play(id);
    },

    renderAtual: function (v) {
      const t = document.querySelector("#ob_titulo");
      const m = document.querySelector("#ob_modulo");
      const d = document.querySelector("#ob_descricao");
      if (t) t.textContent = v.titulo || "—";
      if (m) m.textContent = v.categoria || "—";
      if (d) d.textContent = v.descricao || "—";
    },

    renderMaisVistos: function (lista, idAtual) {
      const box = document.querySelector("#ob_maisvistos");
      if (!box) return;

      const itens = (lista || []).slice(0, 6);
      box.innerHTML = itens
        .map(
          (x) => `
        <div class="ap-mv-item ${Number(x.id) === Number(idAtual) ? "ativo" : ""}" data-id="${x.id}">
          <div class="t">${HubAcademiaPlayer._esc(x.titulo)}</div>
          <div class="s">${HubAcademiaPlayer._esc(x.categoria)} • ${HubAcademiaPlayer._esc(x.duracao_txt || "")}</div>
        </div>`
        )
        .join("");

      box.querySelectorAll(".ap-mv-item").forEach((el) => {
        el.addEventListener("click", async () => {
          const nextId = Number(el.getAttribute("data-id") || 0) || 0;
          if (nextId <= 0) return;
          HubAcademiaPlayer.idVideo = nextId;
          await HubAcademiaPlayer.carregarContextoEPlay(nextId);
        });
      });
    },

    play: function (id) {
      const v = document.querySelector("#ob_video");
      if (!v) return;
      v.src = `/academia/stream/${id}`;
      v.load();
      v.play().catch(() => {});
    },

    _esc: function (s) {
      return String(s ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;");
    },
  };

  document.addEventListener("DOMContentLoaded", () => HubAcademiaPlayer.init(), { once: true });
})();
