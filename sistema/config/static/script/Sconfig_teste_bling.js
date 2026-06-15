(function () {
  const badgeApp = document.getElementById("ti_bl_badge_app");
  const badgeConn = document.getElementById("ti_bl_badge_conn");
  const statusMsg = document.getElementById("ti_bl_status_msg");
  const btnTestar = document.getElementById("ti_bl_btn_testar");
  const resultado = document.getElementById("ti_bl_resultado");
  const passosEl = document.getElementById("ti_bl_passos");
  const resumoEl = document.getElementById("ti_bl_resumo");
  const duracaoEl = document.getElementById("ti_bl_duracao");

  let pronto = false;

  function renderPassos(passos) {
    if (!passosEl) return;
    passosEl.innerHTML = (passos || [])
      .map(
        (p) => `
      <tr class="${p.ok ? "is-ok" : "is-erro"}">
        <td>${p.ordem}</td>
        <td><code>${p.metodo || ""}</code></td>
        <td>${p.status ?? ""}</td>
        <td>${p.resumo || ""}</td>
        <td class="ti-detalhe">${p.detalhe || ""}</td>
      </tr>`
      )
      .join("");
  }

  async function carregarStatus() {
    const r = await fetch("/api/integracoes/bling/status");
    const j = await r.json();
    if (!j.success) throw new Error(j.message || "Falha ao carregar status.");

    const appOk = !!j.app_configurado;
    const connOk = !!j.conectado;
    pronto = appOk && connOk;

    if (badgeApp) {
      badgeApp.textContent = appOk ? "Credenciais OK" : "Credenciais ausentes";
      badgeApp.className = "Ti_Badge " + (appOk ? "is-ok" : "is-erro");
    }
    if (badgeConn) {
      badgeConn.textContent = connOk ? "Conta conectada" : "Não conectado";
      badgeConn.className = "Ti_Badge " + (connOk ? "is-ok" : "is-off");
    }
    if (statusMsg) {
      if (!appOk) {
        statusMsg.textContent =
          "Configure BLING_CLIENT_ID e BLING_CLIENT_SECRET no .env do servidor.";
      } else if (!connOk) {
        statusMsg.innerHTML =
          'Conecte o Bling em <a href="/integracoes/bling">Integrações → Bling</a> antes de testar.';
      } else {
        statusMsg.textContent = j.conectado_em
          ? `Conectado em ${new Date(j.conectado_em).toLocaleString("pt-BR")}. Pronto para homologação.`
          : "Pronto para homologação.";
      }
    }
    if (btnTestar) btnTestar.disabled = !pronto;
  }

  async function executarTeste() {
    if (!btnTestar || !pronto) return;
    btnTestar.disabled = true;
    btnTestar.textContent = "Executando…";
    if (resultado) resultado.hidden = true;

    try {
      const r = await fetch("/api/integracoes/bling/homologacao/executar", { method: "POST" });
      const j = await r.json();

      if (resultado) resultado.hidden = false;
      if (resumoEl) {
        resumoEl.textContent = j.message || (j.success ? "Concluído" : "Falhou");
        resumoEl.className = "Ti_Resumo " + (j.success ? "is-ok" : "is-erro");
      }
      if (duracaoEl) {
        duracaoEl.textContent =
          j.dados && j.dados.duracao_seg != null
            ? `Tempo total: ${j.dados.duracao_seg}s`
            : "";
      }
      renderPassos(j.dados && j.dados.passos);

      if (window.Util && Util.alertar) {
        await Util.alertar(j.message, j.success ? "success" : "error");
      }
    } catch (e) {
      if (window.Util && Util.alertar) {
        await Util.alertar(String(e.message || e), "error");
      }
    } finally {
      btnTestar.disabled = !pronto;
      btnTestar.textContent = "Executar homologação";
    }
  }

  btnTestar?.addEventListener("click", executarTeste);

  carregarStatus().catch((e) => {
    if (window.Util && Util.alertar) Util.alertar(e.message, "error");
  });

  if (window.GlobalUtils && typeof window.GlobalUtils.refreshIcons === "function") {
    window.GlobalUtils.refreshIcons();
  }
})();
