const $ = (id) => document.getElementById(id);
const fa = new Intl.NumberFormat('fa-IR');
const num = (value) => fa.format(value ?? 0);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const icon = (name) => `<svg class="icon" aria-hidden="true"><use href="/assets/icons.svg#${name}"></use></svg>`;
const labels = {succeeded:'موفق',failed:'ناموفق',cancelled:'متوقف‌شده',running:'در حال اجرا',cancelling:'در حال توقف',interrupted:'ناتمام',integrity_error:'نیاز به بررسی'};
const reasons = {timeout:'مهلت اجرا تمام شد.',loopback_error:'اتصال محلی کامل نشد.',payload_mismatch:'پاسخ با ورودی آزمایش یکسان نبود.',endpoint_io_error:'ارتباط با endpoint انجام نشد.',endpoint_transient_error:'ارتباط موقتاً قطع شد.',endpoint_protocol_error:'پاسخ endpoint معتبر نبود.',internal_error:'اجرا به خطای داخلی رسید.',cancelled:'اجرا به درخواست شما متوقف شد.',runner_busy:'یک آزمایش در حال اجراست. تا پایان آن صبر کنید.',replay_definition_mismatch:'این اجرا با نسخهٔ فعلی قابل بازاجرا نیست.',storage_or_io_error:'خواندن یا ذخیرهٔ داده انجام نشد.',invalid_input:'نام و مقدارهای کانفیگ را بررسی کنید.',authentication_required:'دوباره وارد پنل شوید.',invalid_credentials:'نام کاربری یا رمز عبور درست نیست.',login_rate_limited:'تعداد تلاش‌های ورود زیاد شده است. پنج دقیقه بعد امتحان کنید.',server_restarted:'سرویس هنگام اجرا دوباره راه‌اندازی شد.',artifact_integrity_failed:'فایل خروجی تغییر کرده و قابل تأیید نیست.'};
let state = null, detail = null, previousState = '', currentView = 'experiments';
let refreshVersion = 0, poller = null, toastTimer = null, lastActive = null;

