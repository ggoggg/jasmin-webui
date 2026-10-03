let editingInterceptor=null, interceptorGateway='';
function interceptorDirection(){return page.slice(0,2);}
function renderInterceptors(){
 const direction=interceptorDirection(), items=state.interceptors[direction];
 $('#content').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>${titles[page]}</h2><p>Higher orders run first. Order 0 is the fallback. Filters use AND matching.</p></div><div class="toolbar"><button class="danger" id="flush-interceptors" ${items.length?'':'disabled'}>Remove all</button><button class="primary" data-create="${page}">+ Add interceptor</button></div></div>${items.length?`<div class="table-wrap"><table><thead><tr><th>Order</th><th>Type</th><th>Filters</th><th>Python script</th><th></th></tr></thead><tbody>${items.map(item=>`<tr><td>${item.order}</td><td>${esc(item.type)}</td><td class="route-filters">${item.filters.map(esc).join('<br>')||'Fallback · all unmatched messages'}</td><td><div class="script-preview mono">${esc(item.script.split('\n').find(line=>line.trim())||'Empty script')}</div><small>${item.script.split('\n').length} lines</small></td><td><div class="row-actions"><button data-interceptor-edit="${item.order}">View / edit</button><button class="danger" data-interceptor-delete="${item.order}">Delete</button></div></td></tr>`).join('')}</tbody></table></div>`:'<div class="empty"><strong>No interceptors configured</strong>Add a filtered script or a default interceptor.</div>'}<div class="hint">Changes apply immediately on ${esc(gatewayName())}. Save configuration to persist them. Script execution requires a connected Jasmin interceptor service.</div></section>`;
}
function openInterceptorForm(kind, item=null){
 if(!state||busy)return;
 editingEntity=null;formKind=kind;editingInterceptor=item;interceptorGateway=selectedGateway;
 const direction=kind.slice(0,2), preserve=item && !item.editable_filters;
 $('#editor').reset();$('#form-error').hidden=true;$('#submit-form').disabled=false;
 $('#modal').classList.add('interceptor-form');
 $('#modal-title').textContent=(item?'Edit ':'Create ')+direction.toUpperCase()+' interceptor';
 $('#submit-form').textContent=item?'Save changes':'Create interceptor';
 $('#fields').innerHTML=select('type','Interceptor type',[['Static','Static · filtered'],['Default','Default · fallback']])+field('order','Order','number',item?.order??10)+`<div class="interceptor-note">Target: <strong>${esc(gatewayName())}</strong>. This Python script runs on matching messages in Jasmin. Changes apply immediately; the manager only checks syntax.</div>`+(preserve?`<div class="full"><label>Existing filters (preserved)</label><p class="interceptor-filters">${item.filters.map(esc).join('\n')}</p><small>These filter types cannot be edited in this form. Script changes preserve them.</small></div>`:`<div class="full" id="filters"></div><button type="button" id="add-filter">+ Add filter</button>`)+`<label class="full">Python script<textarea class="script-editor" name="script" required spellcheck="false" aria-label="Python script"></textarea><div class="field-help">Available globals include routable, smpp_status and http_status. The script source is stored in Jasmin.</div></label>`;
 const type=$('#fields [name="type"]'), order=$('#fields [name="order"]');
 type.value=item?(item.type==='DefaultInterceptor'?'Default':'Static'):'Static';
 order.readOnly=!!item;
 if(item || preserve)type.disabled=true;
 $('#fields [name="script"]').value=item?.script??'# Process the matching message here.\nsmpp_status = 0\nhttp_status = 0\n';
 function addFilter(spec={type:'Transparent',value:''}){
  $('#filters').insertAdjacentHTML('beforeend',filterRow(direction));
  const row=$('#filters').lastElementChild;
  row.querySelector('[name="filterType"]').value=spec.type;
  updateFilterInput(row,spec.value);
 }
 if(!preserve){
  (item?item.filter_specs:[{type:'Transparent',value:''}]).forEach(addFilter);
  $('#add-filter').onclick=()=>addFilter();
  const updateType=()=>{const fallback=type.value==='Default';$('#filters').hidden=fallback;$('#add-filter').hidden=fallback;if(!item)order.value=fallback?0:10;};
  type.onchange=updateType;updateType();
 }
 $('#modal').showModal();
}
$('#modal').addEventListener('close',()=>$('#modal').classList.remove('interceptor-form'));
$('#editor').addEventListener('submit',async e=>{
 if(!formKind?.endsWith('_interceptors'))return;
 e.preventDefault();if(busy)return;
 if(interceptorGateway!==selectedGateway){$('#modal').close();return;}
 setBusy(true);$('#submit-form').disabled=true;$('#form-error').hidden=true;
 try{
  const direction=formKind.slice(0,2), kind=$('#fields [name="type"]').value;
  const preserve=!!editingInterceptor && !editingInterceptor.editable_filters;
  const data={type:kind,order:$('#fields [name="order"]').value,script:$('#fields [name="script"]').value,
   preserve_filters:preserve,revision:editingInterceptor?.revision,
   filters:kind==='Default'||preserve?[]:[...document.querySelectorAll('#filters .filter')].map(row=>({type:row.querySelector('[name="filterType"]').value,value:row.querySelector('[name="filterValue"]').value}))};
  await api('interceptors/'+direction+(editingInterceptor?'/'+editingInterceptor.order:''),'POST',data);
  $('#modal').close();toast('Interceptor saved on '+gatewayName()+'.');await refresh();
 }catch(error){$('#form-error').textContent=error.message;$('#form-error').hidden=false;}
 finally{setBusy(false);$('#submit-form').disabled=false;}
});
document.addEventListener('click',async e=>{
 if(!page.endsWith('_interceptors')||!state||busy)return;
 const edit=e.target.closest('[data-interceptor-edit]');
 if(edit){openInterceptorForm(page,state.interceptors[interceptorDirection()].find(item=>item.order===Number(edit.dataset.interceptorEdit)));return;}
 const remove=e.target.closest('[data-interceptor-delete]'), flush=e.target.closest('#flush-interceptors');
 if(!remove&&!flush)return;
 const direction=interceptorDirection();
 const item=remove?state.interceptors[direction].find(item=>item.order===Number(remove.dataset.interceptorDelete)):null;
 if(!confirm(`Remove ${flush?'ALL '+direction.toUpperCase()+' interceptors':'interceptor '+item.order} on ${gatewayName()}? This applies immediately.`))return;
 setBusy(true);
 try{
  await api('interceptors/'+direction+(item?'/'+item.order:''),'DELETE',{revision:item?item.revision:state.interceptor_revisions[direction]});
  toast('Interceptors updated on '+gatewayName()+'.');await refresh();
 }catch(error){$('#error').textContent=error.message;$('#error').hidden=false;}
 finally{setBusy(false);}
});
