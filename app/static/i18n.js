'use strict';
(function(root){
 const key='LucentThinker-language',draftKey='LucentThinker-language-draft';
 let locale='en',pendingDraft=null;
 try{locale=root.localStorage?.getItem(key)==='zh'?'zh':'en';}catch{}
 // The DSH shell stores the preference on its stable origin, across engine ports.
 const embedded=typeof document!=='undefined'&&!!document.querySelector('meta[name="lucent-base"]')?.content;
 if(embedded){const requested=new URLSearchParams(location.search).get('language');if(['en','zh'].includes(requested))locale=requested;}
 try{pendingDraft=root.sessionStorage?.getItem(draftKey);if(pendingDraft)root.sessionStorage.removeItem(draftKey);}catch{}
 function t(text,...values){
  const translated=locale==='en'?(root.LUCENT_EN?.[text]??text):text;
  return typeof translated==='string'?translated.replace(/\{(\d+)\}/g,(match,i)=>values[i]??match):translated;
 }
 function applyStatic(){
  document.documentElement.lang=locale==='en'?'en':'zh-CN';
  for(const node of document.querySelectorAll('[data-i18n]'))node.textContent=t(node.dataset.i18n);
  for(const attr of ['title','aria-label','placeholder','data-prompt']){
   for(const node of document.querySelectorAll(`[data-i18n-${attr}]`))node.setAttribute(attr,t(node.getAttribute('data-i18n-'+attr)));
  }
  for(const button of document.querySelectorAll('[data-language-toggle]')){button.textContent=locale==='en'?'中文':button.dataset.compact==='true'?'EN':'English';button.title=button.getAttribute('aria-label')||'';
   button.onclick=()=>{
    const draft={};for(const id of ['question','mode','composer-iterations','composer-main-profile','composer-summary-profile'])draft[id]=document.getElementById(id)?.value;
    try{sessionStorage.setItem(draftKey,JSON.stringify(draft));localStorage.setItem(key,locale==='en'?'zh':'en');}
    catch{document.getElementById('toast').textContent=t('浏览器无法保存语言设置');document.getElementById('toast').classList.remove('hidden');return;}
    if(embedded){const next=locale==='en'?'zh':'en',url=new URL(location.href);url.searchParams.set('language',next);history.replaceState(null,'',url);parent.postMessage({type:'lucentthinker-language',language:next},'*');}
    location.reload();
   };
  }
 }
 function restoreDraft(){
  try{const raw=pendingDraft;if(!raw)return;pendingDraft=null;
   const draft=JSON.parse(raw);for(const [id,value] of Object.entries(draft)){
    const node=document.getElementById(id);if(node&&typeof value==='string'&&(node.tagName!=='SELECT'||[...node.options].some(o=>o.value===value)))node.value=value;
   }
   document.getElementById('composer-iterations').classList.toggle('hidden',document.getElementById('mode').value!=='custom');
  }catch{}
 }
 // Translate application status messages only, never questions, answers or model output.
 function serverText(text){
  if(locale!=='en'||typeof text!=='string')return text;
  if(root.LUCENT_EN?.[text])return t(text);
  const rules=[
   [/^研究尝试 (\d+) · 主模型迭代 (\d+) \/ (\d+)$/,(_,a,b,c)=>`Research attempt ${a} · Main model iteration ${b} / ${c}`],
   [/^研究(执行|初始化)失败（([^）]+)）(?:，请检查请求详情)?。$/,(_,stage,kind)=>`Research ${stage==='执行'?'execution':'initialization'} failed (${kind}). Check request details.`],
   [/^(temperature|top_p) 参数无效$/,(_,field)=>`Invalid ${field} parameter.`],
   [/^供应商模块 (.+) 已停用或移除，请选择其他模型配置。$/,(_,id)=>`Provider module ${id} is disabled or removed. Select another model configuration.`],
   [/^(.*)；当前研究尝试没有该 URL 的可用 Search content 或 summary。$/,(_,error)=>serverText(error)+' No usable Search content or summary for this URL is available in this research attempt.'],
   [/^(模型响应协议解析失败：|响应协议解析失败：|模型流返回错误：|模型服务 模型被过滤或未正常完成：|4router Gemini 未正常结束：)(.*)$/s,(_,prefix,detail)=>({
    '模型响应协议解析失败：':'Model response parsing failed: ', '响应协议解析失败：':'Response parsing failed: ',
    '模型流返回错误：':'Model stream error: ', '模型服务 模型被过滤或未正常完成：':'The model was filtered or did not complete normally: ',
    '4router Gemini 未正常结束：':'4router Gemini did not complete normally: '
   }[prefix]+serverText(detail))],
   [/^服务 HTTP (\d+)：([^·]+?)( · .*)?$/s,(_,code,description,detail)=>`Service HTTP ${code}: ${t(description.trim())}${detail||''}`],
   [/^(\w+) 必须是非空字符串。$/,(_,field)=>`${field} must be a nonempty string.`],
   [/^(\w+) 最多 (\d+) 个字符，当前 (\d+) 个；请生成更短的检索意图。未发送请求，原参数未截断。$/,(_,field,max,count)=>`${field} is limited to ${max} characters; received ${count}. Generate a shorter search intent. No request was sent and parameters were not truncated.`],
   [/^(存储对象缺失：|存储对象校验失败：|无法还原存储对象：)(.*)$/s,(_,prefix,id)=>({'存储对象缺失：':'Missing stored object: ','存储对象校验失败：':'Stored object verification failed: ','无法还原存储对象：':'Could not restore stored object: '}[prefix]+id)],
  ];
  for(const [pattern,render] of rules)if(pattern.test(text))return text.replace(pattern,render);
  return t(text);
 }
 // Only recognize known system records, never arbitrary provider/project names.
 function systemName(item){
  const known={supplier_main:'DeepSeek 主模型',supplier_summary:'DeepSeek 独立提取',default:'默认配置',legacy:'原研究配置'};
  return item&&known[item.id]===item.name?t(item.name):item?.name||'';
 }
 const api={t,serverText,systemName,restoreDraft,applyStatic,get language(){return locale;}};
 root.LucentI18n=api;
 if(typeof module==='object'&&module.exports)module.exports=api;
 if(typeof document!=='undefined')applyStatic();
})(globalThis);
