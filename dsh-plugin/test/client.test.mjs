import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import vm from 'node:vm';
import {contribution} from '../src/protocol.js';

const source=await readFile(new URL('../src/client.cjs',import.meta.url),'utf8');
function client(fail=false){
 const entries=[],disposers=[],messages=[];
 const service={session:async()=>({ok:true,value:{url:'http://127.0.0.1:1/'}})};
 const slots={inject(name,fn){const dispose=fn();disposers.push(dispose);},register(spec,component){const row={spec,component};entries.push(row);return()=>entries.splice(entries.indexOf(row),1);}};
 const remote=new Proxy({$mount:async data=>{assert.equal(data,contribution);if(fail)throw Error('fixture missing transport');}},
  {get(target,key){if(key==='lucentThinker')throw Error('cannot get remote.lucentThinker without inject');return target[key];}});
 const ctx={slots,remote,inject(deps,fn){assert.ok(deps.includes('remote.lucentThinker'));return fn({slots,remote:{lucentThinker:service}});}};
 const context=vm.createContext({exports:{},REMOTE_CONTRIBUTION:contribution,console:{error:(...args)=>messages.push(args)},
  require:()=>({createElement:()=>null,useState(){},useEffect(){}})});
 vm.runInContext(source,context);
 return {ctx,entries,disposers,messages,apply:context.exports.apply};
}
test('client declares dynamic Remote dependency before reading it and owns all three slots',async()=>{
 const c=client();await c.apply(c.ctx);assert.equal(c.messages.length,0);
 assert.deepEqual(c.entries.map(e=>e.spec.name),['main','sidebar.panellist','settings.section']);
 for(const dispose of c.disposers.reverse())dispose();assert.equal(c.entries.length,0);
});
test('client transport initialization failure is contained rather than rejecting DSH boot',async()=>{
 const c=client(true);await c.apply(c.ctx);assert.equal(c.messages.length,1);assert.equal(c.entries.length,0);
});

function surfaceHarness(saved){
 const hooks=[],effects=[],listeners=new Map(),storage=new Map(saved?[['LucentThinker-language',saved]]:[]);
 let cursor=0,intervals=0;
 const window={addEventListener(type,fn){if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn);},
  removeEventListener(type,fn){listeners.get(type)?.delete(fn);},dispatchEvent(e){for(const fn of listeners.get(e.type)||[])fn(e);}};
 const react={createElement:(tag,props,...children)=>({tag,props,children}),
  useState(initial){const i=cursor++;if(!hooks[i])hooks[i]={value:typeof initial==='function'?initial():initial};return [hooks[i].value,value=>{hooks[i].value=typeof value==='function'?value(hooks[i].value):value;}];},
  useRef(initial){const i=cursor++;return hooks[i]??=( {current:initial});},
  useEffect(fn,deps){const i=cursor++,old=hooks[i];if(!old||deps.some((v,n)=>v!==old.deps[n]))effects.push(()=>{old?.cleanup?.();hooks[i]={deps,cleanup:fn()};});}};
 const context=vm.createContext({exports:{},require:()=>react,URL,Event,window,console,
  localStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v)},
  setInterval:()=>++intervals,clearInterval:()=>{intervals--;}});
 vm.runInContext(source,context);
 const service={session:async()=>({ok:true,value:{url:'http://127.0.0.1:4567/dsh/test/'}})};
 return {context,storage,window,listeners,render(){cursor=0;const tree=context.Surface({service,settings:true});while(effects.length)effects.shift()();return tree;},
  dispose(){for(const h of hooks)h?.cleanup?.();},get intervals(){return intervals;}};
}
test('DSH defaults to English, persists trusted iframe choices and cleans up on disable',async()=>{
 const h=surfaceHarness();assert.match(JSON.stringify(h.render()),/Starting the LucentThinker/);
 await Promise.resolve();const ready=h.render(),frame=ready.children.find(x=>x?.tag==='iframe');
 assert.match(frame.props.src,/language=en&surface=settings/);
 assert.doesNotMatch(JSON.stringify(ready),/\p{Script=Han}/u);
 const source={};frame.props.ref.current={contentWindow:source};
 const data={type:'lucentthinker-language',language:'zh'};
 h.window.dispatchEvent({type:'message',origin:'http://untrusted.test',source,data});assert.equal(h.storage.size,0);
 h.window.dispatchEvent({type:'message',origin:'http://127.0.0.1:4567',source:{},data});assert.equal(h.storage.size,0);
 h.window.dispatchEvent({type:'message',origin:'http://127.0.0.1:4567',source,data});
 assert.equal(h.storage.get('LucentThinker-language'),'zh');
 const updated=h.render();assert.match(JSON.stringify(updated),/研究服务已就绪/);
 assert.equal(updated.children.find(x=>x?.tag==='iframe').props.src,frame.props.src,'do not reload the iframe twice and discard drafts');
 h.dispose();assert.equal(h.intervals,0);assert.equal([...h.listeners.values()].reduce((n,s)=>n+s.size,0),0);
 const reopened=surfaceHarness('zh');assert.match(JSON.stringify(reopened.render()),/正在启动/);reopened.dispose();
});
test('all application-owned engine errors have English shell translations',async()=>{
 const h=surfaceHarness();
 const engine=await readFile(new URL('../src/engine.js',import.meta.url),'utf8');
 const messages=[...engine.matchAll(/new Error\('([^']+)'\)/g)].map(m=>m[1]);
 for(const message of messages)assert.doesNotMatch(h.context.translate(message,'en'),/\p{Script=Han}/u);
 assert.equal(h.context.translate('研究引擎已退出（SIGTERM），请点击重试。','en'),'The research engine exited (SIGTERM). Please retry.');
});
