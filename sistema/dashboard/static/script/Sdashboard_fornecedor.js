(function () {
  const root = document.getElementById("dash_fn");
  if (!root) return;

  const loading = document.getElementById("dash_fn_loading");
  const erro = document.getElementById("dash_fn_erro");
  const alertasWrap = document.getElementById("dash_fn_alertas_wrap");
  const alertasEl = document.getElementById("dash_fn_alertas");
  const okEl = document.getElementById("dash_fn_ok");
  const pedidosEl = document.getElementById("dash_fn_pedidos");

  function esc(s) {
    const d = document.createElement("div");
    d.textContent = s == null ? "" : String(s);
    return d.innerHTML;
  }

  function fmtData(iso) {
    if (!iso) return "—";
    try {
      return new Date(iso).toLocaleString("pt-BR", {
        day: "2-digit",
        month: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return iso;
    }
  }

  function setKpis(k) {
    const map = {
      pedidos: k.pedidos_7d ?? 0,
      fat: k.faturamento_7d_fmt || "R$ 0,00",
      vendedores: k.vendedores_ativos ?? 0,
      aguardando: k.aguardando ?? 0,
    };
    Object.entries(map).forEach(([key, val]) => {
      const el = root.querySelector('[data-k="' + key + '"]');
      if (el) el.textContent = String(val);
    });
  }

  function renderAlertas(list) {
    if (!alertasEl || !alertasWrap || !okEl) return;
    if (!list.length) {
      alertasWrap.hidden = true;
      alertasEl.innerHTML = "";
      okEl.hidden = false;
      return;
    }
    okEl.hidden = true;
    alertasWrap.hidden = false;
    alertasEl.innerHTML = list
      .map((a) => {
        const nivel = a.nivel || "baixa";
        return (
          '<article class="DashVd_Alerta is-' +
          esc(nivel) +
          '">' +
          '<div><p class="DashVd_AlertaTitulo">' +
          esc(a.titulo) +
          '</p><p class="DashVd_AlertaTexto">' +
          esc(a.texto) +
          "</p></div>" +
          (a.url
            ? '<a href="' + esc(a.url) + '">' + esc(a.cta || "Abrir") + "</a>"
            : "") +
          "</article>"
        );
      })
      .join("");
  }

  function renderPedidos(rows) {
    if (!pedidosEl) return;
    if (!rows.length) {
      pedidosEl.innerHTML = '<p class="DashVd_PedVazio">Nenhum pedido ainda.</p>';
      return;
    }
    pedidosEl.innerHTML = rows
      .map((p) => {
        return (
          '<a class="DashVd_Ped" href="' +
          esc(p.url || "/fornecedor/pedidos") +
          '">' +
          '<div><div class="DashVd_PedNum">#' +
          esc(p.numero) +
          '</div><div class="DashVd_PedMeta">' +
          esc(fmtData(p.criado_em)) +
          "</div></div>" +
          '<div class="DashVd_PedMeta">' +
          esc(p.parceiro || "—") +
          "</div>" +
          '<div class="DashVd_PedStatus">' +
          esc(p.status_label || p.status || "—") +
          "</div>" +
          '<div class="DashVd_PedValor">' +
          esc(p.valor_fmt || "—") +
          "</div>" +
          "</a>"
        );
      })
      .join("");
  }

  async function carregar() {
    try {
      const r = await fetch("/index/dados-fornecedor", { credentials: "same-origin" });
      const j = await r.json();
      if (!j.success) throw new Error(j.message || "Falha ao carregar.");
      const d = j.dados || {};
      setKpis(d.kpis || {});
      renderAlertas(d.alertas || []);
      renderPedidos(d.pedidos_recentes || []);
      if (loading) loading.hidden = true;
      root.removeAttribute("data-loading");
    } catch (e) {
      if (loading) loading.hidden = true;
      if (erro) {
        erro.hidden = false;
        erro.textContent = e.message || "Erro ao carregar o dashboard.";
      }
    }
  }

  carregar();
})();
