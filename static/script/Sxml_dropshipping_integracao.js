(function () {
  const BASE = "/api/integracoes/xml-dropshipping";
  const badge = document.getElementById("xml_status_badge");
  const secGuia = document.getElementById("xml_sec_guia");
  const painel = document.getElementById("xml_painel");
  const msgEl = document.getElementById("xml_msg");
  const msgGuia = document.getElementById("xml_msg_guia");
  const ultimaEl = document.getElementById("xml_ultima_sync");
  const catLista = document.getElementById("xml_cat_lista");
  let catsDrop = [];

  function showMsg(el, text, ok) {
    if (!el) return;
    el.hidden = !text;
    el.textContent = text || "";
    el.style.color = ok ? "#15803d" : "#b91c1c";
  }

  function setConectado(on) {
    if (badge) {
      badge.textContent = on ? "Conectado" : "Desconectado";
      badge.classList.toggle("is-on", !!on);
      badge.classList.toggle("is-off", !on);
    }
    if (secGuia) secGuia.hidden = !!on;
    if (painel) painel.hidden = !on;
  }

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
        '<p class="Mp_Hint">Nenhuma categoria no cache ainda. Rode «Sincronizar estoque agora».</p>';
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
    }
    if (ultimaEl) {
      ultimaEl.textContent = j.ultima_sync
        ? `Última sync: ${new Date(j.ultima_sync).toLocaleString("pt-BR")}${
            j.ultimo_erro ? " · erro: " + j.ultimo_erro : ""
          }`
        : "Ainda não sincronizou.";
    }
    if (j.conectado) await carregarMapCats();
  }

  document.getElementById("xml_btn_conectar")?.addEventListener("click", async () => {
    const btn = document.getElementById("xml_btn_conectar");
    if (btn) btn.disabled = true;
    showMsg(msgGuia, "Conectando e importando o feed… isso pode levar alguns minutos.", true);
    try {
      const body = {
        url_xml: document.getElementById("xml_url")?.value || "",
        ...readOrigem(),
      };
      const r = await fetch(`${BASE}/conectar`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao conectar.");
      showMsg(msgGuia, j.message || "Conectado.", true);
      if (window.Swal) {
        Swal.fire({
          icon: "success",
          title: "Feed conectado",
          text: j.message || "Produtos no Catálogo. Ative os que quiser.",
          confirmButtonColor: "#021F81",
        });
      }
      await status();
    } catch (e) {
      showMsg(msgGuia, e.message, false);
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  document.getElementById("xml_btn_sync")?.addEventListener("click", async () => {
    const btn = document.getElementById("xml_btn_sync");
    if (btn) btn.disabled = true;
    showMsg(msgEl, "Atualizando estoque e catálogo…", true);
    try {
      const r = await fetch(`${BASE}/sincronizar`, {
        method: "POST",
        credentials: "same-origin",
      });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha no sync.");
      showMsg(msgEl, j.mensagem || "Estoque atualizado.", true);
      await status();
    } catch (e) {
      showMsg(msgEl, e.message, false);
    } finally {
      if (btn) btn.disabled = false;
    }
  });

  document.getElementById("xml_btn_desconectar")?.addEventListener("click", async () => {
    if (!confirm("Desconectar o feed XML? O acervo deixa de aparecer no Catálogo.")) return;
    const r = await fetch(`${BASE}/desconectar`, { method: "POST", credentials: "same-origin" });
    const j = await r.json();
    if (!j.success) {
      alert(j.message || "Falha ao desconectar.");
      return;
    }
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
