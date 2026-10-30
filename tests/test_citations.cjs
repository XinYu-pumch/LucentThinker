const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync(require.resolve('../app/static/app.js'),'utf8').split('let historyMenu=')[0];
function render(text,ancestor=null,sources=[42,56].map(id=>({id,title:`Source ${id}`,url:`https://example.org/${id}`}))){
 const document={
  createDocumentFragment:()=>({children:[],append(...nodes){this.children.push(...nodes);}}),
  createElement:tag=>({tag})
 };
 const context=vm.createContext({document,URL});
 vm.runInContext(source,context);
 const node={textContent:text,parentElement:{closest:()=>ancestor},replaceWith(fragment){this.fragment=fragment;}};
 context.linkCitationText(node,sources);
 return node;
}
for(const marker of ['[42, 56]','[42,56]','[42][56]','[42，56]','[42、56]','[42;56]','［42，56］','【４２、５６】','[４２, ５６]','[ 42 ,\t56 ]']){
 test(`separate registered links for ${marker}`,()=>{
  const node=render('Claim '+marker+' end');
  const links=node.fragment.children.filter(x=>typeof x==='object');
  assert.deepEqual(Array.from(links,x=>x.href),['https://example.org/42','https://example.org/56']);
  assert.deepEqual(Array.from(links,x=>x.textContent),['42','56']);
  assert.equal(node.fragment.children[0],'Claim ');
  assert.equal(node.fragment.children.at(-1),' end');
  assert.ok(links.every(x=>x.target==='_blank'&&x.rel==='noopener noreferrer'));
 });
}
test('code, existing links, ranges and ordinary brackets are untouched',()=>{
 for(const ancestor of ['a','code','pre'])assert.equal(render('[42,56]',ancestor).fragment,undefined);
 for(const text of ['[42-56]','[42–56]','[^42]','[item 42]','［42,56]'])assert.equal(render(text).fragment,undefined);
});
test('unknown or unsafe targets stay plain text',()=>{
 const node=render('[42,56,999]',null,[{id:42,url:'javascript:alert(1)'},{id:56,url:'https://example.org/56'}]);
 assert.equal(node.fragment.children.filter(x=>typeof x==='object').length,1);
 assert.ok(node.fragment.children.includes('[42]'));
 assert.ok(node.fragment.children.includes('[999]'));
});
