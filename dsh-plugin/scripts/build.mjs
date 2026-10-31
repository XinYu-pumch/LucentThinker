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
const filter=p=>!p.split(/[\\/]/).some(x=>x==='__pycache__'||x==='.DS_Store')&&!p.endsWith('.pyc');
await cp(join(root,'app'),join(pkg,'engine/app'),{recursive:true,filter});
await cp(join(root,'app/static/icon.svg'),join(pkg,'icon.svg'));
await cp(join(root,'NOTICE'),join(pkg,'NOTICE'));
await cp(join(root,'LICENSE'),join(pkg,'LICENSE'));
await mkdir(join(pkg,'licenses'),{recursive:true});
await cp(join(root,'docs/licenses'),join(pkg,'licenses'),{recursive:true});
await cp(join(root,'docs/upstream/1c4253f6774bf40314271a827304b842100e054c/LICENSE'),join(pkg,'licenses/MiroThinker-Apache-2.0'));
if(process.argv.includes('--code-only')){console.log('Updated plugin code; existing runtime retained.');process.exit(0);}
// Each native builder adds its target while retaining other prepared runtimes.
const target = `${process.platform}-${process.arch}`;
if (!['darwin-arm64', 'win32-x64'].includes(target)) throw new Error(`Unsupported target ${target}`);
const runtime = process.env.LUCENT_RUNTIME_SOURCE ?? join(root, '.cache/dsh-python',
  process.platform === 'win32' ? 'cpython-3.12.9-windows-x86_64-none' : 'cpython-3.12.9-macos-aarch64-none');
const relativePython = process.platform === 'win32' ? 'python.exe' : 'bin/python3.12';
const python = join(runtime, relativePython);
await access(python);
const meta = JSON.parse(execFileSync(python, ['-c', 'import json,platform;print(json.dumps({"machine":platform.machine(),"version":platform.python_version()}))'], {encoding:'utf8'}));
const architecture = {aarch64:'arm64', arm64:'arm64', AMD64:'x64', x86_64:'x64'}[meta.machine];
if (architecture !== process.arch) throw new Error(`Runtime architecture mismatch: ${meta.machine}`);
const destination = join(pkg, 'runtime', target);
await rm(destination, {recursive:true, force:true});
await cp(runtime, destination, {recursive:true, filter, dereference:false});
const manifestPath = join(pkg, 'runtime/manifest.json');
let manifest = {targets:{}};
try { manifest = JSON.parse(await readFile(manifestPath, 'utf8')); } catch (error) {
  if (error.code !== 'ENOENT') throw error;
}
// Discard the old single-platform manifest and its obsolete runtime directory.
if (!manifest.targets) {
  manifest = {targets:{}};
  await rm(join(pkg, 'runtime/python'), {recursive:true, force:true});
}
manifest.targets[target] = {executable:`${target}/${relativePython}`, python:meta.version, lockedDependencies:'uv.lock'};
await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
execFileSync(join(destination, relativePython), ['-s', '-c', 'import fastapi,uvicorn,httpx,pydantic,tiktoken;print("Bundled runtime imports OK")'], {
  stdio:'inherit', env:{...process.env,PYTHONNOUSERSITE:'1',PYTHONDONTWRITEBYTECODE:'1',PYTHONUTF8:'1'},
});
console.log('Built DSH package for', target, 'with Python', meta.version);
