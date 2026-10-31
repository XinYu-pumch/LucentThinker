import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtemp, rm, readFile, access} from 'node:fs/promises';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';
import {spawn} from 'node:child_process';
import {createServer} from 'node:http';
import {once} from 'node:events';

const packageRoot=process.env.LUCENT_TEST_PACKAGE || fileURLToPath(new URL('..',import.meta.url));
const moduleURL=pathToFileURL(join(packageRoot,'lib/engine.js')).href;
const {Engine}=await import(moduleURL);
async function setup(t){
 const dataDir=await mkdtemp(join(tmpdir(),'Lucent 测试 space-'));
 const engine=new Engine({packageRoot,dataDir});
 const engines=[engine];
 t.after(async()=>{for(const owned of engines)await owned.dispose();await rm(dataDir,{recursive:true,force:true});});
 return {engine,dataDir,engines};
}
async function json(url,method='GET',body){
 const response=await fetch(url,{method,headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined});
 const value=await response.json();assert.equal(response.status,200,JSON.stringify(value));return value;
}
async function gone(pid,timeout=8000){
 const end=Date.now()+timeout;
 while(Date.now()<end){try{process.kill(pid,0);}catch(e){if(e.code==='ESRCH')return;throw e;}await new Promise(r=>setTimeout(r,30));}
 throw new Error('Process remains: '+pid);
}

test('concurrent views share one capability-protected engine; unload releases port and keeps records',async t=>{
 const {engine,dataDir,engines}=await setup(t);
 const views=await Promise.all([engine.session(),engine.session(),engine.session()]);
 assert.equal(new Set(views.map(v=>v.pid)).size,1);
 const {url,pid}=views[0],origin=new URL(url).origin;
 assert.equal((await fetch(origin+'/api/projects')).status,404);
 assert.equal((await fetch(url+'api/projects',{headers:{Origin:'https://untrusted.invalid'}})).status,403);
 const page=await fetch(url,{headers:{'Sec-Fetch-Site':'cross-site'}});
 assert.match(page.headers.get('content-security-policy'),/frame-ancestors dsh-app:\/\/app/);
 const html=await page.text();
 assert.ok(html.includes(new URL(url).pathname+'static/app.js?v='));
 for(const file of ['app.js','settings.js','search.js','dsh.js'])assert.equal((await fetch(url+'static/'+file)).status,200);
 const p=await json(url+'api/projects','POST',{name:'保留项目'});
 const c=await json(url+'api/conversations','POST',{project_id:p.id});
 await engine.dispose();await engine.dispose();await gone(pid);
 await assert.rejects(fetch(origin+'/'));
 await assert.rejects(access(join(dataDir,'engine-state.json')));
 await access(join(dataDir,'research.sqlite3'));
 await assert.rejects(engine.session(),/停用/);
 const next=new Engine({packageRoot,dataDir});engines.push(next);
 const reopened=await next.session();assert.notEqual(reopened.url,url);
 assert.equal((await json(reopened.url+'api/conversations/'+c.id)).project_id,p.id);
});

test('unloading during startup cannot leave a late child alive',async t=>{
 const {engine}=await setup(t);
 const pending=engine.start();await engine.dispose();await assert.rejects(pending,/停用/);
 assert.equal(engine.status().state,'stopped');assert.equal(engine.child,null);
});

test('another activation cannot take over or remove the first engine state',async t=>{
 const {engine,dataDir,engines}=await setup(t);const first=await engine.session();
 const second=new Engine({packageRoot,dataDir});engines.push(second);
 await assert.rejects(second.start());
 assert.equal(JSON.parse(await readFile(join(dataDir,'engine-state.json'),'utf8')).enginePid,first.pid);
 assert.equal((await fetch(first.url+'api/projects')).status,200);
});

test('stopping active research cancels the request and preserves saved records',async t=>{
 const {engine,dataDir,engines}=await setup(t);const {url,pid}=await engine.session();
 let called;const started=new Promise(r=>called=r);
 const mock=createServer((req,res)=>{req.resume();called();});
 mock.listen(0,'127.0.0.1');await once(mock,'listening');
 t.after(()=>{mock.closeAllConnections();mock.close();});
 const profile=await json(url+'api/settings/profiles','POST',{name:'Local fixture',base_url:`http://127.0.0.1:${mock.address().port}/v1`,api_key:'fixture-only',model:'fixture-model',provider:'openai'});
 await json(url+'api/settings/web','PUT',{api_key:'fixture-web'});
 const c=await json(url+'api/conversations','POST',{});
 const r=await json(url+`api/conversations/${c.id}/runs`,'POST',{question:'Local lifecycle fixture',main_profile:profile.id,summary_profile:profile.id});
 await Promise.race([started,new Promise((_,reject)=>setTimeout(()=>reject(new Error('Mock was not called')),5000).unref())]);
 const stream=await fetch(url+`api/runs/${r.id}/events`);const reader=stream.body.getReader();await reader.read();
 await engine.dispose();await gone(pid);await reader.cancel().catch(()=>{});
 const next=new Engine({packageRoot,dataDir});engines.push(next);const reopened=await next.session();
 const saved=await json(reopened.url+'api/conversations/'+c.id);
 assert.equal(saved.runs[0].status,'cancelled');assert.equal(saved.runs[0].question,'Local lifecycle fixture');
});

