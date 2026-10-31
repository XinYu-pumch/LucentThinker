import {cp, mkdir, readFile, writeFile, rm, access} from 'node:fs/promises';
import {join, resolve} from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {contribution} from '../src/protocol.js';

const pkg=fileURLToPath(new URL('..',import.meta.url)), root=resolve(pkg,'..');
await mkdir(join(pkg,'lib'),{recursive:true});
for(const file of ['host.js','engine.js','protocol.js'])await cp(join(pkg,'src',file),join(pkg,'lib',file));
const client=await readFile(join(pkg,'src/client.cjs'),'utf8');
await writeFile(join(pkg,'lib/client.js'),`window.__ModuleLoader__.load({id:"dsh-plugin-lucentthinker",factory:require=>{const module={exports:{}};const exports=module.exports;Object.defineProperty(exports,Symbol.toStringTag,{value:"Module"});const REMOTE_CONTRIBUTION=${JSON.stringify(contribution)};\n${client}\nreturn module.exports;}});\n`);
await rm(join(pkg,'engine'),{recursive:true,force:true});
await mkdir(join(pkg,'engine'),{recursive:true});
const filter=p=>!p.split('/').some(x=>x==='__pycache__'||x==='.DS_Store')&&!p.endsWith('.pyc');
await cp(join(root,'app'),join(pkg,'engine/app'),{recursive:true,filter});
await cp(join(root,'app/static/icon.svg'),join(pkg,'icon.svg'));
await cp(join(root,'NOTICE'),join(pkg,'NOTICE'));
await mkdir(join(pkg,'licenses'),{recursive:true});
await cp(join(root,'docs/licenses'),join(pkg,'licenses'),{recursive:true});
await cp(join(root,'docs/upstream/1c4253f6774bf40314271a827304b842100e054c/LICENSE'),join(pkg,'licenses/MiroThinker-Apache-2.0'));
if(process.argv.includes('--code-only')){console.log('Updated plugin code; existing runtime retained.');process.exit(0);}
// Runtime preparation is a maintainer action, never an npm install script.
// An override supplies a portable Python with all locked runtime dependencies installed.
let runtime=process.env.LUCENT_RUNTIME_SOURCE;
if(!runtime){
  const native=join(root,'.cache/dsh-python/cpython-3.12.9-macos-aarch64-none');
  try{await access(join(native,'bin/python3.12'));runtime=native;}catch{}
}
const fallback=!runtime;
if(!runtime)runtime=join(root,'.runtime/python/cpython-3.12.9-macos-x86_64-none');
const py=join(runtime,'bin/python3.12');await access(py);
const meta=JSON.parse(execFileSync(py,['-c','import json,platform;print(json.dumps({"machine":platform.machine(),"version":platform.python_version()}))'],{encoding:'utf8'}));
const declared=JSON.parse(await readFile(join(pkg,'package.json'),'utf8'));
const arch=meta.machine==='x86_64'?'x64':meta.machine;
if(!declared.cpu.includes(arch))throw new Error(`Runtime ${arch} does not match package cpu ${declared.cpu.join(',')}; prepare the target runtime first.`);
await rm(join(pkg,'runtime'),{recursive:true,force:true});
await cp(runtime,join(pkg,'runtime/python'),{recursive:true,filter,dereference:false});
if(fallback){
  // Local fallback for this Mac: preserve the working x86_64 runtime and its matching wheels.
  await cp(join(root,'.venv/lib/python3.12/site-packages'),join(pkg,'runtime/python/lib/python3.12/site-packages'),{recursive:true,filter:p=>filter(p)&&!/(?:^|\/)(?:pytest|_pytest|pytest_asyncio|iniconfig|pluggy)(?:[/.\-_]|$)/.test(p)});
}
await writeFile(join(pkg,'runtime/manifest.json'),JSON.stringify({platform:'darwin',architecture:meta.machine,
  executable:'python/bin/python3.12',python:meta.version,lockedDependencies:'uv.lock',
  note:meta.machine==='x86_64'?'Apple Silicon requires Rosetta 2. No system Python is used.':'Native Apple Silicon runtime.'},null,2)+'\n');
execFileSync(join(pkg,'runtime/python/bin/python3.12'),['-s','-c','import fastapi,uvicorn,httpx,pydantic,tiktoken;print("Bundled runtime imports OK")'],{stdio:'inherit',env:{...process.env,PYTHONNOUSERSITE:'1',PYTHONDONTWRITEBYTECODE:'1'}});
console.log('Built local DSH package with',meta.machine,'Python',meta.version);
