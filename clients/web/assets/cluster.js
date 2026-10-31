const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num = value => new Intl.NumberFormat('fa-IR', {maximumFractionDigits:2}).format(value);
const errors = {protocol_dependency_unavailable:'ابتدا ابزارهای QUIC را روی سرورهای انتخابی نصب کنید.',certificate_verification_failed:'گواهی تأیید نشد.',quic_or_tls_handshake_failed:'اتصال امن برقرار نشد؛ نتیجهٔ ضبط و جهت مسیر را بررسی کنید.',handshake_timeout:'مهلت برقراری اتصال تمام شد.',request_timeout:'مهلت دریافت پاسخ تمام شد.',duplicate_node:'این شناسه یا IP قبلاً ثبت شده است.',node_not_found:'سرور پیدا نشد.',host_key_required:'ابتدا کلید میزبان همهٔ سرورها را بررسی و ثبت کنید.',controller_key_required:'ابتدا کلید کنترل‌کننده را بسازید و دسترسی آن را روی سرور مقصد ثبت کنید.',ssh_command_failed:'اتصال SSH یا دستور نصب انجام نشد. دسترسی کلید، ابزارهای git و python3 و تازه بودن پوشه را بررسی کنید.',ssh_host_unreachable:'پورت SSH پاسخ نداد.',invalid_input:'مقادیر فرم و متمایز بودن نقش‌ها را بررسی کنید.',runner_busy:'یک عملیات در حال اجراست.',port_in_use:'پورت انتخابی اشغال است؛ هیچ سرویس دیگری متوقف نشد.',host_key_change_requires_operator:'کلید ثبت‌شده تغییر کرده است؛ پیش از اتصال هویت میزبان را بررسی کنید.',clean_source_required:'نسخهٔ کنترل‌کننده باید در گیت ثبت شده باشد.'};
let current = null, pin = null, editingNode = null;
let pathsPage=0, networkPage=0;
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
  $('nav-nodes-count').textContent=num(nodes.length);
  $('nav-paths-count').textContent=num(topologies.length);
  $('nav-network-count').textContent=num(state.network_runs.length);
  const query=$('path-search').value.trim().toLocaleLowerCase('fa');
  const protocol=$('path-protocol-filter').value;
  const filtered=topologies.filter(topology=>{
    const names=[...topology.clients,...topology.servers,topology.load_balancer].filter(Boolean).map(title).join(' ');
    return (protocol==='all'||topology.protocol===protocol)&&`${topology.name} ${names}`.toLocaleLowerCase('fa').includes(query);
  });
  const pathPages=Math.max(1,Math.ceil(filtered.length/8));
  pathsPage=Math.min(pathsPage,pathPages-1);
  updatePagination('paths',pathsPage,pathPages,filtered.length);

  $('cluster-nodes-empty').hidden=!!nodes.length; $('cluster-nodes-wrap').hidden=!nodes.length;
  $('new-topology').disabled=nodes.length<2;
  const busy=!!state.active_job;
  $('cluster-nodes').innerHTML=nodes.map(node=>`<tr><td><strong class="row-name">${esc(node.name)}</strong><small class="mono">${esc(node.address)}</small></td><td class="mono">${esc(node.ssh_user)} : ${esc(node.ssh_port)}</td><td class="mono small">${esc(node.install_dir)}</td><td><div class="row-actions"><button class="button secondary" data-node="${esc(node.node_id)}" data-action="edit" ${busy?'disabled':''}>تنظیمات</button><button class="button secondary" data-node="${esc(node.node_id)}" data-action="scan" ${busy?'disabled':''}>${node.host_key?'کلید تأییدشده':'بررسی کلید'}</button><button class="button secondary" data-node="${esc(node.node_id)}" data-action="bootstrap" ${busy||!node.host_key?'disabled':''}>نصب تازه</button><button class="button secondary" data-node="${esc(node.node_id)}" data-action="dependencies" ${busy||!node.host_key?'disabled':''}>نصب ابزار QUIC</button><button class="button secondary" data-node="${esc(node.node_id)}" data-action="preflight" ${busy||!node.host_key?'disabled':''}>بررسی اتصال</button></div></td></tr>`).join('');
  $('cluster-topologies-empty').hidden=!!topologies.length;
  $('cluster-topologies').innerHTML=filtered.slice(pathsPage*8,pathsPage*8+8).map(topology=>{
    const route=`${topology.clients.map(title).join('، ')} → ${topology.load_balancer?title(topology.load_balancer)+' → ':''}${topology.servers.map(title).join('، ')}`;
    return `<div class="topology-row"><div><strong>${esc(topology.name)}</strong><p class="small">${esc(route)}</p><small class="muted">${esc(topology.protocol.toUpperCase())} · پورت ${num(topology.port)} · ${num(topology.repetitions)} تکرار</small></div><div class="row-actions"><button class="button secondary" data-topology="${esc(topology.topology_id)}" ${busy?'disabled':''}>اجرای مسیر</button><button class="button secondary" data-topology="${esc(topology.topology_id)}" data-capture="true" ${busy?'disabled':''}>اجرا + PCAP</button></div></div>`;
  }).join('');
  if(topologies.length&&!filtered.length)$('cluster-topologies').innerHTML='<p class="empty-filter">مسیری با این جست‌وجو پیدا نشد.</p>';
  const runQuery=$('network-search').value.trim().toLocaleLowerCase('fa');
  const runStatus=$('network-status-filter').value;
  const matched=state.network_runs.filter(run=>(runStatus==='all'||run.status===runStatus)&&`${run.topology.name} ${run.run_id} ${run.topology.protocol}`.toLocaleLowerCase('fa').includes(runQuery));
  const runPages=Math.max(1,Math.ceil(matched.length/10));
  networkPage=Math.min(networkPage,runPages-1);
  updatePagination('network',networkPage,runPages,matched.length);
  const runs=matched.slice(networkPage*10,networkPage*10+10);
  $('network-runs').innerHTML=runs.length?`<table><thead><tr><th>آزمایش</th><th>نتیجه</th><th>نمونه / بایت</th><th>گزارش</th></tr></thead><tbody>${runs.map(run=>`<tr><td>${esc(run.topology.name)}<span class="row-id">${esc(run.run_id)}</span></td><td><span class="status-label ${esc(run.status)}">${{succeeded:'موفق',failed:'ناموفق',cancelled:'متوقف‌شده'}[run.status]||esc(run.status)}</span>${run.failure_reason?`<p class="small">${esc(errors[run.failure_reason]||run.failure_reason)}</p>`:''}</td><td>${num(run.observations.length)} نمونه / ${num(run.observations.reduce((sum,item)=>sum+item.bytes_echoed,0))} بایت</td><td><div class="row-actions"><button class="button secondary" data-view="${esc(run.run_id)}">جزئیات</button><button class="button secondary" data-report="${esc(run.run_id)}">JSON</button></div></td></tr>`).join('')}</tbody></table>`:`<p class="empty-filter">${state.network_runs.length?'نتیجه‌ای با این فیلتر پیدا نشد.':'هنوز آزمایش بین سرورها اجرا نشده است.'}</p>`;
  const latest=state.jobs.find(job=>['bootstrap','preflight','dependencies'].includes(job.kind));
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
  syncProtocolControls();
  $('topology-dialog').showModal();
});
$('topology-form').addEventListener('submit',async event=>{
  event.preventDefault(); $('save-topology').disabled=true; $('topology-error').hidden=true;
  const selected=role=>[...$('topology-form').querySelectorAll(`input[name="${role}"]:checked`)].map(input=>input.value);
  const definition={name:$('topology-name').value.trim(),clients:selected('clients'),servers:selected('servers'),load_balancer:$('topology-lb').value||null,protocol:$('topology-protocol').value,port:Number($('topology-port').value),repetitions:Number($('topology-repetitions').value),run_seed:Number($('topology-seed').value),controlled_failure:$('topology-failure').checked};
  try{await call('/topologies',definition);$('topology-dialog').close();refresh();}catch(error){$('topology-error').textContent=error.message;$('topology-error').hidden=false;}finally{$('save-topology').disabled=false;}
});
$('cluster-topologies').addEventListener('click',async event=>{const button=event.target.closest('button[data-topology]');if(!button)return;button.disabled=true;try{await call(`/topologies/${button.dataset.topology}/run`,button.dataset.capture?{capture:true}:{});location.hash='network-results';refresh();}catch(error){message(error.message);button.disabled=false;}});
function captureMarkup(record) {
  if(!record.captures?.length) return `<p class="detail-notice">${record.topology.capture?'ضبط درخواست شد ولی خروجی ثبت نشد.':'ضبط بسته برای این اجرا فعال نبود.'}</p>`;
  const names=Object.fromEntries(record.plan.nodes.map(node=>[node.node_id,node.name]));
  return `<h3 class="attempts-title cluster-section">ضبط بسته‌ها</h3><p class="field-help">فقط هدرها؛ بدون payload و توکن، با IP جایگزین. شمارش هر میزبان مستقل است و بستهٔ یکسان ممکن است در چند میزبان دیده شود.</p>${record.captures.map(capture=>{
    if(capture.error)return `<p class="detail-notice warning">${esc(names[capture.node_id]||capture.node_id)}: ضبط کامل نشد.</p>`;
    const prefix=`/api/cluster/runs/${encodeURIComponent(record.run_id)}/capture/${encodeURIComponent(capture.node_id)}`;
    return `<div class="capture-report"><strong>${esc(names[capture.node_id]||capture.node_id)}</strong><p class="small">${num(capture.packets)} بسته · ${num(capture.ip_bytes)} بایت IP</p><p class="field-help">حذف‌شده در کرنل: ${capture.kernel_dropped_packets==null?'نامعلوم':num(capture.kernel_dropped_packets)} · رکورد کنارگذاشته‌شده: ${num(capture.records_excluded)}</p>${capture.limit_reached?'<p class="detail-notice warning">سقف ضبط پر شده؛ خروجی تمام ترافیک آزمایش را پوشش نمی‌دهد.</p>':''}<div class="row-actions"><a class="button secondary" href="${prefix}/pcap" download>دریافت PCAP</a><a class="button secondary" href="${prefix}/csv" download>دریافت CSV</a></div><details class="advanced"><summary><span>جریان‌های ثبت‌شده</span><span>${num(capture.flows.length)}</span></summary><div class="table-wrap"><table><thead><tr><th>مبدأ</th><th>مقصد</th><th>بسته</th><th>بایت IP</th></tr></thead><tbody>${capture.flows.slice(0,40).map(flow=>`<tr><td class="mono">${esc(flow.source_ip)}:${esc(flow.source_port)}</td><td class="mono">${esc(flow.destination_ip)}:${esc(flow.destination_port)}</td><td>${num(flow.packets)}</td><td>${num(flow.ip_bytes)}</td></tr>`).join('')}</tbody></table></div>${capture.flows.length>40?'<p class="field-help">۴۰ جریان اول؛ همهٔ جریان‌ها در CSV هستند.</p>':''}</details><p class="hash-value">SHA256 ${esc(capture.pcap_sha256)}</p></div>`;
  }).join('')}`;
}
function showNetworkReport(record) {
  const names=Object.fromEntries(record.plan.nodes.map(node=>[node.node_id,node.name]));
  $('network-report-title').textContent=record.topology.name;
  $('network-details').innerHTML=`<div class="result-hero"><h3>${record.status==='succeeded'?'ارتباط بین سرورها موفق بود':'این اجرا کامل نشد'}</h3><p>${esc(record.run_id)}</p><div class="result-numbers"><div><strong>${num(record.observations.length)}</strong><small>نمونهٔ ثبت‌شده</small></div><div><strong>${num(record.observations.reduce((sum,item)=>sum+item.bytes_echoed,0))}</strong><small>بایت بازگشته</small></div></div></div>${record.failure_reason?`<p class="detail-notice warning">${esc(errors[record.failure_reason]||record.failure_reason)}</p>`:''}<p class="field-help">زمان رفت‌وبرگشت، زمان کامل تبادل پیام آزمایش است و با تأخیر خالص شبکه یکسان نیست.</p><div class="table-wrap"><table><thead><tr><th>کلاینت</th><th>لودبالانسر</th><th>backend</th><th>زمان کل</th><th>اتصال امن</th><th>تبادل پیام</th><th>نتیجه</th><th>بایت</th></tr></thead><tbody>${record.observations.map(sample=>`<tr><td>${esc(names[sample.client]||sample.client)}</td><td>${sample.via?esc(names[sample.via]||sample.via):'مستقیم'}</td><td>${esc(names[sample.backend]||sample.backend)}</td><td>${num(sample.rtt_ms)} ms</td><td>${sample.handshake_ms==null?'—':num(sample.handshake_ms)+' ms'}</td><td>${sample.request_ms==null?'—':num(sample.request_ms)+' ms'}</td><td>${sample.status==='failed'?esc(errors[sample.failure_reason]||sample.failure_reason):'موفق'}</td><td>${num(sample.bytes_echoed)}</td></tr>`).join('')}</tbody></table></div><p class="hash-value">${esc(record.workload_sha256)}</p><p class="field-help">پورت ${num(record.topology.port)} · ${esc(record.topology.protocol.toUpperCase())} · seed ${esc(record.topology.run_seed)}</p>`;
  $('network-report-dialog').showModal();
  $('network-details').insertAdjacentHTML('beforeend',baselineMarkup(record)+captureMarkup(record));
}
$('network-runs').addEventListener('click',async event=>{const button=event.target.closest('button[data-report],button[data-view]');if(!button)return;try{const record=await call(`/runs/${button.dataset.report||button.dataset.view}`);if(button.dataset.view){showNetworkReport(record);return;}const url=URL.createObjectURL(new Blob([JSON.stringify(record,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download=record.run_id+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){message(error.message);}});

function baselineMarkup(record) {
  if(!record.analysis)return '';
  const a=record.analysis;
  return `<h3 class="attempts-title cluster-section">خط مبنای اتصال امن</h3><p class="field-help">هر نمونه اتصال تازه دارد. زمان اتصال TLS شامل TCP نیز هست؛ زمان کل، بستن اتصال را هم شامل می‌شود. QUIC با HTTP3 و TLS با پیام قاب‌بندی‌شده اجرا می‌شود؛ این اعداد به‌تنهایی برتری یک پروتکل را ثابت نمی‌کنند.</p><p>مشاهده‌شده: ${num(a.observed.successful_samples)} موفق · ${num(a.observed.failed_samples)} ناموفق · ${num(a.observed.timeouts)} پایان مهلت · Retry در QUIC: ${a.observed.retry_packets==null?'—':num(a.observed.retry_packets)}</p><p>محاسبه‌شده: میانگین اتصال ${a.derived.mean_handshake_ms==null?'—':num(a.derived.mean_handshake_ms)+' ms'} · میانگین تبادل ${a.derived.mean_request_ms==null?'—':num(a.derived.mean_request_ms)+' ms'}</p><p class="field-help">فرضیه: مسیر و پیاده‌سازی می‌توانند روی زمان اثر بگذارند؛ علت هنوز اثبات نشده است.</p><p class="field-help">نامعلوم: تأخیر یک‌طرفه، نرخ افت شبکه و عملکرد زیر بار.</p>${record.topology.controlled_failure?'<p class="detail-notice warning">هدف این اجرا رد گواهی است؛ timeout یا خطای شبکه، رد گواهی را تأیید نمی‌کند.</p>':''}${record.qlogs?.length?`<div class="row-actions">${record.qlogs.map(q=>`<a class="button secondary" download href="/api/cluster/runs/${encodeURIComponent(record.run_id)}/qlog/${encodeURIComponent(q.trace_id)}">qlog نمونه ${num(q.sample_index+1)}</a>`).join('')}</div><p class="field-help">qlog محدود و پالایش‌شده؛ بدون IP، شناسهٔ اتصال، هدر HTTP یا کلید رمزنگاری.</p>`:''}`;
}

function syncProtocolControls() {
  const secure=['h3','tls'].includes($('topology-protocol').value);
  $('topology-lb').disabled=secure;
  if(secure)$('topology-lb').value='';
  $('topology-failure').disabled=!secure;
  if(!secure)$('topology-failure').checked=false;
}
$('topology-protocol').addEventListener('change',syncProtocolControls);

function updatePagination(prefix,page,pages,count) {
  $(prefix+'-pagination').hidden=pages<2;
  $(prefix+'-page-label').textContent=`صفحهٔ ${num(page+1)} از ${num(pages)} · ${num(count)} مورد`;
  $(prefix+'-prev').disabled=page===0;
  $(prefix+'-next').disabled=page>=pages-1;
}
for(const [id,event,kind] of [['path-search','input','paths'],['path-protocol-filter','change','paths'],['network-search','input','network'],['network-status-filter','change','network']]) {
  $(id).addEventListener(event,()=>{if(kind==='paths')pathsPage=0;else networkPage=0;if(current)renderCluster(current);});
}
for(const [id,kind,delta] of [['paths-prev','paths',-1],['paths-next','paths',1],['network-prev','network',-1],['network-next','network',1]]) {
  $(id).addEventListener('click',()=>{
    if(kind==='paths')pathsPage+=delta;else networkPage+=delta;
    if(current)renderCluster(current);
    $('view-'+(kind==='paths'?'paths':'network-results')).scrollIntoView({block:'start'});
  });
}
