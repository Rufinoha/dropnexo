(function () {
  const elQTenant = document.getElementById("cfgst_tenant_q");
  const elTenant = document.getElementById("cfgst_tenant");
  const elQPed = document.getElementById("cfgst_ped_q");
  const elPedido = document.getElementById("cfgst_pedido");
  const painel = document.getElementById("cfgst_painel");
  const elAtual = document.getElementById("cfgst_atual");
  const elStatus = document.getElementById("cfgst_status");
  const elEfeitos = document.getElementById("cfgst_efeitos");
  const elMotivo = document.getElementById("cfgst_motivo");

  let detalhe = null;

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  async function jsonFetch(url, opts) {
    const r = await fetch(url, Object.assign({ credentials: "same-origin" }, opts || {}));
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Falha.");
    return j;
  }

  function aviso(texto, icone) {
    if (window.Swal) {
      Swal.fire({ icon: icone || "info", title: "Status do pedido", text: texto, confirmButtonColor: "#021F81" });
    }
  }

  async function buscarTenants() {
    const q = (elQTenant.value || "").trim();
    const j = await jsonFetch("/configuracoes/status-pedido/tenants?q=" + encodeURIComponent(q));
    const rows = j.tenants || [];
    elTenant.innerHTML = rows.length
      ? rows.map((t) => `<option value="${t.id}">${esc(t.nome)} · ${esc(t.tipo)} · #${t.id}</option>`).join("")
      : `<option value="">Nenhum tenant</option>`;
    if (rows.length) await buscarPedidos();
  }

  async function buscarPedidos() {
    const id = elTenant.value;
    if (!id) return;
    const q = (elQPed.value || "").trim();
    const j = await jsonFetch(
      "/configuracoes/status-pedido/pedidos?id_tenant=" + encodeURIComponent(id) + "&q=" + encodeURIComponent(q)
    );
    const rows = j.pedidos || [];
    elPedido.innerHTML = rows.length
      ? rows
          .map((p) => {
            const quando = p.criado_em ? new Date(p.criado_em).toLocaleDateString("pt-BR") : "";
            return `<option value="${p.id}">${esc(p.numero)} · ${esc(p.status_rotulo)} · ${esc(p.cliente)} · ${esc(p.fornecedor)}${quando ? " · " + quando : ""}</option>`;
          })
          .join("")
      : `<option value="">Nenhum pedido</option>`;
    if (rows.length) await carregarPedido();
    else {
      detalhe = null;
      painel.hidden = true;
    }
  }

  function pintarEfeitos() {
    if (!detalhe || !elStatus) return;
    const dest = (detalhe.destinos || []).find((d) => d.status === elStatus.value);
    elEfeitos.innerHTML = (dest?.efeitos || []).map((linha) => `<li>${esc(linha)}</li>`).join("");
  }

  async function carregarPedido() {
    const id = elPedido.value;
    if (!id) {
      painel.hidden = true;
      return;
    }
    const j = await jsonFetch("/configuracoes/status-pedido/pedido/" + id);
    detalhe = j.pedido;
    elAtual.textContent =
      (detalhe.numero || "Pedido") +
      " · agora " +
      (detalhe.status_rotulo || detalhe.status) +
      (detalhe.estoque_baixado ? " · estoque já baixado" : " · estoque ainda não baixado");
    elStatus.innerHTML = (detalhe.destinos || [])
      .map((d) => `<option value="${esc(d.status)}">${esc(d.rotulo)}</option>`)
      .join("");
    painel.hidden = false;
    pintarEfeitos();
  }

  async function aplicar() {
    if (!detalhe) return;
    const status = elStatus.value;
    const motivo = (elMotivo.value || "").trim();
    const dest = (detalhe.destinos || []).find((d) => d.status === status);
    if (!dest) return;
    if (motivo.length < 5) {
      aviso("Informe o motivo com pelo menos 5 caracteres.", "warning");
      return;
    }
    const ok = window.Swal
      ? (
          await Swal.fire({
            icon: "warning",
            title: "Alterar para " + dest.rotulo + "?",
            html: "<ul style='text-align:left;margin:0;padding-left:1.1rem'>" +
              dest.efeitos.map((l) => "<li>" + esc(l) + "</li>").join("") +
              "</ul>",
            showCancelButton: true,
            confirmButtonText: "Aplicar",
            cancelButtonText: "Voltar",
            confirmButtonColor: "#021F81",
          })
        ).isConfirmed
      : confirm("Aplicar o status " + dest.rotulo + "?");
    if (!ok) return;
    try {
      const j = await jsonFetch("/configuracoes/status-pedido/aplicar", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id_pedido: detalhe.id, status: status, motivo: motivo }),
      });
      if (window.Swal) {
        Swal.fire({ icon: "success", title: "Status atualizado", text: j.message, confirmButtonColor: "#021F81" });
      }
      elMotivo.value = "";
      await buscarPedidos();
    } catch (e) {
      aviso(e.message || "Erro ao alterar.", "error");
    }
  }

  document.getElementById("cfgst_tenant_buscar")?.addEventListener("click", () => {
    buscarTenants().catch((e) => aviso(e.message, "error"));
  });
  elQTenant?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      buscarTenants().catch((e) => aviso(e.message, "error"));
    }
  });
  elTenant?.addEventListener("change", () => {
    buscarPedidos().catch((e) => aviso(e.message, "error"));
  });
  document.getElementById("cfgst_ped_buscar")?.addEventListener("click", () => {
    buscarPedidos().catch((e) => aviso(e.message, "error"));
  });
  elQPed?.addEventListener("keydown", (ev) => {
    if (ev.key === "Enter") {
      ev.preventDefault();
      buscarPedidos().catch((e) => aviso(e.message, "error"));
    }
  });
  elPedido?.addEventListener("change", () => {
    carregarPedido().catch((e) => aviso(e.message, "error"));
  });
  elStatus?.addEventListener("change", pintarEfeitos);
  document.getElementById("cfgst_aplicar")?.addEventListener("click", aplicar);

  buscarTenants().catch(() => {});
})();
