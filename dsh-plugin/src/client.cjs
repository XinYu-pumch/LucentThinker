const React = require('react');
const h = React.createElement;
const {useEffect, useState, useRef} = React;
const PANEL = 'lucentthinker';
const LANGUAGE_KEY = 'LucentThinker-language';
function savedLanguage(){try{return localStorage.getItem(LANGUAGE_KEY)==='zh'?'zh':'en';}catch{return 'en';}}
const EN = {
 '插件连接失败，请重试。':'Could not connect to the plugin. Please retry.',
 '研究服务连接失败，请重试或重新启用插件。':'Could not connect to the research service. Retry or re-enable the plugin.',
 '正在启动 LucentThinker 研究引擎…':'Starting the LucentThinker research engine…',
 '重试启动':'Retry', 'LucentThinker 设置':'LucentThinker settings',
 'LucentThinker 研究工作台':'LucentThinker research workspace',
 '研究服务已就绪 · 停用插件会停止研究并保留记录。':'Research service ready · Disabling the plugin stops research and preserves records.',
 'LucentThinker 模型与研究设置':'LucentThinker model and research settings',
 'LucentThinker 已停用':'LucentThinker is disabled.',
 '研究引擎启动超时，请查看插件日志后重试。':'The research engine timed out. Check the plugin log and retry.',
 '无法启动内置 Python，请检查插件平台版本或重新安装。':'Could not start bundled Python. Check the plugin platform or reinstall.',
 '研究引擎未能启动，请查看插件日志；数据将保留。':'The research engine could not start. Check the plugin log. Your data is preserved.',
 '引擎进程未能退出，请查看日志。':'The engine process could not exit. Check the log.'
};
function translate(text,language){
 if(language==='zh')return text;
 return EN[text]||text?.replace(/^研究引擎已退出（(.+)），请点击重试。$/, 'The research engine exited ($1). Please retry.');
}

function Icon(){return h('svg',{viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.7,width:20,height:20,'aria-hidden':true},h('path',{d:'M7 4v16h12M4 4h6M4 20h16M16 3v6M13 6h6'}));}
function Surface({service,settings=false}) {
  const [state,setState] = useState({loading:true}), [retry,setRetry] = useState(0);
  const [language,setLanguage] = useState(savedLanguage), frame=useRef(null), frameSource=useRef({});
  const tr=text=>translate(text,language);
  useEffect(()=>{
    const sync=()=>setLanguage(savedLanguage());
    const receive=event=>{
      if(!state.url||event.source!==frame.current?.contentWindow||event.origin!==new URL(state.url).origin)return;
      const value=event.data;
      if(value?.type!=='lucentthinker-language'||!['en','zh'].includes(value.language))return;
      try{localStorage.setItem(LANGUAGE_KEY,value.language);}catch{}
      setLanguage(value.language);
      window.dispatchEvent(new Event('lucentthinker-language'));
    };
    window.addEventListener('message',receive);
    window.addEventListener('lucentthinker-language',sync);
    return()=>{window.removeEventListener('message',receive);window.removeEventListener('lucentthinker-language',sync);};
  },[state.url]);
  useEffect(() => {
    let active=true, timer;
    service.session().then(result => {
      if(!active)return;
      if(!result.ok){setState({error:result.error?.message||'插件连接失败，请重试。'});return;}
      setState(result.value);
      timer=setInterval(async()=>{
        try{const status=await service.status();if(active&&status.ok&&status.value.state==='error')setState({error:status.value.error});}catch{}
      },5000);
    }).catch(()=>{if(active)setState({error:'研究服务连接失败，请重试或重新启用插件。'});});
    return()=>{active=false;clearInterval(timer);};
  },[service,retry]);
  const container={height:settings?'min(68vh, 760px)':'100%',minHeight:settings?420:0,display:'flex',flexDirection:'column',background:'var(--background, #fff)'};
  if(state.loading)return h('div',{style:{...container,padding:24}},tr('正在启动 LucentThinker 研究引擎…'));
  if(state.error)return h('div',{style:{...container,padding:24}},h('h2',null,'LucentThinker'),h('p',{role:'alert'},tr(state.error)),h('button',{onClick:()=>{setState({loading:true});setRetry(n=>n+1);}},tr('重试启动')));
  // Keep the iframe source stable during its own language reload, preserving drafts.
  if(frameSource.current.url!==state.url)frameSource.current={url:state.url,src:state.url+'?language='+language+(settings?'&surface=settings':'')};
  return h('section',{style:container,'aria-label':tr(settings?'LucentThinker 设置':'LucentThinker 研究工作台')},
    settings?h('div',{style:{padding:'0 0 12px',fontSize:12,color:'#777'}},tr('研究服务已就绪 · 停用插件会停止研究并保留记录。')):null,
    h('iframe',{ref:frame,title:tr(settings?'LucentThinker 模型与研究设置':'LucentThinker 研究工作台'),
      src:frameSource.current.src,referrerPolicy:'no-referrer',
      allow:'clipboard-write',sandbox:'allow-scripts allow-same-origin allow-forms allow-downloads allow-popups allow-popups-to-escape-sandbox',
      style:{display:'block',width:'100%',flex:1,minHeight:0,border:0}}));
}

exports.inject=['slots','remote','layout'];
exports.apply=async function(ctx){
 try {
  // REMOTE_CONTRIBUTION is injected by the build from the shared wire definition.
  await ctx.remote.$mount(REMOTE_CONTRIBUTION);
  ctx.inject(['remote.lucentThinker','slots'], scoped=>{
    const service=scoped.remote.lucentThinker;
    scoped.slots.inject('main',()=>scoped.slots.register({name:'main',key:PANEL,inject:()=>({service})},Surface));
    scoped.slots.inject('sidebar.panellist',()=>scoped.slots.register({name:'sidebar.panellist',id:PANEL,order:5,label:'LucentThinker'},Icon));
    scoped.slots.inject('settings.section',()=>scoped.slots.register({name:'settings.section',id:PANEL,order:15,label:'LucentThinker',inject:()=>({service,settings:true})},Surface));
  });
  // Slots, Remote namespace, React effects and iframe documents are all scoped to this activation.
 } catch(error) {
   console.error('LucentThinker activation:',error?.stack||String(error));
   // A third-party feature must never reject DSH's application boot.
   // Keep the host-side status and disable switch available for recovery.
 }
};
