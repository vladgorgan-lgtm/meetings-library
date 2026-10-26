/* Settings page. Static; reads L.settings and L.review (built into data/library.js).
 * Saving needs the local server (engine/serve.py). Opened straight from disk the page is
 * read-only. Every save writes small local files; none of them starts a sync run. */
const SRV = window.ML_SERVER || null;
const SET = L.settings || {}, REV = L.review || {items: [], general: [], open: 0, answered: 0};

async function mlApi(path, body){
  if (!SRV) throw new Error('Settings can only be saved while the local server is running (Start Meeting Library).');
  const r = await fetch(path, {method: 'POST', headers: {'Content-Type': 'application/json', 'X-ML-Token': SRV.token},
    body: JSON.stringify(body || {})});
  let j = {}; try { j = await r.json(); } catch(e){}
  if (!r.ok || j.ok === false && j.error) throw new Error(j.error || ('Server said ' + r.status));
  return j;
}
function keepPlace(id){ try { sessionStorage.setItem('ml.scroll', id || ''); } catch(e){} }
function toast(msg, bad){
  let t = document.getElementById('toast');
  if (!t){ t = document.createElement('div'); t.id = 'toast'; document.body.appendChild(t); }
  t.textContent = msg; t.className = 'show' + (bad ? ' bad' : '');
  clearTimeout(toast.h); toast.h = setTimeout(() => t.className = '', 4200);
}
async function act(btn, fn, okMsg, reload){
  if (btn) btn.disabled = true;
  try { const j = await fn(); toast(okMsg || 'Saved');
    if (reload){ keepPlace(reload === true ? '' : reload); setTimeout(() => location.reload(), 350); }
    return j; }
  catch(err){ toast(err.message, true); if (btn) btn.disabled = false; }
  finally { if (btn && !reload) btn.disabled = false; }
}

const dis = SRV ? '' : ' disabled';
const checked = v => v ? ' checked' : '';
const ago = s => s ? esc(String(s).replace('T', ' ')) : 'never';
const KIND = {names: 'Names', term: 'Terms', inconsistency: 'Inconsistencies', held: 'Held back',
  unclear: 'Unclear', empty: 'Empty notes'};
let revKind = 'all', revShow = 'open';

function secCap(){
  const c = SET.cap || {};
  return `<h2 class="sec">Cost cap</h2><div class="box sbox">
    <p class="hint first">The cap is an estimate of what scheduled runs cost. Over the cap, the daily sync pauses and a banner shows on the dashboard; a manual run can still override it.</p>
    <div class="frow">
      <label>Monthly cap (USD)<input type="number" step="0.5" min="0" id="cap-m" value="${esc(c.monthly_budget_usd)}"${dis}></label>
      <label>Warn at (USD / month)<input type="number" step="0.5" min="0" id="cap-w" value="${esc(c.warn_monthly_usd)}"${dis}></label>
      <label>Warn per run (USD)<input type="number" step="0.1" min="0" id="cap-r" value="${esc(c.warn_run_usd)}"${dis}></label>
    </div>${typeof capMeter === 'function' ? capMeter() : ''}
    <div class="fact"><button class="btn" id="save-cap"${dis}>Save cap</button></div></div>`;
}

function conn(id, title, what, on, status, extra){
  return `<div class="conn"><div class="ch"><b>${title}</b>
      <label class="tgl"><input type="checkbox" id="${id}"${checked(on)}${dis}> on</label></div>
    <div class="cw">${what}</div>${extra || ''}
    <div class="cs">Last fetch: ${ago(status)}</div></div>`;
}
function secConnectors(){
  const g = SET.gemini || {}, lf = SET.local_files || {}, gr = SET.granola || {}, cs = SET.connectors || {};
  return `<h2 class="sec">Connectors</h2><div class="box sbox">
    <p class="hint first">Where meetings come from. Turning one off only stops <b>future</b> fetching. Notes already in the library are never changed, hidden or deleted.</p>
    <div class="cgrid">
      ${conn('c-granola', 'Granola', 'Meeting notes and transcripts from Granola. The base of every note. Free plan keeps 30 days, so skipping many days loses history.', gr.enabled !== false, (cs.granola || {}).last_ok)}
      ${conn('c-gemini', 'Gmail: Notes by Gemini', 'Finds the "Notes by Gemini" emails and reads the linked doc. Merged into the matching Granola note, or kept as its own note when Granola missed the meeting.', g.enabled !== false, (cs.gmail || {}).last_ok,
        `<div class="frow sm"><label>Look back (days)<input type="number" min="1" max="30" id="g-days" value="${esc(g.lookback_days || 2)}"${dis}></label>
          <label>Backfill from<input type="date" id="g-from" value="${esc(g.backfill_from || '')}"${dis}></label></div>`)}
      ${conn('c-drive', 'Google Drive', 'Safety net behind Gmail: searches Drive for Gemini docs the emails missed, and opens links you add by hand.', g.drive_safety_net !== false, (cs.drive || {}).last_ok,
        `<div class="frow sm"><label>Skip docs over (KB)<input type="number" min="10" max="2000" id="g-kb" value="${esc(g.max_doc_kb || 200)}"${dis}></label></div>`)}
      ${conn('c-local', 'Local files', 'Documents and transcripts you add from this computer (txt, md, docx, pdf). Stored in inbox/ and picked up by the next run.', lf.enabled !== false, '',
        `<div class="frow sm"><label>Max file size (MB)<input type="number" min="1" max="25" id="l-mb" value="${esc(lf.max_mb || 5)}"${dis}></label></div>`)}
    </div>
    <div class="fact"><button class="btn" id="save-conn"${dis}>Save settings</button>
      <span class="hint inl">Saves to local files only. It does not start a run.</span></div>
    <div class="fact runrow"><button class="btn pri" id="run-now"${dis}>Run fetch now</button>
      <span class="hint inl">Asks Claude to run the sync now, with the settings above. Without a saved routine token it opens the Run now page instead.</span></div>
    <div id="run-msg" class="hint"></div></div>`;
}

