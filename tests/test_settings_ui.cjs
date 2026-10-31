const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
function setup(language='zh'){
 const nodes=new Map(),calls=[];
 function node(){return {value:'',textContent:'',type:'password',dataset:{},disabled:false,open:true,children:[],classList:{toggle(){}},replaceChildren(...ns){this.children=[];this.append(...ns);},append(...ns){for(const n of ns){if(n&&typeof n==='object')n.parentNode=this;this.children.push(n);}},showModal(){this.open=true;},close(){this.open=false;},addEventListener(){},setAttribute(){}};}
 const $=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id);};
 const context=vm.createContext({$,el:(tag,cls,text)=>({...node(),textContent:text}),document:{querySelectorAll:()=>[]},toast(){},conversationDialog:async()=>null,api:async(...args)=>{calls.push(args);return {api_key:'fixture-real-key'};}});
 const source=fs.readFileSync(require.resolve('../app/static/settings.js'),'utf8').replace('loadSettings().catch(e=>toast(e.message));','');
 const doc=context.document;delete context.document;context.localStorage={getItem:()=>language};
 for(const name of ['i18n-en','i18n'])vm.runInContext(fs.readFileSync(require.resolve('../app/static/'+name+'.js'),'utf8'),context);
 context.document=doc;vm.runInContext(source,context);
 return {context,$,calls};
}
test('Go exposes model-specific thinking controls and preserves effort while disabled',()=>{
 const {context:c,$}=setup();
 const manifest=JSON.parse(fs.readFileSync(require.resolve('../app/llm_providers/opencode_go/manifest.json'),'utf8'));
 c.goModels=Object.entries(manifest.models).map(([id,spec])=>({id,...spec}));
 vm.runInContext(`settingsDoc={suppliers:{go:{provider:'opencode_go',module:{models:goModels}}},profiles:{
  gemini:{id:'gemini',supplier_id:'go',model:'gemini-4-argon-contributor'},
  flash:{id:'flash',supplier_id:'go',model:'deepseek-v4.1-flash',reasoning_effort:'max',thinking:'disabled'},
  other:{id:'other',supplier_id:'go',model:'deepseek-v4-pro'}
 }};currentSupplier='go';`,c);
 c.renderModelRows();
 function control(row,label){return row.children.flatMap(n=>n.children||[]).find(n=>n.children?.[0]?.textContent===label)?.children[1];}
 const [gemini,flash,other]=$('#supplier-models').children;
 const geminiEffort=control(gemini,'Gemini 思考档位');
 assert.deepEqual(Array.from(geminiEffort.children,o=>o.value),['low','medium','high']);
 assert.equal(geminiEffort.value,'medium');assert.equal(control(gemini,'思考模式'),undefined);
 const flashMode=control(flash,'思考模式'),flashEffort=control(flash,'DeepSeek Flash 思考档位');
 assert.deepEqual(Array.from(flashEffort.children,o=>o.value),['low','high','max']);
 assert.equal(flashMode.value,'disabled');assert.equal(flashEffort.disabled,true);assert.equal(flashEffort.value,'max');
 flashMode.value='enabled';flashMode.onchange();assert.equal(flashEffort.disabled,false);assert.equal(flashEffort.value,'max');
 assert.equal(control(other,'思考模式'),undefined);assert.equal(control(other,'思考档位').children[0].value,'');
});
test('saved keys are masked; unchanged save never submits the mask; reveal loads real key',async()=>{
 const {context:c,$,calls}=setup();
 vm.runInContext("settingsDoc={suppliers:{one:{configured:true}},profiles:{},research_profiles:{}};currentSupplier='one';",c);
 const input=$('#supplier-key');c.maskSavedKey(input,true);
 assert.equal(input.type,'password');assert.ok(input.value.length>0);
 assert.equal(c.supplierDraft().api_key,null);
 await $('#reveal-supplier-key').onclick();
 assert.equal(input.type,'text');assert.equal(input.value,'fixture-real-key');
 assert.equal(calls[0][0],'/api/settings/suppliers/one/reveal');
 assert.equal(c.supplierDraft().api_key,null);
 c.maskSavedKey(input,true);input.onfocus();assert.equal(input.value,'');
 input.value='replacement';input.oninput();assert.equal(c.supplierDraft().api_key,'replacement');
 c.maskSavedKey(input,false);assert.equal(input.value,'');
});
test('web keys use independent saved key and credential changes do not submit search count',async()=>{
 const {context:c,$,calls}=setup();
 c.maskSavedKey($('#web-key'),true);
 assert.equal(c.webDraft().api_key,null);assert.equal('search_count' in c.webDraft(),false);
 await $('#reveal-web-key').onclick();
 assert.equal(calls[0][0],'/api/settings/web/reveal?independent=true');
 assert.equal($('#web-key').value,'fixture-real-key');
 assert.equal(c.webDraft().api_key,null);
});
test('research selector renders all five values, protects builtin, enables custom saving',()=>{
 const {context:c,$}=setup();
 vm.runInContext(`settingsDoc={active_research_profile:'default',research:{preset:'demo',iteration_tier:'deep',max_iterations:200,keep_tool_result:-1,context_compress_limit:5,memory_mode:'strict',search_count:20},research_profiles:{default:{id:'default',name:'默认配置',builtin:true},custom:{id:'custom',name:'My config',builtin:false}}};`,c);
 c.renderResearch();
 assert.equal($('#research-profile-select').children.length,2);
 assert.equal($('#setting-tier').value,'deep');assert.equal($('#setting-iterations').value,200);
 assert.equal($('#setting-context').value,'-1');assert.equal($('#setting-retries').value,'5');
 assert.equal($('#memory-mode').value,'strict');assert.equal($('#research-search-count').value,20);
 assert.equal($('#save-research').disabled,true);
 vm.runInContext("settingsDoc.active_research_profile='custom'",c);c.updateResearchControls();
 assert.equal($('#save-research').disabled,false);assert.equal($('#delete-research-profile').disabled,false);
 $('#research-search-count').value='35';assert.equal(c.researchDraft().search_count,35);
 $('#research-search-count').value='0';assert.throws(()=>c.researchDraft());
});

