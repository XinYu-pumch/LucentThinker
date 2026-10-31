import {readFile,access} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {join} from 'node:path';
import {homedir} from 'node:os';

const root=fileURLToPath(new URL('..',import.meta.url));
const home=process.env.DSH_HOME||join(homedir(),'.dsh'),profile=process.argv[2]||'desktop';
if(!/^[a-zA-Z0-9_-]+$/.test(profile))throw Error('Invalid profile name');
await access(join(root,'runtime/manifest.json'));
const state=join(home,'plugin-data/lucentthinker/engine-state.json');
try {
 const record=JSON.parse(await readFile(state,'utf8'));
 try{process.kill(record.enginePid,0);throw Error('请先在 DSH 中停用 LucentThinker，确认研究结束后再更新。');}
 catch(error){if(error.code!=='ESRCH')throw error;}
}catch(error){if(error.code!=='ENOENT')throw error;}
execFileSync(process.execPath,[join(root,'scripts/build.mjs'),'--code-only'],{stdio:'inherit'});
let installed=false;
try{const doc=JSON.parse(await readFile(join(home,'profiles',profile,'package.json'),'utf8'));
 installed=doc.dependencies?.['dsh-plugin-lucentthinker']==='link:'+root.replace(/\/$/,'');
 if(doc.dependencies?.['dsh-plugin-lucentthinker']&&!installed)throw Error('已有另一种安装来源；请先通过 DSH 卸载旧插件，数据会保留。');
}catch(error){if(error.code!=='ENOENT')throw error;}
if(!installed){
 const cli=process.env.DSH_CLI||'/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh';
 execFileSync(cli,['plugin','--profile',profile,'add','link:'+root.replace(/\/$/,'')],{stdio:'inherit'});
}
console.log('本地插件已准备好。请在 DSH 插件页启用 LucentThinker；宿主代码更新后如仍显示旧版，请重启 DSH。');