function secAdd(){
  const q = SET.queue || [];
  return `<h2 class="sec">Add notes manually</h2><div class="box sbox">
    <p class="hint first">Queued here, then fetched, enhanced and merged by the next run (or by Run fetch now).</p>
    <div class="addgrid">
      <div><label>Google Doc or Drive link<input id="a-link" placeholder="https://docs.google.com/document/d/..."${dis}></label>
        <button class="btn" id="add-link"${dis}>Queue link</button></div>
      <div><label>Local file (txt, md, docx, pdf)<input type="file" id="a-file" accept=".txt,.md,.docx,.pdf,.vtt,.srt"${dis}></label>
        <button class="btn" id="add-file"${dis}>Queue file</button></div>
      <div class="wide2"><label>Paste a transcript or notes<textarea id="a-text" rows="4" placeholder="Paste text here. Add the meeting title and date on the first line if you know them."${dis}></textarea></label>
        <button class="btn" id="add-text"${dis}>Queue text</button></div>
    </div>
    <label class="tgl sm"><input type="checkbox" id="a-sens"${dis}> mark as sensitive</label>
    <div class="qlist">${q.length ? q.map(i => `<div class="qi"><span class="qk">${esc(i.kind)}</span>
      <span class="qv">${esc(i.name || i.value)}</span>${i.sensitive ? LOCK : ''}
      <span class="qs">${esc(i.status)}</span>
      ${i.status === 'pending' ? `<button class="x" data-qrm="${esc(i.id)}" title="Remove from queue"${dis}>&times;</button>` : ''}</div>`).join('')
      : '<div class="hint">Nothing queued.</div>'}</div></div>`;
}

