'use strict';
var tr = globalThis.LucentI18n?.t || ((text,...values)=>typeof text==='string'?text.replace(/\{(\d+)\}/g,(_,i)=>values[i]??_):text);
let settingsDoc=null, settingsTab='models', currentSupplier=null, settingsBusy=false;
let pickerModels=[], pickerSupplier=null, settingsDraftEpoch=0;
const tiers={quick:10,standard:50,deep:200};
function option(value,text){const n=el('option','',text);n.value=value;return n;}
function supplierPath(id=currentSupplier){return '/api/settings/suppliers/'+encodeURIComponent(id);}
function modelPath(id,sid=currentSupplier){return supplierPath(sid)+'/models/'+encodeURIComponent(id);}
function modelLabel(p){return p.display_name||`${p.supplier_name||p.name} / ${p.model}`;}
function acceptSettings(doc){settingsDoc=doc;renderComposerModels(true);}
function renderComposerModels(keep=true){
 for(const role of ['main','summary']){
  const select=$('#composer-'+role+'-profile'),old=keep?select.value:null;
  select.replaceChildren(option('',tr("请选择")+(role==='main'?tr("主模型"):tr("摘要模型"))));
  for(const p of Object.values(settingsDoc.profiles)){
   const o=option(p.id,modelLabel(p)+(p.capabilities?.unavailable?tr(" · 模块停用"):''));o.disabled=!!p.capabilities?.unavailable;select.append(o);
  }
  select.value=old&&settingsDoc.profiles[old]?old:(settingsDoc.active[role]||'');
 }
 updateComposerBadge();
}
function updateComposerBadge(){
 const p=settingsDoc?.profiles[$('#composer-main-profile').value];$('.model-badge').textContent=p?modelLabel(p):tr("请选择主模型");
 for(const role of ['main','summary']){const select=$('#composer-'+role+'-profile'),profile=settingsDoc?.profiles[select.value];select.title=profile?modelLabel(profile):tr("请选择模型");}
}
function currentExecution(){
 if(!settingsDoc)throw Error(tr("正在加载研究设置"));const r=settingsDoc.research,tier=$('#mode').value;
 const n=tier==='custom'?Number($('#composer-iterations').value):tiers[tier];
 if(!Number.isSafeInteger(n)||n<1)throw Error(tr("迭代上限必须为正整数"));
 const main=$('#composer-main-profile').value,summary=$('#composer-summary-profile').value;
 for(const id of [main,summary])if(!settingsDoc.profiles[id]||settingsDoc.profiles[id].capabilities?.unavailable)throw Error(tr("请选择有效的主模型和摘要模型"));
 return {language:globalThis.LucentI18n?.language||'zh',mode:r.preset,memory_mode:r.memory_mode,max_iterations:n,keep_tool_result:r.keep_tool_result,context_compress_limit:r.context_compress_limit,main_profile:main,summary_profile:summary};
}
let selectionSave=Promise.resolve();
for(const role of ['main','summary'])$('#composer-'+role+'-profile').onchange=()=>{
 updateComposerBadge();const main=$('#composer-main-profile').value,summary=$('#composer-summary-profile').value;
 if(!main||!summary)return;
 selectionSave=selectionSave.catch(()=>{}).then(async()=>{const d=await api('/api/settings/active','PUT',{main,summary});settingsDoc.active=d.active;}).catch(e=>toast(e.message));
};
function syncComposer(){const r=settingsDoc.research;$('#mode').value=r.iteration_tier;$('#composer-iterations').value=r.max_iterations;$('#composer-iterations').classList.toggle('hidden',r.iteration_tier!=='custom');}
async function loadSettings(){const c=await api('/api/config');if(!c.settings?.suppliers||!c.settings?.research_profiles)throw Error(tr("后台尚未更新，请退出应用并重新运行启动脚本。"));appConfig=c;acceptSettings(c.settings);syncComposer();globalThis.LucentI18n?.restoreDraft();updateComposerBadge();}
const KEY_MASK='••••••••••••••••';
function maskSavedKey(input,configured){input.type='password';input.value=configured?KEY_MASK:'';input.dataset.dirty='false';input.dataset.masked=String(!!configured);input.dataset.configured=String(!!configured);}
function startKeyEdit(input){if(input.dataset.masked==='true'){input.value='';input.dataset.masked='false';}}
for(const id of ['supplier-key','web-key']){
 const input=$('#'+id);input.onfocus=()=>startKeyEdit(input);
 input.onblur=()=>{if(input.dataset.dirty!=='true'&&!input.value)maskSavedKey(input,input.dataset.configured==='true');};
}
function hideKeys(){for(const id of ['supplier-key','web-key']){const input=$('#'+id);input.value='';input.type='password';input.dataset.dirty='false';input.dataset.masked='false';}$('#reveal-supplier-key').textContent=$('#reveal-web-key').textContent=tr("显示");}
async function action(result,work){
 if(settingsBusy)return;settingsBusy=true;
 const controls=[...document.querySelectorAll('#settings button,#settings input,#settings select,#model-picker button,#model-picker input')].filter(n=>!['close-settings','close-model-picker'].includes(n.id));
 const previous=controls.map(n=>n.disabled);controls.forEach(n=>n.disabled=true);result.textContent=tr("正在处理…");
 try{await work();}catch(e){result.textContent=e.message;}finally{settingsBusy=false;controls.forEach((n,i)=>n.disabled=previous[i]);if(currentSupplier&&settingsDoc?.suppliers[currentSupplier])$('#delete-supplier').disabled=!!settingsDoc.suppliers[currentSupplier].builtin;if(settingsDoc?.research_profiles)updateResearchControls();}
}
function supplierModels(sid=currentSupplier){return Object.values(settingsDoc.profiles).filter(p=>p.supplier_id===sid);}
function renderSupplierSidebar(){
 const list=$('#supplier-list');list.replaceChildren();
 for(const s of Object.values(settingsDoc.suppliers)){
  const b=el('button','supplier-item'+(s.id===currentSupplier?' selected':''));b.type='button';b.dataset.supplierId=s.id;
  b.append(el('strong','',s.name),el('small','',tr("{0}{1} · {2} 个模型", s.builtin?tr("内置 · "):'', s.unavailable?tr("模块停用"):s.provider==='openai'?tr("OpenAI 兼容"):s.provider==='deepseek'?'DeepSeek':s.module?.fixed_model?tr("Gemini 原生"):s.module?.default_thinking_preset?tr("官方接口"):tr("原生协议"), supplierModels(s.id).length)));
  b.onclick=()=>{if(!settingsBusy)showSupplier(s.id);};list.append(b);
 }
}
function showSupplier(id){
 currentSupplier=id;settingsDraftEpoch++;const s=settingsDoc.suppliers[id];if(!s)return;
 hideKeys();renderSupplierSidebar();$('#supplier-title').textContent=s.name;
 $('#supplier-kind').textContent=s.unavailable?tr("模块已停用，请先恢复模块或选择其他供应商。"):s.provider==='openai'?tr("OpenAI 兼容接口"):s.provider==='deepseek'?tr("DeepSeek 官方模块"):s.module?.name||s.provider;
 const bases=s.module?.base_urls||[];const baseSelect=$('#supplier-base-options');baseSelect.replaceChildren(...bases.map(v=>option(v,v)));baseSelect.value=s.base_url;baseSelect.classList.toggle('hidden',bases.length<2);$('#supplier-base').classList.toggle('hidden',bases.length>1);$('#manual-add-model').disabled=!!s.unavailable||(s.provider!=='openai'&&!s.module?.allow_manual_models);
 $('#supplier-name').value=s.name;$('#supplier-base').value=s.base_url;$('#supplier-base').readOnly=s.provider!=='openai';
 maskSavedKey($('#supplier-key'),s.configured);$('#supplier-key').placeholder=s.configured?tr("已保存；留空保留原 Key"):tr("可留空（不发送鉴权头）");
 $('#supplier-note').textContent=tr(s.migration_note||s.module?.reasoning_source||'');$('#supplier-note').classList.toggle('hidden',!$('#supplier-note').textContent);
 $('#supplier-result').textContent='';$('#delete-supplier').disabled=!!s.builtin;$('#delete-supplier').title=s.builtin?tr("内置供应商可清空 Key；可拆卸模块的停用方式见 README"):'';
 $('#refresh-supplier-models').disabled=!!s.unavailable;$('#save-supplier').disabled=!!s.unavailable;renderModelRows();
}
function supplierDraft(){return {name:$('#supplier-name').value.trim(),base_url:$('#supplier-base').value.trim(),api_key:$('#supplier-key').dataset.dirty==='true'?$('#supplier-key').value:null};}
async function persistSupplier(){
 const doc=await api(supplierPath(),'PUT',supplierDraft());acceptSettings(doc);
 maskSavedKey($('#supplier-key'),doc.suppliers[currentSupplier].configured);$('#reveal-supplier-key').textContent=tr("显示");$('#supplier-title').textContent=doc.suppliers[currentSupplier].name;renderSupplierSidebar();
}
function labeledControl(label,node){const wrap=el('label','');wrap.append(el('span','',label),node);return wrap;}
function numberField(value,step='any'){const n=el('input');n.type='number';n.step=step;n.value=value??'';return n;}
function renderModelRows(){
 const box=$('#supplier-models'),s=settingsDoc.suppliers[currentSupplier],models=supplierModels();box.replaceChildren();$('#supplier-model-count').textContent=models.length+tr(" 个");
 if(!models.length){box.append(el('p','empty-models',tr("还没有加入模型。填写供应商信息，点击“刷新模型列表 / 添加模型”选择模型。")));return;}
 for(const p of models){
  const sid=currentSupplier,row=el('article','supplier-model-row');row.dataset.modelId=p.id;
  const heading=el('div','model-row-heading');heading.append(el('strong','',p.model),el('small','',modelLabel(p)));row.append(heading);
  const controls=el('div','model-row-controls');const concurrency=numberField(p.concurrency??1,'1');concurrency.min='1';concurrency.setAttribute('aria-label',p.model+tr(" 并发数"));controls.append(labeledControl(tr("并发数"),concurrency));
  let thinking=null,effort=null,thinkingDraft=p.thinking_config||null,goChoice=p.go_reasoning??null,reasoningBudget=p.reasoning_budget??null;
  const thinkingButton=el('button','secondary-button',tr("思考设置"));thinkingButton.type='button';thinkingButton.setAttribute('aria-label',p.model+tr(" 思考设置"));controls.append(thinkingButton);
  thinkingButton.onclick=()=>openThinking({...p,thinking_config:thinkingDraft,go_reasoning:goChoice,reasoning_budget:reasoningBudget,thinking:thinking?.value||p.thinking,reasoning_effort:effort?.value??p.reasoning_effort},s,values=>{thinkingDraft=values.thinking_config;goChoice=values.go_reasoning;reasoningBudget=values.reasoning_budget;if(values.thinking!==undefined&&thinking)thinking.value=values.thinking;if(values.reasoning_effort!==undefined&&effort)effort.value=values.reasoning_effort;thinkingButton.textContent=tr("思考设置 · 已修改");if(s.provider==='opencode_go'){if(thinking)thinking.disabled=goChoice!==null;if(effort)effort.disabled=goChoice!==null;}invalidate();});
  if(s.provider==='deepseek'){
   thinking=el('select');thinking.append(option('enabled',tr("开启")),option('disabled',tr("关闭")));thinking.value=p.thinking||'enabled';controls.append(labeledControl(tr("DeepSeek 思考模式"),thinking));
   effort=el('select');effort.append(option('',tr("服务端默认")),...['low','high','max'].map(v=>option(v,v)));effort.value=p.reasoning_effort??'high';controls.append(labeledControl(tr("DeepSeek 思考档位"),effort));
  }else if(s.module&&!(s.provider==='opencode_go'&&goChoice!==null)){
   const spec=s.module.models.find(m=>m.id===p.model),levels=spec?.reasoning_levels||[];
   const defaultEffort=spec?.default_reasoning_effort||s.module.default_reasoning_effort;
   if(spec?.thinking_modes?.length){thinking=el('select');thinking.append(...spec.thinking_modes.map(v=>option(v,v==='enabled'?tr("开启"):tr("关闭"))));thinking.value=p.thinking||spec.default_thinking;controls.append(labeledControl(tr("思考模式"),thinking));}
   if(levels.length){effort=el('select');if(!defaultEffort)effort.append(option('',tr("服务端默认")));effort.append(...levels.map(v=>option(v,v)));effort.value=p.reasoning_effort||defaultEffort||'';controls.append(labeledControl(tr(spec?.reasoning_label)||tr("思考档位"),effort));}
   if(spec?.reasoning_note)row.append(el('p','capability-note',tr(spec.reasoning_note)));
   if(thinking&&effort){const syncEffort=()=>{effort.disabled=thinking.value==='disabled';};thinking.onchange=syncEffort;syncEffort();}
  }
  row.append(controls);
  const details=el('details','parameter-details');details.append(el('summary','',tr("采样参数")));const samples=el('div','settings-grid');
  const temperature=numberField(p.temperature),topP=numberField(p.top_p);temperature.min='0';temperature.max='2';topP.min='0';topP.max='1';temperature.placeholder=topP.placeholder=tr("服务默认");
  samples.append(labeledControl('Temperature',temperature),labeledControl('Top P',topP));details.append(samples);row.append(details);
  function params(){const n=Number(concurrency.value);if(!Number.isSafeInteger(n)||n<1)throw Error(tr("模型并发数必须为正整数"));return {concurrency:n,thinking:goChoice!==null?null:thinking?.value||null,reasoning_effort:goChoice!==null?null:effort?.value??null,thinking_config:thinkingDraft,go_reasoning:goChoice,reasoning_budget:reasoningBudget,temperature:temperature.value===''?null:Number(temperature.value),top_p:topP.value===''?null:Number(topP.value)};}
  const actions=el('div','settings-actions'),result=el('pre','test-result');result.setAttribute('role','status');
  function invalidate(){settingsDraftEpoch++;result.textContent='';}
  row.addEventListener('input',invalidate);row.addEventListener('change',invalidate);
  const save=el('button','primary-button',tr("保存参数")),test=el('button','secondary-button',tr("测试连接")),tools=el('button','secondary-button',tr("测试工具")),probe=el('button','secondary-button',tr("检查参数校验")),remove=el('button','danger-button',tr("移除模型"));
  save.onclick=()=>action(result,async()=>{const values=params();await persistSupplier();acceptSettings(await api(modelPath(p.id,sid),'PUT',values));thinkingButton.textContent=tr("思考设置");result.textContent=tr("参数已保存，并发数立即生效；生成参数用于新研究。");});
  for(const [button,useTools,negative] of [[test,false,false],[tools,true,false],[probe,false,true]])button.onclick=()=>action(result,async()=>{const values=params();await persistSupplier();const epoch=settingsDraftEpoch;const r=await api(modelPath(p.id,sid)+'/test'+(useTools?'?tools=true':negative?'?probe=true':''),'POST',values);if(currentSupplier===sid&&epoch===settingsDraftEpoch)result.textContent=formatThinkingTest(r);});
  remove.onclick=async()=>{if(settingsBusy||!await conversationDialog(tr("移除模型"),tr("移除 {0}？历史研究不受影响；正在选用它的输入区选项将清空。", modelLabel(p))))return;action(result,async()=>{acceptSettings(await api(modelPath(p.id,sid),'DELETE'));renderSupplierSidebar();renderModelRows();});};
  if(s.unavailable){save.disabled=test.disabled=tools.disabled=probe.disabled=thinkingButton.disabled=true;}
  actions.append(save,test,tools,probe,remove);row.append(actions,result);box.append(row);
 }
}
$('#supplier-key').oninput=()=>{$('#supplier-key').dataset.dirty='true';$('#supplier-key').dataset.masked='false';};
$('#clear-supplier-key').onclick=()=>{$('#supplier-key').value='';$('#supplier-key').dataset.dirty='true';$('#supplier-result').textContent=tr("保存后将移除 Key，使用无鉴权请求。");};
$('#reveal-supplier-key').onclick=async()=>{
 const input=$('#supplier-key');if(input.type==='text'){input.type='password';$('#reveal-supplier-key').textContent=tr("显示");return;}
 try{const sid=currentSupplier;if(input.dataset.dirty!=='true'){const data=await api(supplierPath(sid)+'/reveal','POST');if(currentSupplier!==sid||!$('#settings').open)return;input.value=data.api_key;input.dataset.masked='false';}input.type='text';$('#reveal-supplier-key').textContent=tr("隐藏");}catch(e){toast(e.message);}
};
$('#save-supplier').onclick=()=>action($('#supplier-result'),async()=>{await persistSupplier();renderModelRows();$('#supplier-result').textContent=tr("供应商已保存。此供应商的模型共用地址和 Key；正在进行的研究保持原快照。");});
$('#new-supplier').onclick=async()=>{
 if(settingsBusy)return;const name=await conversationDialog(tr("新增 OpenAI 兼容供应商"),tr("为此供应商取一个不同的名称。"),'',tr("供应商名称"));if(name===null)return;
 action($('#supplier-result'),async()=>{const r=await api('/api/settings/suppliers','POST',{name,base_url:'',api_key:''});acceptSettings(r.settings);showSupplier(r.id);});
};
$('#delete-supplier').onclick=async()=>{
 if(settingsBusy)return;const s=settingsDoc.suppliers[currentSupplier];if(s.builtin)return;
 if(!await conversationDialog(tr("删除供应商"),tr("删除 {0} 及其已加入模型？历史研究保持不变，使用它的模型选择将清空。", s.name)))return;
 action($('#supplier-result'),async()=>{acceptSettings(await api(supplierPath(),'DELETE'));showSupplier(Object.keys(settingsDoc.suppliers)[0]);});
};
function renderPicker(){
 const list=$('#model-picker-list');list.replaceChildren();const existing=new Set(supplierModels(pickerSupplier).map(p=>p.model));
 for(const m of pickerModels){const label=el('label','picker-model');label.dataset.search=m.id.toLowerCase();const check=el('input');check.type='checkbox';check.value=m.id;check.checked=existing.has(m.id);check.disabled=existing.has(m.id);label.append(check,el('span','',m.id),el('small','',existing.has(m.id)?tr("已加入"):m.name||''));list.append(label);}
 $('#model-picker-filter').value='';$('#model-picker-result').textContent='';
}
$('#refresh-supplier-models').onclick=()=>action($('#supplier-result'),async()=>{
 await persistSupplier();const r=await api(supplierPath()+'/discover','POST');if(!r.ok)throw Error(r.message);
 pickerModels=r.models;pickerSupplier=currentSupplier;renderPicker();$('#model-picker-description').textContent=tr("{0} · 拉取到 {1} 个模型。勾选后加入；已加入模型的参数保持不变。", settingsDoc.suppliers[currentSupplier].name, r.models.length);
 $('#supplier-result').textContent=tr("模型列表已获取。");const notices=[];if(r.unmapped_models?.length)notices.push(tr("未登记协议的模型已排除：")+r.unmapped_models.join('、'));if(r.saved_missing_models?.length)notices.push(tr("目录未返回的已保存模型仍保留：")+r.saved_missing_models.join('、'));if(notices.length)$('#model-picker-description').textContent+=' '+notices.join('。');$('#model-picker').showModal();
});
$('#model-picker-filter').oninput=()=>{const term=$('#model-picker-filter').value.toLowerCase();for(const n of $('#model-picker-list').children)n.classList.toggle('hidden',!n.dataset.search.includes(term));};
$('#model-picker-all').onclick=()=>{for(const n of $('#model-picker-list').querySelectorAll('input:not(:disabled)'))n.checked=true;};
$('#model-picker-none').onclick=()=>{for(const n of $('#model-picker-list').querySelectorAll('input:not(:disabled)'))n.checked=false;};
$('#close-model-picker').onclick=()=>$('#model-picker').close();
$('#add-picked-models').onclick=()=>{
 const names=[...$('#model-picker-list').querySelectorAll('input:checked')].map(n=>n.value);
 action($('#model-picker-result'),async()=>{
  const r=await api(supplierPath(pickerSupplier)+'/models','POST',{models:names});acceptSettings(r.settings);$('#model-picker').close();renderSupplierSidebar();renderModelRows();$('#supplier-result').textContent=tr("已加入 {0} 个模型。请在对话输入区选择研究使用的模型。", r.added.length);
 });
};
function renderWeb(){const select=$('#web-profile');select.replaceChildren(option('',tr("单独输入 DeepSeek API Key")));for(const p of Object.values(settingsDoc.profiles).filter(p=>['openai','deepseek'].includes(p.provider)))select.append(option(p.id,tr("复用：")+modelLabel(p)));select.value=settingsDoc.web.credential_profile||'';maskSavedKey($('#web-key'),settingsDoc.web.independent_configured);$('#reveal-web-key').textContent=tr("显示");$('#web-key').placeholder=settingsDoc.web.configured?tr("已配置；留空保留原 Key"):tr("输入 DeepSeek API Key");$('#web-key-status').textContent=settingsDoc.web.configured?tr("DeepSeek 凭据已配置"):tr("尚未配置 DeepSeek 凭据");$('#web-key-field').classList.toggle('hidden',!!select.value);$('#web-result').textContent='';}
function webDraft(){return {api_key:$('#web-key').dataset.dirty==='true'?$('#web-key').value:null,credential_profile:$('#web-profile').value||null};}
$('#web-key').oninput=()=>{$('#web-key').dataset.dirty='true';$('#web-key').dataset.masked='false';};
$('#web-profile').onchange=()=>$('#web-key-field').classList.toggle('hidden',!!$('#web-profile').value);
$('#reveal-web-key').onclick=async()=>{const input=$('#web-key');if(input.type==='text'){input.type='password';$('#reveal-web-key').textContent=tr("显示");return;}try{if(input.dataset.dirty!=='true'){const data=await api('/api/settings/web/reveal?independent=true','POST');if(!$('#settings').open)return;input.value=data.api_key;input.dataset.masked='false';}input.type='text';$('#reveal-web-key').textContent=tr("隐藏");}catch(e){toast(e.message);}};
$('#save-web').onclick=()=>action($('#web-result'),async()=>{acceptSettings(await api('/api/settings/web','PUT',webDraft()));maskSavedKey($('#web-key'),settingsDoc.web.independent_configured);$('#reveal-web-key').textContent=tr("显示");$('#web-result').textContent=tr("网页服务配置已保存，用于新研究。");});
for(const service of ['search','fetch'])$('#test-'+service).onclick=()=>action($('#web-result'),async()=>{$('#web-result').textContent=JSON.stringify(await api('/api/settings/web/test/'+service,'POST',webDraft()),null,2);});
function researchPath(id=settingsDoc.active_research_profile){return '/api/settings/research-profiles/'+encodeURIComponent(id);}
function researchDraft(){
 const iterations=Number($('#setting-iterations').value),count=Number($('#research-search-count').value);
 if(!Number.isSafeInteger(iterations)||iterations<1)throw Error(tr("迭代上限必须为正整数"));
 if(!Number.isSafeInteger(count)||count<1)throw Error(tr("Search 请求结果数必须为正整数"));
 return {preset:settingsDoc.research.preset,iteration_tier:$('#setting-tier').value,max_iterations:iterations,keep_tool_result:Number($('#setting-context').value),context_compress_limit:Number($('#setting-retries').value),memory_mode:$('#memory-mode').value,search_count:count};
}
function updateResearchControls(){
 const fixed=!!settingsDoc.research_profiles[settingsDoc.active_research_profile]?.builtin;
 for(const id of ['setting-tier','setting-iterations','setting-context','setting-retries','memory-mode','research-search-count','save-research','rename-research-profile','delete-research-profile'])$('#'+id).disabled=settingsBusy||fixed;
}
function renderResearch(){
 const r=settingsDoc.research,select=$('#research-profile-select');select.replaceChildren();
 for(const p of Object.values(settingsDoc.research_profiles))select.append(option(p.id,(p.builtin?tr(p.name):p.name)+(p.builtin?tr(" · 内置"):'')));
 select.value=settingsDoc.active_research_profile;$('#setting-tier').value=r.iteration_tier;$('#setting-iterations').value=r.max_iterations;
 $('#setting-context').value=String(r.keep_tool_result);$('#setting-retries').value=String(r.context_compress_limit);$('#memory-mode').value=r.memory_mode;$('#research-search-count').value=r.search_count;
 $('#research-result').textContent='';updateResearchControls();
}
$('#setting-tier').onchange=()=>{const v=$('#setting-tier').value;if(tiers[v])$('#setting-iterations').value=tiers[v];};
$('#setting-iterations').oninput=()=>$('#setting-tier').value='custom';
$('#research-profile-select').onchange=()=>{
 const id=$('#research-profile-select').value;
 action($('#research-result'),async()=>{try{acceptSettings(await api(researchPath(id)+'/activate','POST'));renderResearch();syncComposer();$('#research-result').textContent=tr("已选用此配置，用于新研究。");}catch(e){$('#research-profile-select').value=settingsDoc.active_research_profile;throw e;}});
};
$('#new-research-profile').onclick=async()=>{
 if(settingsBusy)return;
 let values;try{values=researchDraft();}catch(e){$('#research-result').textContent=e.message;return;}
 const name=await conversationDialog(tr("新增研究执行配置"),tr("复制当前参数，保存为一份可编辑的新配置。"),'',tr("配置名称"));if(name===null)return;
 action($('#research-result'),async()=>{const result=await api('/api/settings/research-profiles','POST',{name,...values});acceptSettings(result.settings);renderResearch();syncComposer();$('#research-result').textContent=tr("新配置已保存并选用，可继续修改参数。");});
};
$('#rename-research-profile').onclick=async()=>{
 if(settingsBusy)return;const p=settingsDoc.research_profiles[settingsDoc.active_research_profile];
 const name=await conversationDialog(tr("重命名研究执行配置"),tr("修改配置名称，已保存参数保持不变。"),p.name,tr("配置名称"));if(name===null)return;
 action($('#research-result'),async()=>{acceptSettings(await api(researchPath(p.id),'PATCH',{name}));const select=$('#research-profile-select');for(const o of select.children)if(o.value===p.id)o.textContent=name.trim();$('#research-result').textContent=tr("名称已保存。");});
};
$('#delete-research-profile').onclick=async()=>{
 if(settingsBusy)return;const p=settingsDoc.research_profiles[settingsDoc.active_research_profile];
 if(!await conversationDialog(tr("删除研究执行配置"),tr("删除“{0}”？删除后将选用默认配置，已有研究记录不受影响。", p.name)))return;
 action($('#research-result'),async()=>{acceptSettings(await api(researchPath(p.id),'DELETE'));renderResearch();syncComposer();$('#research-result').textContent=tr("配置已删除，已选用默认配置。");});
};
$('#save-research').onclick=()=>action($('#research-result'),async()=>{acceptSettings(await api(researchPath(),'PUT',researchDraft()));renderResearch();syncComposer();$('#research-result').textContent=tr("配置已保存，用于新研究。");});
$('#mode').onchange=()=>{const tier=$('#mode').value;if(tiers[tier])$('#composer-iterations').value=tiers[tier];$('#composer-iterations').classList.toggle('hidden',tier!=='custom');};
function switchTab(tab){if(settingsBusy)return;settingsTab=tab;for(const b of document.querySelectorAll('[data-tab]'))b.classList.toggle('selected',b.dataset.tab===tab);$('#model-settings-pane').classList.toggle('hidden',tab!=='models');$('#web-settings-pane').classList.toggle('hidden',tab!=='web');$('#research-settings-pane').classList.toggle('hidden',tab!=='research');if(tab==='web')renderWeb();else if(tab==='research')renderResearch();else if(!currentSupplier||!settingsDoc.suppliers[currentSupplier])showSupplier(Object.keys(settingsDoc.suppliers)[0]);}
for(const b of document.querySelectorAll('[data-tab]'))b.onclick=()=>switchTab(b.dataset.tab);
$('#settings-button').onclick=async()=>{try{await loadSettings();showSupplier(settingsDoc.suppliers[currentSupplier]?currentSupplier:Object.keys(settingsDoc.suppliers)[0]);switchTab(settingsTab);$('#settings').showModal();}catch(e){toast(e.message);}};
$('#close-settings').onclick=()=>$('#settings').close();$('#settings').addEventListener('close',()=>{hideKeys();$('#model-picker').close();});
loadSettings().catch(e=>toast(e.message));

