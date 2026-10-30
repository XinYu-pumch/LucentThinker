'use strict';
var tr = globalThis.LucentI18n?.t || ((text,...values)=>typeof text==='string'?text.replace(/\{(\d+)\}/g,(_,i)=>values[i]??_):text);
// All values come from saved provider usage, never from tokenization or model names.
const tokenUsageFields=['completion_tokens','prompt_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens'];
function tokenCount(value){return Number.isSafeInteger(value)&&value>=0?value:null;}
function tokenUsageDetails(raw){
 const u=raw&&typeof raw==='object'?raw:{};
 const output=tokenCount(u.completion_tokens),input=tokenCount(u.prompt_tokens);
 let hit=tokenCount(u.prompt_cache_hit_tokens),miss=tokenCount(u.prompt_cache_miss_tokens);
 if(hit===null)hit=tokenCount(u.prompt_tokens_details?.cached_tokens);
 if(input!==null){
  if(hit===null&&miss!==null&&miss<=input)hit=input-miss;
  if(miss===null&&hit!==null&&hit<=input)miss=input-hit;
  if((hit!==null&&hit>input)||(miss!==null&&miss>input)||(hit!==null&&miss!==null&&hit+miss!==input))hit=miss=null;
 }
 return {completion_tokens:output,prompt_tokens:input,prompt_cache_hit_tokens:hit,prompt_cache_miss_tokens:miss};
}
function observeUsage(run,event){
 const {kind,data:d}=event;
 if((kind==='model_start'||kind==='model_end')&&d.call_id!==undefined){
  run.modelUsage??=new Map();
  if(kind==='model_end')run.modelUsage.set(d.call_id,{role:d.role,usage:tokenUsageDetails(d.usage)});
  else if(!run.modelUsage.has(d.call_id))run.modelUsage.set(d.call_id,{role:d.role,usage:tokenUsageDetails(null)});
 }
 if(kind==='web_request'&&['search','fetch'].includes(d.service)){
  run.apiUsage??={search:0,fetch:0};
  run.apiUsage[d.service]++;
 }
}
function usageTotals(run,role){
 const records=[...(run.modelUsage?.values()||[])].filter(r=>r.role===role);
 const saved=run.usage?.[role]||{};
 const calls=Math.max(tokenCount(saved.calls)||0,records.length);
 const fields={};
 for(const key of tokenUsageFields){
  const values=records.map(r=>r.usage[key]).filter(v=>v!==null);
  // Old records without model events may still have aggregate input/output totals.
  if(!records.length&&!key.startsWith('prompt_cache_')&&tokenCount(saved[key])!==null){
   fields[key]={value:saved[key],missing:tokenCount(saved.usage_missing_calls)??calls,known:calls-(tokenCount(saved.usage_missing_calls)??calls)};
  }else fields[key]={value:values.reduce((a,b)=>a+b,0),missing:Math.max(0,calls-values.length),known:values.length};
 }
 return {calls,fields};
}
function usageNumber(field,calls){
 if(calls===0)return '0';
 if(!field.known)return tr("未知");
 const text=field.value.toLocaleString();
 return field.missing?tr("{0}（已知；{1} 次未返回/待返回）", text, field.missing):text;
}
function webRequestCount(run,service){
 const saved=tokenCount(run.usage?.[service+'_http_requests']);
 const observed=run.apiUsage?.[service];
 return saved===null&&observed===undefined?tr("未知"):Math.max(saved??0,observed??0).toLocaleString();
}
function renderUsage(run){
 const box=run.ui.footer.querySelector('.run-usage'),u=run.usage||{};
 box.replaceChildren();
 if(!u.main){box.textContent=u.total_tokens?tr("{0} tokens（旧版统计）", u.total_tokens.toLocaleString()):'';return;}
 const wrap=el('div','usage-table-wrap'),table=el('table','usage-table');
 const caption=el('caption','',tr("本次研究用量 · 服务端返回值"));table.append(caption);
 const head=el('tr');
 for(const label of [tr("角色 / 请求"),tr("输出 tokens"),tr("输入 tokens（缓存命中）"),tr("输入 tokens（缓存未命中）"),tr("输入 tokens（合计）")])head.append(el('th','',label));
 const thead=el('thead');thead.append(head);table.append(thead);
 const tbody=el('tbody');
 for(const [role,label] of [['main',tr("主模型")],['summary',tr("摘要模型")]]){
  const totals=usageTotals(run,role),row=el('tr');row.append(el('th','',tr("{0} · {1} 次", label, totals.calls)));
  for(const key of ['completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens','prompt_tokens'])row.append(el('td','',usageNumber(totals.fields[key],totals.calls)));
  tbody.append(row);
 }
 table.append(tbody);wrap.append(table);box.append(wrap);
 box.append(el('p','usage-api',tr("DeepSeek Search API：{0} 次 · DeepSeek Fetch API：{1} 次（实际 HTTP 请求尝试，含重试）", webRequestCount(run,'search'), webRequestCount(run,'fetch'))));
 box.append(el('p','usage-note',tr("工具调用：Search {0} 次 / Fetch {1} 次 · 有效迭代 {2} 次 · 独立提取 {3} 次 · 搜索备用提取 {4} 次 · 研究尝试 {5} · 主/摘要模型错误 {6}/{7}", u.search_calls??0, u.fetch_calls??0, u.main_iterations??0, u.extraction_calls??0, u.fallback_extractions??0, u.research_attempts??0, u.main.errors??0, u.summary?.errors??0)));
 box.append(el('p','usage-note',tr("按本次研究全部请求累计，包含最终写作、重试和回退交互。输出以 completion_tokens 为准，可能含思考 token；未返回的用量不记为 0。API 请求尝试次数不等于供应商成功处理或计费次数。")));
}
if(typeof module!=='undefined')module.exports={tokenUsageDetails,observeUsage,usageTotals,usageNumber,webRequestCount};
