'use strict';
// This mode exists only in the authenticated, DSH-owned engine instance.
if(document.querySelector('meta[name="lucent-base"]')?.content){
 document.documentElement.classList.add('dsh-embedded');
 if(new URLSearchParams(location.search).get('surface')==='settings'){
  document.documentElement.classList.add('dsh-settings');
  $('#settings').addEventListener('cancel',e=>e.preventDefault());
  $('#settings-button').onclick();
 }
}
