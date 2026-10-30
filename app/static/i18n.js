'use strict';
(function(root){
 const key='LucentThinker-language',draftKey='LucentThinker-language-draft';
 let locale='zh',pendingDraft=null;
 try{locale=root.localStorage?.getItem(key)==='en'?'en':'zh';}catch{}
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
  const rules=[
   [/^研究尝试 (\d+) · 主模型迭代 (\d+) \/ (\d+)$/, 'Research attempt $1 · Main model iteration $2 / $3'],
   [/^正在生成最终答案 · 工具已停用$/, 'Writing the final answer · Tools disabled'],
   [/^研究已停止。$/, 'Research stopped.'],
   [/^研究已停止，完整记录与来源已保存。$/, 'Research stopped. Records and sources saved.'],
   [/^服务重启，研究已中断。可继续追问或重新提交。$/, 'Research interrupted by a server restart. Ask a follow-up or submit again.'],
  ];
  for(const [pattern,value] of rules)if(pattern.test(text))return text.replace(pattern,value);
  return t(text);
 }
 const api={t,serverText,restoreDraft,applyStatic,get language(){return locale;}};
 root.LucentI18n=api;
 if(typeof module==='object'&&module.exports)module.exports=api;
 if(typeof document!=='undefined')applyStatic();
})(globalThis);
