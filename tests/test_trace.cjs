const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');
const fs=require('node:fs');
class Element{
 constructor(tag,cls='',text=''){this.tag=tag;this.className=cls;this.textContent=text;this.children=[];this.dataset={};this.classList={add:()=>{}};}
 append(...nodes){this.children.push(...nodes);}
 replaceChildren(...nodes){this.children=nodes;}
}
function setup(){
 const context=vm.createContext({el:(...args)=>new Element(...args),markdown:(el,text)=>{el.textContent=text;},safeUrl:u=>u,URL});
 vm.runInContext(fs.readFileSync(require.resolve('../app/static/trace.js'),'utf8'),context);
 const run={status:'running',usage:{},sources:[],ui:{traceContent:new Element('div')}};
 context.initTrace(run);return {context,run};
}
test('public deltas display immediately; completion and replay never duplicate a card',()=>{
 const {context:c,run}=setup();
 c.renderTraceEvent(run,{id:1,kind:'model_start',data:{call_id:7,role:'main',purpose:'research',attempt:1,iteration:1}});
 const first={id:2,kind:'note_delta',data:{call_id:7,text:'我将先'}};
 c.renderTraceEvent(run,first);
 assert.equal(run.ui.traceState.notes.get(7).body.textContent,'我将先');
 c.renderTraceEvent(run,first);
 c.renderTraceEvent(run,{id:3,kind:'note_delta',data:{call_id:7,text:'核对来源。'}});
 c.renderTraceEvent(run,{id:4,kind:'note',data:{call_id:7,text:'我将先核对来源。',attempt:1,iteration:1}});
 assert.equal(run.ui.traceState.notes.size,1);
 assert.equal(run.ui.traceState.notes.get(7).body.textContent,'我将先核对来源。');
 assert.equal(run.ui.traceState.current.body.children.filter(x=>x.className==='public-note').length,1);
});
test('tool-only replies display public action and program-resolved URL; old notes still render',()=>{
 const {context:c,run}=setup();
 c.renderTraceEvent(run,{id:1,kind:'tool_start',data:{tool:'scrape_and_extract_info',attempt:1,iteration:2,arguments:{source_id:3,url:'https://e.org/a#2#1',info_to_extract:'日期',progress:'核对公告日期'}}});
 const card=run.ui.traceState.activeTool;
 assert.equal(card.args.url,'https://e.org/a#2#1');
 assert.equal(card.body.children[0].textContent,'模型公开行动说明：核对公告日期');
 c.renderTraceEvent(run,{id:2,kind:'note',data:{text:'旧记录',iteration:2,attempt:1}});
 assert.equal(run.ui.traceState.notes.get('legacy:2').body.textContent,'旧记录');
});
test('queue events update a visible row without inventing a model request',()=>{
 const {context:c,run}=setup();
 c.renderTraceEvent(run,{id:1,kind:'model_queued',data:{role:'main',purpose:'research',attempt:1,iteration:2,limit:1}});
 assert.equal(run.ui.traceState.requests.size,0);
 const row=run.ui.traceState.queueRow;
 assert.match(row.textContent,/主模型排队中.*并发 1/);
 c.renderTraceEvent(run,{id:2,kind:'model_dequeued',data:{waited_seconds:1.23}});
 assert.match(row.textContent,/等待 1.2 秒/);
 assert.equal(run.ui.traceState.queueRow,null);
 c.renderTraceEvent(run,{id:3,kind:'model_queued',data:{role:'summary',limit:1}});
 const cancelled=run.ui.traceState.queueRow;
 c.renderTraceEvent(run,{id:4,kind:'model_queue_cancelled',data:{role:'summary'}});
 assert.match(cancelled.textContent,/排队已取消/);
});

test('provider thinking is folded separately and event replay does not duplicate it',()=>{
 const {context:c,run}=setup();c.renderTraceEvent(run,{id:1,kind:'model_start',data:{call_id:9,role:'main',purpose:'research'}});
 const event={id:2,kind:'reasoning_delta',data:{call_id:9,text:'Provider summary'}};
 c.renderTraceEvent(run,event);c.renderTraceEvent(run,event);
 const thought=run.ui.traceState.thoughts.get(9);assert.equal(thought.text.textContent,'Provider summary');assert.equal(thought.box.hidden,false);assert.equal(thought.box.open,undefined);
 c.renderTraceEvent(run,{id:3,kind:'model_characters',data:{call_id:9,content_chars:4,reasoning_chars:16}});
 assert.match(run.ui.traceState.characters.get(9).textContent,/正文 4.*思考 16/);assert.equal(run.ui.traceState.notes.size,0);
});