function revItem(it){
  const res = it.resolution, status = it.status, mp = (res && res.map) || {};
  const sug = it.suggest || {};
  const rows = (it.variants || []).map(v => {
    const cur = mp[v] ? mp[v].canonical : (sug[v] || '');
    const np = mp[v] ? mp[v].not_person : (it.suggest_not_person && sug[v] ? true : false);
    return `<div class="vrow"><span class="vn">${esc(v)}</span><span class="va">means</span>
      <input class="vin" data-v="${esc(v)}" value="${esc(cur)}" placeholder="${it.kind === 'term' ? 'correct term' : 'full name'}"${dis}>
      <label class="tgl sm"><input type="checkbox" class="vnp" data-v="${esc(v)}"${checked(np)}${dis}> not a person</label></div>`;
  }).join('');
  const refs = (it.refs || []).map(r => `<a class="rl" href="#n/${encodeURIComponent(r.id)}">${r.sensitive ? LOCK + ' ' : ''}${esc(r.title)} <em>${esc(r.day)}</em></a>`).join('');
  return `<div class="ritem ${status}" id="rv-${esc(it.id)}" data-rid="${esc(it.id)}">
    <div class="rh"><span class="rk k-${esc(it.kind)}">${esc(KIND[it.kind] || it.kind)}</span>
      <b>${esc(it.title)}</b>${status !== 'open' ? `<span class="rdone">${status === 'ignored' ? 'ignored' : 'answered'}</span>` : ''}</div>
    ${it.detail && it.detail !== it.title ? `<div class="rd">${esc(it.detail)}</div>` : ''}
    <div class="rrefs">${refs}</div>
    ${rows ? `<div class="vrows">${rows}${(it.variants || []).length > 1 ? `<div class="setall"><label>Set all to
        <input class="vall" placeholder="one name for all"${dis}></label><button class="btn sm" data-setall="1"${dis}>Apply</button></div>` : ''}</div>` : ''}
    <label class="rlab">Your response (becomes a rule for the middle layer)
      <textarea class="rtx" rows="2" placeholder="${it.kind === 'names' ? 'e.g. Jon, John and Jonn are the same person: John Smith.' : 'Say what is right, or what to do with this.'}"${dis}>${esc((res && res.response) || '')}</textarea></label>
    <div class="ract"><button class="btn pri sm" data-rsave="1"${dis}>${status === 'open' ? 'Save answer' : 'Update answer'}</button>
      ${status === 'open' ? `<button class="btn sm" data-rign="1"${dis}>Not a problem, ignore</button>` : `<button class="btn sm" data-rreopen="1"${dis}>Reopen</button>`}</div>
  </div>`;
}
function secReview(){
  const items = REV.items || [];
  const kinds = [...new Set(items.map(i => i.kind))];
  const list = items.filter(i => (revKind === 'all' || i.kind === revKind) &&
    (revShow === 'all' || (revShow === 'open' ? i.status === 'open' : i.status !== 'open')));
  const cnt = k => items.filter(i => (k === 'all' || i.kind === k) && i.status === 'open').length;
  return `<h2 class="sec">Needs review <span class="cnt">${REV.open} open &middot; ${REV.answered} answered</span></h2>
    <div class="box sbox">
    <p class="hint first">Things the library could not settle on its own. Answer in your own words. Name mappings (and "not a person") apply at build time across every note; your text is saved as a rule the middle layer reads in later runs. Notes on disk are not edited.</p>
    <div class="rfil"><button class="chip${revKind === 'all' ? ' on' : ''}" data-rkind="all">All ${cnt('all')}</button>
      ${kinds.map(k => `<button class="chip${revKind === k ? ' on' : ''}" data-rkind="${esc(k)}">${esc(KIND[k] || k)} ${cnt(k)}</button>`).join('')}
      <span class="rsp"></span>
      ${['open', 'done', 'all'].map(s => `<button class="chip${revShow === s ? ' on' : ''}" data-rshow="${s}">${s === 'done' ? 'answered' : s}</button>`).join('')}</div>
    <div id="rlist">${list.length ? list.map(revItem).join('') : '<div class="none">Nothing here.</div>'}</div>
    <h3 class="sub">Your own rules</h3>
    <div class="gen">${(REV.general || []).map(g => `<div class="gi"><span>${esc(g.text)}</span>
      <button class="x" data-gdel="${esc(g.id)}" title="Delete rule"${dis}>&times;</button></div>`).join('') ||
      '<div class="hint">No general rules yet.</div>'}</div>
    <label class="rlab">Add a rule<textarea id="g-text" rows="2" placeholder="e.g. Meetings titled 'Sam / Me' are 1:1s. Action owners from Gemini are unreliable: prefer Granola."${dis}></textarea></label>
    <div class="ract"><button class="btn sm" id="g-add"${dis}>Add rule</button></div></div>`;
}

function secDisplay(){
  const o = SET.overrides || {add: [], remove: [], title_patterns: []};
  return `<h2 class="sec">Display</h2><div class="box sbox">
    <label class="rlab">Tags that never appear as Active topics (comma separated)
      <input id="d-tags" value="${esc((SET.topic_exclude || []).join(', '))}"${dis}></label>
    <p class="hint">Capture tags like gemini-only describe how a note was made, not what it is about, so they are kept out of topics.</p>
    <div class="fact"><button class="btn" id="save-disp"${dis}>Save</button></div>
    <div class="hint">Sensitive meetings: ${nSensitive} now. Always sensitive by title: ${(o.title_patterns || []).map(esc).join(', ') || 'none'}.
      Marked by hand: ${o.add.length}; unmarked by hand: ${o.remove.length}. Mark or unmark a meeting from its own page.</div></div>`;
}

function renderSettings(pane){
  pane.classList.remove('wide');
  pane.innerHTML = `<div class="topbar"><button class="bk" data-clear="1">&larr; Dashboard</button>
      <div class="bcrumb">settings</div><div class="nav"></div></div>
    <div class="mhead"><h1>Settings</h1>
      <div class="pillrow"><span class="gp ${SRV ? 'ok' : ''}">${SRV ? '&#9679; server running: changes are saved' : '&#9675; read-only: start the server to save changes'}</span></div>
      ${SRV ? '' : '<div class="hint">Double-click <code>Start Meeting Library.command</code> in the library folder, then use the page it opens.</div>'}
      <hr class="rule"></div>
    ${secConnectors()}${secAdd()}${secCap()}${secReview()}${secDisplay()}`;
  main.scrollTop = 0;
  let want = ''; try { want = sessionStorage.getItem('ml.scroll') || ''; sessionStorage.removeItem('ml.scroll'); } catch(e){}
  const el = want && document.getElementById(want);
  if (el) el.scrollIntoView({block: 'center'});
}

