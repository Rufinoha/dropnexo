(function () {
  const lista = document.getElementById("ts_lista");
  const modal = document.getElementById("ts_modal_log");
  const logEl = document.getElementById("ts_log_texto");
  const btnFechar = document.getElementById("ts_modal_fechar");
  const btnOk = document.getElementById("ts_modal_ok");
  if (!lista) return;

  const BASE = "/configuracoes/tarefas-secundarias";
  let pollTimer = null;
  const openIds = new Set();

  const DIAS = [
    ["domingo", "Domingo"],
    ["segunda", "Segunda"],
    ["terca", "Terça"],
    ["quarta", "Quarta"],
    ["quinta", "Quinta"],
    ["sexta", "Sexta"],
    ["sabado", "Sábado"],
    ["diario", "Diário"],
    ["manual", "Somente manual"],
  ];

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

  function labelDia(a) {
    const hit = DIAS.find((d) => d[0] === a);
    return hit ? hit[1] : a || "Manual";
  }

  function labelAgendamento(a, hora, horas) {
    if (a === "manual") return "Somente manual";
    const hs = Array.isArray(horas) && horas.length > 1 ? horas : null;
    if (a === "diario") {
      if (hs) return `Diário · ${hs.join(" · ")}`;
      return `Diário às ${hora || "—"}`;
    }
    if (hs) return `${labelDia(a)} · ${hs.join(" · ")}`;
    return `${labelDia(a)} às ${hora || "—"}`;
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
      meta.hora_slot ? `slot ${meta.hora_slot}` : "",
      meta.site_id ? `Site ${meta.site_id}` : "",
      meta.raiz_idx && meta.raizes_total
        ? `raiz ${meta.raiz_idx}/${meta.raizes_total}`
        : "",
      meta.raiz_nome ? `«${meta.raiz_nome}»` : "",
      meta.nos_visitados != null ? `${meta.nos_visitados} nós` : "",
      meta.folhas != null ? `${meta.folhas} folhas` : "",
      meta.tenants != null ? `${meta.ok || 0}/${meta.tenants} tenants` : "",
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

  function blocoDoador(d) {
    if (!d) {
      return `<p class="TsCfg_Doador is-empty">Doador: nenhum — aguardando 1ª conexão</p>`;
    }
    const cls = d.valido ? "is-ok" : "is-warn";
    const status = d.valido ? "conectado" : "inválido / desconectado";
    return `
      <p class="TsCfg_Doador ${cls}">
        Doador: <strong>${esc(d.nome)}</strong>
        <span class="TsCfg_DoadorMeta">#${esc(d.id_tenant)} · ${esc(status)}</span>
      </p>`;
  }

  function blocoSlots(slots) {
    if (!Array.isArray(slots) || slots.length < 2) return "";
    return `
      <div class="TsCfg_Slots">
        ${slots
          .map((s) => {
            const st = s.status || "nunca";
            const lab =
              st === "sucesso"
                ? "OK"
                : st === "erro"
                  ? "Erro"
                  : st === "rodando"
                    ? "Rodando"
                    : "Pendente";
            return `<span class="TsCfg_Pill ${pillStatus(st)}" title="${esc(
              s.mensagem || fmtData(s.iniciado_em)
            )}">${esc(s.hora)} · ${esc(lab)}</span>`;
          })
          .join("")}
      </div>`;
  }

  function optionsDia(sel) {
    return DIAS.map(
      ([v, l]) =>
        `<option value="${esc(v)}"${v === sel ? " selected" : ""}>${esc(l)}</option>`
    ).join("");
  }

  function render(itens) {
    if (!itens.length) {
      lista.innerHTML =
        '<p class="TsCfg_Hint">Nenhuma tarefa cadastrada. Aplique o SQL 107.</p>';
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
        const horas = t.horas_local || (t.hora_local ? [t.hora_local] : ["02:00"]);
        const hora = horas[0] || "02:00";
        const multi = horas.length > 1;
        const isOpen =
          openIds.has(String(t.id)) || st === "rodando" || travada;
        if (isOpen) openIds.add(String(t.id));
        const temDoador = !!t.doador || t.codigo?.includes("categorias") || t.codigo?.includes("product_types");
        return `
        <article class="TsCfg_Card${isOpen ? " is-open" : ""}" data-codigo="${esc(
          t.codigo
        )}" data-id="${t.id}">
          <button type="button" class="TsCfg_CardSummary" data-acao="toggle" aria-expanded="${
            isOpen ? "true" : "false"
          }">
            <div class="TsCfg_CardSummaryMain">
              <h3>${esc(t.nome)}</h3>
              <div class="TsCfg_Meta">
                <span class="TsCfg_Pill">${esc(
                  labelAgendamento(t.agendamento, hora, horas)
                )}</span>
                <span class="TsCfg_Pill ${pillStatus(st)}">${esc(
                  travada ? "Travada" : stLabel
                )}</span>
              </div>
              ${blocoSlots(t.slots)}
            </div>
            <span class="TsCfg_Chevron" aria-hidden="true"></span>
          </button>
          <div class="TsCfg_CardDetail">
            <p class="TsCfg_Desc">${esc(t.descricao || "")}</p>
            ${temDoador ? blocoDoador(t.doador) : ""}
            ${
              u?.iniciado_em
                ? `<p class="TsCfg_Msg">Última execução: ${esc(fmtData(u.iniciado_em))}</p>`
                : ""
            }
            <form class="TsCfg_Agenda" data-acao-form="agenda">
              <label>
                <span>Dia</span>
                <select name="agendamento">${optionsDia(t.agendamento || "domingo")}</select>
              </label>
              ${
                multi
                  ? `<label class="TsCfg_AgendaWide">
                      <span>Horários (Brasília, separados por vírgula)</span>
                      <input type="text" name="horas_local" value="${esc(
                        horas.join(", ")
                      )}" placeholder="07:00, 10:00, 13:00" required />
                    </label>`
                  : `<label>
                      <span>Hora (Brasília)</span>
                      <input type="time" name="hora_local" value="${esc(hora)}" required />
                    </label>`
              }
              <button type="submit" class="Cl_botaoFiltro">Salvar agenda</button>
            </form>
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

  async function salvarAgenda(codigo, form, btn) {
    if (btn) btn.disabled = true;
    try {
      const fd = new FormData(form);
      const body = {
        agendamento: String(fd.get("agendamento") || "").trim(),
      };
      const horasTxt = String(fd.get("horas_local") || "").trim();
      if (horasTxt) body.horas_local = horasTxt;
      else body.hora_local = String(fd.get("hora_local") || "").trim();
      const r = await fetch(`${BASE}/${encodeURIComponent(codigo)}/agenda`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao salvar agenda.");
      if (window.Swal) {
        Swal.fire({
          icon: "success",
          title: "Agenda salva",
          text: `${labelAgendamento(
            j.item?.agendamento,
            j.item?.hora_local,
            j.item?.horas_local
          )}`,
          confirmButtonColor: "#021F81",
          timer: 1800,
          showConfirmButton: false,
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
      const blocks = itens.map((e) => {
        const slot = e.hora_slot ? ` · slot ${e.hora_slot}` : "";
        return (
          `[#${e.id}] ${e.status} · ${e.disparado_por}${slot} · ${fmtData(e.iniciado_em)}\n` +
          `${e.mensagem || ""}\n` +
          `${"─".repeat(40)}\n` +
          `${e.log_texto || "(sem log)"}\n`
        );
      });
      if (logEl) logEl.textContent = blocks.join("\n");
    }
    modal?.showModal();
  }

  lista.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-acao]");
    const card = ev.target.closest(".TsCfg_Card");
    if (!btn || !card) return;
    const acao = btn.getAttribute("data-acao");
    const id = card.getAttribute("data-id");
    if (acao === "toggle") {
      const open = card.classList.toggle("is-open");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      if (open) openIds.add(id);
      else openIds.delete(id);
      return;
    }
    if (acao === "executar") executar(card.getAttribute("data-codigo"), btn);
    if (acao === "historico") abrirHistorico(id);
  });

  lista.addEventListener("submit", (ev) => {
    const form = ev.target.closest('form[data-acao-form="agenda"]');
    const card = ev.target.closest(".TsCfg_Card");
    if (!form || !card) return;
    ev.preventDefault();
    const btn = form.querySelector('button[type="submit"]');
    salvarAgenda(card.getAttribute("data-codigo"), form, btn);
  });

  btnFechar?.addEventListener("click", () => modal?.close());
  btnOk?.addEventListener("click", () => modal?.close());

  carregar();
})();
