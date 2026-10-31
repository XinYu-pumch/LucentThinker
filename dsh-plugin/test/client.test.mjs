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
