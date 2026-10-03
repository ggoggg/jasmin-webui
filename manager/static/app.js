const $ = s => document.querySelector(s);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let editingUser;
let gateways=[], selectedGateway='', refreshVersion=0;
function setBusy(value){busy=value;$('#gateway-select').disabled=value || !gateways.length;}
function gatewayName(){return gateways.find(g=>g.id===selectedGateway)?.name || selectedGateway;}
let state, page = 'overview', token = sessionStorage.getItem('jasmin-token') || '', formKind, busy = false;
const titles = {overview:'Gateway overview',users:'Users',groups:'Groups',connectors:'SMPP connections',mt:'MT routes',mo:'MO routes',mt_interceptors:'MT interceptors',mo_interceptors:'MO interceptors'};
const subtitles = {overview:'Your connections, users, and message routing in one place.',users:'Manage gateway accounts, access, and messaging quotas.',groups:'Organize users and control access by group.',connectors:'Connect your gateway to upstream SMS providers.',mt:'Route outbound messages from your users to SMPP providers.',mo:'Route incoming messages to HTTP endpoints or SMPP clients.',mt_interceptors:'Process outbound messages with Python scripts before routing.',mo_interceptors:'Process inbound messages with Python scripts before routing.'};
function badge(text, kind='') { return `<span class="badge ${kind}">${esc(text)}</span>`; }
function toast(text) { $('#toast').textContent=text; $('#toast').hidden=false; setTimeout(()=>$('#toast').hidden=true,4500); }
async function api(path, method='GET', data) {
  if(method!=='GET' && (!state || state.gateway_id!==selectedGateway))throw new Error('Refresh the selected gateway before making changes.');
  const response=await fetch('/api/'+path,{method,headers:{'Content-Type':'application/json','X-Jasmin-Manager':'1',...(selectedGateway?{'X-Jasmin-Gateway':selectedGateway}:{}),...(token?{Authorization:'Bearer '+token}:{})},...(data?{body:JSON.stringify(data)}:{})});
  const result=await response.json();
  if(response.status===401){if(!$('#login').open)$('#login').showModal(); throw new Error(result.error);}
  if(!response.ok)throw new Error(result.error || 'Request failed.');
  return result;
}
async function refresh(){
  const version=++refreshVersion;
  $('#refresh').disabled=true;
  try {
    if(!gateways.length){
      const catalog=await api('gateways');
      if(version!==refreshVersion)return false;
      gateways=catalog.gateways;
      const saved=sessionStorage.getItem('jasmin-gateway');
      selectedGateway=gateways.some(g=>g.id===saved)?saved:catalog.default;
      $('#gateway-select').innerHTML=gateways.map(g=>`<option value="${esc(g.id)}">${esc(g.name)} · ${esc(g.host)}</option>`).join('');
      $('#gateway-select').value=selectedGateway;
      $('#gateway-select').disabled=busy;
    }
    const target=selectedGateway;
    $('#gateway-target').textContent='Selected: '+gatewayName();
    const result=await api('state');
    if(version!==refreshVersion || target!==selectedGateway)return false;
    if(result.gateway_id!==target)throw new Error('Gateway response does not match your selection. Refresh before continuing.');
    state=result;
    $('#error').hidden=true;$('#demo-banner').hidden=state.mode!=='demo';$('#mode').textContent=state.mode==='demo'?'Demo workspace':'Live gateway';
    $('#connection-label').textContent=gatewayName()+(state.mode==='demo'?' · simulated':' · connected');
    $('#connection-dot').classList.add('online');$('#updated').textContent='Last refreshed '+new Date().toLocaleTimeString(); render();return true;
  }catch(error){
    if(version!==refreshVersion)return false;
    state=undefined;
    $('#content').innerHTML='<div class="empty">Unable to load this gateway. Check its connection settings and refresh.</div>';
    $('#error').textContent=error.message;$('#error').hidden=false;$('#connection-label').textContent=gatewayName()+' · unavailable';$('#connection-dot').classList.remove('online');return false;
  }finally{if(version===refreshVersion)$('#refresh').disabled=false;}
}
$('#gateway-select').addEventListener('change',async e=>{
  if(busy){e.target.value=selectedGateway;return;}
  selectedGateway=e.target.value;sessionStorage.setItem('jasmin-gateway',selectedGateway);
  state=undefined;$('#modal').close();$('#editor').reset();$('#toast').hidden=true;
  $('#error').hidden=true;$('#connection-dot').classList.remove('online');
  $('#connection-label').textContent='Connecting to '+gatewayName();$('#updated').textContent='Waiting for selected gateway';
  $('#content').innerHTML='<div class="empty">Connecting to the selected gateway…</div>';
  await refresh();
});
function navigate(next){page=next;location.hash=next;$('#title').textContent=titles[page];$('#subtitle').textContent=subtitles[page];$('#breadcrumb').textContent=page==='overview'?'Overview':titles[page];document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('active',b.dataset.page===page));if(state)render();}
const action=(label,op,id,cls='')=>`<button class="${cls}" data-op="${op}" data-id="${esc(id)}">${label}</button>`;
function empty(kind){return `<div class="empty"><strong>No ${titles[kind].toLowerCase()} yet</strong>${kind==='users'?'Create a group, then add your first gateway user.':kind==='connectors'?'Add an SMPP provider to start connecting your gateway.':'Create your first configuration to get started.'}<br><button data-create="${kind}">+ Add ${kind==='connectors'?'connection':kind==='mt'||kind==='mo'?'route':kind.slice(0,-1)}</button></div>`;}
function table(kind, compact=false){
 let rows=[], headers=[];
 if(kind==='users'){headers=['User / ID','Group','Balance','SMS quota','Status',''];rows=state.users.map(u=>[`${esc(u.username)}<small class="mono">${esc(u.uid)}</small>`,esc(u.gid),u.balance===null?'Unlimited':esc(u.balance),u.submit_sm_count===null?'Unlimited':esc(u.submit_sm_count),badge(u.enabled?'Enabled':'Disabled',u.enabled?'':'neutral'),`<div class="row-actions">${action('Edit','edit',u.uid)}${action('Quotas','quotas',u.uid)}${action(u.enabled?'Disable':'Enable',u.enabled?'disable':'enable',u.uid)}${action('Delete','delete',u.uid,'danger')}</div>`]);}
 if(kind==='groups'){headers=['Group ID','Users','Status',''];rows=state.groups.map(g=>[`<strong class="mono">${esc(g.gid)}</strong>`,state.users.filter(u=>u.gid===g.gid).length,badge(g.enabled?'Enabled':'Disabled',g.enabled?'':'neutral'),`<div class="row-actions">${action(g.enabled?'Disable':'Enable',g.enabled?'disable':'enable',g.gid)}${action('Delete','delete',g.gid,'danger')}</div>`]);}
 if(kind==='connectors'){headers=compact?['Connection','Session','Service']:['Connection','Endpoint','Bind mode','SMS / sec','Session',''];rows=state.connectors.map(c=>compact?[`<strong>${esc(c.id)}</strong><small>${esc(c.host)}:${esc(c.port)}</small>`,badge(c.session_state || 'NONE',String(c.session_state).startsWith('BOUND')?'':'neutral'),badge(c.service_status?'Running':'Stopped',c.service_status?'':'neutral')]:[`<strong>${esc(c.id)}</strong><small>${esc(c.username)}</small>`,`<span class="mono">${esc(c.host)}:${esc(c.port)}</span>`,esc(c.bindOperation),esc(c.throughput),badge(c.session_state || 'NONE',String(c.session_state).startsWith('BOUND')?'':'neutral'),`<div class="row-actions">${action('Edit','edit',c.id)}${action(c.service_status?'Stop':'Start',c.service_status?'stop':'start',c.id)}${action('Delete','delete',c.id,'danger')}</div>`]);}
 if(kind==='mt'||kind==='mo'){headers=['Order','Route type','Destination','Filters',...(kind==='mt'?['Rate']:[]),''];rows=state.routes[kind].map(r=>[`<strong class="mono">${r.order}</strong>`,esc(r.type),r.connectors.map(c=>`${esc(c.id)} ${badge(c.type,'neutral')}${c.url?`<small>${esc(c.url)}</small>`:''}`).join('<br>'),`<div class="route-filters">${r.filters.map(esc).join('<br>')||'Fallback · all unmatched messages'}</div>`,...(kind==='mt'?[esc(r.rate)]:[]),action('Delete','delete',r.order,'danger')]);}
 if(!rows.length)return empty(kind);
 return `<div class="table-wrap"><table><thead><tr>${headers.map(h=>`<th>${h}</th>`).join('')}</tr></thead><tbody>${rows.map(row=>`<tr>${row.map(v=>`<td>${v}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
}
function render(){
 if(page.endsWith("_interceptors")){renderInterceptors();return;}
 const running=state.connectors.filter(c=>c.service_status).length;
 if(page==='overview'){
 const cards=[['Total users',state.users.length,`${state.users.filter(u=>u.enabled).length} enabled`,'Gateway accounts','♙'],['SMPP connections',state.connectors.length,`${running} running`,'Upstream providers','⇄'],['MT routes',state.routes.mt.length,'Outbound','User → SMS provider','↗'],['MO routes',state.routes.mo.length,'Inbound','Provider → application','↙']];
 $('#content').innerHTML=`<div class="stats">${cards.map(c=>`<div class="stat"><div class="stat-top">${c[0]}<span class="stat-icon">${c[4]}</span></div><div class="stat-value">${c[1]}</div><div class="stat-bottom"><strong>${c[2]}</strong> · ${c[3]}</div></div>`).join('')}</div><div class="grid"><div><section class="panel"><div class="panel-head"><div><h2>SMPP connections</h2><p>Your upstream provider connections</p></div><button data-page="connectors" class="quiet">View all ↗</button></div>${table('connectors',true)}<div class="hint">A running service is connected only when its SMPP session is bound.</div></section><section class="panel"><div class="panel-head"><div><h2>Build your gateway</h2><p>A few steps to get messages moving</p></div></div><div class="quick-actions"><button data-create="groups"><span>▦</span>Create a group<small>Organize your accounts</small></button><button data-create="users"><span>♙</span>Add a user<small>Set up messaging access</small></button><button data-create="mt"><span>↗</span>Create a route<small>Choose a delivery path</small></button></div></section></div><div><section class="panel"><div class="panel-head"><h2>Message routing</h2>${badge('MO + MT','neutral')}</div>${['mt','mo'].map(d=>`<div class="route-flow"><div class="flow-title"><span>${d==='mt'?'↗ Mobile terminated':'↙ Mobile originated'}</span><span>${state.routes[d].length} routes</span></div><div class="flow-diagram"><span class="flow-node">${d==='mt'?'Gateway user':'SMS provider'}</span><span class="flow-arrow">→</span><span class="flow-node">Jasmin</span><span class="flow-arrow">→</span><span class="flow-node">${d==='mt'?'SMS provider':'Application'}</span></div><p>${d==='mt'?'Deliver outbound messages through your SMPP connections.':'Forward incoming messages to your application.'}</p></div>`).join('')}<div class="hint">Higher route orders are evaluated first. Order 0 is the fallback route.</div></section><section class="panel"><div class="panel-head"><h2>Configuration</h2>${badge(state.persisted?'Saved':'Unsaved',state.persisted?'':'amber')}</div><div class="hint">${state.mode==='demo'?'Demo changes last only for this server session.':'Changes apply immediately. Save configuration to keep changes across gateway restarts.'}</div></section></div></div>`;
 }else{
 $('#content').innerHTML=`<section class="panel"><div class="panel-head"><div><h2>${titles[page]}</h2><p>${page==='mt'||page==='mo'?'Routes are evaluated in descending order. Filters use AND matching.':'Manage your gateway configuration'}</p></div><div class="toolbar"><input class="search" id="search" aria-label="Search list" placeholder="Search ${titles[page].toLowerCase()}…"><button class="primary" data-create="${page}">+ Add ${page==='connectors'?'connection':page==='mt'||page==='mo'?'route':page.slice(0,-1)}</button></div></div>${table(page)}<div class="hint">Changes apply immediately. ${state.mode==='demo'?'Demo data is temporary.':'Save configuration to persist changes on the gateway.'}</div></section>`;
 $('#search')?.addEventListener('input',e=>document.querySelectorAll('tbody tr').forEach(row=>row.hidden=!row.textContent.toLowerCase().includes(e.target.value.toLowerCase())));
 }
}
function field(name,label,type='text',value='',help='',required=true){return `<label>${label}<input name="${name}" type="${type}" value="${esc(value)}" ${required?'required':''} ${type==='number'?'min="0" step="any"':''}>${help?`<div class="field-help">${help}</div>`:''}</label>`;}
function select(name,label,options){return `<label>${label}<select name="${name}" required>${options.map(o=>`<option value="${esc(Array.isArray(o)?o[0]:o)}">${esc(Array.isArray(o)?o[1]:o)}</option>`).join('')}</select></label>`;}
function destinationRow(direction){return `<div class="destination full">${direction==='mt'?select('destination','SMPP destination',state.connectors.map(c=>[c.id,c.id+' · '+c.host])):select('destinationType','Destination type',[['http','HTTP endpoint'],['smpps','SMPP server system ID']])+field('destination','Destination ID')+field('url','HTTP URL','url','','Required for HTTP destinations.',false)+select('httpMethod','HTTP method',['POST','GET'])}<button type="button" class="quiet remove-row">Remove destination</button></div>`;}
function filterRow(direction){return `<div class="filter full" data-direction="${direction}">${select('filterType','Match filter',['Transparent','SourceAddr','DestinationAddr','ShortMessage',...(direction==='mt'?['User','Group']:['Connector']),['Existing','Use an existing filter']])}<div class="filter-value">${field('filterValue','Filter value','text','','Transparent matches all messages.',false)}</div><button type="button" class="quiet remove-row">Remove filter</button></div>`;}
function openForm(kind){
 if(kind.endsWith("_interceptors")){openInterceptorForm(kind);return;}
 if(!state)return;
 editingEntity=null;
 editingUser=null;formKind=kind;$('#editor').reset();$('#form-error').hidden=true;$('#submit-form').textContent='Create';$('#submit-form').disabled=false;
 $('#modal-title').textContent='Create '+(kind==='mt'?'MT route':kind==='mo'?'MO route':kind==='connectors'?'SMPP connection':kind.slice(0,-1));
 let html='';
 if(kind==='groups')html=field('gid','Group ID');
 if(kind==='users')html=field('uid','User ID')+select('gid','Group',state.groups.map(g=>g.gid))+field('username','Username')+field('password','Password','password')+field('balance','Balance','number','','Blank means unlimited.',false)+field('submit_sm_count','SMS quota','number','','Blank means unlimited.',false)+field('http_throughput','HTTP SMS / sec','number','','Blank means unlimited.',false)+field('smpps_throughput','SMPP SMS / sec','number','','Blank means unlimited.',false)+(state.groups.length?'':'<p class="full">Create a group before adding users.</p>');
 if(kind==='connectors')html=field('id','Connection ID')+field('host','Provider hostname')+field('port','Port','number',2775)+select('bindOperation','Bind mode',['transceiver','transmitter','receiver'])+field('username','System ID','text','','Up to 15 ASCII characters.')+field('password','Password','password','','Up to 8 ASCII characters.')+field('throughput','Submit rate (SMS / sec)','number',10,'0 disables throttling.')+'<div class="field-help full">New connections are stopped. Start the connection after creating it.</div>';
 if(kind==='mt'||kind==='mo')html=select('type','Route type',[['Static','Static · one destination'],['Default','Default · fallback'],['Failover','Failover · ordered destinations'],['RandomRoundrobin','Random round robin']])+field('order','Route order','number',10,'Higher orders run first; use 0 for default.')+(kind==='mt'?field('rate','Rate per message','number',0):'')+`<div class="full" id="destinations">${destinationRow(kind)}</div><button type="button" id="add-destination">+ Add destination</button><div class="full" id="filters">${filterRow(kind)}</div><button type="button" id="add-filter">+ Add filter</button>`;
 $('#fields').innerHTML=html;
 $('#add-destination')?.addEventListener('click',()=>$('#destinations').insertAdjacentHTML('beforeend',destinationRow(kind)));
 $('#add-filter')?.addEventListener('click',()=>$('#filters').insertAdjacentHTML('beforeend',filterRow(kind)));
 $('#fields [name="type"]')?.addEventListener('change',e=>{
 const def=e.target.value==='Default';$('#fields [name="order"]').value=def?0:10;$('#filters').hidden=def;$('#add-filter').hidden=def;
 });
 $('#modal').showModal();
}
$('#fields').addEventListener('click',e=>{if(e.target.closest('.remove-row'))e.target.closest('.destination,.filter').remove();});
$('#editor').addEventListener('submit',async e=>{
 e.preventDefault();if(editingEntity || formKind?.endsWith('_interceptors'))return;if(busy)return;setBusy(true);$('#submit-form').disabled=true;$('#form-error').hidden=true;
 try{
 let data=Object.fromEntries(new FormData(e.target)),path=editingUser?'users/'+encodeURIComponent(editingUser)+'/quotas':formKind;
 if(formKind==='mt'||formKind==='mo'){
  path='routes/'+formKind;
  data.connectors=[...document.querySelectorAll('.destination')].map(row=>({id:row.querySelector('[name="destination"]').value,type:formKind==='mt'?'smppc':row.querySelector('[name="destinationType"]').value,url:row.querySelector('[name="url"]')?.value,method:row.querySelector('[name="httpMethod"]')?.value}));
  data.filters=data.type==='Default'?[]:[...document.querySelectorAll('.filter')].map(row=>({type:row.querySelector('[name="filterType"]').value,value:row.querySelector('[name="filterValue"]').value}));
 }
 await api(path,'POST',data);$('#modal').close();toast(editingUser?'Quotas updated.':'Configuration created.');await refresh();
 }catch(err){$('#form-error').textContent=err.message;$('#form-error').hidden=false;}finally{setBusy(false);$('#submit-form').disabled=false;}
});
document.addEventListener('click',async e=>{
 const nav=e.target.closest('[data-page]');if(nav)navigate(nav.dataset.page);
 const create=e.target.closest('[data-create]');if(create)openForm(create.dataset.create);
 const button=e.target.closest('[data-op]');if(!button||busy||!state)return;
 const {op,id}=button.dataset;
 if(op==='edit'){openEntityEditor(page,id);return;}
 if(op==='quotas'){
  const user=state.users.find(u=>u.uid===id);openForm('users');editingUser=id;
  $('#modal-title').textContent='Edit quotas · '+user.username;$('#submit-form').textContent='Update quotas';
  $('#fields').innerHTML=['balance','submit_sm_count','http_throughput','smpps_throughput'].map(key=>field(key,({balance:'Balance',submit_sm_count:'SMS quota',http_throughput:'HTTP SMS / sec',smpps_throughput:'SMPP SMS / sec'})[key],'number',user[key]??'','Blank means unlimited.',false)).join('');return;
 }
 if(['delete','stop','disable'].includes(op)&&!confirm(`${op[0].toUpperCase()+op.slice(1)} ${id}? This applies immediately on ${gatewayName()}.`))return;
 setBusy(true);button.disabled=true;
 try{const path=(page==='mt'||page==='mo'?'routes/'+page:page)+'/'+encodeURIComponent(id);await api(path+(op==='delete'?'':'/'+op),op==='delete'?'DELETE':'POST');toast('Gateway updated.');await refresh();}catch(err){$('#error').textContent=err.message;$('#error').hidden=false;}finally{setBusy(false);button.disabled=false;}
});
$('#save').addEventListener('click',async()=>{if(busy||!state)return;setBusy(true);$('#save').disabled=true;try{await api('persist','POST',{profile:'jcli-prod'});toast(state.mode==='demo'?'Demo configuration marked saved. Data remains temporary.':'Configuration saved to jcli-prod.');await refresh();}catch(err){$('#error').textContent=err.message;$('#error').hidden=false;}finally{setBusy(false);$('#save').disabled=false;}});
$('#refresh').addEventListener('click',refresh);
$('#close-modal').onclick=$('#cancel-modal').onclick=()=>$('#modal').close();
$('#login-form').addEventListener('submit',async e=>{e.preventDefault();token=$('#token').value;$('#login-error').textContent='';if(await refresh()){sessionStorage.setItem('jasmin-token',token);$('#token').value='';$('#login').close();}else{$('#login-error').textContent='Unable to connect. Check the token and gateway configuration.';}});
$('#login').addEventListener('cancel',e=>e.preventDefault());
$('#logout').onclick=()=>{token='';sessionStorage.removeItem('jasmin-token');++refreshVersion;gateways=[];selectedGateway='';$('#gateway-select').disabled=true;$('#gateway-target').textContent='Workspace locked';state=undefined;$('#content').innerHTML='<div class="empty">Workspace locked</div>';$('#login').showModal();};
window.addEventListener('hashchange',()=>{const next=location.hash.slice(1);if(titles[next])navigate(next);});
navigate(titles[location.hash.slice(1)]?location.hash.slice(1):'overview');refresh();