function status(value) {
  const symbol = value === 'succeeded' ? 'check' : value === 'failed' || value === 'integrity_error' ? 'x' : 'square';
  return `<span class="status-label ${esc(value)}">${icon(symbol)}${esc(labels[value] || 'اجرا نشده')}</span>`;
}
function date(value) {
  if (!value) return 'ثبت نشده';
  return new Date(value).toLocaleString('fa-IR', {timeZone:'Asia/Tehran',month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'});
}
function toast(message) {
  $('toast').textContent = message; $('toast').hidden = false;
  clearTimeout(toastTimer); toastTimer = setTimeout(() => {$('toast').hidden = true;}, 4500);
}
async function api(path, body) {
  const options = {credentials:'same-origin', headers:{'X-NetSpectra-Client':'panel'}};
  if (body !== undefined) { options.method = 'POST'; options.headers['Content-Type'] = 'application/json'; options.body = JSON.stringify(body); }
  const response = await fetch(`/api${path}`, options);
  let data;
  try { data = await response.json(); } catch { data = {error:'internal_error'}; }
  if (!response.ok) {
    if (response.status === 401 && path !== '/login') showLogin();
    const error = new Error(reasons[data.error || data.detail] || 'این کار انجام نشد. دوباره تلاش کنید.');
    error.code = data.error || data.detail; throw error;
  }
  return data;
}
function showLogin() {
  clearInterval(poller); poller = null; state = detail = null; previousState = ''; lastActive = null;
  document.querySelectorAll('dialog[open]').forEach(dialog => dialog.close());
  $('app').hidden = true; $('login-screen').hidden = false;
}
async function showApp() {
  $('login-screen').hidden = true; $('app').hidden = false;
  setView(); await refresh();
  try { const health = await api('/health'); $('host-label').textContent = `${health.platform === 'Linux' ? 'میزبان لینوکس' : 'میزبان ویندوز'}`; $('source-label').textContent = health.source.git_sha ? health.source.git_sha.slice(0,8) : `v${health.version}`; } catch { /* state error already visible */ }
  clearInterval(poller); poller = setInterval(refresh, 2000);
}
async function refresh() {
  const version = ++refreshVersion;
  try {
    const next = await api('/state'); if (version !== refreshVersion || $('app').hidden) return;
    $('connection-error').hidden = true; $('connection-label').textContent = 'متصل به میزبان';
    $('experiments-loading').hidden = true;
    const serialized = JSON.stringify(next);
    if (serialized === previousState) return;
    if (lastActive && !next.active_job) {
      const job = next.jobs.find(item => item.job_id === lastActive);
      if (job) toast(job.status === 'succeeded' ? 'نتیجهٔ آزمایش ثبت شد.' : reasons[job.error] || `اجرا ${labels[job.status] || 'تمام'} شد.`);
    }
    lastActive = next.active_job?.job_id || null;
    previousState = serialized; state = next; render();
  } catch (error) {
    if ($('app').hidden) return;
    $('connection-error').hidden = false; $('connection-label').textContent = 'اتصال برقرار نیست';
    $('experiments-loading').hidden = true;
  }
}
function setView() {
  const value = location.hash.slice(1); currentView = ['experiments','runs','guide'].includes(value) ? value : 'experiments';
  for (const view of ['experiments','runs','guide']) {
    $(`view-${view}`).hidden = view !== currentView;
    const nav = document.querySelector(`[data-nav="${view}"]`);
    if (view === currentView) nav.setAttribute('aria-current','page'); else nav.removeAttribute('aria-current');
  }
  $('breadcrumb-current').textContent = {experiments:'آزمایش‌ها',runs:'تاریخچهٔ اجرا',guide:'روش کار'}[currentView];
}
function nameOf(identifier) { return state?.experiments.find(item => item.experiment_id === identifier)?.name || identifier; }
function render() {
  if (!state) return;
  $('nav-count').textContent = num(state.stats.experiments); $('config-count').textContent = num(state.stats.experiments);
  $('success-count').textContent = num(state.stats.succeeded); $('total-count').textContent = `از ${num(state.stats.runs)} اجرا`;
  const latest = state.runs[0];
  $('latest-activity').textContent = latest ? `${labels[latest.status] || 'ثبت‌شده'}، ${date(latest.started_at)}` : 'هنوز اجرایی ثبت نشده';
  $('history-strip').innerHTML = state.runs.slice(0,16).reverse().map(run => `<span class="history-tick ${esc(run.status)}" title="${esc(labels[run.status])} · ${esc(date(run.started_at))}"></span>`).join('');
  const active = state.active_job;
  $('active-job').hidden = !active;
  if (active) {
    $('active-title').textContent = active.status === 'cancelling' ? 'در حال توقف آزمایش…' : active.kind === 'replay' ? 'در حال بازاجرای ورودی قبلی…' : `در حال اجرا: ${nameOf(active.target)}`;
    $('active-description').textContent = 'نتیجه و تلاش‌ها بعد از پایان ثبت می‌شوند.';
    $('cancel-job').disabled = active.status === 'cancelling';
  }
  renderExperiments(); renderRuns();
  $('replay-run').disabled = !!active || !detail || detail.record.status === 'integrity_error';
}
function renderExperiments() {
  if (!state) return;
  const query = $('experiment-search').value.trim().toLocaleLowerCase('fa');
  const protocol = $('protocol-filter').value;
  const items = state.experiments.filter(item => (protocol === 'all' || item.protocol === protocol) && `${item.name} ${item.experiment_id}`.toLocaleLowerCase('fa').includes(query));
  $('experiments-empty').hidden = state.experiments.length > 0;
  $('experiments-table-wrap').hidden = !items.length;
  $('no-filter-results').hidden = !state.experiments.length || !!items.length;
  $('experiments-table').innerHTML = items.map(item => {
    const latest = state.runs.find(run => run.experiment_id === item.experiment_id);
    return `<tr><td><strong class="row-name">${esc(item.name)}</strong><span class="row-id">${esc(item.experiment_id)}</span></td><td><span class="protocol">${esc(item.protocol.toUpperCase())}</span></td><td><div class="cell-meta"><span>${num(item.repetitions)} تکرار</span><small>seed ${esc(item.run_seed)}</small></div></td><td>${latest ? status(latest.status) : '<span class="muted small">اجرا نشده</span>'}</td><td><div class="row-actions"><button class="icon-button" data-action="copy" data-id="${esc(item.experiment_id)}" aria-label="کپی و تنظیم ${esc(item.name)}" title="کپی و تنظیم">${icon('settings-2')}</button><button class="button secondary" data-action="run" data-id="${esc(item.experiment_id)}" ${state.active_job ? 'disabled title="یک اجرا در حال انجام است"' : ''}>${icon('play')}اجرا</button></div></td></tr>`;
  }).join('');
}
function renderRuns() {
  if (!state) return;
  const filter = $('status-filter').value;
  const items = state.runs.filter(run => filter === 'all' || run.status === filter);
  $('runs-empty').hidden = state.runs.length > 0; $('runs-table-wrap').hidden = !items.length;
  $('no-run-results').hidden = !state.runs.length || !!items.length;
  $('runs-table').innerHTML = items.map(run => {
    const bytes = run.metrics?.find(metric => metric.name === 'bytes_echoed')?.value;
    return `<tr><td><strong class="row-name">${esc(nameOf(run.experiment_id))}</strong><span class="row-id">${esc(run.run_id)}</span></td><td>${status(run.status)}</td><td>${run.sample_size == null ? 'ثبت نشده' : num(run.sample_size)}</td><td>${bytes == null ? 'ثبت نشده' : `${num(bytes)} بایت`}</td><td class="small">${esc(date(run.started_at))}</td><td><button class="button secondary" data-action="inspect" data-id="${esc(run.run_id)}">جزئیات${icon('chevron-left')}</button></td></tr>`;
  }).join('');
}
function openConfig(item = null) {
  $('config-form').reset(); $('config-error').hidden = true;
  $('config-title').textContent = item ? 'کانفیگ را کپی و تنظیم کنید' : 'یک آزمایش تازه بسازید';
  $('config-name').value = item ? `${item.name.slice(0, 58)} (کپی)` : '';
  $('config-protocol').value = item?.protocol || 'tcp';
  $('config-repetitions').value = item?.repetitions ?? 3; $('config-seed').value = item?.run_seed ?? 42;
  const execution = item?.execution || {timeout:20,attempt_timeout:5,retries:1,retry_delay:0.05};
  for (const [field,key] of [['config-timeout','timeout'],['config-attempt-timeout','attempt_timeout'],['config-retries','retries'],['config-delay','retry_delay']]) $(field).value = execution[key];
  $('run-after-save').disabled = !!state?.active_job; $('run-after-save').checked = !state?.active_job;
  updateSaveLabel(); $('config-dialog').showModal(); $('config-name').focus();
}
function updateSaveLabel() { $('config-submit').innerHTML = $('run-after-save').checked ? `ذخیره و اجرا${icon('play')}` : 'ذخیره کانفیگ'; }
async function launch(identifier) {
  const item = state.experiments.find(config => config.experiment_id === identifier);
  try { await api(`/experiments/${encodeURIComponent(identifier)}/run`, item.execution); toast('آزمایش شروع شد.'); await refresh(); } catch (error) { toast(error.message); }
}
async function inspect(identifier) {
  detail = null; $('run-detail').innerHTML = '<p class="muted">در حال دریافت نتیجه…</p>';
  $('replay-run').disabled = true; $('download-run').disabled = true;
  $('run-dialog').showModal();
  try {
    detail = await api(`/runs/${encodeURIComponent(identifier)}`);
    const {record,summary,experiment} = detail;
    const bytes = record.metrics.find(metric => metric.name === 'bytes_echoed')?.value;
    const title = record.status === 'succeeded' ? 'آزمایش با موفقیت تمام شد' : record.status === 'cancelled' ? 'آزمایش متوقف شد' : 'این اجرا کامل نشد';
    const attempts = summary.attempts || [];
    $('run-title').textContent = nameOf(record.experiment_id);
    $('run-detail').innerHTML = `<div class="result-hero">${status(record.status)}<h3>${esc(title)}</h3><p>${esc(record.run_id)}</p><div class="result-numbers"><div><strong>${num(record.sample_size)}</strong><small>نمونهٔ کامل</small></div><div><strong>${bytes == null ? 'ثبت نشده' : num(bytes)}</strong><small>بایت بازگشته</small></div><div><strong class="mono">${esc(experiment.protocol.toUpperCase())}</strong><small>پروتکل</small></div></div></div>${record.failure_reason ? `<p class="detail-notice warning">${esc(reasons[record.failure_reason] || 'این اجرا به خطا رسید.')}</p>` : ''}${summary.source?.dirty ? '<p class="detail-notice warning">این اجرا با تغییرات ذخیره‌نشدهٔ کد انجام شده است.</p>' : ''}<dl class="detail-grid"><div><dt>شروع اجرا</dt><dd>${esc(date(record.started_at))}</dd></div><div><dt>پایان اجرا</dt><dd>${esc(date(record.finished_at))}</dd></div><div><dt>seed</dt><dd class="mono">${esc(record.run_seed)}</dd></div><div><dt>کد منبع</dt><dd class="mono" title="${esc(record.git_sha)}">${esc(record.git_sha.slice(0,12))}</dd></div><div><dt>میزبان</dt><dd>${esc(record.platform.os)} · ${esc(record.platform.architecture)}</dd></div><div><dt>مهلت کل</dt><dd>${num(summary.execution?.timeout)} ثانیه</dd></div></dl><h3 class="attempts-title">تلاش‌های اجرا <span class="count">${num(attempts.length)}</span></h3>${attempts.map(event => `<div class="attempt-row"><span>نمونهٔ ${num(event.sample_index + 1)} · تلاش ${num(event.attempt)}</span><span>${status(event.status)}${event.reason ? ` <span class="muted">${esc(reasons[event.reason] || 'خطای اجرا')}</span>` : ''}</span></div>`).join('') || '<p class="muted small">تاریخچهٔ تلاش برای این اجرا ثبت نشده است.</p>'}${summary.replay_of ? '<p class="detail-notice">این نتیجه، بازاجرای ورودی یک Run قبلی است.</p>' : ''}<p class="hash-value">${esc(summary.workload_sha256 || record.scenario_sha256)}</p><p class="field-help">بازاجرا ورودی را یکسان نگه می‌دارد؛ زمان و نتیجه ممکن است متفاوت باشند.</p>`;
    $('download-run').disabled = false; $('replay-run').disabled = !!state?.active_job;
  } catch (error) { $('run-detail').textContent = error.message; }
}

$('login-form').addEventListener('submit', async event => {
  event.preventDefault(); $('login-error').hidden = true; $('login-submit').disabled = true;
  try { await api('/login',{username:$('username').value.trim(),password:$('password').value}); $('login-form').reset(); await showApp(); }
  catch (error) { $('login-error').textContent = error.message; $('login-error').hidden = false; $('password').focus(); }
  finally { $('login-submit').disabled = false; }
});
$('toggle-password').addEventListener('click', () => { const showing = $('password').type === 'password'; $('password').type = showing ? 'text' : 'password'; $('toggle-password').setAttribute('aria-label',showing ? 'پنهان‌کردن رمز' : 'نمایش رمز'); });
$('logout').addEventListener('click', async () => { try { await api('/logout',{}); showLogin(); } catch (error) { toast(error.message); } });
$('new-experiment').addEventListener('click', () => openConfig()); $('empty-new').addEventListener('click', () => openConfig());
$('run-after-save').addEventListener('change',updateSaveLabel);
$('config-form').addEventListener('submit', async event => {
  event.preventDefault(); $('config-error').hidden = true;
  const name = $('config-name').value.trim();
  if (!name) { $('config-name').setCustomValidity('نام آزمایش را بنویسید.'); $('config-name').reportValidity(); return; }
  $('config-submit').disabled = true;
  const body = {name,protocol:$('config-protocol').value,run_seed:Number($('config-seed').value),repetitions:Number($('config-repetitions').value),execution:{timeout:Number($('config-timeout').value),attempt_timeout:Number($('config-attempt-timeout').value),retries:Number($('config-retries').value),retry_delay:Number($('config-delay').value)}};
  try {
    const created = await api('/experiments',body); const runAfter = $('run-after-save').checked;
    $('config-dialog').close(); await refresh();
    if (runAfter) await launch(created.experiment_id); else toast('کانفیگ ذخیره شد.');
  } catch (error) { $('config-error').textContent = error.message; $('config-error').hidden = false; }
  finally { $('config-submit').disabled = false; }
});
$('config-name').addEventListener('input',() => $('config-name').setCustomValidity(''));
document.querySelectorAll('.close-dialog').forEach(button => button.addEventListener('click',() => button.closest('dialog').close()));
$('experiments-table').addEventListener('click', event => { const button = event.target.closest('button[data-action]'); if (!button) return; const item = state.experiments.find(config => config.experiment_id === button.dataset.id); if (button.dataset.action === 'copy') openConfig(item); else launch(item.experiment_id); });
$('runs-table').addEventListener('click', event => { const button = event.target.closest('button[data-action]'); if (button) inspect(button.dataset.id); });
$('experiment-search').addEventListener('input', renderExperiments); $('protocol-filter').addEventListener('change',renderExperiments); $('status-filter').addEventListener('change',renderRuns);
$('refresh-runs').addEventListener('click',refresh); $('retry-connection').addEventListener('click',refresh);
$('cancel-job').addEventListener('click',async () => { if (!state?.active_job) return; $('cancel-job').disabled = true; try { await api(`/jobs/${state.active_job.job_id}/cancel`,{}); await refresh(); } catch(error) { toast(error.message); $('cancel-job').disabled = false; } });
$('replay-run').addEventListener('click',async () => { if (!detail) return; $('replay-run').disabled = true; try { await api(`/runs/${detail.record.run_id}/replay`,{}); $('run-dialog').close(); toast('بازاجرای ورودی قبلی شروع شد.'); await refresh(); } catch(error) { toast(error.message); $('replay-run').disabled = false; } });
$('download-run').addEventListener('click',() => { if (!detail) return; const url = URL.createObjectURL(new Blob([JSON.stringify(detail,null,2)],{type:'application/json'})); const link=document.createElement('a'); link.href=url; link.download=`${detail.record.run_id}.json`; link.click(); setTimeout(() => URL.revokeObjectURL(url),1000); });
window.addEventListener('hashchange',setView);
document.addEventListener('visibilitychange',() => { if (!document.hidden && !$('app').hidden) refresh(); });
api('/session').then(result => result.authenticated ? showApp() : showLogin()).catch(() => { showLogin(); $('login-error').textContent='اتصال به پنل برقرار نشد. صفحه را دوباره باز کنید.'; $('login-error').hidden=false; });
