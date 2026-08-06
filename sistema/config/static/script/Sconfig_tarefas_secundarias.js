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

  function segundosDesde(iso) {
    if (!iso) return null;
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return null;
    return Math.max(0, Math.round((Date.now() - t) / 1000));
  }

  function pillStatus(st) {
    if (st === "sucesso") return "is-ok";
    if (st === "erro") return "is-err";
    if (st === "rodando") return "is-run";
    return "is-skip";
  }

  function labelAgendamento(a) {
    if (a === "segunda") return "Toda segunda-feira";
    if (a === "domingo") return "Todo domingo às 02:00";
    if (a === "diario") return "Diário";
    return a || "Manual";
  }

  function execucaoTravada(u) {
    if (!u || u.status !== "rodando") return false;
    const hb = u.meta?.heartbeat_em;
    if (hb) return (segundosDesde(hb) || 0) > 180;
    const ini = segundosDesde(u.iniciado_em);
    return ini == null || ini > 90;
  }

  function blocoProgresso(u) {
    if (!u || u.status !== "rodando") return "";
    const meta = u.meta || {};
    const pct = Math.max(0, Math.min(100, Number(meta.pct) || 0));
    const hb = meta.heartbeat_em || null;
    const idadeHb = segundosDesde(hb);
    const idadeIni = segundosDesde(u.iniciado_em);
    const travada = execucaoTravada(u);
    let sinal = "Aguardando primeiro sinal…";
    let sinalCls = "";
    if (travada) {
      const idade = idadeHb != null ? idadeHb : idadeIni;
      sinal =
        idade != null
          ? `Travada / sem sinal há ${idade}s — clique em Executar agora para reiniciar`
          : "Travada / sem sinal — clique em Executar agora para reiniciar";
      sinalCls = "is-stuck";
    } else if (idadeHb != null) {
      sinal = `Sinal há ${idadeHb}s`;
      if (idadeHb > 60) sinalCls = "is-warn";
    } else if (idadeIni != null && idadeIni > 20) {
      sinal = `Ainda sem sinal (${idadeIni}s)…`;
      sinalCls = "is-warn";
    }
    const detalhe = [
      meta.site_id ? `Site ${meta.site_id}` : "",
      meta.raiz_idx && meta.raizes_total
        ? `raiz ${meta.raiz_idx}/${meta.raizes_total}`
        : "",
      meta.raiz_nome ? `«${meta.raiz_nome}»` : "",
      meta.nos_visitados != null ? `${meta.nos_visitados} nós` : "",
      meta.folhas != null ? `${meta.folhas} folhas` : "",
    ]
      .filter(Boolean)
      .join(" · ");

    return `
      <div class="TsCfg_Progress">
        <div class="TsCfg_ProgressTop">
          <strong>${pct.toFixed(0)}%</strong>
          <span class="TsCfg_Heartbeat ${sinalCls}">${esc(sinal)}</span>
        </div>
        <div class="TsCfg_ProgressBar" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="${pct.toFixed(0)}">
          <span style="width:${pct}%"></span>
        </div>
        ${detalhe ? `<p class="TsCfg_ProgressDetail">${esc(detalhe)}</p>` : ""}
      </div>`;
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
        const travada = execucaoTravada(u);
        const btnExecDisabled = st === "rodando" && !travada ? " disabled" : "";
        const btnExecLabel = travada ? "Reiniciar agora" : "Executar agora";
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
            <span class="TsCfg_Pill ${pillStatus(st)}">${esc(travada ? "Travada" : stLabel)}</span>
            ${
              u?.iniciado_em
                ? `<span class="TsCfg_Pill">Última: ${esc(fmtData(u.iniciado_em))}</span>`
                : ""
            }
          </div>
          ${blocoProgresso(u)}
          ${
            u?.mensagem && st !== "rodando"
              ? `<p class="TsCfg_Msg">${esc(u.mensagem)}</p>`
              : ""
          }
          <div class="TsCfg_Acoes">
            <button type="button" class="Cl_botaoprimario" data-acao="executar"${btnExecDisabled}>${btnExecLabel}</button>
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
      if (!pollTimer) pollTimer = setInterval(carregar, 2000);
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
          text: j.mensagem || "Rodando em segundo plano. Acompanhe o progresso no card.",
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
