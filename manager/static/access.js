function syncAccess(){
 $('#access-mode').textContent=canEdit?'Editing enabled':'Read only';
 $('#logout').textContent=canEdit?'Sign out':'Sign in';
 document.querySelectorAll('#save,[data-create],[data-op]:not([data-op="edit"]),#flush-interceptors,[data-interceptor-delete]').forEach(button=>{if(button.hidden===canEdit)button.hidden=!canEdit;});
 if(!canEdit && $('#modal').open)applyReadonlyForm();
}
function applyReadonlyForm(){
 $('#submit-form').hidden=!canEdit;
 if(canEdit)return;
 $('#fields').querySelectorAll('input,textarea,select,button').forEach(input=>{
  if(input.tagName==='TEXTAREA'||(input.tagName==='INPUT'&&input.type!=='checkbox'))input.readOnly=true;
  else input.disabled=true;
 });
 $('#cancel-modal').textContent='Close';
}
$('#modal').addEventListener('close',()=>{$('#submit-form').hidden=false;$('#cancel-modal').textContent='Cancel';});
new MutationObserver(syncAccess).observe($('#content'),{childList:true,subtree:true});
syncAccess();
