'use strict';
var tr = globalThis.LucentI18n?.t || ((text,...values)=>typeof text==='string'?text.replace(/\{(\d+)\}/g,(_,i)=>values[i]??_):text);
// User-facing event projection. It never requests or reconstructs private reasoning.
function initTrace(run){
 const u=run.ui, overview=el('div','trace-overview'), timeline=el('div','research-timeline');
 u.traceContent.append(overview,timeline);
 u.traceState={overview,timeline,steps:new Map(),requests:new Map(),thoughts:new Map(),characters:new Map(),notes:new Map(),seen:new Set(),current:null,activeTool:null};
 updateTraceOverview(run);
}
function updateTraceOverview(run){
 const t=run.ui.traceState;if(!t)return;const n=run.usage||{},sources=run.sources||[];
 t.overview.replaceChildren();
 for(const [label,value] of [[tr("搜索"),n.search_calls||0],[tr("网页读取"),n.extraction_calls||0],[tr("原文提取成功"),n.original_extractions??sources.filter(s=>s.fetched).length],[tr("搜索备用提取"),n.fallback_extractions||0]]){
  const chip=el('div','trace-metric');chip.append(el('strong','',String(value)),el('span','',label));t.overview.append(chip);
 }
 if(n.search_calls&&!n.extraction_calls&&run.status!=='running')t.overview.append(el('p','trace-warning',tr("本次仅使用搜索结果，未通过 Fetch 与独立摘要模型读取原文。")));
}
function traceStep(run,attempt=1,iteration=0,purpose='research'){
 const t=run.ui.traceState,key=`${attempt}:${iteration}:${purpose}`;
 if(!t.steps.has(key)){
  const box=el('details','research-step');box.open=true;
  const head=el('summary','step-heading'),title=purpose==='final'?tr("生成最终回答"):tr("第 {0} 次主模型迭代", iteration||'—');
  const activity=el('small','step-activity');
  head.append(el('span','step-dot',purpose==='final'?'✓':String(iteration||'·')),el('span','step-title',title),activity,el('small','step-attempt',tr("研究尝试 {0}", attempt)));
  const body=el('div','step-body');box.append(head,body);t.timeline.append(box);
  t.steps.set(key,{box,body,head,activity,searches:0,reads:0});
 }
 t.current=t.steps.get(key);return t.current;
}
function traceBody(run){return run.ui.traceState.current?.body||traceStep(run).body;}
function sourceLink(item){
 const card=el('div','result-card'),url=safeUrl(item.url),name=item.title||item.url||tr("未命名来源");
 const heading=url?el('a','result-title',name):el('strong','result-title',name);
 if(url){heading.href=url;heading.target='_blank';heading.rel='noopener noreferrer';}
 card.append(heading);
 const meta=[item.source_id?`[${item.source_id}]`:'',item.site_name||(url?new URL(url).hostname:''),item.date||''].filter(Boolean).join(' · ');
 card.append(el('small','result-meta',meta));
 if(item.snippet)card.append(el('p','result-snippet',item.snippet));
 return card;
}
function newToolCard(run,data){
 if(data.iteration)traceStep(run,data.attempt||1,data.iteration);
 const search=data.tool==='search',box=el('section','tool-card '+(search?'search-card':'read-card'));
 const step=run.ui.traceState.current||traceStep(run);step[search?'searches':'reads']++;
 step.activity.textContent=tr("搜索 {0} · 阅读 {1}", step.searches, step.reads);
 const head=el('div','tool-card-heading'),status=el('span','tool-status running',tr("进行中"));
 head.append(el('strong','',search?tr("⌕ 搜索"):tr("▤ 阅读网页")),status);box.append(head);
 const args=data.arguments||{},target=args.query||args.url||data.label||'';
 if(search){box.append(el('p','search-query',target));if(args.ori_question){const origin={search_intent:tr("模型生成的聚焦检索意图"),original_question:tr("原始问题"),query:tr("长问题采用本次搜索词；完整研究问题保留")};box.append(el('p','result-help',tr("检索意图：")+args.ori_question+'（'+(origin[args.ori_question_source]||tr("已保存的实际参数"))+'）'));}}
 else {box.append(sourceLink({url:target,title:target}));box.append(el('div','extract-task-label',tr("定向提取目标")),el('p','extract-task',args.info_to_extract||tr("旧记录未保存提取任务")));}
 const body=el('div','tool-card-body');if(args.progress)body.append(el('p','public-action', tr("模型公开行动说明：")+args.progress));box.append(body);traceBody(run).append(box);
 const card={box,body,status,args,tool:data.tool};run.ui.traceState.activeTool=card;return card;
}
function traceNotice(run,text,warning=false){text=globalThis.LucentI18n?.serverText(text)??text;traceBody(run).append(el('p',warning?'trace-warning':'trace-notice',text));}
function renderTraceEvent(run,event){
 const t=run.ui.traceState;if(event.id&&t.seen.has(event.id))return false;if(event.id)t.seen.add(event.id);
 const {kind,data:d}=event;
 if(kind==='model_queued'){
  if(d.role==='main')traceStep(run,d.attempt||1,d.iteration,d.purpose);
  const row=el('p','model-state',tr("{0}排队中 · 配置并发 {1}", d.role==='main'?tr("主模型"):tr("独立摘要模型"), d.limit));
  (d.role==='summary'&&t.activeTool?t.activeTool.body:traceBody(run)).append(row);
  t.queueRow=row;
 }else if(kind==='model_dequeued'||kind==='model_queue_cancelled'){
  if(t.queueRow)t.queueRow.textContent=kind==='model_queue_cancelled'?tr("排队已取消（未发出模型请求）"):tr("排队结束 · 等待 {0} 秒", d.waited_seconds.toFixed(1));
  t.queueRow=null;
 }else if(kind==='model_start'){
  if(d.role==='main')traceStep(run,d.attempt||1,d.iteration,d.purpose);
  const row=el('p','model-state',tr("{0}正在响应 · 请求 #{1}", d.role==='main'?tr("主模型"):tr("独立摘要模型"), d.call_id));
  (d.role==='summary'&&t.activeTool?t.activeTool.body:traceBody(run)).append(row);t.requests.set(d.call_id,row);
  const counts=el('small','model-characters',tr("已接收正文 0 字符 · 思考 0 字符"));row.parentNode?.append(counts);t.characters.set(d.call_id,counts);
  const thought=el('details','model-thought'),label=el('summary','',tr("思考文本 / 摘要")),text=el('pre','thought-text');thought.append(label,text);thought.hidden=true;
  (d.role==='summary'&&t.activeTool?t.activeTool.body:traceBody(run)).append(thought);t.thoughts.set(d.call_id,{box:thought,text});
 }else if(kind==='reasoning_delta'){
  const thought=t.thoughts.get(d.call_id);if(thought){thought.box.hidden=false;thought.text.textContent+=d.text;}
 }else if(kind==='model_characters'){
  const counts=t.characters.get(d.call_id);if(counts)counts.textContent=tr("已接收正文 {0} 字符 · 思考 {1} 字符", d.content_chars, d.reasoning_chars);
 }else if(kind==='model_end'){
  const row=t.requests.get(d.call_id);if(row){row.textContent=tr("{0} · 请求 #{1} · {2}{3}", d.role==='main'?tr("主模型"):tr("独立摘要模型"), d.call_id, d.status==='completed'?tr("已完成"):d.status==='incomplete'?tr("输出未完成"):d.status==='cancelled'?tr("已取消"):tr("失败"), d.usage?.total_tokens?' · '+d.usage.total_tokens.toLocaleString()+' tokens':'');if(d.error)row.append(el('span','trace-warning',d.error));}
 }else if(kind==='tool_start'){newToolCard(run,d);
 }else if(kind==='tool_done'){
  const card=t.activeTool||newToolCard(run,d),r=d.result||{};card.status.className='tool-status';
  if(d.tool==='search'){
   card.status.textContent=tr("找到 {0} 条结果", r.results?.length||0);
   const results=el('details','search-results');results.append(el('summary','',tr("查看搜索结果 · {0} 条", r.results?.length||0)));results.open=false;
   results.ontoggle=()=>{if(!results.open||results.dataset.loaded)return;for(const item of r.results||[])results.append(sourceLink(item));results.dataset.loaded='true';};card.body.append(results);
   card.body.append(el('p','result-help',tr("搜索结果用于发现来源，尚未核验原文。")));
  }else{
   card.status.textContent=r.success?(r.degraded?tr("搜索备用提取完成"):tr("原文定向提取完成")):tr("读取未完成");
   if(r.degraded){card.box.classList.add('degraded');card.body.append(el('p','trace-warning',tr("Fetch 失败：")+r.fetch_error+tr("。以下为 ")+(r.content_source==='search_content'?'Search content':'Search summary')+tr(" 经独立摘要模型提取的结果，并非 Fetch 成功。")));}
   if(r.extracted_info){const details=el('details','extraction-result');details.open=true;details.append(el('summary','',tr("返回主模型的提取结果")));const content=el('div','extracted-markdown');markdown(content,r.extracted_info,d.sources||run.sources);details.append(content);card.body.append(details);}
   if(!r.success)card.body.append(el('p','trace-warning',r.error||tr("没有可用提取结果")));
   if(r.tokens_used!==undefined)card.body.append(el('small','result-meta',tr("提取模型：{0} · {1}", r.model_used||tr("未调用/未返回"), r.tokens_used===null?tr("用量未知"):r.tokens_used+' tokens')));
  }
  t.activeTool=null;updateTraceOverview(run);
 }else if(kind==='note'||kind==='note_delta'){
  if(kind==='note'&&d.iteration)traceStep(run,d.attempt||1,d.iteration);
  const key=d.call_id||`legacy:${event.id}`;
  let note=t.notes.get(key);
  if(!note){
   const box=el('details','public-note');box.open=true;box.append(el('summary','',tr("研究进展 · 模型公开输出")));
   const body=el('div','extracted-markdown');box.append(body);traceBody(run).append(box);
   note={body,text:''};t.notes.set(key,note);
  }
  note.text=kind==='note'?d.text:note.text+d.text;
  if(kind==='note')markdown(note.body,note.text,run.sources);else note.body.textContent=note.text;
 }else if(['fetch_start','fetch_done','fetch_error','fetch_fallback','extraction_start','extraction_done','extraction_error'].includes(kind)){
  const card=t.activeTool;const labels={fetch_start:tr("正在获取网页正文"),fetch_done:tr("已获取正文 · {0} 字符", d.scrape_stats?.char_count?.toLocaleString()||0),fetch_error:tr("抓取失败：")+d.text,fetch_fallback:tr("转用当前 URL 的 ")+(d.content_source==='search_content'?'Search content':'Search summary')+tr("，继续独立提取"),extraction_start:tr("独立摘要模型按目标提取中"),extraction_done:tr("定向提取完成"),extraction_error:tr("独立提取失败")};
  (card?card.body:traceBody(run)).append(el('p',kind==='fetch_error'||kind==='fetch_fallback'||kind==='extraction_error'?'trace-warning':'read-stage',labels[kind]));
 }else if(kind==='tool_error'){
  if(t.activeTool){t.activeTool.status.textContent=tr("工具报错");t.activeTool.status.className='tool-status failed';}
  traceNotice(run,d.text,true);
 }else if(kind==='rollback'){
  if(t.activeTool){t.activeTool.status.textContent=tr("已回退（记录保留）");t.activeTool.box.classList.add('rolled-back');t.activeTool=null;}
  traceNotice(run,tr("本次交互已回退，记录保留：")+d.reason,true);
 }else if(kind==='evidence_status'){
  traceNotice(run,tr("本次研究尝试：原文提取成功 {0} 次 · 搜索备用提取 {1} 次 · 提取失败 {2} 次。", d.original_extractions, d.fallback_extractions, d.failed_extractions)+(d.search_calls&&!d.original_extractions?tr(" 尚无成功的原文提取，结论需注明核验缺口。"):''),!d.original_extractions&&d.search_calls>0);
 }else if(kind==='finish_requested'){
  traceNotice(run,(d.status==='blocked'?tr("研究结束，仍有缺口："):tr("已请求生成报告："))+d.summary);
  if(d.unresolved_questions?.length)traceNotice(run,tr("待核实：")+d.unresolved_questions.join('；'),true);
 }else if(['action_validation','research_retry','model_retry','final_retry','citation_warning','research_end'].includes(kind)){
  const text=d.text||(kind==='research_end'?tr("研究阶段结束 · {0}", d.reason==='model_finished'?tr("模型自主结束"):d.reason==='iteration_limit'?tr("达到迭代上限"):d.reason):tr("正在重试"));traceNotice(run,text,kind!=='research_end');
 }else if(['error','cancelled','incomplete'].includes(kind)){
  if(t.activeTool){t.activeTool.status.textContent=tr("已停止");t.activeTool.status.className='tool-status failed';}
  traceNotice(run,d.text,true);
 }
 return true;
}
