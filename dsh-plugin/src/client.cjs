const React = require('react');
const h = React.createElement;
const {useEffect, useState} = React;
const PANEL = 'lucentthinker';

function Icon(){return h('svg',{viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.7,width:20,height:20,'aria-hidden':true},h('path',{d:'M7 4v16h12M4 4h6M4 20h16M16 3v6M13 6h6'}));}
function Surface({service,settings=false}) {
  const [state,setState] = useState({loading:true}), [retry,setRetry] = useState(0);
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
  if(state.loading)return h('div',{style:{...container,padding:24}},'正在启动 LucentThinker 研究引擎…');
  if(state.error)return h('div',{style:{...container,padding:24}},h('h2',null,'LucentThinker'),h('p',{role:'alert'},state.error),h('button',{onClick:()=>{setState({loading:true});setRetry(n=>n+1);}},'重试启动'));
  return h('section',{style:container,'aria-label':settings?'LucentThinker 设置':'LucentThinker 研究工作台'},
    settings?h('div',{style:{padding:'0 0 12px',fontSize:12,color:'#777'}},'研究服务已就绪 · 停用插件会停止研究并保留记录。'):null,
    h('iframe',{title:settings?'LucentThinker 模型与研究设置':'LucentThinker 研究工作台',
      src:state.url+(settings?'?surface=settings':''),referrerPolicy:'no-referrer',
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
