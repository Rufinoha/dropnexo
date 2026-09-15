(function () {
  const BASE = "/configuracoes/manutencao-tenant";
  const el = {
    busca: document.getElementById("ob_filtroBusca"),
    tipo: document.getElementById("ob_filtroTipo"),
    ativo: document.getElementById("ob_filtroAtivo"),
    btnFiltrar: document.getElementById("ob_btnFiltrar"),
    btnLimpar: document.getElementById("ob_btnLimpar"),
    lista: document.getElementById("ob_listaTenants"),
  };
  if (!el.lista) return;

  function esc(s) {
    return String(s ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/"/g, "&quot;");
  }

  function badgeTipo(t) {
    const x = (t || "vendedor").toLowerCase();
    return `<span class="CfgMt_Badge CfgMt_Badge--${esc(x)}">${esc(x)}</span>`;
  }

  function formatarDataHora(iso) {
    if (!iso) return "—";
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) {
      const s = String(iso).replace("T", " ");
      return esc(s.length >= 16 ? s.slice(0, 16) : s);
    }
    const pad = (n) => String(n).padStart(2, "0");
    return (
      `${pad(d.getDate())}/${pad(d.getMonth() + 1)}/${d.getFullYear()} ` +
      `${pad(d.getHours())}:${pad(d.getMinutes())}`
    );
  }

  function abrirApoio(id) {
    window.GlobalUtils?.abrirJanelaApoioModal({
      rota: `${BASE}/editar`,
      id: id || null,
      titulo: id ? `Editar tenant #${id}` : "Tenant",
      largura: 920,
      altura: 680,
      nivel: 1,
    });
  }

  async function carregar() {
    const qs = new URLSearchParams();
    const q = (el.busca?.value || "").trim();
    const tipo = (el.tipo?.value || "").trim();
    const ativo = (el.ativo?.value || "").trim();
    if (q) qs.set("q", q);
    if (tipo) qs.set("tipo", tipo);
    if (ativo !== "") qs.set("ativo", ativo);
    el.lista.innerHTML = `<tr><td colspan="9">Carregando…</td></tr>`;
    try {
      const r = await fetch(`${BASE}/dados?${qs}`, { credentials: "same-origin" });
      const j = await r.json();
      if (!r.ok || !j.success) throw new Error(j.message || "Falha ao listar.");
      const itens = j.itens || [];
      if (!itens.length) {
        el.lista.innerHTML = `<tr><td colspan="9">Nenhum tenant encontrado.</td></tr>`;
        return;
      }
      const util = window.Util || { gerarIconeTech: () => "…" };
      el.lista.innerHTML = itens
        .map((t) => {
          const sessao = t.eh_tenant_sessao
            ? ' <span class="CfgMt_Badge CfgMt_Badge--sessao">sessão</span>'
            : "";
          const bloqueado = !!(t.eh_tenant_sessao || t.protegido);
          const titleExcluir = t.protegido
            ? "Tenant protegido"
            : t.eh_tenant_sessao
              ? "Não exclua o tenant da sessão atual"
              : "Excluir";
          const ehCnpj =
            String(t.tipo_pessoa || "").toUpperCase() === "J" ||
            String(t.documento || "").replace(/\D+/g, "").length === 14;
          const razao = ehCnpj ? esc(t.razao_social || "") || "—" : "—";
          return `
        <tr data-id="${t.id}">
          <td class="CfgMt_ColId">${t.id}</td>
          <td class="CfgMt_ColNome"><strong>${esc(t.nome)}</strong>${sessao}</td>
          <td class="CfgMt_ColRazao">${razao}</td>
          <td class="CfgMt_ColTipo">${badgeTipo(t.tipo_negocio)}</td>
          <td class="CfgMt_ColPlano">${esc(t.plano)}</td>
          <td class="CfgMt_ColAtivo">${t.ativo ? "Sim" : "Não"}</td>
          <td class="CfgMt_ColData">${formatarDataHora(t.criado_em)}</td>
          <td class="CfgMt_ColData">${formatarDataHora(t.dono_ultimo_acesso)}</td>
          <td class="Cl_TableActions CfgMt_ColAcoes">
            <button type="button" class="Cl_BtnAcao btnEditar" data-id="${t.id}" title="Editar">${util.gerarIconeTech("editar")}</button>
            <button type="button" class="Cl_BtnAcao btnExcluir" data-id="${t.id}" data-slug="${esc(t.slug)}" data-nome="${esc(t.nome)}" title="${titleExcluir}" ${bloqueado ? "disabled" : ""}>${util.gerarIconeTech("excluir")}</button>
          </td>
        </tr>`;
        })
        .join("");
      window.lucide?.createIcons?.();
      window.Util?.gerarIconeTech?.refresh?.();
    } catch (e) {
      el.lista.innerHTML = `<tr><td colspan="9">${esc(e.message)}</td></tr>`;
    }
  }
  async function excluir(id, slug, nome) {
    if (!id || !slug) return;
    const c1 = await Swal.fire({
      icon: "warning",
      title: "Excluir tenant permanentemente?",
      html:
        `Isso remove <strong>${esc(nome || slug)}</strong> (#${id}) e todos os dados ligados ` +
        `(produtos, pedidos, usuários, integrações, etc.).<br><br>` +
        `<small>Ação irreversível — use só para tenants de teste.</small>`,
      showCancelButton: true,
      confirmButtonText: "Continuar",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
    });
    if (!c1.isConfirmed) return;

    const c2 = await Swal.fire({
      icon: "warning",
      title: "Confirme digitando o slug",
      html: `Digite <strong>${esc(slug)}</strong> para confirmar a exclusão.`,
      input: "text",
      inputPlaceholder: slug,
      showCancelButton: true,
      confirmButtonText: "Excluir de vez",
      cancelButtonText: "Cancelar",
      confirmButtonColor: "#b91c1c",
      preConfirm: (v) => {
        if ((v || "").trim().toLowerCase() !== String(slug).toLowerCase()) {
          Swal.showValidationMessage("Slug não confere.");
          return false;
        }
        return (v || "").trim();
      },
    });
    if (!c2.isConfirmed) return;

    Swal.fire({
      title: "Excluindo…",
      text: "Removendo dados em cascata. Pode demorar alguns segundos.",
      allowOutsideClick: false,
      didOpen: () => Swal.showLoading(),
    });
    const r = await fetch(`${BASE}/excluir`, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ id, confirm_slug: c2.value }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || !j.success) {
      throw new Error(j.message || "Falha ao excluir.");
    }
    await Swal.fire({
      icon: "success",
      title: "Tenant excluído",
      text: j.message || "Concluído.",
      confirmButtonColor: "#021F81",
    });
    await carregar();
  }

  el.btnFiltrar?.addEventListener("click", () => carregar());
  el.btnLimpar?.addEventListener("click", () => {
    if (el.busca) el.busca.value = "";
    if (el.tipo) el.tipo.value = "";
    if (el.ativo) el.ativo.value = "";
    carregar();
  });
  el.busca?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      carregar();
    }
  });
  el.lista.addEventListener("click", async (ev) => {
    const btn = ev.target.closest("button");
    if (!btn) return;
    const id = Number(btn.dataset.id || 0);
    if (!id) return;
    try {
      if (btn.classList.contains("btnEditar")) return abrirApoio(id);
      if (btn.classList.contains("btnExcluir")) {
        return await excluir(id, btn.dataset.slug || "", btn.dataset.nome || "");
      }
    } catch (e) {
      await Swal.fire("Erro", e.message, "error");
    }
  });

  window.addEventListener("message", (event) => {
    if (event.data?.grupo === "atualizarTabela") {
      carregar().catch((e) => Swal.fire("Erro", e.message, "error"));
    }
  });

  carregar();
})();
