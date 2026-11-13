(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);
  let cache = [];

  async function api(url, opts) {
    const r = await fetch(url, {
      credentials: "include",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      ...(opts || {}),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok || j.success === false) throw new Error(j.message || "Falha na requisição");
    return j;
  }

  function toast(title, text, icon) {
    if (window.Swal) Swal.fire({ icon: icon || "info", title, text, confirmButtonColor: "#021F81" });
    else alert(title + (text ? "\n" + text : ""));
  }

  function esc(v) {
    return String(v ?? "").replace(/[&<>"']/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
    );
  }

  function badgeStatus(item) {
    if (!item.ativo) return '<span class="AeAdm_Badge AeAdm_Badge--off">desligado</span>';
    const st = String(item.status || "ativo");
    if (st === "erro") return '<span class="AeAdm_Badge AeAdm_Badge--err">erro</span>';
    if (st === "atencao") return '<span class="AeAdm_Badge AeAdm_Badge--warn">atenção</span>';
    return '<span class="AeAdm_Badge AeAdm_Badge--ok">ativo</span>';
  }

  function abrirModal(item) {
    const editando = !!(item && item.id_tenant);
    $("ae_editando").value = editando ? "1" : "0";
    $("ae_modal_titulo").textContent = editando ? "Editar liberação" : "Liberar tenant";
    $("ae_busca_wrap").hidden = editando;
    $("ae_tenant").value = item?.id_tenant || "";
    $("ae_tenant").readOnly = editando;
    $("ae_nome").value = item?.nome_parceiro || "";
    $("ae_contato").value = item?.contato_tecnico || "";
    $("ae_ambiente").value = item?.ambiente === "producao" ? "producao" : "homologacao";
    $("ae_busca").value = "";
    $("ae_sugestoes").innerHTML = "";
    $("ae_modal").hidden = false;
    document.body.style.overflow = "hidden";
    if (!editando) $("ae_busca").focus();
    else $("ae_nome").focus();
  }

  function fecharModal() {
    $("ae_modal").hidden = true;
    document.body.style.overflow = "";
  }

  function renderLista(itens) {
    const tbody = $("ae_tbody");
    if (!itens.length) {
      tbody.innerHTML = '<tr><td colspan="7" class="CfgCup_Hint">Nenhum tenant liberado ainda.</td></tr>';
      return;
    }
    tbody.innerHTML = itens
      .map((i) => {
        const sync = i.ultima_sync_em
          ? `${esc(i.ultima_sync_em)}<br><small>${esc(i.ultima_mensagem || "")}</small>`
          : "—";
        return `<tr>
          <td><strong>#${esc(i.id_tenant)}</strong><br><small>${esc(i.tenant_nome || "")}</small></td>
          <td>${esc(i.nome_parceiro || "—")}</td>
          <td>${esc(i.contato_tecnico || "—")}</td>
          <td>${esc(i.ambiente || "—")}</td>
          <td>${badgeStatus(i)}</td>
          <td>${sync}</td>
          <td class="Cl_TableActions">
            <button type="button" class="Cl_BtnCancelar ae-editar" data-id="${esc(i.id_tenant)}">Editar</button>
            <button type="button" class="Cl_BtnCancelar ae-revogar" data-id="${esc(i.id_tenant)}">Revogar</button>
          </td>
        </tr>`;
      })
      .join("");

    tbody.querySelectorAll(".ae-editar").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = Number(btn.dataset.id);
        const item = cache.find((x) => Number(x.id_tenant) === id);
        if (item) abrirModal(item);
      });
    });
    tbody.querySelectorAll(".ae-revogar").forEach((btn) => {
      btn.addEventListener("click", async () => {
        const id = Number(btn.dataset.id);
        const ok = window.Swal
          ? (
              await Swal.fire({
                icon: "warning",
                title: "Revogar?",
                text: "O card some das Integrações deste tenant.",
                showCancelButton: true,
                confirmButtonText: "Revogar",
                cancelButtonText: "Cancelar",
                confirmButtonColor: "#991b1b",
              })
            ).isConfirmed
          : confirm("Revogar liberação?");
        if (!ok) return;
        try {
          await api("/api/configuracoes/api-externa/revogar", {
            method: "POST",
            body: JSON.stringify({ id_tenant: id }),
          });
          toast("Revogado", "Liberação removida.", "success");
          await carregar();
        } catch (e) {
          toast("Erro", e.message, "error");
        }
      });
    });
  }

  async function carregar() {
    const termo = ($("ae_filtro")?.value || "").trim();
    const j = await api("/api/configuracoes/api-externa/listar?termo=" + encodeURIComponent(termo));
    cache = j.dados || [];
    renderLista(cache);
  }

  let buscaTimer = null;
  $("ae_busca")?.addEventListener("input", () => {
    clearTimeout(buscaTimer);
    buscaTimer = setTimeout(async () => {
      const termo = ($("ae_busca").value || "").trim();
      const box = $("ae_sugestoes");
      if (!termo) {
        box.innerHTML = "";
        return;
      }
      try {
        const j = await api(
          "/api/configuracoes/api-externa/buscar-tenants?termo=" + encodeURIComponent(termo)
        );
        const itens = j.dados || [];
        if (!itens.length) {
          box.innerHTML = "<small>Nenhum tenant encontrado.</small>";
          return;
        }
        box.innerHTML = itens
          .map(
            (t) =>
              `<button type="button" class="ae-pick" data-id="${t.id}">#${t.id} — ${esc(t.nome)}${t.liberado ? " (já liberado)" : ""}</button>`
          )
          .join("");
        box.querySelectorAll(".ae-pick").forEach((b) => {
          b.addEventListener("click", () => {
            $("ae_tenant").value = b.dataset.id;
            box.innerHTML = "";
          });
        });
      } catch (e) {
        box.innerHTML = `<small>${esc(e.message)}</small>`;
      }
    }, 280);
  });

  $("ae_btnNovo")?.addEventListener("click", () => abrirModal(null));
  $("ae_modal_fechar")?.addEventListener("click", fecharModal);
  $("ae_btnCancelar")?.addEventListener("click", fecharModal);
  $("ae_modal")?.addEventListener("click", (ev) => {
    if (ev.target === $("ae_modal")) fecharModal();
  });
  document.addEventListener("keydown", (ev) => {
    if (ev.key === "Escape" && !$("ae_modal").hidden) fecharModal();
  });

  $("ae_btnSalvar")?.addEventListener("click", async () => {
    try {
      const id_tenant = Number($("ae_tenant")?.value || 0);
      if (!id_tenant) throw new Error("Informe o tenant.");
      await api("/api/configuracoes/api-externa/liberar", {
        method: "POST",
        body: JSON.stringify({
          id_tenant,
          nome_parceiro: $("ae_nome")?.value || "",
          contato_tecnico: $("ae_contato")?.value || "",
          ambiente: $("ae_ambiente")?.value || "homologacao",
        }),
      });
      fecharModal();
      toast("Salvo", "Tenant liberado / atualizado.", "success");
      await carregar();
    } catch (e) {
      toast("Erro", e.message, "error");
    }
  });

  let filtroTimer = null;
  $("ae_filtro")?.addEventListener("input", () => {
    clearTimeout(filtroTimer);
    filtroTimer = setTimeout(() => carregar().catch(() => {}), 250);
  });

  carregar().catch((e) => {
    $("ae_tbody").innerHTML = `<tr><td colspan="7" class="CfgCup_Hint">${esc(e.message)}</td></tr>`;
  });
})();
