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
  const cfgCampos=["razao_social","nome_fantasia","cnpj","inscricao_municipal","cep","municipio_ibge_codigo","municipio_nome","uf","regime_tributario","regime_especial_tributacao","percentual_tributos_sn","serie_dps","proximo_numero_dps","serie_nfe","proximo_numero_nfe","ambiente"];
  let buscandoCep=false;
  let ultimoCep="";
  let enderecoViaCep={logradouro:"",bairro:""};
  function travarIdentidade(){
    ["cfg_cnpj","cfg_razao_social"].forEach(id=>{
      const e=$(id); if(!e) return;
      e.readOnly=true;
      e.classList.add("is-readonly");
    });
  }
  function setAvisoEmpresa(texto){
    const aviso=$("cfgEmpresaAviso");
    if(!aviso) return;
    const msg=(texto||"").trim();
    if(!msg){
      aviso.textContent="";
      aviso.hidden=true;
      aviso.setAttribute("hidden","");
      return;
    }
    aviso.textContent=msg;
    aviso.hidden=false;
    aviso.removeAttribute("hidden");
  }
  function aplicarEmpresa(d, cryptoFallback){
    if(!d) d={};
    cfgCampos.forEach(c=>{const e=$(`cfg_${c}`); if(e && d[c]!=null && d[c]!=="") e.value=d[c];});
    if($("cfg_cnpj")) $("cfg_cnpj").value=d.cnpj?formatarCnpj(d.cnpj):(d.cnpj_formatado||$("cfg_cnpj").value||"");
    if($("cfg_razao_social") && d.razao_social) $("cfg_razao_social").value=d.razao_social;
    if($("cfg_nome_fantasia") && d.nome_fantasia) $("cfg_nome_fantasia").value=d.nome_fantasia;
    if($("cfg_cep")) $("cfg_cep").value=d.cep?formatarCep(d.cep):($("cfg_cep").value||"");
    if($("cfg_municipio_nome") && d.municipio_nome) $("cfg_municipio_nome").value=d.municipio_nome;
    if($("cfg_uf") && d.uf) $("cfg_uf").value=d.uf;
    if($("cfg_inscricao_municipal") && d.inscricao_municipal) $("cfg_inscricao_municipal").value=d.inscricao_municipal;
    if($("cfg_municipio_ibge_codigo") && d.municipio_ibge_codigo) $("cfg_municipio_ibge_codigo").value=d.municipio_ibge_codigo;
    ultimoCep=String(d.cep||"").replace(/\D/g,"").slice(0,8);
    enderecoViaCep={logradouro:d.logradouro||"",bairro:d.bairro||""};
    if($("cfg_serie_dps")) $("cfg_serie_dps").value=(d.serie_dps!=null && d.serie_dps!=="")?d.serie_dps:"1";
    if($("cfg_proximo_numero_dps")) $("cfg_proximo_numero_dps").value=d.proximo_numero_dps!=null?d.proximo_numero_dps:1;
    if($("cfg_serie_nfe")) $("cfg_serie_nfe").value=d.serie_nfe!=null?d.serie_nfe:1;
    if($("cfg_proximo_numero_nfe")) $("cfg_proximo_numero_nfe").value=d.proximo_numero_nfe!=null?d.proximo_numero_nfe:1;
    if($("cfg_ambiente") && d.ambiente) $("cfg_ambiente").value=d.ambiente;
    if($("cfg_regime_tributario") && d.regime_tributario) $("cfg_regime_tributario").value=d.regime_tributario;
    if($("cfg_percentual_tributos_sn") && d.percentual_tributos_sn) $("cfg_percentual_tributos_sn").value=d.percentual_tributos_sn;
    if($("cfg_optante_simples")) $("cfg_optante_simples").checked=!!d.optante_simples;
    if($("cfg_incentivador_cultural")) $("cfg_incentivador_cultural").checked=!!d.incentivador_cultural;
    if($("cryptoWarning") && cryptoFallback!=null) $("cryptoWarning").hidden=!cryptoFallback;
    travarIdentidade();
    const formBox=document.querySelector('.nfse-panel[data-panel="empresa"]');
    if(d.eh_pj===false){
      setAvisoEmpresa("Sua conta não é pessoa jurídica (PJ). Altere o tipo em Minha empresa para emitir NFS-e.");
      formBox?.classList.add("is-bloqueado");
      formBox?.querySelectorAll("input,select,button,textarea").forEach(el=>{ el.disabled=true; });
    }else{
      formBox?.classList.remove("is-bloqueado");
      formBox?.querySelectorAll("input,select,button,textarea").forEach(el=>{ el.disabled=false; });
      travarIdentidade();
      if(!d.cnpj || !d.razao_social){
        setAvisoEmpresa("CNPJ ou razão social ausentes. Complete em Minha empresa (não editáveis aqui).");
      }else{
        setAvisoEmpresa("");
      }
    }
  }
  function bootEmpresa(){
    try{
      const raw=$("nfse_empresa_boot")?.textContent||"{}";
      const d=JSON.parse(raw);
      if(d && (d.cnpj || d.razao_social || d.eh_pj!=null)) aplicarEmpresa(d, null);
    }catch(_){}
  }
  async function carregarConfig(){
    setAvisoEmpresa("");
    bootEmpresa();
    const r=await req("/nfse/api/config");
    if(!r?.ok){
      if(!($("cfg_cnpj")?.value) && !($("cfg_razao_social")?.value)){
        setAvisoEmpresa((r?.json&& (r.json.message||r.json.mensagem))||"Não foi possível carregar a empresa fiscal.");
      }
      return;
    }
    aplicarEmpresa(r.json.dados||{}, r.json.dev_crypto_fallback);
  }
  function formatarCnpj(v){
    const d=String(v||"").replace(/\D/g,"").slice(0,14);
    if(d.length!==14) return d;
    return d.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/,"$1.$2.$3/$4-$5");
  }
  function formatarCep(v){
    const d=String(v||"").replace(/\D/g,"").slice(0,8);
    if(d.length!==8) return d;
    return d.replace(/^(\d{5})(\d{3})$/,"$1-$2");
  }
  function tituloCidade(v){
    return String(v||"").toLocaleLowerCase("pt-BR").replace(/(^|[\s\-'])(\p{L})/gu,(_,a,b)=>a+b.toLocaleUpperCase("pt-BR"));
  }
  async function buscarCepEmpresa(){
    const el=$("cfg_cep");
    if(!el) return;
    const cep=String(el.value||"").replace(/\D/g,"").slice(0,8);
    el.value=formatarCep(cep);
    if(cep.length!==8 || buscandoCep || cep===ultimoCep) return;
    buscandoCep=true;
    ultimoCep=cep;
    try{
      const r=await req("/nfse/api/consulta-cep?cep="+encodeURIComponent(cep),"GET");
      const d=r?.json||{};
      if(!r?.ok){
        ultimoCep="";
        return msg("Consulta CEP", d.erro||d.message||"Não foi possível consultar o CEP.","warning");
      }
      el.value=formatarCep(d.cep||cep);
      if(d.ibge) $("cfg_municipio_ibge_codigo").value=String(d.ibge).replace(/\D/g,"").slice(0,7);
      if(d.municipio||d.cidade) $("cfg_municipio_nome").value=tituloCidade(d.municipio||d.cidade);
      if(d.uf) $("cfg_uf").value=String(d.uf).toUpperCase().slice(0,2);
      enderecoViaCep={
        logradouro:d.logradouro||"",
        bairro:d.bairro||"",
      };
      msg("CEP encontrado","Município, UF e código IBGE foram preenchidos.","success");
    }catch(err){
      ultimoCep="";
      msg("Consulta CEP", err?.message||"Falha ao consultar o CEP.","warning");
    }finally{
      buscandoCep=false;
    }
  }
  function textoApi(j){
    if(!j) return "";
    const partes=[];
    if(j.message) partes.push(String(j.message));
    if(Array.isArray(j.erros) && j.erros.length){
      const ja=String(j.message||"");
      j.erros.forEach(e=>{
        const t=String(e||"").trim();
        if(t && !ja.includes(t)) partes.push("• "+t);
      });
    }
    return partes.join("\n");
  }
  $("btnPreencherCnpj").onclick=async()=>{
    const cnpj=($("cfg_cnpj").value||"").replace(/\D/g,"");
    if(cnpj.length!==14) return msg("Atenção","CNPJ da sua empresa ausente. Cadastre em Minha empresa.","warning");
    const btn=$("btnPreencherCnpj");
    btn.disabled=true; const rotulo=btn.textContent; btn.textContent="Consultando...";
    try{
      const r=await req("/nfse/api/consulta-cnpj","POST",{cnpj});
      const d=r?.json||{};
      if(!r?.ok) return msg("Consulta", d.erro||d.message||"Não foi possível consultar o CNPJ.","warning");
      // CNPJ e razão social permanecem os da empresa (imutáveis aqui).
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
  function montarPayloadEmpresa(){
    const p={};
    cfgCampos.forEach(c=>{
      const el=$(`cfg_${c}`);
      if(!el) throw new Error(`Campo ausente na tela: ${c}`);
      p[c]=el.value;
    });
    const ibge=String(p.municipio_ibge_codigo||"").replace(/\D/g,"");
    const uf=String(p.uf||"").trim().toUpperCase();
    const municipio=String(p.municipio_nome||"").trim();
    if(!uf || uf.length!==2){
      throw new Error("Informe a UF (2 letras) da sua empresa na aba Empresa fiscal.");
    }
    if(!municipio){
      throw new Error("Informe o município da sua empresa na aba Empresa fiscal.");
    }
    if(ibge && ibge.length!==7){
      throw new Error("Código IBGE deve ter 7 dígitos. Use Completar da Receita.");
    }
    if(!ibge){
      throw new Error("Informe o código IBGE (7 dígitos) na aba Empresa fiscal.");
    }
    p.uf=uf;
    p.cep=String(p.cep||"").replace(/\D/g,"").slice(0,8);
    if(enderecoViaCep.logradouro) p.logradouro=enderecoViaCep.logradouro;
    if(enderecoViaCep.bairro) p.bairro=enderecoViaCep.bairro;
    p.optante_simples=$("cfg_optante_simples").checked;
    p.incentivador_cultural=$("cfg_incentivador_cultural").checked;
    p.serie_dps=String(p.serie_dps||"1").trim()||"1";
    p.proximo_numero_dps=Math.max(1, parseInt(p.proximo_numero_dps||"1",10)||1);
    p.serie_nfe=Math.max(1, parseInt(p.serie_nfe||"1",10)||1);
    p.proximo_numero_nfe=Math.max(1, parseInt(p.proximo_numero_nfe||"1",10)||1);
    return p;
  }
  async function salvarConfiguracao(btn, tituloOk){
    try{
      const p=montarPayloadEmpresa();
      if(btn) btn.disabled=true;
      const r=await req("/nfse/api/config/salvar","POST",p);
      if(!r) return;
      if(r.ok && r.json?.dados) aplicarEmpresa(r.json.dados, null);
      const texto=textoApi(r.json)||(r.ok?(tituloOk||"Configuração salva."):"Falha ao salvar.");
      const icon=r.ok?(r.json?.hub_sincronizado?"success":"warning"):"error";
      await msg(r.ok?(r.json?.hub_sincronizado?"Salvo no Hub":"Salvo"):"Erro", texto, icon);
    }catch(err){
      await msg("Atenção", err?.message||"Falha ao salvar.","warning");
    }finally{
      if(btn) btn.disabled=false;
    }
  }
  $("btnSalvarConfig").onclick=()=>salvarConfiguracao($("btnSalvarConfig"), "Empresa fiscal salva.");
  if($("btnSalvarNumeracao")){
    $("btnSalvarNumeracao").onclick=()=>salvarConfiguracao($("btnSalvarNumeracao"), "Ambiente e numeração salvos.");
  }
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
  function fecharMenusPerfis(){
    document.querySelectorAll(".Fin_MenuLista").forEach(n=>n.remove());
  }
  function abrirMenuPerfil(btn){
    fecharMenusPerfis();
    const id=btn.getAttribute("data-id");
    const box=document.createElement("div");
    box.className="Fin_MenuLista";
    const editar=document.createElement("button");
    editar.type="button";
    editar.className="Fin_MenuItem";
    editar.textContent="Editar perfil";
    editar.addEventListener("click",()=>{
      fecharMenusPerfis();
      abrirPerfil(perfis.find(p=>String(p.id)===String(id))||{});
    });
    box.appendChild(editar);
    document.body.appendChild(box);
    const r=btn.getBoundingClientRect();
    box.style.top=`${r.bottom+4}px`;
    box.style.left=`${Math.max(8,r.right-box.offsetWidth)}px`;
  }
  async function carregarPerfis(){
    const r=await req("/nfse/api/perfis");if(!r?.ok)return;perfis=r.json.dados;
    $("listaPerfis").innerHTML=perfis.length?perfis.map(p=>`<tr>
      <td>${esc(p.nome)}</td>
      <td title="Código de tributação municipal">${esc(p.codigo_servico)||"—"}</td>
      <td>${esc(p.codigo_tributacao_nacional)||"—"}</td>
      <td>${Number(p.aliquota_iss||0)}% ${p.iss_retido?"retido":""}</td>
      <td>${p.ativo?"Ativo":"Inativo"}</td>
      <td><button type="button" class="Fin_MenuBtn nfse-perfil-menu" data-id="${p.id}" aria-label="Ações">⋮</button></td>
    </tr>`).join(""):'<tr><td colspan="6">Nenhum perfil cadastrado.</td></tr>';
  }
  $("btnNovoPerfil").onclick=()=>abrirPerfil();
  $("btnCancelarPerfil").onclick=fecharModalPerfil;
  $("btnFecharPerfil").onclick=fecharModalPerfil;
  $("modalPerfil").addEventListener("mousedown",e=>{if(e.target===$("modalPerfil"))fecharModalPerfil();});
  document.addEventListener("keydown",e=>{
    if(e.key==="Escape"){
      if(!$("modalPerfil").hidden) fecharModalPerfil();
      fecharMenusPerfis();
    }
  });
  document.addEventListener("click",fecharMenusPerfis);
  $("listaPerfis").onclick=e=>{
    const b=e.target.closest(".nfse-perfil-menu");
    if(!b) return;
    e.stopPropagation();
    abrirMenuPerfil(b);
  };
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
    e.preventDefault();
    const btn=e.target.querySelector('button[type="submit"]');
    try{
      const f=$("cert_arquivo")?.files?.[0];
      if(!f) return msg("Atenção","Selecione o arquivo .pfx/.p12 do certificado.","warning");
      const senha=$("cert_senha")?.value||"";
      if(!senha) return msg("Atenção","Informe a senha do certificado.","warning");
      const fd=new FormData();
      fd.append("arquivo",f);
      fd.append("senha",senha);
      if(btn) btn.disabled=true;
      const r=await GlobalUtils.requestFormData({url:"/nfse/api/certificados/upload",formData:fd});
      if(!r) return;
      if(!r.ok) return msg("Certificado rejeitado", textoApi(r.json)||r.json?.message||"Falha no upload.","error");
      e.target.reset();
      await carregarCertificados();
      const texto=textoApi(r.json)||"Certificado validado e armazenado.";
      const icon=r.json?.hub_sincronizado?"success":"warning";
      await msg(r.json?.hub_sincronizado?"Certificado e Hub":"Certificado armazenado", texto, icon);
    }catch(err){
      await msg("Erro", err?.message||"Falha ao enviar o certificado.","error");
    }finally{
      if(btn) btn.disabled=false;
    }
  };
  if($("cfg_cep")){
    $("cfg_cep").addEventListener("blur", buscarCepEmpresa);
    $("cfg_cep").addEventListener("change", buscarCepEmpresa);
    $("cfg_cep").addEventListener("input",()=>{
      const el=$("cfg_cep");
      const d=String(el.value||"").replace(/\D/g,"").slice(0,8);
      if(d.length===8) el.value=formatarCep(d);
      if(d.length===8 && d!==ultimoCep) buscarCepEmpresa();
    });
  }
  document.addEventListener("DOMContentLoaded", function(){
    bootEmpresa();
    carregarConfig();
    carregarPerfis();
    carregarCertificados();
  });
})();
