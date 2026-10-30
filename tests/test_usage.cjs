const test=require('node:test');
const assert=require('node:assert/strict');
const {tokenUsageDetails,observeUsage,usageTotals,usageNumber,webRequestCount}=require('../app/static/usage.js');

test('DeepSeek reports output, cache hit and miss without tokenization',()=>{
 assert.deepEqual(tokenUsageDetails({completion_tokens:20,prompt_tokens:100,prompt_cache_hit_tokens:64,prompt_cache_miss_tokens:36}),
  {completion_tokens:20,prompt_tokens:100,prompt_cache_hit_tokens:64,prompt_cache_miss_tokens:36});
 assert.equal(tokenUsageDetails({prompt_tokens:10,prompt_cache_hit_tokens:0}).prompt_cache_miss_tokens,10);
});
test('OpenAI-compatible cached_tokens supports deriving uncached input',()=>{
 const result=tokenUsageDetails({prompt_tokens:100,prompt_tokens_details:{cached_tokens:40},completion_tokens:12});
 assert.equal(result.prompt_cache_hit_tokens,40);assert.equal(result.prompt_cache_miss_tokens,60);
});
test('missing, invalid and contradictory cache fields are not zeros',()=>{
 for(const raw of [null,{}, {prompt_tokens:100}, {prompt_tokens:10,prompt_cache_hit_tokens:11},
  {prompt_tokens:10,prompt_cache_hit_tokens:3,prompt_cache_miss_tokens:8}]){
  const value=tokenUsageDetails(raw);
  assert.equal(value.prompt_cache_hit_tokens,null);assert.equal(value.prompt_cache_miss_tokens,null);
 }
 assert.equal(tokenUsageDetails({completion_tokens:-1}).completion_tokens,null);
 assert.equal(tokenUsageDetails({completion_tokens:'10'}).completion_tokens,null);
});
test('per-role totals include failures and retries; duplicate end events do not double count',()=>{
 const run={usage:{main:{calls:3},summary:{calls:1}}};
 const end=(id,role,usage)=>({kind:'model_end',data:{call_id:id,role,usage}});
 const first=end(1,'main',{completion_tokens:20,prompt_tokens:100,prompt_cache_hit_tokens:64,prompt_cache_miss_tokens:36});
 observeUsage(run,first);observeUsage(run,first);
 observeUsage(run,end(2,'main',null));
 observeUsage(run,end(3,'main',{completion_tokens:10,prompt_tokens:50}));
 observeUsage(run,end(4,'summary',{completion_tokens:5,prompt_tokens:30,prompt_tokens_details:{cached_tokens:10}}));
 const main=usageTotals(run,'main'),summary=usageTotals(run,'summary');
 assert.deepEqual(main.fields.completion_tokens,{value:30,known:2,missing:1});
 assert.deepEqual(main.fields.prompt_cache_hit_tokens,{value:64,known:1,missing:2});
 assert.equal(summary.fields.prompt_cache_miss_tokens.value,20);
 assert.match(usageNumber(main.fields.prompt_cache_hit_tokens,3),/64.*2 次/);
});
test('pending calls and completely missing responses remain unknown',()=>{
 const run={usage:{main:{calls:1}}};
 observeUsage(run,{kind:'model_start',data:{role:'main',call_id:1}});
 assert.equal(usageNumber(usageTotals(run,'main').fields.completion_tokens,1),'未知');
 assert.equal(usageNumber(usageTotals(run,'summary').fields.completion_tokens,0),'0');
});
test('historical aggregate cannot be misrepresented as cache details',()=>{
 const run={usage:{main:{calls:2,completion_tokens:30,prompt_tokens:80,usage_missing_calls:0}}};
 assert.equal(usageNumber(usageTotals(run,'main').fields.completion_tokens,2),'30');
 assert.equal(usageNumber(usageTotals(run,'main').fields.prompt_cache_hit_tokens,2),'未知');
});
test('HTTP request attempts are separate from logical tools and include retries',()=>{
 const run={usage:{search_calls:1,fetch_calls:1,search_http_requests:1,fetch_http_requests:0}};
 observeUsage(run,{kind:'web_request',data:{service:'search'}});
 observeUsage(run,{kind:'web_request',data:{service:'fetch'}});
 observeUsage(run,{kind:'web_request',data:{service:'fetch'}});
 assert.equal(webRequestCount(run,'search'),'1');assert.equal(webRequestCount(run,'fetch'),'2');
 assert.equal(run.usage.fetch_calls,1);
 assert.equal(webRequestCount({usage:{}},'fetch'),'未知');
});
test('saved live usage matches independently summed provider response values',()=>{
 const fs=require('node:fs'),path=require('node:path');
 const file=path.join(__dirname,'../data/usage-live-audit.json');
 if(!fs.existsSync(file))return;
 const fixture=JSON.parse(fs.readFileSync(file,'utf8'));
 const run={usage:fixture.saved_usage};
 for(const event of fixture.events)observeUsage(run,event);
 for(const role of ['main','summary']){
  const totals=usageTotals(run,role);
  for(const key of ['completion_tokens','prompt_cache_hit_tokens','prompt_cache_miss_tokens']){
   assert.equal(totals.fields[key].value,fixture.expected[role][key]);
   assert.equal(totals.fields[key].missing,0);
  }
 }
 assert.equal(webRequestCount(run,'search'),String(fixture.expected.search_requests));
 assert.equal(webRequestCount(run,'fetch'),String(fixture.expected.fetch_requests));
});