function collect(item){
  const map = {};
  item.querySelectorAll('.vin').forEach(i => { map[i.dataset.v] = {canonical: i.value, not_person: false}; });
  item.querySelectorAll('.vnp').forEach(c => { map[c.dataset.v] = {...(map[c.dataset.v] || {canonical: ''}), not_person: c.checked}; });
  return {id: item.dataset.rid, response: item.querySelector('.rtx').value, map};
}

document.addEventListener('click', e => {
  const t = e.target.closest('button, a'); if (!t || view !== 'settings') return;
  const val = id => document.getElementById(id);
  if (t.id === 'save-cap') return void act(t, () => mlApi('/api/settings', {cap: {
      monthly_budget_usd: val('cap-m').value, warn_monthly_usd: val('cap-w').value, warn_run_usd: val('cap-r').value}}), 'Cap saved', true);
  if (t.id === 'save-conn') return void act(t, () => mlApi('/api/settings', {
      granola: {enabled: val('c-granola').checked},
      gemini: {enabled: val('c-gemini').checked, drive_safety_net: val('c-drive').checked,
        lookback_days: val('g-days').value, backfill_from: val('g-from').value, max_doc_kb: val('g-kb').value},
      local_files: {enabled: val('c-local').checked, max_mb: val('l-mb').value}}), 'Connector settings saved (no run started)', true);
  if (t.id === 'save-disp') return void act(t, () => mlApi('/api/settings',
      {topic_exclude: val('d-tags').value.split(',')}), 'Saved', true);
  if (t.id === 'run-now') return void (async () => {
    t.disabled = true; const m = val('run-msg'); m.textContent = 'Asking Claude...';
    try { const j = await mlApi('/api/run', {});
      m.innerHTML = esc(j.message || '') + (j.fallback_url ? ` <a href="${esc(j.fallback_url)}" target="_blank" rel="noopener">Open the Run now page</a>` : '');
    } catch(err){ m.textContent = err.message; }
    t.disabled = false; })();
  if (t.id === 'add-link') return void act(t, () => mlApi('/api/queue/add', {kind: 'drive', value: val('a-link').value, sensitive: val('a-sens').checked}), 'Queued', true);
  if (t.id === 'add-text') return void act(t, () => mlApi('/api/queue/add', {kind: 'transcript', value: val('a-text').value, sensitive: val('a-sens').checked}), 'Queued', true);
  if (t.id === 'add-file') return void (async () => {
    const f = val('a-file').files[0]; if (!f) return toast('Choose a file first', true);
    const b64 = await new Promise(res => { const r = new FileReader(); r.onload = () => res(String(r.result).split(',')[1] || ''); r.readAsDataURL(f); });
    act(t, () => mlApi('/api/queue/add', {kind: 'file', name: f.name, content_b64: b64, sensitive: val('a-sens').checked}), 'Queued', true); })();
  if (t.dataset.qrm) return void act(t, () => mlApi('/api/queue/remove', {id: t.dataset.qrm}), 'Removed', true);
  if (t.id === 'g-add') return void act(t, () => mlApi('/api/general', {text: val('g-text').value}), 'Rule added', true);
  if (t.dataset.gdel) return void act(t, () => mlApi('/api/general', {delete: t.dataset.gdel}), 'Rule deleted', true);
  if (t.dataset.rkind){ revKind = t.dataset.rkind; return renderSettings(pane); }
  if (t.dataset.rshow){ revShow = t.dataset.rshow; return renderSettings(pane); }
  const item = t.closest('.ritem');
  if (item && t.dataset.setall){ const v = item.querySelector('.vall').value;
    item.querySelectorAll('.vin').forEach(i => i.value = v); return; }
  if (item && t.dataset.rsave) return void act(t, () => mlApi('/api/answer', {...collect(item), status: 'answered'}), 'Answer saved and applied', 'rv-' + item.dataset.rid);
  if (item && t.dataset.rign) return void act(t, () => mlApi('/api/answer', {...collect(item), status: 'ignored'}), 'Ignored', 'rv-' + item.dataset.rid);
  if (item && t.dataset.rreopen) return void act(t, () => mlApi('/api/answer', {id: item.dataset.rid, status: 'open'}), 'Reopened', 'rv-' + item.dataset.rid);
});

if (view === 'settings') render();   /* the first render ran before this file loaded */
