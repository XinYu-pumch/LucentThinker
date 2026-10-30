const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../app/static/app.js'),'utf8').split('let historyMenu=')[0];
function migrate(entries){
 const values=new Map(entries);
 const storage={getItem:k=>values.get(k)??null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)};
 const context=vm.createContext({document:{},URL});vm.runInContext(source,context);
 context.migrateConversationSelection(storage);return values;
}
test('renaming preserves the previous browser conversation selection',()=>{
 const result=migrate([['openmirothinker-conversation','saved-conversation']]);
 assert.equal(result.get('LucentThinker-conversation'),'saved-conversation');
 assert.equal(result.has('openmirothinker-conversation'),false);
});
test('an existing new-brand selection takes precedence over a legacy selection',()=>{
 const result=migrate([['openmirothinker-conversation','older'],['LucentThinker-conversation','current']]);
 assert.equal(result.get('LucentThinker-conversation'),'current');
 assert.equal(migrate([...result]).get('LucentThinker-conversation'),'current');
});
