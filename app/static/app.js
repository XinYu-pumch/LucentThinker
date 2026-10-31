'use strict';
var tr = globalThis.LucentI18n?.t || ((text,...values)=>typeof text==='string'?text.replace(/\{(\d+)\}/g,(_,i)=>values[i]??_):text);
const $ = (s, root=document) => root.querySelector(s);
const el = (tag, cls, text) => { const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n; };
const CONVERSATION_KEY = 'LucentThinker-conversation';
function migrateConversationSelection(storage=localStorage){
 const legacyKey='openmirothinker-conversation';
 if(!storage.getItem(CONVERSATION_KEY)){const previous=storage.getItem(legacyKey);if(previous)storage.setItem(CONVERSATION_KEY,previous);}
 storage.removeItem(legacyKey);
}
const state = {cid:null, projectId:'default', active:null, stream:null, runs:new Map(), sources:[], loading:false};
const modes={demo:'Demo',keep5_max200:'keep5_max200',quick:tr("旧版快速"),balanced:tr("旧版均衡"),deep:tr("旧版深入")};
let appConfig, debugData;
let toastTimer;
function toast(text){$('#toast').textContent=text;$('#toast').classList.remove('hidden');clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').classList.add('hidden'),4000);}
function appPath(url){return (document.querySelector('meta[name="lucent-base"]')?.content||'')+url;}
async function api(url, method='GET', body){const r=await fetch(appPath(url),{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});if(!r.ok){let d;try{d=await r.json();}catch{}throw Error(typeof d?.detail==='string'?tr(d.detail):tr("请求失败 ({0})", r.status));}return r.json();}
function safeUrl(value){try{const u=new URL(value);return ['http:','https:'].includes(u.protocol)&&!u.username&&!u.password?u.href:null;}catch{return null;}}
function linkCitationText(node,sources){
 if(node.parentElement.closest('a,code,pre'))return;
 const ids='[ \\t]*[0-9０-９]+(?:[ \\t]*[,，、;；][ \\t]*[0-9０-９]+)*[ \\t]*';
 const re=new RegExp(`(?:\\[${ids}\\]|［${ids}］|【${ids}】)`,'g');
 let match,last=0;const frag=document.createDocumentFragment();
 while((match=re.exec(node.textContent))){
  frag.append(node.textContent.slice(last,match.index));
  for(const raw of match[0].match(/[0-9０-９]+/g)){
   const digits=raw.replace(/[０-９]/g,c=>String.fromCharCode(c.charCodeAt(0)-0xfee0));
   const source=sources.find(s=>s.id===Number(digits));
   if(source&&safeUrl(source.url)){
    const a=el('a','citation',String(Number(digits)));a.href=safeUrl(source.url);a.title=source.title;a.target='_blank';a.rel='noopener noreferrer';frag.append(a);
   }else frag.append(`[${digits}]`);
  }
  last=re.lastIndex;
 }
 if(last){frag.append(node.textContent.slice(last));node.replaceWith(frag);}
}
function markdown(target,text,sources){
 target.innerHTML=DOMPurify.sanitize(marked.parse(text||''),{FORBID_TAGS:['img','style','input','form','iframe'],FORBID_ATTR:['style','id']});
 target.querySelectorAll('a').forEach(a=>{const url=safeUrl(a.getAttribute('href'));if(url){a.href=url;a.target='_blank';a.rel='noopener noreferrer';}else a.removeAttribute('href');});
 const walker=document.createTreeWalker(target,NodeFilter.SHOW_TEXT),nodes=[];while(walker.nextNode())nodes.push(walker.currentNode);
 for(const node of nodes)linkCitationText(node,sources);
}
let historyMenu=null, historyRevision=0, historySignature=null;
const historyTimings=new Map();
function closeHistoryMenu(){if(historyMenu){historyMenu.remove();historyMenu=null;}}
function conversationDialog(title,description,initial=null,inputLabel=tr("对话名称")){
 return new Promise(resolve=>{
  const dialog=el('dialog','conversation-dialog'),heading=el('h3','',title),help=el('p','',description);
  const id='conversation-dialog-title';heading.id=id;dialog.setAttribute('aria-labelledby',id);
  const form=el('form'),input=initial===null?null:el('input');
  if(input){input.value=initial;input.required=true;input.setAttribute('aria-label',inputLabel);form.append(input);}
  const actions=el('div','dialog-actions'),cancel=el('button','secondary-button',tr("取消")),submit=el('button','primary-button',input?tr("保存名称"):tr("确认删除"));
  cancel.type='button';submit.type='submit';actions.append(cancel,submit);form.append(actions);dialog.append(heading,help,form);document.body.append(dialog);
  let closed=false;const finish=value=>{if(closed)return;closed=true;dialog.close();dialog.remove();resolve(value);};
  cancel.onclick=()=>finish(null);dialog.oncancel=e=>{e.preventDefault();finish(null);};
  form.onsubmit=e=>{e.preventDefault();if(input&&!input.value.trim()){input.setCustomValidity(tr("名称不能为空"));input.reportValidity();return;}finish(input?input.value.trim():true);};
  if(input)input.oninput=()=>input.setCustomValidity('');
  dialog.showModal();(input||cancel).focus();if(input)input.select();
 });
}
async function deleteConversation(c){
 if(!await conversationDialog(tr("删除对话"),tr("删除“")+c.title+tr("”及其所有研究记录？此操作无法撤销。删除后会自动整理数据库、释放磁盘空间，可能需要稍等。")))return;
 toast(tr("正在删除对话并释放空间…"));
 const result=await api('/api/conversations/'+c.id,'DELETE');
 if(state.cid===c.id)reset();await refreshHistory();
 const cleanup=result.storage_cleanup;
 toast(cleanup?.warning||(cleanup?.compacted?tr("对话已删除，数据库已整理，释放 {0} MB。", (cleanup.reclaimed_bytes/1024/1024).toFixed(2)):tr("对话已删除。")));
}
async function renameConversation(c){
 const value=await conversationDialog(tr("编辑对话名称"),tr("只修改侧栏名称，研究内容保持原样。"),c.title);if(value===null)return;
 const title=value.trim();if(!title){toast(tr("名称不能为空"));return;}
 await api('/api/conversations/'+c.id,'PATCH',{title});
 if(state.cid===c.id)$('#header-title').textContent=title;
 await refreshHistory();
}
function openHistoryMenu(event,c,anchor){
 openContextMenu(event,anchor,tr('对话操作'),[
  [tr('编辑对话名称'),()=>renameConversation(c)],
  [tr('删除对话'),()=>deleteConversation(c),'danger']
 ]);
}
function openContextMenu(event,anchor,label,actions){
 event.preventDefault();closeHistoryMenu();
 const menu=el('div','history-context-menu');menu.setAttribute('role','menu');menu.setAttribute('aria-label',label);
 for(const [title,action,kind] of actions){
  const button=el('button',kind||'',title);button.type='button';button.setAttribute('role','menuitem');
  button.onclick=()=>{closeHistoryMenu();Promise.resolve().then(action).catch(e=>toast(e.message));};menu.append(button);
 }
 document.body.append(menu);historyMenu=menu;
 const rect=anchor.getBoundingClientRect(),x=event.clientX||rect.right,y=event.clientY||rect.top;
 menu.style.left=Math.max(8,Math.min(x,window.innerWidth-menu.offsetWidth-8))+'px';
 menu.style.top=Math.max(8,Math.min(y,window.innerHeight-menu.offsetHeight-8))+'px';
 menu.firstElementChild.focus();
 menu.onkeydown=e=>{if(e.key==='Escape'){e.preventDefault();closeHistoryMenu();anchor.focus();}else if(e.key==='Tab'){closeHistoryMenu();anchor.focus();}else if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();const items=[...menu.children],i=items.indexOf(document.activeElement);items[(i+(e.key==='ArrowDown'?1:items.length-1))%items.length].focus();}};
}
document.addEventListener('pointerdown',e=>{if(historyMenu&&!historyMenu.contains(e.target))closeHistoryMenu();});
window.addEventListener('resize',closeHistoryMenu);
async function refreshHistory(){
 const revision=++historyRevision,[list,projects]=await Promise.all([api('/api/conversations'),api('/api/projects')]);
 if(revision!==historyRevision)return;const signature=JSON.stringify([state.cid,list,projects]);if(signature===historySignature)return;
 historySignature=signature;closeHistoryMenu();historyTimings.clear();Sidebar.render(projects,list);
}
function conversationRow(c){
 const row=el('div','history-item'+(state.cid===c.id?' active':'')),b=el('button','history-select');
 b.append(el('span','conversation-title',c.title==='新的研究'?tr('新对话'):c.title));
 if(c.latest_status){const timing=el('small','history-status');b.append(timing);historyTimings.set(c.id,{c,node:timing});renderHistoryTiming(c,timing);}
 b.title=c.title+tr('（右键可重命名或删除）');b.setAttribute('aria-haspopup','menu');b.setAttribute('aria-current',state.cid===c.id?'page':'false');
 b.onclick=()=>{if(Sidebar.selectionMode)Sidebar.toggleSelection(c.id);else openConversation(c.id).catch(e=>toast(e.message));};b.oncontextmenu=e=>{if(Sidebar.selectionMode)e.preventDefault();else openHistoryMenu(e,c,b);};
 b.onkeydown=e=>{if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10'))openHistoryMenu(e,c,b);};
 const menu=el('button','history-delete conversation-menu','⋯');menu.title=tr('对话操作');menu.setAttribute('aria-label',tr('对话操作')+' · '+c.title);menu.setAttribute('aria-haspopup','menu');
 menu.onclick=e=>openHistoryMenu(e,c,menu);row.append(b,menu);Sidebar.decorateSelection(c,row);return row;
}
function renderHistoryTiming(c,node){node.textContent=(RunTiming.statusNames[c.latest_status]||c.latest_status)+' · '+RunTiming.duration(RunTiming.elapsed(c));node.classList.toggle('running',c.latest_status==='running');node.title=RunTiming.label(c);}
function renderTiming(run){if(run.ui?.timing)run.ui.timing.textContent=RunTiming.label(run);}
function disconnect(){state.stream?.close();state.stream=null;}
function busy(value){$('#send').classList.toggle('hidden',value);$('#stop').classList.toggle('hidden',!value);$('#question').disabled=value;$('#mode').disabled=value;$('#composer-iterations').disabled=value;$('#composer-main-profile').disabled=value;$('#composer-summary-profile').disabled=value;}
function reset(){++opening;disconnect();state.loading=false;$('#send').disabled=false;state.cid=null;state.active=null;state.runs.clear();$('#conversation').replaceChildren();$('#conversation').classList.add('hidden');$('#welcome').classList.remove('hidden');$('#header-title').textContent=tr("研究工作台");$('#sources-panel').classList.add('hidden');Sidebar.closeMobile();busy(false);$('#question').value='';$('#question').focus();localStorage.removeItem(CONVERSATION_KEY);Sidebar.select('default');historySignature=null;}
function addRun(run){
 state.runs.set(run.id,run);
 const article=el('article','turn');article.dataset.run=run.id;
 const q=el('div','question');q.append(el('span','avatar',tr("你")),el('h2','',run.question));
 const head=el('div','assistant-heading');head.append(el('span','mini-spark','✳'),el('span','','LucentThinker'),el('span','run-mode',tr(run.config_snapshot?.label||modes[run.mode]||run.mode)));
 const trace=el('details','trace');trace.open=true;const summary=el('summary','',tr("研究过程"));const traceContent=el('div','trace-content');trace.append(summary,traceContent);
 const body=el('div','answer');const pending=el('div','pending',tr("正在连接研究引擎…"));const err=el('div','run-error hidden');const footer=el('div','run-footer');
 const source=el('button','source-button',tr("{0} 个来源 ↗", run.sources.length));source.onclick=()=>showSources(run.sources);const copy=el('button','copy-button',tr("复制回答"));copy.onclick=async()=>{try{await navigator.clipboard.writeText(run.answer||'');toast(tr("回答已复制"));}catch{toast(tr("浏览器未允许访问剪贴板"));}};const detail=el('button','copy-button',tr("研究详情"));detail.onclick=()=>openDebug(run.id).catch(e=>toast(e.message));const download=el('button','copy-button',tr("导出本次回答"));download.onclick=()=>{const a=el('a');a.href=appPath(`/api/runs/${run.id}/export`);a.download=`LucentThinker-${run.id}${run.status==='completed'?'':'-partial'}.md`;a.click();};footer.append(source,copy,download,detail,el('div','run-usage'));const badge=el('div','snapshot-badge',snapshotLabel(run.config_snapshot));head.append(badge);
 const timing=el('div','run-timing');timing.title=tr("本地时间 · 从提交研究到结束，含排队、搜索、提取和写作");article.append(q,head,timing,trace,body,pending,err,footer);$('#conversation').append(article);run.ui={article,trace,summary,traceContent,body,pending,err,source,copy,download,footer,timing};initTrace(run);renderRun(run);return run;
}
function renderRun(run){renderTiming(run);updateTraceOverview(run);const u=run.ui;markdown(u.body,run.answer,run.sources);u.pending.classList.toggle('hidden',run.status!=='running');u.err.classList.toggle('hidden',!run.error);u.err.textContent=LucentI18n.serverText(run.error||'');u.source.textContent=tr("{0} 个来源 ↗", run.sources.length);u.copy.classList.toggle('hidden',!run.answer);u.download.classList.toggle('hidden',!run.answer||run.status==='running');u.download.textContent=run.status==='completed'?tr("导出本次回答"):tr("导出已生成部分");u.download.title=tr("仅导出本次保存的回答正文及引文（Markdown）");renderUsage(run);u.summary.textContent=run.status==='running'?tr("研究进行中…"):run.status==='completed'?tr("研究已完成"):tr("研究过程");}
function snapshotLabel(c){return c?.version?tr("{0} · 迭代上限 {1} · 工具结果 {2} · compress {3} · retry summary {4} · {5}", tr(c.label), c.max_iterations, c.keep_tool_result===-1?tr("全部"):c.keep_tool_result, c.context_compress_limit, c.retry_with_summary, c.memory_mode==='strict'?tr("独立研究"):tr("扩展追问")):tr("旧版记录（无配置快照）");}
function textViewer(value){const box=el('div'),text=typeof value==='string'?value:JSON.stringify(value,null,2),pre=el('pre',''),more=el('button','secondary-button',tr("继续显示（仅显示分页，数据未裁剪）"));let offset=0;const next=()=>{pre.append(document.createTextNode(text.slice(offset,offset+30000)));offset+=30000;more.hidden=offset>=text.length;};more.onclick=next;box.append(pre,more);next();return box;}
function jsonBlock(title,value){const d=el('details','event-detail');d.append(el('summary','',title));d.ontoggle=()=>{if(d.open&&!d.dataset.loaded){d.append(textViewer(value));d.dataset.loaded='true';}};return d;}
function handleEvent(run,event,replay=false){const {kind,data}=event;const u=run.ui;
 if(!renderTraceEvent(run,event))return;
 observeUsage(run,event);
 if(data.timing&&!replay)Object.assign(run,data.timing);
 if(['model_start','model_end','web_request'].includes(kind))renderUsage(run);
 if(kind==='model_queued'&&!replay){u.pending.textContent=tr("等待{0}空闲名额（配置并发 {1}）…", data.role==='main'?tr("主模型"):tr("摘要模型"), data.limit);u.summary.textContent=tr("模型请求排队中…");}
 else if(kind==='model_dequeued'&&!replay){u.pending.textContent=tr("已获得模型名额，正在请求…");u.summary.textContent=tr("研究进行中…");}
 else if(kind==='status'){u.pending.textContent=LucentI18n.serverText(data.text);u.summary.textContent=LucentI18n.serverText(data.text);}
 else if(kind==='usage'){run.usage=data.usage;renderUsage(run);updateTraceOverview(run);}
 else if(kind==='tool_done'){if(data.sources)run.sources=data.sources;u.source.textContent=tr("{0} 个来源 ↗", run.sources.length);updateTraceOverview(run);}
 else if(kind==='model_start'){if(data.purpose==='final'&&!replay){run.answer='';u.body.textContent='';}}
 else if(kind==='answer_delta'){if(!replay){run.answer=(run.answer||'')+data.text;u.body.textContent=run.answer;}}
 else if(kind==='incomplete'){if(!replay){run.answer=data.answer;run.status='incomplete';run.error=data.text;run.usage=data.usage;run.sources=data.sources;}renderRun(run);}
 else if(kind==='done'){if(!replay){run.answer=data.answer;run.sources=data.sources;run.usage=data.usage;run.status='completed';}renderRun(run);}
 else if((kind==='error'||kind==='cancelled')&&!replay){run.status=kind==='error'?'failed':'cancelled';run.error=data.text;renderRun(run);}
}
function withoutReasoning(value){if(Array.isArray(value))return value.filter(v=>!v||!['thinking','redacted_thinking','reasoning'].includes(v.type)&&!v.thought).map(withoutReasoning);if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([k])=>!['reasoning_content','_provider_native','provider_event','thinking','signature','thoughtSignature','encrypted_content'].includes(k)).map(([k,v])=>[k,withoutReasoning(v)]));return value;}
function debugValue(value){return $('#protocol-reasoning').checked?value:withoutReasoning(value);}
function renderDebug(){const d=debugData;if(!d)return;const box=$('#debug-content');box.replaceChildren();box.append(el('p','snapshot-badge',snapshotLabel(d.run.config_snapshot)),jsonBlock(tr("保存的配置快照（含提示词与哈希）"),d.run.config_snapshot),jsonBlock(tr("显式追问背景"),d.run.memory_context));const history=el('details','event-detail');history.append(el('summary','',tr("完整主研究记录（按需加载，含回退标记）")));history.ontoggle=async()=>{if(!history.open||history.dataset.loaded)return;try{const items=await api(`/api/runs/${d.run.id}/history`);history.append(textViewer(debugValue(items)));history.dataset.loaded='true';}catch(e){toast(e.message);}};box.append(history);const searchAudit=el('details','event-detail');searchAudit.append(el('summary','',tr("搜索服务原始响应（含后台保留的 content / summary，不等于发给主模型的内容）")));searchAudit.ontoggle=async()=>{if(!searchAudit.open||searchAudit.dataset.loaded)return;try{searchAudit.append(textViewer(await api(`/api/runs/${d.run.id}/search-responses`)));searchAudit.dataset.loaded='true';}catch(e){toast(e.message);}};box.append(searchAudit);const list=el('div','request-list');for(const r of d.requests){const row=el('details','request-row');row.append(el('summary','',tr("#{0} {1} / {2} · 尝试 {3} · 迭代 {4} · {5}", r.id, r.role==='main'?tr("主模型"):tr("独立提取模型"), r.purpose, r.attempt, r.iteration, r.status)));row.ontoggle=async()=>{if(!row.open||row.dataset.loaded)return;try{const payload=await api(`/api/runs/${d.run.id}/requests/${r.id}`);row.append(textViewer(debugValue(payload)));row.dataset.loaded='true';}catch(e){toast(e.message);}};list.append(row);}box.append(el('h3','',tr("实际发出的模型请求（每次 HTTP 调用）")),list);}
async function openDebug(id){debugData=await api(`/api/runs/${id}/details?include_history=false&include_events=false`);renderDebug();$('#debug').showModal();}
$('#close-debug').onclick=()=>$('#debug').close();$('#protocol-reasoning').onchange=renderDebug;
function watch(run){
 disconnect();const cid=state.cid;state.active=run.status==='running'?run.id:null;busy(!!state.active);
 const stream=new EventSource(appPath('/api/runs/'+run.id+'/events'));state.stream=stream;
 const selected=()=>state.cid===cid&&state.stream===stream&&state.runs.get(run.id)===run;
 stream.onmessage=e=>{if(selected())handleEvent(run,JSON.parse(e.data));};
 stream.addEventListener('closed',async()=>{
  stream.close();if(!selected())return;
  try{const c=await api('/api/conversations/'+cid);if(!selected())return;const saved=c.runs.find(r=>r.id===run.id);if(saved){Object.assign(run,saved);renderRun(run);}}
  catch(e){if(selected())toast(e.message);}
  finally{if(selected()){state.stream=null;state.active=null;busy(false);}refreshHistory().catch(()=>{});}
 });
 stream.onerror=()=>{if(!selected())return;if(run.status==='running')run.ui.pending.textContent=tr("正在重新连接…研究会在后台继续");else stream.close();};
}
async function loadEvents(run){const r=await fetch(appPath('/api/runs/'+run.id+'/events'));const text=await r.text();for(const block of text.split('\n\n')){const data=block.split('\n').find(l=>l.startsWith('data: '));if(data&&!block.includes('event: closed'))handleEvent(run,JSON.parse(data.slice(6)),true);}}
let opening=0;
async function openConversation(cid,{reveal=true}={}){
 const n=++opening,c=await api('/api/conversations/'+cid);if(n!==opening)return;
 disconnect();state.cid=cid;state.projectId=c.project_id||'default';state.active=null;state.loading=false;$('#send').disabled=false;state.runs.clear();
 localStorage.setItem(CONVERSATION_KEY,cid);const empty=c.runs.length===0;
 $('#welcome').classList.toggle('hidden',!empty);$('#conversation').classList.toggle('hidden',empty);$('#conversation').replaceChildren();
 $('#header-title').textContent=c.title==='新的研究'?tr('新对话'):c.title;Sidebar.closeMobile();Sidebar.select(state.projectId,reveal);$('#sources-panel').classList.add('hidden');
 for(const saved of c.runs){const run=addRun(saved);if(run.status==='running')watch(run);else loadEvents(run).catch(()=>{});}
 busy(!!state.active);await refreshHistory();if(n===opening)window.scrollTo({top:empty?0:document.body.scrollHeight});
}
function showSources(sources){state.sources=sources;$('#sources-list').replaceChildren();$('#source-count').textContent=sources.length;$('#sources-panel').classList.remove('hidden');if(!sources.length)$('#sources-list').append(el('p','sources-description',tr("还没有发现外部来源。")));for(const s of sources){const url=safeUrl(s.url);if(!url)continue;const a=el('a','source-card');a.href=url;a.target='_blank';a.rel='noopener noreferrer';const top=el('div','source-number',String(s.id).padStart(2,'0'));top.append(el('span','read-tag',s.fetched?tr("原文已提取"):s.read_status==='search_content_fallback'?tr("搜索正文备用"):s.read_status==='search_summary_fallback'?tr("搜索摘要备用"):s.read_status==='extraction_failed'?tr("提取失败"):tr("仅搜索发现")));a.append(top,el('h3','',s.title));if(s.snippet)a.append(el('p','',s.snippet));a.append(el('span','source-domain',new URL(url).hostname+' ↗'));$('#sources-list').append(a);}}
$('#composer').onsubmit=async e=>{
 e.preventDefault();if(state.active||state.loading)return;const question=$('#question').value.trim();if(!question)return;
 const token={},view=opening;let cid=state.cid;state.loading=token;$('#send').disabled=true;
 try{
  const execution=currentExecution();
  if(!cid){cid=(await api('/api/conversations','POST',{project_id:state.projectId})).id;if(view===opening){state.cid=cid;localStorage.setItem(CONVERSATION_KEY,cid);}}
  const saved=await api(`/api/conversations/${cid}/runs`,'POST',{question,...execution});
  if(view===opening&&state.cid===cid){
   $('#welcome').classList.add('hidden');$('#conversation').classList.remove('hidden');$('#question').value='';
   const run=addRun({...saved,question,mode:execution.mode,status:'running',answer:'',sources:[],usage:{}});watch(run);
   window.scrollTo({top:document.body.scrollHeight,behavior:'smooth'});
  }
  await refreshHistory();
 }catch(e){toast(e.message);}finally{if(state.loading===token){state.loading=false;$('#send').disabled=false;}}
};
$('#question').onkeydown=e=>{if(e.key==='Enter'&&!e.shiftKey&&!e.isComposing){e.preventDefault();$('#composer').requestSubmit();}};
$('#new-chat').onclick=()=>Sidebar.newConversation();
$('#stop').onclick=async()=>{if(state.active){try{await api(`/api/runs/${state.active}/cancel`,'POST');}catch(e){toast(e.message);}}};
$('#menu').onclick=()=>Sidebar.toggle();
$('#close-sources').onclick=()=>$('#sources-panel').classList.add('hidden');
$('#export').onclick=()=>{if(!state.cid){toast(tr("开始研究后即可导出会话"));return;}const a=el('a');a.href=appPath(`/api/conversations/${state.cid}/export`);a.download='LucentThinker.md';a.click();};
for(const b of document.querySelectorAll('.suggestion'))b.onclick=()=>{$('#question').value=b.dataset.prompt;$('#question').focus();};
document.onkeydown=e=>{if((e.metaKey||e.ctrlKey)&&e.key==='k'){e.preventDefault();$('#new-chat').click();}if(e.key==='Escape'){Sidebar.closeMobile();$('#sources-panel').classList.add('hidden');}};
Sidebar.init();
(async()=>{try{migrateConversationSelection();await refreshHistory();const cid=localStorage.getItem(CONVERSATION_KEY);if(cid){try{await openConversation(cid,{reveal:false});}catch{reset();}}}catch(e){toast(e.message);}})();

setInterval(()=>{for(const run of state.runs.values())if(run.status==='running')renderTiming(run);for(const {c,node} of historyTimings.values())if(c.latest_status==='running')renderHistoryTiming(c,node);},1000);
let historyPolling=false;
setInterval(async()=>{if(historyPolling||historyMenu||document.hidden)return;historyPolling=true;try{await refreshHistory();}catch{}finally{historyPolling=false;}},4000);
