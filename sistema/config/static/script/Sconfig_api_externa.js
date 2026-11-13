(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

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

  function renderLista(itens) {
    const box = $("ae_lista");
    if (!box) return;
    if (!itens.length) {
      box.innerHTML = '<p class="HsCfg_Hint">Nenhum tenant liberado ainda.</p>';
      return;
    }
    box.innerHTML = `
      <table class="Fin_Table" style="width:100%;font-size:.9rem">
        <thead><tr>
          <th>Tenant</th><th>Parceiro</th><th>Status</th><th>Ambiente</th><th></th>
        </tr></thead>
        <tbody>
          ${itens
            .map(
              (i) => `<tr>
            <td>#${i.id_tenant} — ${i.tenant_nome || ""}</td>
            <td>${i.nome_parceiro || "—"}</td>
            <td>${i.ativo ? i.status || "ativo" : "desligado"}</td>
            <td>${i.ambiente || "—"}</td>
            <td><button type="button" class="Cl_BtnCancelar ae-revogar" data-id="${i.id_tenant}">Revogar</button></td>
          </tr>`
            )
            .join("")}
        </tbody>
      </table>`;
    box.querySelectorAll(".ae-revogar").forEach((btn) => {
      btn.addEventListener("click", async () => {
        try {
          await api("/api/configuracoes/api-externa/revogar", {
            method: "POST",
            body: JSON.stringify({ id_tenant: Number(btn.dataset.id) }),
          });
          toast("Revogado", "Card removido das Integrações do tenant.", "success");
          carregar();
        } catch (e) {
          toast("Erro", e.message, "error");
        }
      });
    });
  }

  async function carregar() {
    const termo = ($("ae_filtro")?.value || "").trim();
    const j = await api("/api/configuracoes/api-externa/listar?termo=" + encodeURIComponent(termo));
    renderLista(j.dados || []);
  }

  let buscaTimer = null;
  $("ae_busca")?.addEventListener("input", () => {
    clearTimeout(buscaTimer);
    buscaTimer = setTimeout(async () => {
      const termo = ($("ae_busca").value || "").trim();
      const box = $("ae_sugestoes");
      if (!termo) {
        box.textContent = "";
        return;
      }
      try {
        const j = await api(
          "/api/configuracoes/api-externa/buscar-tenants?termo=" + encodeURIComponent(termo)
        );
        const itens = j.dados || [];
        if (!itens.length) {
          box.textContent = "Nenhum tenant encontrado.";
          return;
        }
        box.innerHTML = itens
          .map(
            (t) =>
              `<button type="button" class="Cl_BtnLink ae-pick" data-id="${t.id}" style="display:block;margin:.25rem 0">#${t.id} — ${t.nome}${t.liberado ? " (já liberado)" : ""}</button>`
          )
          .join("");
        box.querySelectorAll(".ae-pick").forEach((b) => {
          b.addEventListener("click", () => {
            $("ae_tenant").value = b.dataset.id;
            box.textContent = "";
          });
        });
      } catch (e) {
        box.textContent = e.message;
      }
    }, 300);
  });

  $("ae_btnLiberar")?.addEventListener("click", async () => {
    try {
      const id_tenant = Number($("ae_tenant")?.value || 0);
      await api("/api/configuracoes/api-externa/liberar", {
        method: "POST",
        body: JSON.stringify({
          id_tenant,
          nome_parceiro: $("ae_nome")?.value || "",
          contato_tecnico: $("ae_contato")?.value || "",
          ambiente: $("ae_ambiente")?.value || "homologacao",
        }),
      });
      toast("Liberado", "O card API Externa aparece em Integrações desse tenant.", "success");
      carregar();
    } catch (e) {
      toast("Erro", e.message, "error");
    }
  });

  $("ae_filtro")?.addEventListener("change", () => carregar().catch(() => {}));
  carregar().catch((e) => toast("Erro", e.message, "error"));
})();
