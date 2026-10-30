const test=require('node:test'),assert=require('node:assert/strict');
const t=require('../app/static/timing.js');
test('running elapsed updates; terminal elapsed stays frozen',()=>{
 const run={started_at:100,status:'running'};
 assert.equal(t.elapsed(run,110),10);assert.equal(t.elapsed(run,120),20);
 assert.equal(t.elapsed({...run,status:'completed',finished_at:115},900),15);
 assert.equal(t.elapsed({...run,status:'cancelled'},900),null);
 assert.equal(t.elapsed(run,90),0);
});
test('legacy and interrupted ends are unknown, never zero or ongoing',()=>{
 for(const status of ['completed','interrupted','failed','cancelled','incomplete']){
  const run={created:100,status};assert.equal(t.elapsed(run,120),null);
  assert.match(t.label(run,120),/结束：未记录 · 时长：未记录/);
 }
 assert.equal(t.duration(null),'未记录');assert.equal(t.duration(3661.9),'1 小时 1 分 1 秒');
 assert.equal(t.duration(90000),'25 小时 0 分 0 秒');
});
test('sidebar uses latest run status and timestamps',()=>{
 assert.equal(t.elapsed({started_at:100,latest_status:'running'},130),30);
 assert.match(t.label({started_at:100,status:'running'},130),/结束：进行中 · 已用时：30 秒/);
});
