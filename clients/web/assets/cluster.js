const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = value => new Intl.NumberFormat('fa-IR', {maximumFractionDigits:2}).format(value);
const errors = {duplicate_node:'این شناسه یا IP قبلاً ثبت شده است.',node_not_found:'سرور پیدا نشد.',host_key_required:'ابتدا کلید میزبان همهٔ سرورها را بررسی و ثبت کنید.',controller_key_required:'ابتدا کلید کنترل‌کننده را بسازید و دسترسی آن را روی سرور مقصد ثبت کنید.',ssh_command_failed:'اتصال SSH یا دستور نصب انجام نشد. دسترسی کلید، ابزارهای git و python3 و تازه بودن پوشه را بررسی کنید.',ssh_host_unreachable:'پورت SSH پاسخ نداد.',invalid_input:'مقادیر فرم و متمایز بودن نقش‌ها را بررسی کنید.',runner_busy:'یک عملیات در حال اجراست.',port_in_use:'پورت انتخابی اشغال است؛ هیچ سرویس دیگری متوقف نشد.',host_key_change_requires_operator:'کلید ثبت‌شده تغییر کرده است؛ پیش از اتصال هویت میزبان را بررسی کنید.',clean_source_required:'نسخهٔ کنترل‌کننده باید در گیت ثبت شده باشد.'};
let current = null, pin = null, editingNode = null;
function message(text) { const box=$('toast'); box.textContent=text; box.hidden=false; setTimeout(()=>{box.hidden=true;},7000); }
async function call(path, body) {
  const response = await fetch('/api/cluster'+path,{method:body===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-NetSpectra-Client':'panel'},...(body===undefined?{}:{body:JSON.stringify(body)})});
  const result=await response.json(); if(!response.ok) throw new Error(errors[result.error||result.detail]||'عملیات انجام نشد. تنظیمات و اتصال را بررسی کنید.');
  return result;
}
function refresh() { window.dispatchEvent(new Event('cluster-refresh')); }
function title(id) { return current?.cluster.nodes.find(n=>n.node_id===id)?.name || id; }
export function renderCluster(state) {
  current=state;
  const {nodes,topologies}=state.cluster;
  $('cluster-nodes-empty').hidden=!!nodes.length; $('cluster-nodes-wrap').hidden=!nodes.length;
  $('new-topology').disabled=nodes.length<2;
  const busy=!!state.active_job;
  $('cluster-nodes').innerHTML=nodes.map(node=>`<tr><td><strong class="row-name">${esc(node.name)}</strong><small class="mono">${esc(node.address)}</small></td><td class="mono">${esc(node.ssh_user)} : ${esc(node.ssh_port)}</td><td class="mono small">${esc(node.install_dir)}</td><td><div class="row-actions"><button class="button secondary" data-node="${esc(node.node_id)}" data-action="edit" ${busy?'disabled':''}>تنظیمات</button><button class="button secondary" data-node="${esc(node.node_id)}" data-action="scan" ${busy?'disabled':''}>${node.host_key?'کلید تأییدشده':'بررسی کلید'}</button><button class="button secondary" data-node="${esc(node.node_id)}" data-action="bootstrap" ${busy||!node.host_key?'disabled':''}>نصب تازه</button><button class="button secondary" data-node="${esc(node.node_id)}" data-action="preflight" ${busy||!node.host_key?'disabled':''}>بررسی اتصال</button></div></td></tr>`).join('');
  $('cluster-topologies-empty').hidden=!!topologies.length;
  $('cluster-topologies').innerHTML=topologies.map(topology=>{
    const route=`${topology.clients.map(title).join('، ')} → ${topology.load_balancer?title(topology.load_balancer)+' → ':''}${topology.servers.map(title).join('، ')}`;
    return `<div class="topology-row"><div><strong>${esc(topology.name)}</strong><p class="small">${esc(route)}</p><small class="muted">${esc(topology.protocol.toUpperCase())} · پورت ${num(topology.port)} · ${num(topology.repetitions)} تکرار</small></div><button class="button secondary" data-topology="${esc(topology.topology_id)}" ${busy?'disabled':''}>اجرای مسیر</button></div>`;
  }).join('');
  const runs=state.network_runs;
  $('network-runs').innerHTML=runs.length?`<table><thead><tr><th>آزمایش</th><th>نتیجه</th><th>نمونه / بایت</th><th>گزارش</th></tr></thead><tbody>${runs.map(run=>`<tr><td>${esc(run.topology.name)}<span class="row-id">${esc(run.run_id)}</span></td><td><span class="status-label ${esc(run.status)}">${{succeeded:'موفق',failed:'ناموفق',cancelled:'متوقف‌شده'}[run.status]||esc(run.status)}</span>${run.failure_reason?`<p class="small">${esc(errors[run.failure_reason]||run.failure_reason)}</p>`:''}</td><td>${num(run.observations.length)} نمونه / ${num(run.observations.reduce((sum,item)=>sum+item.bytes_echoed,0))} بایت</td><td><button class="button secondary" data-report="${esc(run.run_id)}">دریافت JSON</button></td></tr>`).join('')}</tbody></table>`:'<p class="empty-filter">هنوز آزمایش بین سرورها اجرا نشده است.</p>';
  const latest=state.jobs.find(job=>['bootstrap','preflight'].includes(job.kind));
  if(latest && !['running','cancelling'].includes(latest.status)) {
    $('cluster-operation-status').textContent=`آخرین آماده‌سازی: ${title(latest.target)} · ${latest.status==='succeeded'?'موفق':errors[latest.error]||'انجام نشد'}`;
  }
}
function editNode(node=null) {
  editingNode=node?.node_id||null; $('node-form').reset(); $('node-error').hidden=true;
  $('node-id').readOnly=!!node;
  $('node-title').textContent=node?'تنظیمات سرور':'افزودن سرور';
  if(node) for(const [id,key] of [['node-id','node_id'],['node-name','name'],['node-address','address'],['node-port','ssh_port'],['node-user','ssh_user'],['node-directory','install_dir']]) $(id).value=node[key];
  $('node-dialog').showModal();
}
$('new-node').addEventListener('click',()=>editNode());
$('node-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('save-node').disabled=true; $('node-error').hidden=true;
  try { await call(editingNode?`/nodes/${editingNode}/update`:'/nodes',{node_id:$('node-id').value,name:$('node-name').value.trim(),address:$('node-address').value.trim(),ssh_port:Number($('node-port').value),ssh_user:$('node-user').value.trim(),install_dir:$('node-directory').value.trim()}); $('node-dialog').close(); refresh(); }
  catch(error){ $('node-error').textContent=error.message; $('node-error').hidden=false; } finally{$('save-node').disabled=false;}
});
$('create-cluster-key').addEventListener('click',async()=>{ try { const result=await call('/key',{}); $('cluster-public-key').value=result.public_key; $('cluster-public-key').hidden=false; } catch(error){message(error.message);} });
$('cluster-nodes').addEventListener('click',async event=>{
  const button=event.target.closest('button[data-node]'); if(!button)return;
  if(button.dataset.action==='edit'){editNode(current.cluster.nodes.find(node=>node.node_id===button.dataset.node));return;}
  button.disabled=true;
  try {
    if(button.dataset.action==='scan') {
      const result=await call(`/nodes/${button.dataset.node}/scan`,{});
      pin={node:button.dataset.node,...result.candidates[0]};
      $('host-fingerprint').textContent=pin.fingerprint; $('host-key-dialog').showModal();
    } else {await call(`/nodes/${button.dataset.node}/${button.dataset.action}`,{}); message('عملیات آماده‌سازی شروع شد.');refresh();}
  } catch(error){message(error.message);} finally{button.disabled=false;}
});
$('pin-host-key').addEventListener('click',async()=>{ if(!pin)return; try{await call(`/nodes/${pin.node}/pin`,{host_key:pin.host_key});$('host-key-dialog').close();refresh();}catch(error){message(error.message);} });
$('new-topology').addEventListener('click',()=>{
  $('topology-form').reset(); $('topology-error').hidden=true;
  for(const role of ['clients','servers']) $('topology-'+role).innerHTML=current.cluster.nodes.map(node=>`<label class="checkbox-label"><input type="checkbox" name="${role}" value="${esc(node.node_id)}">${esc(node.name)}</label>`).join('');
  $('topology-lb').innerHTML='<option value="">بدون لودبالانسر</option>'+current.cluster.nodes.map(node=>`<option value="${esc(node.node_id)}">${esc(node.name)}</option>`).join('');
  $('topology-dialog').showModal();
});
$('topology-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('save-topology').disabled=true; $('topology-error').hidden=true;
  const selected=role=>[...$('topology-form').querySelectorAll(`input[name="${role}"]:checked`)].map(input=>input.value);
  const definition={name:$('topology-name').value.trim(),clients:selected('clients'),servers:selected('servers'),load_balancer:$('topology-lb').value||null,protocol:$('topology-protocol').value,port:Number($('topology-port').value),repetitions:Number($('topology-repetitions').value),run_seed:Number($('topology-seed').value)};
  try{await call('/topologies',definition);$('topology-dialog').close();refresh();}catch(error){$('topology-error').textContent=error.message;$('topology-error').hidden=false;}finally{$('save-topology').disabled=false;}
});
$('cluster-topologies').addEventListener('click',async event=>{const button=event.target.closest('button[data-topology]');if(!button)return;button.disabled=true;try{await call(`/topologies/${button.dataset.topology}/run`,{});refresh();}catch(error){message(error.message);button.disabled=false;}});
$('network-runs').addEventListener('click',async event=>{const button=event.target.closest('button[data-report]');if(!button)return;try{const record=await call(`/runs/${button.dataset.report}`);const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=record.run_id+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){message(error.message);}});