$('#supplier-base-options').onchange=()=>{$('#supplier-base').value=$('#supplier-base-options').value;settingsDraftEpoch++;};
for(const id of ['supplier-base','supplier-key'])$('#'+id).addEventListener('input',()=>{settingsDraftEpoch++;for(const n of document.querySelectorAll('.test-result'))n.textContent='';});
$('#manual-add-model').onclick=async()=>{
 if(settingsBusy)return;const sid=currentSupplier;const model=await conversationDialog(tr("手动添加模型"),tr("填写服务商提供的准确模型 ID。"),'',tr("模型 ID"));if(!model?.trim())return;
 action($('#supplier-result'),async()=>{await persistSupplier();const r=await api(supplierPath(sid)+'/models','POST',{models:[model.trim()],manual:true});acceptSettings(r.settings);renderSupplierSidebar();renderModelRows();});
};
function formatThinkingTest(r){
 if(!r.ok)return tr(r.message)||tr("测试失败");
 const t=r.thinking,lines=[tr(r.message)||tr("测试完成"),tr("模型：{0}", r.model),tr("耗时：{0} 秒", r.elapsed_seconds),tr("回复：{0}", r.reply||'')];
 if(t){lines.push(tr("协议：{0}", t.protocol),tr("实际端点：{0}", t.endpoint),tr("实际思考参数：{0}", JSON.stringify(t.parameters,null,2)),tr("思考类型：{0}", t.output?.kind==='summary'?tr("摘要"):tr("服务端推理文本")),tr("可读思考：{0} 字符 · 思考 token：{1}", t.characters, t.reasoning_tokens??tr("未报告")));if(t.text)lines.push(t.text);lines.push(tr(t.note));if(t.probe)lines.push(tr("参数对照 {0}：{1}", t.probe.field||'', tr(t.probe.message)));}
 if(r.tool_round_trip!==null&&r.tool_round_trip!==undefined)lines.push(tr("工具结果回传：{0}", r.tool_round_trip?tr("通过"):tr("未通过")));lines.push(tr("用量：{0}", JSON.stringify(r.usage)));return lines.join('\n\n');
}
function openThinking(p,s,onApply){
 const dialog=$('#thinking-dialog'),fields=$('#thinking-fields'),note=$('#thinking-note');$('#thinking-title').textContent=p.model+tr(" · 思考设置");$('#thinking-error').textContent='';
 let read;
 const levelNames={default:tr("服务端默认"),enabled:tr("开启"),disabled:tr("关闭"),budget:tr("思考 token 预算")};
 const outputNames={default:tr("服务端默认"),summary:tr("请求思考摘要"),off:tr("不请求思考摘要（仍可思考）")};
 function select(values,current,names={}){const node=el('select');node.append(...values.map(v=>option(v,names[v]||v)));node.value=current;return node;}
 function budgetField(spec,current){const n=numberField(current??spec.default??'','1');n.min=spec.min??1;if(spec.max!==undefined)n.max=spec.max;fields.append(labeledControl(tr("思考 token 预算"),n));return n;}
 fields.replaceChildren();
 if(s.provider==='opencode_go'){
  const spec=s.module.models.find(m=>m.id===p.model)?.reasoning||{},legacy=p.go_reasoning===null||p.go_reasoning===undefined;
  const choice=select([...(legacy?['__legacy__']:[]),'',...Object.keys(spec.options||{})],legacy?'__legacy__':p.go_reasoning,{...levelNames,'':tr("服务端默认"),__legacy__:tr("保留已有设置")});
  fields.append(labeledControl(tr("强度 / 开关 / 预算"),choice));const budget=budgetField(spec.budget||{},p.reasoning_budget);
  const sync=()=>{budget.parentNode.hidden=choice.value!=='budget';};choice.onchange=sync;sync();
  note.textContent=(tr(spec.output?.note)||tr("接收服务端返回的独立思考文本。"))+(legacy?tr(" 已有设置：")+(p.thinking||'')+' '+(p.reasoning_effort||tr("服务端默认"))+tr("。选择“保留已有设置”保持原请求行为。"):'')+tr(" 输出策略由 Go 模型协议决定；服务端默认不额外设置强度。");
  read=()=>{if(choice.value==='budget'&&(!String(budget.value).trim()||!Number.isSafeInteger(Number(budget.value))||Number(budget.value)<(spec.budget?.min??1)||(spec.budget?.max!==undefined&&Number(budget.value)>spec.budget.max)))throw Error(tr("请输入此模型支持的整数预算"));return {thinking_config:null,go_reasoning:choice.value==='__legacy__'?null:choice.value,reasoning_budget:choice.value==='budget'?Number(budget.value):null};};
 }else if(s.provider==='deepseek'||s.provider==='fourrouter_argon'){
  const deep=s.provider==='deepseek',mode=select(['enabled','disabled'],p.thinking||'enabled',levelNames),level=select(deep?['','low','high','max']:['low','medium','high'],p.reasoning_effort??(deep?'high':'high'),{'':tr("服务端默认")});
  if(deep)fields.append(labeledControl(tr("思考模式"),mode));fields.append(labeledControl(tr("强度"),level));mode.onchange=()=>{level.disabled=mode.value==='disabled';};if(deep)mode.onchange();
  note.textContent=deep?tr("独立接收 reasoning_content；思考模式不发送 Temperature。服务端默认不发送强度参数。"):tr("Gemini 原生接口请求思考摘要；是否返回由服务端决定。");
  read=()=>({thinking_config:null,go_reasoning:null,reasoning_budget:null,thinking:deep?mode.value:null,reasoning_effort:level.value});
 }else{
  const catalog=settingsDoc.thinking_presets||[],current=p.thinking_config;
  const preset=select(['',...catalog.map(v=>v.id)],current?.preset||'',Object.fromEntries([['',tr("服务端默认")],...catalog.map(v=>[v.id,v.name])]));
  if(current&&!catalog.some(v=>v.id===current.preset))preset.append(option(current.preset,tr("预设不可用 · 请重新选择")));
  const options=el('div','thinking-options');fields.append(labeledControl(tr("思考预设"),preset),options);
  function render(initialize){
   options.replaceChildren();const spec=catalog.find(v=>v.id===preset.value);if(!spec){note.textContent=preset.value?tr("此预设不可用，请重新选择。"):tr("不添加思考参数，不改变接口协议；服务端返回的思考文本仍会接收。");read=()=>{if(preset.value)throw Error(tr("请重新选择有效预设"));return {thinking_config:null,go_reasoning:null,reasoning_budget:null};};return;}
   const v=initialize?{level:spec.defaultLevel,output:spec.output.defaultMode}:current;
   const level=select(spec.levels,v?.level||spec.defaultLevel,levelNames),output=select(spec.output.modes,v?.output||'default',outputNames),budget=numberField(v?.budget??spec.budget?.default??'','1');
   if(spec.budget){budget.min=spec.budget.min;budget.max=spec.budget.max;}
   options.append(labeledControl(tr("强度 / 开关"),level),labeledControl(tr("思考输出"),output),labeledControl(tr("思考 token 预算"),budget));
   const sync=()=>{budget.parentNode.hidden=level.value!=='budget';};level.onchange=sync;sync();
   note.textContent=tr(spec.note||'')+' '+tr(spec.output.note)+tr(" 协议：")+spec.protocol;
   read=()=>{if(level.value==='budget'&&(!String(budget.value).trim()||!Number.isSafeInteger(Number(budget.value))||Number(budget.value)<spec.budget.min||Number(budget.value)>spec.budget.max))throw Error(tr("请输入此预设支持的整数预算"));return {thinking_config:{preset:spec.id,level:level.value,output:output.value,...(level.value==='budget'?{budget:Number(budget.value)}:{})},go_reasoning:null,reasoning_budget:null};};
  }
  preset.onchange=()=>render(true);render(false);
 }
 $('#close-thinking').onclick=()=>dialog.close();$('#apply-thinking').onclick=()=>{try{onApply(read());dialog.close();}catch(e){$('#thinking-error').textContent=e.message;}};dialog.showModal();
}
