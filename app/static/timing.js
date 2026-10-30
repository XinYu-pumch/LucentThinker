'use strict';
var tr = globalThis.LucentI18n?.t || ((text,...values)=>typeof text==='string'?text.replace(/\{(\d+)\}/g,(_,i)=>values[i]??_):text);
(function(root){
 const statusNames={running:tr("研究中"),completed:tr("已完成"),failed:tr("失败"),cancelled:tr("已停止"),incomplete:tr("未完成"),interrupted:tr("已中断")};
 function duration(seconds){
  if(!Number.isFinite(seconds))return tr("未记录");
  const s=Math.max(0,Math.floor(seconds)),h=Math.floor(s/3600),m=Math.floor(s%3600/60);
  return (h?h+tr(" 小时 "):'')+(m||h?m+tr(" 分 "):'')+s%60+tr(" 秒");
 }
 function elapsed(run,now=Date.now()/1000){
  const start=run.started_at??run.created;
  if(!Number.isFinite(start))return null;
  if(Number.isFinite(run.finished_at))return Math.max(0,run.finished_at-start);
  return (run.status||run.latest_status)==='running'?Math.max(0,now-start):null;
 }
 function date(value){return Number.isFinite(value)?new Date(value*1000).toLocaleString(root.LucentI18n?.language==='en'?'en-GB':'zh-CN',{hour12:false}):tr("未记录");}
 function label(run,now){
  const status=run.status||run.latest_status;
  return tr("开始：{0} · 结束：{1} · {2}：{3}", date(run.started_at??run.created), Number.isFinite(run.finished_at)?date(run.finished_at):status==='running'?tr("进行中"):tr("未记录"), status==='running'?tr("已用时"):tr("时长"), duration(elapsed(run,now)));
 }
 const api={duration,elapsed,date,label,statusNames};
 if(typeof module==='object'&&module.exports)module.exports=api;else root.RunTiming=api;
})(globalThis);
