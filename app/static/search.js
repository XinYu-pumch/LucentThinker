'use strict';
(function(){
 const dialog=$('#conversation-search'),input=$('#conversation-search-input'),results=$('#conversation-search-results'),status=$('#conversation-search-status'),more=$('#conversation-search-more');
 let scope='all',revision=0,controller=null,timer=null,offset=0;
 function invalidate(){revision++;clearTimeout(timer);controller?.abort();controller=null;more.hidden=true;results.setAttribute('aria-busy','false');}
 function empty(message){results.replaceChildren();const box=el('div','search-empty');box.append(el('span','search-empty-icon','⌕'),el('p','',message));results.append(box);}
 function highlight(node,value,query){
  // Literal matching and text nodes prevent stored content from becoming HTML.
  const escaped=query.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'),pattern=new RegExp(escaped,'gi');
  let at=0;for(const match of value.matchAll(pattern)){node.append(document.createTextNode(value.slice(at,match.index)),el('mark','',match[0]));at=match.index+match[0].length;}
  node.append(document.createTextNode(value.slice(at)));
 }
 async function search(append=false){
  invalidate();const current=revision,query=input.value.trim();
  if(!query){status.textContent='';empty(tr('搜索您的对话历史记录'));return;}
  const start=append?offset:0;if(!append)results.replaceChildren();
  status.textContent=tr('正在搜索…');controller=new AbortController();results.setAttribute('aria-busy','true');
  try{
   const response=await fetch('/api/conversations/search?'+new URLSearchParams({q:query,scope,offset:start}),{signal:controller.signal});
   if(!response.ok)throw Error(tr('搜索失败，请重试'));
   const data=await response.json();if(current!==revision||!dialog.open)return;
   for(const item of data.results){
    const row=el('button','conversation-search-result');row.type='button';
    const heading=el('strong');highlight(heading,item.title,query);row.append(heading);
    if(item.snippet){const snippet=el('p','search-snippet');highlight(snippet,item.snippet,query);row.append(snippet);}
    const names={title:tr('标题'),question:tr('问题'),answer:tr('回答')};
    row.append(el('small','search-result-meta',(item.project_is_default&&item.project_name==='默认项目'?tr('默认项目'):item.project_name||'')+' · '+(names[item.match_field]||'')+' · '+RunTiming.date(item.updated)));
    row.onclick=async()=>{dialog.close();try{await openConversation(item.id);if(item.run_id)state.runs.get(item.run_id)?.ui.article.scrollIntoView({block:'start',behavior:'smooth'});}catch(e){toast(e.message);}};
    results.append(row);
   }
   offset=data.next_offset;more.hidden=!data.has_more;
   const count=results.querySelectorAll('.conversation-search-result').length;
   status.textContent=count?tr('找到 {0} 个对话',count):tr('没有找到匹配的对话');
   if(!count)empty(tr('换一个关键词试试，可以搜索标题、问题或回答。'));
  }catch(e){if(current!==revision||e.name==='AbortError')return;status.textContent=tr('搜索失败，请重试');if(!append)empty(tr('请检查本地服务是否正在运行。'));}
  finally{if(current===revision){results.setAttribute('aria-busy','false');controller=null;}}
 }
 function open(){if(dialog.open)return;dialog.showModal();search();input.focus();input.select();}
 $('#open-search').onclick=open;$('#close-conversation-search').onclick=()=>dialog.close();
 input.oninput=()=>{invalidate();offset=0;results.replaceChildren();status.textContent=input.value.trim()?tr('正在搜索…'):'';timer=setTimeout(()=>search(),180);};
 for(const button of dialog.querySelectorAll('[data-search-scope]'))button.onclick=()=>{
  scope=button.dataset.searchScope;for(const b of dialog.querySelectorAll('[data-search-scope]')){const selected=b===button;b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;}
  search();input.focus();
 };
 more.onclick=()=>search(true);
 dialog.addEventListener('close',()=>{invalidate();results.setAttribute('aria-busy','false');
  const target=window.innerWidth<=760&&!$('#sidebar').classList.contains('open')?$('#menu'):$('#open-search');target.focus({preventScroll:true});
 });
 dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const r=dialog.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)dialog.close();});
 dialog.addEventListener('keydown',event=>{
  if(event.key==='Escape'){event.preventDefault();dialog.close();return;}
  const buttons=[...dialog.querySelectorAll('[data-search-scope]')];const tab=buttons.indexOf(document.activeElement);
  if(tab>=0&&['ArrowLeft','ArrowRight'].includes(event.key)){event.preventDefault();buttons[(tab+(event.key==='ArrowRight'?1:buttons.length-1))%buttons.length].click();return;}
  const rows=[...results.querySelectorAll('button')];
  if(event.key==='ArrowDown'||event.key==='ArrowUp'){
   if(!rows.length)return;event.preventDefault();const i=rows.indexOf(document.activeElement);rows[(i+(event.key==='ArrowDown'?1:rows.length-1)+rows.length)%rows.length].focus();
  }else if(event.key==='Enter'&&document.activeElement===input){event.preventDefault();if(rows.length)rows[0].click();else search();}
 });
 document.addEventListener('keydown',event=>{if((event.metaKey||event.ctrlKey)&&event.shiftKey&&event.key.toLowerCase()==='f'&&!document.querySelector('dialog[open]')){event.preventDefault();open();}});
})();
