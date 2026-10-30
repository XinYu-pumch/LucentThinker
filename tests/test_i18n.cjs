const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function locale(language){
 const context=vm.createContext({localStorage:{getItem:()=>language}});
 for(const name of ['i18n-en','i18n','timing'])vm.runInContext(fs.readFileSync(require.resolve('../app/static/'+name+'.js'),'utf8'),context);
 return context;
}
test('English UI messages interpolate without translating user content',()=>{
 const c=locale('en');assert.equal(c.LucentI18n.t('主模型'),'Main model');
 assert.equal(c.LucentI18n.t('找到 {0} 个对话',8),'Found 8 conversations');
 assert.equal(c.LucentI18n.t('模型：{0}','用户自定义模型'),'Model: 用户自定义模型');
 assert.equal(c.LucentI18n.serverText('研究尝试 2 · 主模型迭代 7 / 200'),'Research attempt 2 · Main model iteration 7 / 200');
 assert.equal(c.RunTiming.duration(61),'1 min 1 sec');
 assert.equal(c.RunTiming.statusNames.completed,'Completed');
});
test('Chinese UI and invalid saved language preserve Chinese labels',()=>{
 for(const lang of ['zh','bad',null])assert.equal(locale(lang).LucentI18n.t('主模型'),'主模型');
});
test('English catalog preserves all placeholder sets',()=>{
 const c=locale('en');
 for(const [key,value] of Object.entries(c.LUCENT_EN)){
  const placeholders=s=>[...s.matchAll(/\{\d+\}/g)].map(m=>m[0]).sort();
  assert.deepEqual(placeholders(key),placeholders(value),key);
 }
});
