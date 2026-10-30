'use strict';
// Project grouping is presentation only; project membership never adds model context.
globalThis.Sidebar=(function(){
 const prefix='LucentThinker-',defaultId='default';
 let projects=[],conversations=[],creating=false,collapsed=false,closedProjects=new Set();
 let selecting=false,selectionBusy=false,selected=new Set();
 function read(key,fallback){try{return JSON.parse(localStorage.getItem(prefix+key))??fallback;}catch{return fallback;}}
 function save(key,value){try{localStorage.setItem(prefix+key,JSON.stringify(value));}catch{}}
 function name(project){return project?.is_default&&project.name==='默认项目'?tr('默认项目'):project?.name||tr('默认项目');}
 function projectName(id){return name(projects.find(p=>p.id===id));}
 function icon(type){
  const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.7');svg.setAttribute('aria-hidden','true');
  const path=document.createElementNS(svg.namespaceURI,'path');path.setAttribute('d',type==='plus'?'M12 5v14M5 12h14':type==='chevron'?'m9 5 7 7-7 7':'M3 7a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z');svg.append(path);return svg;
 }
 function updateContext(){const node=$('#active-project-name');node.textContent=projectName(state.projectId);node.title=node.textContent;}
 function syncLayout(){
  const mobile=window.innerWidth<=760,open=$('#sidebar').classList.contains('open');
  document.body.classList.toggle('sidebar-collapsed',!mobile&&collapsed);
  $('#sidebar').inert=mobile&&!open;$('#sidebar-backdrop').hidden=!mobile||!open;
  $('#menu').setAttribute('aria-expanded',String(mobile?open:!collapsed));
  const label=tr(!mobile&&collapsed?'展开侧栏':'收起侧边栏'),button=$('#sidebar-collapse');button.title=label;button.setAttribute('aria-label',label);button.setAttribute('aria-expanded',String(mobile?open:!collapsed));
 }
 function closeMobile(){const focused=$('#sidebar').contains(document.activeElement);$('#sidebar').classList.remove('open');syncLayout();if(window.innerWidth<=760&&focused)$('#menu').focus({preventScroll:true});}
 function toggle(){
  if(window.innerWidth<=760){$('#sidebar').classList.toggle('open');syncLayout();if($('#sidebar').classList.contains('open'))$('#sidebar-collapse').focus({preventScroll:true});else $('#menu').focus({preventScroll:true});}
  else{collapsed=!collapsed;save('sidebar-collapsed',collapsed);syncLayout();}
 }
 function reveal(projectId){
  closedProjects.delete(projectId);save('closed-projects',[...closedProjects]);
  const node=[...document.querySelectorAll('.project-group')].find(n=>n.dataset.projectId===projectId);if(node)node.open=true;
  $('#projects-section').open=true;save('projects-open',true);
 }
 function select(projectId,expand=true){state.projectId=projectId||defaultId;if(expand)reveal(state.projectId);updateContext();}
 async function newConversation(projectId=defaultId){
  if(creating)return;creating=true;const revision=++opening;
  if(selecting)endSelection();
  try{
   const result=await api('/api/conversations','POST',{project_id:projectId});
   if(revision!==opening){await refreshHistory();return;}
   $('#question').value='';await openConversation(result.id);$('#question').focus();
  }catch(e){toast(e.message);}finally{creating=false;}
 }
 async function newProject(){
  if(creating)return;
  const value=await conversationDialog(tr('新建项目'),tr('为一个研究主题创建项目，将相关对话放在一起。'),'',tr('项目名称'));
  if(value===null)return;
  if(value.trim().length>120){toast(tr('项目名称须为 1–120 个字符'));return;}
  creating=true;
  try{const result=await api('/api/projects','POST',{name:value.trim()});await refreshHistory();reveal(result.id);
   const group=[...document.querySelectorAll('.project-group')].find(n=>n.dataset.projectId===result.id);group?.querySelector('summary').focus({preventScroll:true});group?.scrollIntoView({block:'nearest'});
   toast(tr('项目已创建，点击右侧加号新建对话。'));
  }catch(e){toast(e.message);}finally{creating=false;}
 }
 async function renameProject(project){
  if(creating||selectionBusy)return;
  const value=await conversationDialog(tr('重命名项目'),tr('只修改项目名称，对话和研究内容保持原样。'),name(project),tr('项目名称'));
  if(value===null||value.trim()===name(project))return;
  const title=value.trim();
  if(!title||title.length>120){toast(tr('项目名称须为 1–120 个字符'));return;}
  creating=true;
  try{await api('/api/projects/'+project.id,'PATCH',{name:title});await refreshHistory();toast(tr('项目已重命名'));}
  finally{creating=false;}
 }
 function render(projectList,conversationList){
  projects=projectList;conversations=conversationList;updateContext();
  const valid=new Set(conversations.map(c=>c.id));selected=new Set([...selected].filter(id=>valid.has(id)));historyTimings.clear();
  const current=conversations.find(c=>c.id===state.cid);if(current)$('#header-title').textContent=current.title==='新的研究'?tr('新对话'):current.title;
  const host=$('#history'),scroll=$('.sidebar-scroll'),top=scroll.scrollTop;
  const focused=document.activeElement,focusAdd=focused?.classList.contains('project-add'),focusedProject=(focusAdd||focused?.matches('.project-heading'))?focused.closest('.project-group')?.dataset.projectId:null;
  host.replaceChildren();$('#project-count').textContent=projects.length;
  for(const project of projects){
   const list=conversations.filter(c=>c.project_id===project.id),group=el('details','project-group'+(state.projectId===project.id?' current-project':''));group.dataset.projectId=project.id;group.open=!closedProjects.has(project.id);
   const summary=el('summary','project-heading'),chevron=icon('chevron');chevron.classList.add('project-chevron');
   const folder=icon('folder'),title=el('span','project-name',name(project)),count=el('small','project-conversation-count',String(list.length));title.title=name(project);count.title=tr('{0} 个对话',list.length);
   const add=el('button','project-add');add.type='button';add.append(icon('plus'));add.title=tr('在“{0}”中新建对话',name(project));add.setAttribute('aria-label',add.title);
   add.onclick=event=>{event.preventDefault();event.stopPropagation();newConversation(project.id);};
   summary.title=tr('（右键可重命名）');summary.setAttribute('aria-haspopup','menu');
   const openMenu=event=>{if(selectionBusy||event.target.closest('button,input'))return;openContextMenu(event,summary,tr('项目操作'),[[tr('重命名项目'),()=>renameProject(project)]]);};
   summary.oncontextmenu=openMenu;summary.onkeydown=event=>{if(event.key==='ContextMenu'||(event.shiftKey&&event.key==='F10'))openMenu(event);};
   summary.append(chevron);
   if(selecting){const check=el('input','project-checkbox');check.type='checkbox';check.title=tr('选择“{0}”中的全部对话',name(project));check.setAttribute('aria-label',check.title);check.onclick=e=>e.stopPropagation();check.onchange=()=>{if(selectionBusy)return;for(const c of list)if(check.checked)selected.add(c.id);else selected.delete(c.id);updateSelection();};summary.append(check);}
   summary.append(folder,title,count,add);group.append(summary);
   const children=el('div','project-conversations');
   if(list.length)for(const c of list)children.append(conversationRow(c));
   else children.append(el('p','project-empty',tr('此项目还没有对话')));
   const remember=()=>{if(!group.isConnected)return;if(group.open)closedProjects.delete(project.id);else closedProjects.add(project.id);save('closed-projects',[...closedProjects]);};
   summary.addEventListener('click',event=>{if(event.target.closest('button,input'))return;event.preventDefault();group.open=!group.open;remember();});
   group.append(children);group.addEventListener('toggle',remember);host.append(group);
  }
  scroll.scrollTop=top;
  if(focusedProject){const group=[...host.children].find(n=>n.dataset.projectId===focusedProject);group?.querySelector(focusAdd?'.project-add':'summary').focus({preventScroll:true});}
  updateSelection();
 }
 function decorateSelection(conversation,row){
  row.dataset.conversationId=conversation.id;
  if(!selecting)return;
  const checkbox=el('input','conversation-checkbox');checkbox.type='checkbox';checkbox.setAttribute('aria-label',tr('选择对话：{0}',conversation.title));
  checkbox.checked=selected.has(conversation.id);checkbox.onchange=()=>toggleSelection(conversation.id,checkbox.checked);row.prepend(checkbox);
 }
 function toggleSelection(id,checked=!selected.has(id)){
  if(selectionBusy)return;if(checked)selected.add(id);else selected.delete(id);updateSelection();
 }
 function updateSelection(){
  document.body.classList.toggle('selecting-conversations',selecting);$('#conversation-selection').hidden=!selecting;
  $('#select-conversations').setAttribute('aria-pressed',String(selecting));$('#select-conversations').disabled=selectionBusy;
  $('#selection-count').textContent=tr('已选 {0} 个对话',selected.size);
  $('#selection-all').textContent=conversations.length&&selected.size===conversations.length?tr('取消全选'):tr('全选全部对话');
  for(const id of ['selection-move','selection-delete'])$('#'+id).disabled=selectionBusy||!selected.size;
  $('#selection-all').disabled=selectionBusy||!conversations.length;$('#selection-done').disabled=selectionBusy;
  for(const row of document.querySelectorAll('.history-item')){
   const checked=selected.has(row.dataset.conversationId);row.classList.toggle('bulk-selected',checked);
   const input=row.querySelector('.conversation-checkbox');if(input){input.checked=checked;input.disabled=selectionBusy;}
  }
  for(const group of document.querySelectorAll('.project-group')){
   const list=conversations.filter(c=>c.project_id===group.dataset.projectId),count=list.filter(c=>selected.has(c.id)).length;
   const check=group.querySelector('.project-checkbox');if(check){check.checked=list.length>0&&count===list.length;check.indeterminate=count>0&&count<list.length;check.disabled=selectionBusy||!list.length;}
   group.querySelector('.project-conversation-count').textContent=selecting?`${count}/${list.length}`:String(list.length);
  }
 }
 function endSelection(renderNow=true){selecting=false;selected.clear();if(renderNow)render(projects,conversations);else updateSelection();}
 function batchDialog(kind,chosen){
  return new Promise(resolve=>{
   const dialog=el('dialog','batch-dialog'),heading=el('h2','',tr(kind==='move'?'移动到项目':'删除所选对话'));heading.id='batch-dialog-title';dialog.setAttribute('aria-labelledby',heading.id);
   const help=el('p','',kind==='move'?tr('将 {0} 个对话移动到所选项目，研究内容保持原样。',chosen.length):tr('永久删除这 {0} 个对话及其全部研究记录？此操作无法撤销。',chosen.length));
   const list=el('ul','batch-targets');for(const c of chosen)list.append(el('li','',c.title));
   const form=el('form'),select=el('select');select.required=true;
   if(kind==='move'){
    const label=el('label','batch-destination',tr('目标项目'));const placeholder=el('option','',tr('请选择目标项目'));placeholder.value='';select.append(placeholder);
    for(const p of projects){const option=el('option','',name(p));option.value=p.id;select.append(option);}label.append(select);form.append(label);
   }
   const actions=el('div','dialog-actions'),cancel=el('button','secondary-button',tr('取消')),submit=el('button',kind==='move'?'primary-button':'danger-button',kind==='move'?tr('确认移动'):tr('删除 {0} 个对话',chosen.length));
   cancel.type='button';submit.type='submit';actions.append(cancel,submit);form.append(actions);dialog.append(heading,help,el('p','',tr('操作仅针对所选对话，项目文件夹会保留。')),list,form);document.body.append(dialog);
   let done=false;const finish=value=>{if(done)return;done=true;dialog.close();dialog.remove();resolve(value);};
   cancel.onclick=()=>finish(null);dialog.oncancel=e=>{e.preventDefault();finish(null);};
   form.onsubmit=e=>{e.preventDefault();finish(kind==='move'?select.value:true);};dialog.showModal();(kind==='move'?select:cancel).focus();
  });
 }
 async function bulkAction(kind){
  if(selectionBusy||!selected.size)return;
  const chosen=conversations.filter(c=>selected.has(c.id)),ids=chosen.map(c=>c.id);
  if(kind==='delete'&&chosen.some(c=>c.latest_status==='running')){toast(tr('所选对话中有研究正在进行，请先停止后再删除'));return;}
  selectionBusy=true;creating=true;updateSelection();
  try{
   const target=await batchDialog(kind,chosen);if(target===null)return;
   toast(tr(kind==='move'?'正在移动所选对话…':'正在删除所选对话并释放空间…'));
   const result=await api('/api/conversations/'+(kind==='move'?'move':'delete'),'POST',kind==='move'?{ids,project_id:target}:{ids});
   if(kind==='move'&&ids.includes(state.cid))select(target);
   if(kind==='delete'&&ids.includes(state.cid))reset();
   endSelection(false);historySignature=null;await refreshHistory();
   toast(result.storage_cleanup?.warning?tr(result.storage_cleanup.warning):tr(kind==='move'?'已移动 {0} 个对话':'已删除 {0} 个对话',kind==='move'?result.moved:result.deleted));
  }catch(e){toast(e.message);await refreshHistory().catch(()=>{});}
  finally{selectionBusy=false;creating=false;updateSelection();}
 }
 function init(){
  collapsed=read('sidebar-collapsed',false)===true;const saved=read('closed-projects',[]);closedProjects=new Set(Array.isArray(saved)?saved:[]);
  const section=$('#projects-section');section.open=read('projects-open',true)!==false;
  section.addEventListener('toggle',()=>save('projects-open',section.open));
  $('#projects-heading').addEventListener('click',event=>{if(event.target.closest('button'))return;event.preventDefault();if(window.innerWidth>760&&collapsed){toggle();section.open=true;}else section.open=!section.open;save('projects-open',section.open);});
  $('#sidebar-collapse').onclick=toggle;$('#sidebar-backdrop').onclick=closeMobile;$('#new-project').onclick=newProject;
  $('#select-conversations').onclick=event=>{event.preventDefault();event.stopPropagation();if(selectionBusy)return;if(selecting)endSelection();else{selecting=true;section.open=true;render(projects,conversations);}};
  $('#selection-done').onclick=()=>endSelection();$('#selection-all').onclick=()=>{selected=selected.size===conversations.length?new Set():new Set(conversations.map(c=>c.id));updateSelection();};
  $('#selection-move').onclick=()=>bulkAction('move');$('#selection-delete').onclick=()=>bulkAction('delete');
  window.addEventListener('resize',syncLayout);syncLayout();
 }
 return {init,render,toggle,closeMobile,select,newConversation,projectName,decorateSelection,toggleSelection,get selectionMode(){return selecting;}};
})();
