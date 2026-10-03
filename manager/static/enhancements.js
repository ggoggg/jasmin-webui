let editingEntity=null;
function updateFilterInput(row,value=''){
 const kind=row.querySelector('[name="filterType"]').value;
 const options=kind==='User'?state.users.map(u=>[u.uid,`${u.username} (${u.uid})`]):kind==='Group'?state.groups.map(g=>[g.gid,g.gid]):kind==='Connector'?state.connectors.map(c=>[c.id,c.id]):kind==='Existing'?(state.filters||[]).filter(f=>f.directions.includes(row.dataset.direction)).map(f=>[f.id,f.label]):null;
 row.querySelector('.filter-value').innerHTML=options?select('filterValue',kind==='Existing'?'Existing gateway filter':kind,[[ '', options.length?'Select…':'No existing values available'],...options]):field('filterValue','Filter value','text',value,kind==='Transparent'?'Matches all messages.':'Regular expression.',kind!=='Transparent');
 row.querySelector('[name="filterValue"]').value=value;
 if(kind==='Transparent')row.querySelector('[name="filterValue"]').readOnly=true;
}
$('#fields').addEventListener('change',e=>{if(e.target.name==='filterType')updateFilterInput(e.target.closest('.filter'));});
function openEntityEditor(kind,id){
 const item=kind==='users'?state.users.find(u=>u.uid===id):state.connectors.find(c=>c.id===id);
 openForm(kind);
 editingEntity={kind,id,revision:item.revision,gateway:selectedGateway};
 $('#modal-title').textContent='Edit '+(kind==='users'?'user':'connection')+' · '+id;
 $('#submit-form').textContent='Save changes';
 if(kind==='users'){
  $('#fields').innerHTML=field('uid','User ID','text',id)+select('gid','Group',state.groups.map(g=>g.gid))+field('username','Username','text',item.username)+field('password','New password','password','','Leave blank to keep the current password.',false)+'<div class="field-help full">Messaging quotas, permissions, value filters and enabled status are preserved.</div>';
  $('#fields [name="uid"]').readOnly=true;$('#fields [name="gid"]').value=item.gid;
 }else{
  for(const key of ['id','host','port','username','bindOperation','throughput'])$('#fields [name="'+key+'"]').value=item[key];
  $('#fields [name="id"]').readOnly=true;
  const password=$('#fields [name="password"]');password.required=false;password.value='';
  password.insertAdjacentHTML('afterend','<div class="field-help">Leave blank to keep the current password.</div>');
  $('#fields').insertAdjacentHTML('beforeend','<div class="interceptor-note full">Stop the connection before saving edits. Its ID, routes and advanced settings are retained. It remains stopped after saving; start it when ready.</div>');
  if(item.service_status){$('#form-error').textContent='This connection is running. Close this form and stop it before editing.';$('#form-error').hidden=false;$('#submit-form').disabled=true;}
 }
}
$('#editor').addEventListener('submit',async e=>{
 if(!editingEntity)return;
 e.preventDefault();if(busy)return;
 const current=editingEntity;
 if(current.gateway!==selectedGateway){$('#modal').close();return;}
 setBusy(true);$('#submit-form').disabled=true;$('#form-error').hidden=true;
 try{
  await api(current.kind+'/'+encodeURIComponent(current.id)+'/edit','POST',{...Object.fromEntries(new FormData(e.target)),revision:current.revision});
  $('#modal').close();editingEntity=null;toast('Changes saved on '+gatewayName()+'.');await refresh();
 }catch(error){$('#form-error').textContent=error.message;$('#form-error').hidden=false;}
 finally{setBusy(false);$('#submit-form').disabled=false;}
});
// Sort existing rows so search visibility and action bindings are preserved.
const tableSorts=new Map();
const collator=new Intl.Collator(undefined,{numeric:true,sensitivity:'base'});
function sortRows(table,column,descending){
 const rows=[...table.tBodies[0].rows];
 const value=row=>{const cell=row.cells[column];return (cell.querySelector('strong')?.textContent||cell.childNodes[0]?.textContent||cell.textContent).trim();};
 rows.sort((a,b)=>{
  const x=value(a),y=value(b);
  const nx=x==='Unlimited'?Infinity:Number(x),ny=y==='Unlimited'?Infinity:Number(y);
  const order=x!==''&&y!==''&&!Number.isNaN(nx)&&!Number.isNaN(ny)?(nx===ny?0:nx<ny?-1:1):collator.compare(x,y);
  return descending?-order:order;
 });
 table.tBodies[0].append(...rows);
 [...table.tHead.rows[0].cells].forEach((cell,index)=>{cell.setAttribute('aria-sort',index===column?(descending?'descending':'ascending'):'none');const button=cell.querySelector('button');if(button)button.dataset.arrow=index===column?(descending?'▼':'▲'):'↕';});
}
function prepareTables(){
 document.querySelectorAll('#content table').forEach((table,index)=>{
  if(table.dataset.sortable)return;
  table.dataset.sortable='true';const key=page+':'+index;
  [...table.tHead.rows[0].cells].forEach((cell,column)=>{
   const label=cell.textContent.trim();if(!label)return;
   cell.textContent='';cell.setAttribute('aria-sort','none');
   const button=document.createElement('button');button.className='sort-heading';button.textContent=label;button.setAttribute('aria-label',label);button.dataset.arrow='↕';button.type='button';
   button.onclick=()=>{const previous=tableSorts.get(key);const descending=previous?.column===column?!previous.descending:false;tableSorts.set(key,{column,descending});sortRows(table,column,descending);};
   cell.append(button);
  });
  const saved=tableSorts.get(key);if(saved)sortRows(table,saved.column,saved.descending);
 });
}
new MutationObserver(prepareTables).observe($('#content'),{childList:true,subtree:true});
prepareTables();