test('owner killed without cleanup: pipe watchdog exits engine and clears state',async t=>{
 const dataDir=await mkdtemp(join(tmpdir(),'lucent-dsh-owner-'));
 t.after(()=>rm(dataDir,{recursive:true,force:true}));
 const code=`import {Engine} from ${JSON.stringify(moduleURL)};const e=new Engine(${JSON.stringify({packageRoot,dataDir})});await e.start();console.log(JSON.stringify(e.status()));setInterval(()=>{},1000);`;
 const owner=spawn(process.execPath,['--input-type=module','-e',code],{stdio:['ignore','pipe','pipe']});
 t.after(()=>{if(owner.exitCode===null&&owner.signalCode===null)owner.kill('SIGKILL');});
 const state=await new Promise((resolve,reject)=>{let s='';owner.stdout.on('data',c=>{s+=c;if(s.includes('\n'))resolve(JSON.parse(s.split('\n')[0]));});owner.once('error',reject);owner.once('exit',()=>reject(new Error('Test owner exited before ready')));});
 owner.kill('SIGKILL');await once(owner,'close');await gone(state.pid);
 const diagnostics=await readFile(join(dataDir,'engine.log'),'utf8');
 await assert.rejects(access(join(dataDir,'engine-state.json')), diagnostics || 'No engine stderr output');
 await access(join(dataDir,'research.sqlite3'));
});

test('installed runtime completes research and reloads its Unicode report', async t => {
 const {engine, dataDir, engines} = await setup(t);
 const {url} = await engine.session();
 const answer = 'Windows verification report — 中文内容完整保存。';
 let calls = 0;
 const mock = createServer((req, res) => {
  let raw = '';
  req.on('data', chunk => raw += chunk);
  req.on('end', () => {
   calls++;
   const request = JSON.parse(raw);
   const message = request.tools?.length
    ? {role:'assistant', content:null, tool_calls:[{id:'finish-1', type:'function', function:{name:'finish_research', arguments:JSON.stringify({status:'ready', summary:'Local fixture complete', unresolved_questions:[]})}}]}
    : {role:'assistant', content:answer};
   res.writeHead(200, {'Content-Type':'application/json'});
   res.end(JSON.stringify({choices:[{index:0, message, finish_reason:message.tool_calls ? 'tool_calls' : 'stop'}], usage:{prompt_tokens:10, completion_tokens:10, total_tokens:20}}));
  });
 });
 mock.listen(0, '127.0.0.1'); await once(mock, 'listening');
 t.after(() => {mock.closeAllConnections(); mock.close();});
 const profile = await json(url+'api/settings/profiles', 'POST', {name:'测试 model', base_url:`http://127.0.0.1:${mock.address().port}/v1`, api_key:'fixture-only', model:'fixture-model', provider:'openai'});
 await json(url+'api/settings/web', 'PUT', {api_key:'fixture-web'});
 const conversation = await json(url+'api/conversations', 'POST', {});
 const run = await json(url+`api/conversations/${conversation.id}/runs`, 'POST', {question:'保存中文研究报告', main_profile:profile.id, summary_profile:profile.id});
 const deadline = Date.now()+15000;
 let saved;
 do {
  saved = await json(url+'api/conversations/'+conversation.id);
  if (saved.runs[0].status !== 'running') break;
  await new Promise(resolve => setTimeout(resolve, 50));
 } while (Date.now() < deadline);
 assert.equal(saved.runs[0].status, 'completed', JSON.stringify(saved.runs[0]));
 assert.ok(saved.runs[0].answer.includes(answer));
 assert.equal(calls, 2);
 await engine.dispose();
 const next = new Engine({packageRoot, dataDir}); engines.push(next);
 const reopened = await next.session();
 const restored = await json(reopened.url+'api/conversations/'+conversation.id);
 assert.equal(restored.runs[0].id, run.id);
 assert.equal(restored.runs[0].answer, saved.runs[0].answer);
});
