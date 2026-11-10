(function () {
  const $ = id => document.getElementById(id);
  const esc = v => String(v ?? "").replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let perfis=[];
  async function req(url,method="GET",payload=null){
    return GlobalUtils.requestJSON({url,method,payload});
  }
  function msg(t,x,icon="info"){return GlobalUtils.swalFire({title:t,text:x,icon});}
  document.querySelectorAll(".nfse-tabs button").forEach(b=>b.onclick=()=>{
    document.querySelectorAll(".nfse-tabs button").forEach(x=>x.classList.toggle("is-on",x===b));
    document.querySelectorAll(".nfse-panel").forEach(x=>x.classList.toggle("is-on",x.dataset.panel===b.dataset.tab));
  });
  const cfgCampos=["razao_social","nome_fantasia","cnpj","inscricao_municipal","municipio_ibge_codigo","municipio_nome","uf","regime_tributario","regime_especial_tributacao","percentual_tributos_sn","serie_dps","proximo_numero_dps","ambiente"];
  function travarIdentidade(){
    ["cfg_cnpj","cfg_razao_social"].forEach(id=>{
      const e=$(id); if(!e) return;
      e.readOnly=true;
      e.classList.add("is-readonly");
    });
  }
  async function carregarConfig(){
    const r=await req("/nfse/api/config"); if(!r?.ok)return;
    const d=r.json.dados||{}; cfgCampos.forEach(c=>{const e=$(`cfg_${c}`);if(e)e.value=d[c]??""});
    if($("cfg_cnpj")) $("cfg_cnpj").value=d.cnpj?formatarCnpj(d.cnpj):"";
    if($("cfg_razao_social")) $("cfg_razao_social").value=d.razao_social||"";
    $("cfg_optante_simples").checked=!!d.optante_simples;$("cfg_incentivador_cultural").checked=!!d.incentivador_cultural;
    $("cryptoWarning").hidden=!r.json.dev_crypto_fallback;
    travarIdentidade();
    const aviso=$("cfgEmpresaAviso");
    const formBox=document.querySelector('.nfse-panel[data-panel="empresa"]');
    if(aviso){
      if(d.eh_pj===false){
        aviso.hidden=false;
        aviso.textContent="Este tenant não é PJ. A Empresa fiscal usa o cadastro do tenant — altere o tipo para pessoa jurídica para emitir NFS-e.";
        formBox?.classList.add("is-bloqueado");
        formBox?.querySelectorAll("input,select,button,textarea").forEach(el=>{ if(el.id!=="cfgEmpresaAviso") el.disabled=true; });
      }else{
        aviso.hidden=true;
        formBox?.classList.remove("is-bloqueado");
        formBox?.querySelectorAll("input,select,button,textarea").forEach(el=>{ el.disabled=false; });
        travarIdentidade();
        if(!d.cnpj || !d.razao_social){
          aviso.hidden=false;
          aviso.textContent="CNPJ ou razão social ausentes no cadastro do tenant. Complete em Minha empresa (não editáveis aqui).";
        }
      }
    }
  }
  function formatarCnpj(v){
    const d=String(v||"").replace(/\D/g,"").slice(0,14);
    if(d.length!==14) return d;
    return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/,"$1.$2.$3/$4-$5");
  }
  function tituloCidade(v){
    return String(v||"").toLocaleLowerCase("pt-BR").replace(/(^|[\s\-'])(\p{L})/gu,(_,a,b)=>a+b.toLocaleUpperCase("pt-BR"));
  }
  $("btnPreencherCnpj").onclick=async()=>{
    const cnpj=($("cfg_cnpj").value||"").replace(/\D/g,"");
    if(cnpj.length!==14) return msg("Atenção","CNPJ do tenant ausente. Cadastre em Minha empresa.","warning");
    const btn=$("btnPreencherCnpj");
    btn.disabled=true; const rotulo=btn.textContent; btn.textContent="Consultando...";
    try{
      const r=await req("/clientes/empresa/consulta-cnpj","POST",{cnpj});
      const d=r?.json||{};
      if(!r?.ok) return msg("Consulta", d.erro||d.message||"Não foi possível consultar o CNPJ.","warning");
      // CNPJ e razão social permanecem os do tenant (imutáveis).
      if(d.nome_fantasia && !$("cfg_nome_fantasia").value) $("cfg_nome_fantasia").value=d.nome_fantasia;
      if(d.cidade) $("cfg_municipio_nome").value=tituloCidade(d.cidade);
      if(d.uf) $("cfg_uf").value=d.uf;
      if(d.codigo_municipio_ibge) $("cfg_municipio_ibge_codigo").value=String(d.codigo_municipio_ibge);
      const mei=d.opcao_pelo_mei===true;
      const simples=d.opcao_pelo_simples===true||mei;
      if(d.opcao_pelo_simples!=null||mei) $("cfg_optante_simples").checked=simples;
      if(mei) $("cfg_regime_tributario").value="mei";
      else if(d.opcao_pelo_simples===true) $("cfg_regime_tributario").value="simples_nacional";
      travarIdentidade();
      const aviso=d.situacao_ativa===false?" O CNPJ não está ativo na base pública.":"";
      msg("Dados completados","Município, UF, IBGE e Simples vieram da base pública. CNPJ e razão social não são alterados."+aviso,"success");
    }finally{
      btn.disabled=false; btn.textContent=rotulo;
    }
  };
  $("btnSalvarConfig").onclick=async()=>{
    const p={};cfgCampos.forEach(c=>p[c]=$(`cfg_${c}`).value);
    p.optante_simples=$("cfg_optante_simples").checked;p.incentivador_cultural=$("cfg_incentivador_cultural").checked;
    const r=await req("/nfse/api/config/salvar","POST",p);msg(r?.ok?"Salvo":"Erro",r?.json?.message||"Falha ao salvar.",r?.ok?"success":"error");
  };
  function abrirModalPerfil(){
    const modal=$("modalPerfil");
    modal.hidden=false;
    modal.setAttribute("aria-hidden","false");
    document.body.style.overflow="hidden";
    $("pf_nome").focus();
  }
  function fecharModalPerfil(){
    const modal=$("modalPerfil");
    modal.hidden=true;
    modal.setAttribute("aria-hidden","true");
    document.body.style.overflow="";
  }
  function abrirPerfil(p={}){
    $("modalPerfilTitulo").textContent=p.id?"Editar perfil":"Novo perfil";
    $("pf_id").value=p.id||"";
    ["nome","codigo_servico","codigo_tributacao_nacional","codigo_nbs","descricao_servico"].forEach(c=>$(`pf_${c}`).value=p[c]||"");
    ["iss","pis","cofins","inss","ir","csll"].forEach(t=>{$(`pf_${t}_retido`).checked=!!p[`${t}_retido`];$(`pf_aliquota_${t}`).value=p[`aliquota_${t}`]||0});
    $("pf_ibs_cbs_json").value=JSON.stringify(p.ibs_cbs_json||{},null,2);$("pf_ativo").checked=p.ativo!==false;
    abrirModalPerfil();
  }
  async function carregarPerfis(){
    const r=await req("/nfse/api/perfis");if(!r?.ok)return;perfis=r.json.dados;
    $("listaPerfis").innerHTML=perfis.length?perfis.map(p=>`<tr><td>${esc(p.nome)}</td><td>${esc(p.codigo_servico)}</td><td>${esc(p.codigo_tributacao_nacional)}</td><td>${Number(p.aliquota_iss||0)}% ${p.iss_retido?"retido":""}</td><td>${p.ativo?"Ativo":"Inativo"}</td><td><button class="Cl_btn Cl_btn_neutral editarPerfil" data-id="${p.id}">Editar</button></td></tr>`).join(""):'<tr><td colspan="6">Nenhum perfil cadastrado.</td></tr>';
  }
  $("btnNovoPerfil").onclick=()=>abrirPerfil();
  $("btnCancelarPerfil").onclick=fecharModalPerfil;
  $("btnFecharPerfil").onclick=fecharModalPerfil;
  $("modalPerfil").addEventListener("mousedown",e=>{if(e.target===$("modalPerfil"))fecharModalPerfil();});
  document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("modalPerfil").hidden)fecharModalPerfil();});
  $("listaPerfis").onclick=e=>{const b=e.target.closest(".editarPerfil");if(b)abrirPerfil(perfis.find(p=>String(p.id)===b.dataset.id))};
  $("formPerfil").onsubmit=async e=>{
    e.preventDefault();const p={id:$("pf_id").value||null,ativo:$("pf_ativo").checked};
    ["nome","codigo_servico","codigo_tributacao_nacional","codigo_nbs","descricao_servico"].forEach(c=>p[c]=$(`pf_${c}`).value);
    ["iss","pis","cofins","inss","ir","csll"].forEach(t=>{p[`${t}_retido`]=$(`pf_${t}_retido`).checked;p[`aliquota_${t}`]=$(`pf_aliquota_${t}`).value});
    p.ibs_cbs_json=$("pf_ibs_cbs_json").value;
    const r=await req("/nfse/api/perfis/salvar","POST",p);if(!r?.ok)return msg("Erro",r?.json?.message||"Falha ao salvar.","error");
    fecharModalPerfil();await carregarPerfis();msg("Perfil salvo",r.json.message,"success");
  };
  async function carregarCertificados(){
    const r=await req("/nfse/api/certificados");if(!r?.ok)return;
    $("listaCertificados").innerHTML=r.json.dados.length?r.json.dados.map(c=>`<tr><td>${esc(c.nome_arquivo)}</td><td>${esc(c.titular||"N/D")}<br><small>${esc(c.cnpj_certificado||"CNPJ não identificado")}</small></td><td>${esc(c.serial_certificado||"—")}</td><td>${c.dt_fim_validade?new Date(c.dt_fim_validade).toLocaleDateString("pt-BR"):"—"}</td><td>${c.ativo?"Ativo":"Inativo"}</td></tr>`).join(""):'<tr><td colspan="5">Nenhum certificado cadastrado.</td></tr>';
  }
  $("formCertificado").onsubmit=async e=>{
    e.preventDefault();const f=$("cert_arquivo").files[0];if(!f)return;
    const fd=new FormData();fd.append("arquivo",f);fd.append("senha",$("cert_senha").value);
    const r=await GlobalUtils.requestFormData({url:"/nfse/api/certificados/upload",formData:fd});
    if(!r?.ok)return msg("Certificado rejeitado",r?.json?.message||"Falha no upload.","error");
    e.target.reset();await carregarCertificados();msg("Certificado armazenado",r.json.message,"success");
  };
  carregarConfig();carregarPerfis();carregarCertificados();
})();
