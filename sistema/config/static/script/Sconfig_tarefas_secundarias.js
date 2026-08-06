(function () {
  const lista = document.getElementById("ts_lista");
  const modal = document.getElementById("ts_modal_log");
  const logEl = document.getElementById("ts_log_texto");
  const btnFechar = document.getElementById("ts_modal_fechar");
  const btnOk = document.getElementById("ts_modal_ok");
  if (!lista) return;

  const BASE = "/configuracoes/tarefas-secundarias";
  let pollTimer = null;

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function fmtData(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("pt-BR");
    } catch {
      return iso;
    }
  }

  function pillStatus(st) {
    if (st === "sucesso") return "is-ok";
    if (st === "erro") return "is-err";
    if (st === "rodando") return "is-run";
    return "is-skip";
  }

  function labelAgendamento(a) {
    if (a === "segunda") return "Toda segunda-feira";
    if (a === "diario") return "Diário";
    return a || "Manual";
  }

  function render(itens) {
    if (!itens.length) {
      lista.innerHTML = '<p class="TsCfg_Hint">Nenhuma tarefa cadastrada. Aplique o SQL 104.</p>';
      return;
    }
    lista.innerHTML = itens
      .map((t) => {
        const u = t.ultima_execucao;
        const st = u?.status || "nunca";
        const stLabel =
          st === "nunca"
            ? "Nunca executada"
            : st === "rodando"
              ? "Em execução"
              : st === "sucesso"
                ? "Sucesso"
                : st === "erro"
                  ? "Erro"
                  : st;
        return `
        <article class="TsCfg_Card" data-codigo="${esc(t.codigo)}" data-id="${t.id}">
          <div class="TsCfg_CardTop">
            <div>
              <h3>${esc(t.nome)}</h3>
              <p>${esc(t.descricao || "")}</p>
            </div>
          </div>
          <div class="TsCfg_Meta">
            <span class="TsCfg_Pill">${esc(labelAgendamento(t.agendamento))}</span>
            <span class="TsCfg_Pill ${pillStatus(st)}">${esc(stLabel)}</span>
            ${
              u?.iniciado_em
                ? `<span class="TsCfg_Pill">Última: ${esc(fmtData(u.iniciado_em))}</span>`
                : ""
            }
          </div>
          ${u?.mensagem ? `<p class="TsCfg_Msg">${esc(u.mensagem)}</p>` : ""}
          <div class="TsCfg_Acoes">
            <button type="button" class="Cl_botaoprimario" data-acao="executar">Executar agora</button>
            <button type="button" class="Cl_botaoFiltro" data-acao="historico">Ver histórico / log</button>
          </div>
        </article>`;
      })
      .join("");
  }

  async function carregar() {
    const r = await fetch(`${BASE}/dados`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      lista.innerHTML = `<p class="TsCfg_Hint">${esc(j.message || "Falha ao carregar.")}</p>`;
      return;
    }
    render(j.itens || []);
    const rodando = (j.itens || []).some((t) => t.ultima_execucao?.status === "rodando");
    if (rodando) {
      if (!pollTimer) pollTimer = setInterval(carregar, 4000);
    } else if (pollTimer) {
      clearInterval(pollTimer);
      pollTimer = null;
    }
  }

  async function executar(codigo, btn) {
    if (btn) btn.disabled = true;
    try {
      const r = await fetch(`${BASE}/${encodeURIComponent(codigo)}/executar`, {
        method: "POST",
        credentials: "same-origin",
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao iniciar.");
      if (window.Swal) {
        Swal.fire({
          icon: "info",
          title: "Tarefa iniciada",
          text: j.mensagem || "Rodando em segundo plano.",
          confirmButtonColor: "#021F81",
        });
      }
      await carregar();
    } catch (e) {
      if (window.Swal) Swal.fire("Erro", e.message, "error");
      else alert(e.message);
    } finally {
      if (btn) btn.disabled = false;
    }
  }

  async function abrirHistorico(idTarefa) {
    const r = await fetch(`${BASE}/${idTarefa}/execucoes`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      alert(j.message || "Falha ao carregar histórico.");
      return;
    }
    const itens = j.itens || [];
    if (!itens.length) {
      if (logEl) logEl.textContent = "Nenhuma execução registrada ainda.";
    } else {
      const blocks = itens.map(
        (e) =>
          `[#${e.id}] ${e.status} · ${e.disparado_por} · ${fmtData(e.iniciado_em)}\n` +
          `${e.mensagem || ""}\n` +
          `${"─".repeat(40)}\n` +
          `${e.log_texto || "(sem log)"}\n`
      );
      if (logEl) logEl.textContent = blocks.join("\n");
    }
    modal?.showModal();
  }

  lista.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-acao]");
    const card = ev.target.closest(".TsCfg_Card");
    if (!btn || !card) return;
    const acao = btn.getAttribute("data-acao");
    if (acao === "executar") executar(card.getAttribute("data-codigo"), btn);
    if (acao === "historico") abrirHistorico(card.getAttribute("data-id"));
  });

  btnFechar?.addEventListener("click", () => modal?.close());
  btnOk?.addEventListener("click", () => modal?.close());

  carregar();
})();
