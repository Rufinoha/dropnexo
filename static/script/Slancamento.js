(function () {
  "use strict";

  let cfg = {};
  try {
    cfg = JSON.parse(document.getElementById("dn_lanc_cfg")?.textContent || "{}");
  } catch {
    cfg = {};
  }

  const target = new Date(cfg.targetIso || "2026-09-21T07:00:00-03:00");
  const papel = String(cfg.papel || "vendedor").toLowerCase();
  const isFornecedor = papel === "fornecedor";

  const banner = document.getElementById("dn_lanc_banner");
  const elCount = document.getElementById("dn_lanc_count");
  const elMarquee = document.getElementById("dn_lanc_marquee");
  const elLive = document.getElementById("dn_lanc_live");
  const elBadge = document.getElementById("dn_lanc_badge");
  const elD = document.getElementById("dn_u_d");
  const elH = document.getElementById("dn_u_h");
  const elM = document.getElementById("dn_u_m");
  const elS = document.getElementById("dn_u_s");
  const dialog = document.getElementById("dn_lanc_dialog");
  const body = document.getElementById("dn_lanc_dialog_body");
  const btn = document.getElementById("dn_lanc_saiba");

  function pad(n) {
    return String(n).padStart(2, "0");
  }

  function setLive(on) {
    banner?.classList.toggle("is-live", on);
    if (elBadge) elBadge.textContent = on ? "Estamos no ar" : "Agora é oficial";
    if (elCount) elCount.hidden = on;
    if (elMarquee) elMarquee.hidden = on;
    if (elLive) elLive.hidden = !on;
  }

  function tick() {
    const diff = target.getTime() - Date.now();
    if (diff <= 0) {
      setLive(true);
      return false;
    }
    setLive(false);
    const totalSec = Math.floor(diff / 1000);
    const dias = Math.floor(totalSec / 86400);
    const horas = Math.floor((totalSec % 86400) / 3600);
    const min = Math.floor((totalSec % 3600) / 60);
    const seg = totalSec % 60;
    if (elD) elD.textContent = String(dias);
    if (elH) elH.textContent = pad(horas);
    if (elM) elM.textContent = pad(min);
    if (elS) elS.textContent = pad(seg);
    return true;
  }

  function htmlVendedor() {
    const cupom = cfg.cupomVendedor || "VENDEDOR30";
    return `
      <p><strong>Agora é oficial.</strong> O lançamento da DropNexo é em <strong>21 de setembro, às 7h</strong>.</p>
      <p>A proposta não é substituir as ferramentas que você já usa. É <strong>mais um canal</strong> para conectar você a fornecedores com preço de custo, catálogo organizado e pedido sem depender só de WhatsApp e planilha.</p>
      <p>Até a inauguração (e depois dela), o foco é simples: <strong>usar de verdade</strong> — conectar fornecedor, publicar produto e vender.</p>
      <p>Se ainda não ativou o acesso, use o cupom <span class="DnLanc_Cupom">${cupom}</span> no plano escolhido: <strong>100% de desconto</strong> para quem está conosco nessa fase de testes com operação real.</p>
      <p>Em <strong>21/09 às 7h</strong> abrimos oficialmente. Qualquer dúvida, é só chamar.</p>
      <p>Abraço,<br/>Hazael — DropNexo</p>
    `;
  }

  function htmlFornecedor() {
    const cupom = cfg.cupomFornecedor || "FORNFUND";
    const wa = String(cfg.whatsapp || "").replace(/\D/g, "");
    const waLabel = cfg.whatsappLabel || wa;
    const email = cfg.email || "hazael@h74.com.br";
    return `
      <p><strong>Agora é oficial.</strong><br/>Aqui é o Hazael, fundador da DropNexo.</p>
      <p>Estou montando com calma a primeira rodada: conectar o catálogo de vocês a lojistas que já vendem em marketplace e buscam produtos com preço de custo — sem WhatsApp solto, planilha ou sistema caro só para organizar revenda.</p>
      <p>Vocês seguem no controle: preço, regra comercial e quem pode revender. A DropNexo só organiza o encontro.</p>
      <p>Nesta fase, seleciono <strong>Fornecedores Fundadores</strong> para testar <strong>vendendo de verdade</strong>. Condição:</p>
      <ul>
        <li>cupom <span class="DnLanc_Cupom">${cupom}</span> → <strong>100% de desconto</strong> no plano</li>
        <li>acompanhamento próximo e abertura para sugerir melhorias</li>
        <li>em troca: <strong>catálogo ativo</strong> na plataforma</li>
      </ul>
      <p>O lançamento oficial é em <strong>21 de setembro, às 7h</strong>.</p>
      <p>Se fizer sentido, responda <strong>QUERO</strong> (e o segmento: moda, casa, pet…).</p>
      <div class="DnLanc_Contato">
        <p>Contato direto</p>
        <div class="DnLanc_ContatoRow">
          <a href="https://wa.me/${wa}" target="_blank" rel="noopener">WhatsApp ${waLabel}</a>
          <a href="mailto:${email}">${email}</a>
        </div>
      </div>
      <p>Abraço,</p>
    `;
  }

  function abrirSaibaMais() {
    if (!dialog || !body) return;
    body.innerHTML = isFornecedor ? htmlFornecedor() : htmlVendedor();
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  btn?.addEventListener("click", abrirSaibaMais);
  dialog?.addEventListener("click", (e) => {
    if (e.target === dialog) dialog.close();
  });

  if (tick()) {
    const timer = setInterval(() => {
      if (!tick()) clearInterval(timer);
    }, 1000);
  }
})();
