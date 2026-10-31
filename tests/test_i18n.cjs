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
test('new installs and invalid preferences default to English; explicit Chinese is preserved',()=>{
 for(const lang of ['en','bad',null])assert.equal(locale(lang).LucentI18n.t('主模型'),'Main model');
 assert.equal(locale('zh').LucentI18n.t('主模型'),'主模型');
 const c=vm.createContext({localStorage:{getItem(){throw Error('blocked');}}});
 vm.runInContext(fs.readFileSync(require.resolve('../app/static/i18n.js'),'utf8'),c);
 assert.equal(c.LucentI18n.language,'en');
});
test('English catalog preserves all placeholder sets',()=>{
 const c=locale('en');
 for(const [key,value] of Object.entries(c.LUCENT_EN)){
  const placeholders=s=>[...s.matchAll(/\{\d+\}/g)].map(m=>m[0]).sort();
  assert.deepEqual(placeholders(key),placeholders(value),key);
 }
});

test('system names are localized without translating custom names',()=>{
 const {LucentI18n:i}=locale('en');
 assert.equal(i.systemName({id:'supplier_summary',name:'DeepSeek 独立提取'}),'DeepSeek extraction');
 assert.equal(i.systemName({id:'supplier_summary',name:'我的供应商'}),'我的供应商');
 assert.equal(i.systemName({id:'custom',name:'DeepSeek 独立提取'}),'DeepSeek 独立提取');
 assert.equal(i.systemName({id:'legacy',name:'原研究配置'}),'Previous configuration');
});
test('server validation, HTTP errors and nested extraction failures are localized',()=>{
 const i=locale('en').LucentI18n;
 for(const message of ['请输入供应商名称','服务重启','研究执行失败（ValueError），请检查请求详情。',
  '研究初始化失败（RuntimeError）。','服务 HTTP 401：API Key 无效','供应商模块 example 已停用或移除，请选择其他模型配置。',
  '抓取未返回可用正文。；当前研究尝试没有该 URL 的可用 Search content 或 summary。',
  '模型响应协议解析失败：缺少结束标记'])assert.doesNotMatch(i.serverText(message),/\p{Script=Han}/u,message);
 assert.equal(i.serverText('服务 HTTP 401：API Key 无效 · 用户服务原文'),'Service HTTP 401: Invalid API key. · 用户服务原文');
 assert.equal(i.serverText('用户的研究内容'),'用户的研究内容');
});
test('all static UI translation keys have English catalog entries',()=>{
 const catalog=locale('en').LUCENT_EN,dir=require('node:path').join(__dirname,'../app/static');
 for(const name of fs.readdirSync(dir).filter(n=>/\.(js|html)$/.test(n)&&!n.startsWith('i18n'))){
  const source=fs.readFileSync(require('node:path').join(dir,name),'utf8');
  const keys=[...source.matchAll(/\btr\(\s*(['"])(.*?)\1/g)].map(m=>m[2]);
  keys.push(...[...source.matchAll(/data-i18n(?:-[\w-]+)?="([^"]+)"/g)].map(m=>m[1]));
  for(const key of keys.filter(k=>/\p{Script=Han}/u.test(k))){assert.ok(catalog[key],name+': '+key);assert.doesNotMatch(catalog[key],/\p{Script=Han}/u);}
 }
});