test('ordinary thinking dialog keeps output independent and validates budget',()=>{
 const {context:c,$}=setup();c.catalog=JSON.parse(fs.readFileSync(require.resolve('../app/thinking_presets.json'),'utf8'));vm.runInContext('settingsDoc={thinking_presets:catalog}',c);
 let applied;
 c.openThinking({model:'qwen3.8-flash',thinking_config:{preset:'qwen_openai',level:'budget',budget:0,output:'default'}},{provider:'openai'},v=>applied=v);
 $('#apply-thinking').onclick();assert.equal(applied.thinking_config.budget,0);
 c.openThinking({model:'claude',thinking_config:{preset:'claude55_messages',level:'high',output:'off'}},{provider:'openai'},v=>applied=v);
 $('#apply-thinking').onclick();assert.equal(applied.thinking_config.level,'high');assert.equal(applied.thinking_config.output,'off');
 const preset=$('#thinking-fields').children[0].children[1];preset.value='';preset.onchange();$('#apply-thinking').onclick();assert.equal(applied.thinking_config,null);
});
test('Go dialog preserves legacy choices until explicitly changed and rejects zero budget',()=>{
 const {context:c,$}=setup();const manifest=JSON.parse(fs.readFileSync(require.resolve('../app/llm_providers/opencode_go/manifest.json'),'utf8'));
 const s={provider:'opencode_go',module:{models:Object.entries(manifest.models).map(([id,spec])=>({id,...spec}))}};
 let applied;
 c.openThinking({model:'deepseek-v4.1-flash',thinking:'disabled',reasoning_effort:'max'},s,v=>applied=v);$('#apply-thinking').onclick();assert.equal(applied.go_reasoning,null);
 c.openThinking({model:'qwen3.8-flash',go_reasoning:'budget',reasoning_budget:0},s,v=>applied=v);$('#apply-thinking').onclick();assert.match($('#thinking-error').textContent,/整数预算/);
 const fields=$('#thinking-fields');fields.children[1].children[1].value='1024';$('#apply-thinking').onclick();assert.equal(applied.reasoning_budget,1024);
 fields.children[0].children[1].value='';$('#apply-thinking').onclick();assert.equal(applied.go_reasoning,'');assert.equal(applied.reasoning_budget,null);
});
test('diagnostics distinguish no readable output and missing reasoning usage',()=>{
 const {context:c}=setup();const text=c.formatThinkingTest({ok:true,model:'x',reply:'answer',thinking:{protocol:'messages',parameters:{thinking:{display:'summarized'}},output:{kind:'summary'},characters:0,reasoning_tokens:null,note:'reported only'}});
 assert.match(text,/可读思考：0 字符/);assert.match(text,/思考 token：未报告/);assert.match(text,/summarized/);
});

test('English provider names display locally but unchanged saves preserve the stored name',()=>{
 const {context:c,$}=setup('en');
 vm.runInContext("settingsDoc={suppliers:{supplier_summary:{id:'supplier_summary',name:'DeepSeek 独立提取'}},profiles:{}};currentSupplier='supplier_summary';",c);
 $('#supplier-name').value='DeepSeek extraction';
 assert.equal(c.supplierDraft().name,'DeepSeek 独立提取');
 assert.equal(c.modelLabel({supplier_id:'supplier_summary',model:'deepseek-flash'}),'DeepSeek extraction / deepseek-flash');
 $('#supplier-name').value='My extraction provider';
 assert.equal(c.supplierDraft().name,'My extraction provider');
});

test('web connection diagnostics translate application errors and preserve response content',()=>{
 const {context:c}=setup('en');
 const result=JSON.parse(c.formatWebTest({ok:false,message:'服务 HTTP 401：API Key 无效',sample:'原始来源'}));
 assert.equal(result.message,'Service HTTP 401: Invalid API key.');assert.equal(result.sample,'原始来源');
});
