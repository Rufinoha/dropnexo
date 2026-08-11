(function () {
  const BASE = "/api/integracoes/xml-dropshipping";
  const badge = document.getElementById("xml_status_badge");
  const secGuia = document.getElementById("xml_sec_guia");
  const painel = document.getElementById("xml_painel");
  const msgEl = document.getElementById("xml_msg");
  const msgGuia = document.getElementById("xml_msg_guia");
  const msgEstoque = document.getElementById("xml_msg_estoque");
  const ultimaEl = document.getElementById("xml_ultima_sync");
  const slotsEl = document.getElementById("xml_slots_status");
  const urlResumo = document.getElementById("xml_url_resumo");
  const catLista = document.getElementById("xml_cat_lista");
  let catsDrop = [];

  function showMsg(el, text, ok) {
    if (!el) return;
    el.hidden = !text;
    el.textContent = text || "";
    el.style.color = ok ? "#15803d" : "#b91c1c";
  }

  function makeProgress(prefix) {
    const root = document.getElementById(`xml_progress_${prefix}`);
    const fill = document.getElementById(`xml_progress_${prefix}_fill`);
    const label = document.getElementById(`xml_progress_${prefix}_label`);
    const stepsEl = document.getElementById(`xml_progress_${prefix}_steps`);
    let timer = null;
    let step = 0;
    const labels = {
      conectar: [
        "Baixando o XML da Revenda de Calçados…",
        "Salvando conexão e depósito…",
        "Importando produtos no Catálogo…",
        "Quase lá — finalizando…",
      ],
      sync: [
        "Baixando o feed…",
        "Atualizando estoque e preços…",
        "Zerando produtos ausentes…",
        "Finalizando sincronização…",
      ],
    };

    function paint(active, doneAll, erro) {
      if (!stepsEl) return;
      stepsEl.querySelectorAll("li").forEach((li) => {
        const n = Number(li.getAttribute("data-step"));
        li.classList.toggle("is-done", doneAll || n < active);
        li.classList.toggle("is-active", !doneAll && !erro && n === active);
        li.classList.toggle("is-error", !!erro && n === active);
      });
    }

    return {
      start() {
        if (!root) return;
        root.hidden = false;
        step = 0;
        if (fill) {
          fill.style.width = "12%";
          fill.classList.add("is-pulse");
        }
        if (label) {
          label.style.color = "";
          label.textContent = (labels[prefix] || [])[0] || "Processando…";
        }
        paint(0, false, false);
        clearInterval(timer);
        timer = setInterval(() => {
          if (step < 3) step += 1;
          const pct = [12, 38, 62, 82][step] || 82;
          if (fill) fill.style.width = `${pct}%`;
          if (label) label.textContent = (labels[prefix] || [])[step] || "Processando…";
          paint(step, false, false);
        }, 4500);
      },
      done(ok, finalText) {
        clearInterval(timer);
        timer = null;
        if (!root) return;
        if (fill) {
          fill.classList.remove("is-pulse");
          fill.style.width = ok ? "100%" : `${[12, 38, 62, 82][step] || 40}%`;
        }
        if (label) {
          label.textContent = finalText || (ok ? "Concluído." : "Falhou.");
          label.style.color = ok ? "#15803d" : "#b91c1c";
        }
        paint(step, !!ok, !ok);
        if (ok) {
          setTimeout(() => {
            root.hidden = true;
            if (label) label.style.color = "";
            if (fill) fill.style.width = "8%";
          }, 1600);
        }
      },
      hide() {
        clearInterval(timer);
        timer = null;
        if (root) root.hidden = true;
        if (label) label.style.color = "";
        if (fill) {
          fill.classList.remove("is-pulse");
          fill.style.width = "8%";
        }
      },
    };
  }

  const progConectar = makeProgress("conectar");
  const progSync = makeProgress("sync");

  function setConectado(on) {
    if (badge) {
      badge.textContent = on ? "Conectado" : "Desconectado";
      badge.classList.toggle("is-on", !!on);
      badge.classList.toggle("is-off", !on);
    }
    if (secGuia) secGuia.hidden = !!on;
    if (painel) painel.hidden = !on;
  }

  function ativarAba(nome) {
    document.querySelectorAll(".XmlTabs__btn").forEach((btn) => {
      const on = btn.getAttribute("data-tab") === nome;
      btn.classList.toggle("is-active", on);
      btn.setAttribute("aria-selected", on ? "true" : "false");
    });
    document.querySelectorAll(".XmlTabPanel").forEach((panel) => {
      const on = panel.getAttribute("data-panel") === nome;
      panel.classList.toggle("is-active", on);
      panel.hidden = !on;
    });
    if (nome === "categorias") carregarMapCats();
  }

  document.querySelectorAll(".XmlTabs__btn").forEach((btn) => {
    btn.addEventListener("click", () => ativarAba(btn.getAttribute("data-tab")));
  });

  function fillOrigem(cfg) {
    const map = [
      ["xml_origem_nome", "origem_nome"],
      ["xml_origem_documento", "origem_documento"],
      ["xml_origem_telefone", "origem_telefone"],
      ["xml_origem_cep", "origem_cep"],
      ["xml_origem_logradouro", "origem_logradouro"],
      ["xml_origem_numero", "origem_numero"],
      ["xml_origem_complemento", "origem_complemento"],
      ["xml_origem_bairro", "origem_bairro"],
      ["xml_origem_cidade", "origem_cidade"],
      ["xml_origem_uf", "origem_uf"],
    ];
    for (const [id, key] of map) {
      const el = document.getElementById(id);
      if (el) el.value = cfg[key] || "";
    }
  }

  function readOrigem() {
    return {
      origem_nome: document.getElementById("xml_origem_nome")?.value || "",
      origem_documento: document.getElementById("xml_origem_documento")?.value || "",
      origem_telefone: document.getElementById("xml_origem_telefone")?.value || "",
      origem_cep: document.getElementById("xml_origem_cep")?.value || "",
      origem_logradouro: document.getElementById("xml_origem_logradouro")?.value || "",
      origem_numero: document.getElementById("xml_origem_numero")?.value || "",
      origem_complemento: document.getElementById("xml_origem_complemento")?.value || "",
      origem_bairro: document.getElementById("xml_origem_bairro")?.value || "",
      origem_cidade: document.getElementById("xml_origem_cidade")?.value || "",
      origem_uf: document.getElementById("xml_origem_uf")?.value || "",
    };
  }

  function pillSlot(st) {
    if (st === "sucesso") return "is-ok";
    if (st === "erro") return "is-err";
    if (st === "rodando") return "is-run";
    return "is-skip";
  }

  function labelSlot(st) {
    if (st === "sucesso") return "OK";
    if (st === "erro") return "Erro";
    if (st === "rodando") return "Rodando";
    return "Pendente";
  }

  function renderSlots(slots) {
    if (!slotsEl) return;
    const list = Array.isArray(slots) && slots.length
      ? slots
      : ["07:00", "10:00", "13:00", "16:00", "19:00"].map((h) => ({
          hora: h,
          status: "nunca",
        }));
    slotsEl.innerHTML = `
      <p class="Mp_Hint" style="margin:0 0 0.45rem">Status dos horários (hoje / última execução do slot)</p>
      <div class="XmlSlots__row">
        ${list
          .map(
            (s) =>
              `<span class="XmlSlots__pill ${pillSlot(s.status)}" title="${escapeHtml(
                s.mensagem || ""
              )}">${escapeHtml(s.hora)} · ${escapeHtml(labelSlot(s.status))}</span>`
          )
          .join("")}
      </div>`;
  }

  async function carregarCatsDrop() {
    try {
      const r = await fetch("/vendedor/categorias/arvore", { credentials: "same-origin" });
      const j = await r.json();
      const opcoes = j.opcoes || [];
      catsDrop = opcoes.map((c) => ({
        id: c.id,
        nome: c.caminho || c.nome || `#${c.id}`,
      }));
    } catch {
      catsDrop = [];
    }
  }

  function optionsCat(selId) {
    const opts = ['<option value="">— sem mapear —</option>'];
    for (const c of catsDrop) {
      opts.push(
        `<option value="${c.id}"${String(c.id) === String(selId || "") ? " selected" : ""}>${escapeHtml(
          c.nome
        )}</option>`
      );
    }
    return opts.join("");
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function carregarMapCats() {
    if (!catLista) return;
    await carregarCatsDrop();
    const r = await fetch(`${BASE}/categorias/mapeamento`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      catLista.textContent = j.message || "Falha ao carregar categorias.";
      return;
    }
    const itens = j.itens || [];
    if (!itens.length) {
      catLista.innerHTML =
        '<p class="Mp_Hint">Nenhuma categoria ainda. Rode «Sincronizar estoque agora» na aba Estoque.</p>';
      return;
    }
    catLista.innerHTML = `
      <table class="Mp_Hint" style="width:100%;border-collapse:collapse">
        <thead><tr><th align="left">Feed</th><th align="left">DropNexo</th></tr></thead>
        <tbody>
          ${itens
            .map(
              (it) => `
            <tr data-key="${escapeHtml(it.category_key)}">
              <td style="padding:0.35rem 0.5rem 0.35rem 0">${escapeHtml(it.nome_feed)}</td>
              <td style="padding:0.35rem 0"><select class="Cl_Input xml-cat-sel">${optionsCat(
                it.id_categoria
              )}</select></td>
            </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
  }

  async function status() {
    const r = await fetch(`${BASE}/status`, { credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) return;
    setConectado(!!j.conectado);
    fillOrigem(j);
    if (j.url_xml) {
      const u = document.getElementById("xml_url");
      if (u && !u.value) u.value = j.url_xml;
      if (urlResumo) urlResumo.textContent = `URL: ${j.url_xml}`;
    }
    if (ultimaEl) {
      ultimaEl.textContent = j.ultima_sync
        ? `Última sync desta conta: ${new Date(j.ultima_sync).toLocaleString("pt-BR")}${
            j.ultimo_erro ? " · erro: " + j.ultimo_erro : ""
          }`
        : "Ainda não sincronizou nesta conta.";
    }
    if (j.conectado) {
      const slots = j.agenda_sync?.slots || [];
      renderSlots(slots);
      const abaAtiva = document.querySelector(".XmlTabs__btn.is-active")?.getAttribute("data-tab");
      if (abaAtiva === "categorias") await carregarMapCats();
    }
  }

  document.getElementById("xml_btn_conectar")?.addEventListener("click", async () => {
    const btn = document.getElementById("xml_btn_conectar");
    const url = (document.getElementById("xml_url")?.value || "").trim();
    if (!url) {
      showMsg(msgGuia, "Cole a URL XML da Revenda de Calçados.", false);
      return;
    }
    if (btn) btn.disabled = true;
    showMsg(msgGuia, "", true);
    progConectar.start();
    try {
      const body = { url_xml: url, ...readOrigem() };
      const r = await fetch(`${BASE}/conectar`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao conectar.");
      progConectar.done(true, "Conectado — produtos no Catálogo.");
      showMsg(msgGuia, j.message || "Conectado.", true);
      if (window.Swal) {
        Swal.fire({
          icon: "success",
          title: "Revenda de Calçados conectada",
          text: j.message || "Produtos no Catálogo. Ative os que quiser.",
          confirmButtonColor: "#021F81",
        });
      }
      await status();
      ativarAba("estoque");
    } catch (e) {
      progConectar.done(false, "Não foi possível conectar.");
      showMsg(msgGuia, e.message, false);
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  document.getElementById("xml_btn_sync")?.addEventListener("click", async () => {
    const btn = document.getElementById("xml_btn_sync");
    if (btn) btn.disabled = true;
    showMsg(msgEstoque, "", true);
    progSync.start();
    try {
      const r = await fetch(`${BASE}/sincronizar`, {
        method: "POST",
        credentials: "same-origin",
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha no sync.");
      progSync.done(true, "Estoque atualizado.");
      showMsg(msgEstoque, j.mensagem || "Estoque atualizado.", true);
      await status();
    } catch (e) {
      progSync.done(false, "Falha na sincronização.");
      showMsg(msgEstoque, e.message, false);
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  document.getElementById("xml_btn_desconectar")?.addEventListener("click", async () => {
    if (!confirm("Desconectar o feed da Revenda de Calçados? O acervo deixa de aparecer no Catálogo."))
      return;
    const r = await fetch(`${BASE}/desconectar`, { method: "POST", credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      alert(j.message || "Falha ao desconectar.");
      return;
    }
    progConectar.hide();
    progSync.hide();
    await status();
  });

  document.getElementById("xml_btn_salvar_origem")?.addEventListener("click", async () => {
    const r = await fetch(`${BASE}/salvar-origem`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readOrigem()),
    });
    const j = await r.json();
    showMsg(msgEl, j.message || (j.success ? "Salvo." : "Erro"), !!j.success);
    if (j.success) ativarAba("integracao");
  });

  document.getElementById("xml_btn_salvar_cats")?.addEventListener("click", async () => {
    const rows = catLista?.querySelectorAll("tr[data-key]") || [];
    const itens = [];
    rows.forEach((tr) => {
      const key = tr.getAttribute("data-key");
      const sel = tr.querySelector("select");
      itens.push({
        category_key: key,
        id_categoria: sel?.value ? Number(sel.value) : null,
      });
    });
    const r = await fetch(`${BASE}/categorias/mapeamento`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ itens }),
    });
    const j = await r.json();
    showMsg(msgEl, j.message || (j.success ? "Mapeamentos salvos." : "Erro"), !!j.success);
  });

  status();
})();
