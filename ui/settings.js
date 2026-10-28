/* Settings page. Static; reads L.settings and L.review (built into data/library.js).
 * Saving needs the local server (engine/serve.py). Opened straight from disk the page is
 * read-only. Every save writes small local files; none of them starts a sync run.
 *
 * Routes (all under view === 'settings'):  #settings                the boxes, two per row
 *                                          #settings/review[/tab]   the full review page
 *                                          tabs: conflicts | names | approved */
const SRV = window.ML_SERVER || null;
const SET = L.settings || {}, REV = L.review || {items: [], general: [], open: 0, answered: 0};
const RV = SET.review || {weights: {}, must_threshold: 50, defaults: {weights: {}, must_threshold: 50}, labels: {}};
const SENSI = SET.sensitive || {definition: '', default: '', keywords: [], title_patterns: []};

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
const KINDLABEL = {names: 'Name', term: 'Term', inconsistency: 'Notes disagree', held: 'Held back',
  unclear: 'Unclear', empty: 'Empty note'};
const isName = it => it.kind === 'names' || it.kind === 'term';
const prio = it => (it.priority || {level: 'parked', score: 0, why: []});
const byPrio = (a, b) => ((prio(b).level === 'must') - (prio(a).level === 'must')) || (prio(b).score - prio(a).score);
/* surfaced = names plus the high-scoring conflicts; the rest is parked (Granola's version stands) */
const openItems = () => (REV.items || []).filter(i => i.status === 'open' && prio(i).level !== 'parked').sort(byPrio);
const parkedItems = () => (REV.items || []).filter(i => i.status === 'open' && prio(i).level === 'parked').sort(byPrio);
const doneItems = () => (REV.items || []).filter(i => i.status !== 'open');
const short = (t, n) => { t = String(t || ''); return t.length > n ? t.slice(0, n - 1).trimEnd() + '...' : t; };
let topSkip = 0, openRule = null, aprFilter = 'all', newRuleOpen = false;
const WLABEL = {granola_prior: 'Only Gemini differs (points off, Granola stands)', money: 'Numbers or money in question', commitment: 'A decision or commitment',
  people: 'About people (1:1, sensitive)', external: 'Client or external meeting',
  recent: 'Recent (last 3 days)', reach: 'Touches several meetings'};
const SCOPE_OPT = [['all', 'Everything'], ['person', 'A person'], ['type', 'A meeting type'], ['meeting', 'One meeting']];
const WEIGHT_OPT = [[1, '1 · light'], [2, '2'], [3, '3 · normal'], [4, '4'], [5, '5 · strong']];
function subRoute(){ const h = decodeURIComponent(location.hash.slice(1)).split('/'); return {page: h[1] || '', tab: h[2] || ''}; }
function rerender(){ const y = main.scrollTop; renderSettings(pane); main.scrollTop = y; }

/* ---------------------------------------------------------------- cost cap, connectors, manual add */
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

/* ---------------------------------------------------------------- review cards */
function priBadge(it){
  const p = prio(it);
  if (p.level === 'name') return '';
  return `<span class="pr ${p.level}" title="Score ${p.score} of 100. Counted: ${esc((p.why || []).join(', ') || 'only the base score for this kind')}.">${p.level === 'must' ? 'Must resolve' : 'Parked'}<i>${p.score}</i></span>`;
}
function nameRows(it){
  const res = it.resolution, mp = (res && res.map) || {}, sug = it.suggest || {};
  const rows = (it.variants || []).map(v => {
    const cur = mp[v] ? mp[v].canonical : (sug[v] || '');
    const np = mp[v] ? mp[v].not_person : (it.suggest_not_person && sug[v] ? true : false);
    return `<div class="vrow"><span class="vn">${esc(v)}</span><span class="va">means</span>
      <input class="vin" data-v="${esc(v)}" value="${esc(cur)}" placeholder="${it.kind === 'term' ? 'correct term' : 'full name'}"${dis}>
      <label class="tgl sm"><input type="checkbox" class="vnp" data-v="${esc(v)}"${checked(np)}${dis}> not a person</label></div>`;
  }).join('');
  return rows ? `<div class="vrows">${rows}${(it.variants || []).length > 1 ? `<div class="setall"><label>Set all to
      <input class="vall" placeholder="one name for all"${dis}></label><button class="btn sm" data-setall="1"${dis}>Apply</button></div>` : ''}</div>` : '';
}
/* One card per check. The question and the buttons depend on the kind, so what you are
   approving is always one plain decision:
     names      type the right name (or "not a person")
     held back  yes, add it to the decisions  /  no, keep it out
     the rest   say what is right  /  fine as it is */
function card(it){
  const res = it.resolution, open = it.status === 'open', text = (res && res.response) || '';
  const refs = (it.refs || []).map(r => `<a class="rl" href="#n/${encodeURIComponent(r.id)}">${r.sensitive ? LOCK + ' ' : ''}${esc(r.title)} <em>${esc(r.day)}</em></a>`).join('');
  const p = prio(it);
  const q = isName(it) ? 'Who or what is this?' : it.kind === 'held' ? 'Should this be added to the decisions?'
    : it.kind === 'empty' ? 'What was this meeting about?' : 'What is right?';
  let body = '', btns = '';
  if (isName(it)){
    body = nameRows(it) + `<label class="rlab">Note for the middle layer (optional)<textarea class="rtx" rows="2"${dis}>${esc(text)}</textarea></label>`;
    btns = open ? `<button class="btn pri sm" data-act="save"${dis}>Save answer</button><button class="btn sm" data-act="ignore"${dis}>Not a problem</button>`
      : `<button class="btn pri sm" data-act="save"${dis}>Update answer</button><button class="btn sm" data-act="reopen"${dis}>Reopen</button>`;
  } else if (it.kind === 'held'){
    btns = open ? `<button class="btn pri sm" data-act="yes"${dis}>Yes, add it</button><button class="btn sm" data-act="no"${dis}>No, keep it out</button>`
      : `<span class="hint inl">${it.status === 'answered' ? 'You chose to add it.' : 'You chose to keep it out.'}</span><button class="btn sm" data-act="reopen"${dis}>Reopen</button>`;
  } else {
    body = `<label class="rlab">${open ? '' : esc(q) + ' '}Your answer (becomes a rule for the middle layer)<textarea class="rtx" rows="2" placeholder="${it.kind === 'empty' ? 'A few words on what it covered.' : 'Say what is right, or what to do with this.'}"${dis}>${esc(text)}</textarea></label>`;
    btns = open ? `<button class="btn pri sm" data-act="save"${dis}>Save answer</button><button class="btn sm" data-act="fine"${dis}>${it.kind === 'empty' ? 'Not needed' : 'Fine as it is'}</button>`
      : `<button class="btn pri sm" data-act="save"${dis}>Update answer</button><button class="btn sm" data-act="reopen"${dis}>Reopen</button>`;
  }
  return `<div class="ritem ${it.status}" id="rv-${esc(it.id)}" data-rid="${esc(it.id)}" data-kind="${esc(it.kind)}">
    <div class="rh"><span class="rk k-${esc(it.kind)}">${esc(KINDLABEL[it.kind] || it.kind)}</span><b>${esc(it.title)}</b>${open ? priBadge(it) : `<span class="rdone">${it.status === 'ignored' ? 'ignored' : 'answered'}</span>`}</div>
    ${it.detail && it.detail !== it.title ? `<div class="rd">${esc(it.detail)}</div>` : ''}
    ${open && p.why && p.why.length ? `<div class="why">${p.why.map(w => `<span>${esc(w)}</span>`).join('')}</div>` : ''}
    <div class="rrefs">${refs}</div>
    ${open && (isName(it) || it.kind === 'held') ? `<div class="rq">${esc(q)}</div>` : ''}
    ${body}<div class="ract">${btns}</div></div>`;
}

/* ---------------------------------------------------------------- own rules: scope and weight */
function scopeChip(g){
  const sc = g.scope || 'all';
  const lab = (SCOPE_OPT.find(o => o[0] === sc) || [0, sc])[1].replace(/^An? /, '').toLowerCase();
  return `<span class="sc">${sc === 'all' ? 'everything' : esc(lab) + ': ' + esc(g.scope_value || '')}</span><span class="sc">weight ${esc(g.weight || 3)}</span>`;
}
function listFor(scope){
  if (scope === 'person') return [...new Set((DASH.people || []).map(p => p.name))];
  if (scope === 'type') return [...new Set(DATA.map(d => d.type).filter(Boolean))];
  if (scope === 'meeting') return DATA.map(d => d.title);
  return [];
}
function ruleEditor(g){
  const sc = (g && g.scope) || 'all', gid = g ? g.id : '';
  return `<div class="ed rule-ed" data-gid="${esc(gid)}">
    <label class="rlab">${g ? 'Edit rule' : 'New rule'}<textarea class="g-text" rows="2" placeholder="e.g. Action owners from Gemini are unreliable: prefer Granola."${dis}>${esc(g ? g.text : '')}</textarea></label>
    <div class="rsc">
      <label>Applies to<select class="g-scope"${dis}>${SCOPE_OPT.map(o => `<option value="${o[0]}"${o[0] === sc ? ' selected' : ''}>${o[1]}</option>`).join('')}</select></label>
      <label class="g-valw"${sc === 'all' ? ' hidden' : ''}>Which one<input class="g-val" list="dl-${esc(gid || 'new')}" value="${esc((g && g.scope_value) || '')}" placeholder="type to search"${dis}>
        <datalist id="dl-${esc(gid || 'new')}">${listFor(sc).map(x => `<option value="${esc(x)}">`).join('')}</datalist></label>
      <label>Weight<select class="g-wt"${dis}>${WEIGHT_OPT.map(o => `<option value="${o[0]}"${o[0] === ((g && g.weight) || 3) ? ' selected' : ''}>${o[1]}</option>`).join('')}</select></label>
    </div>
    <div class="hint">A more specific rule beats a general one. When two are equally specific, the higher weight wins. Keep broad rules light.</div>
    <div class="ract"><button class="btn pri sm" data-gsave="${esc(gid)}"${dis}>${g ? 'Save rule' : 'Add rule'}</button>
      ${g ? `<button class="btn sm" data-gdel="${esc(gid)}"${dis}>Delete</button>` : ''}
      <button class="btn sm" data-closeed="1">Cancel</button></div></div>`;
}
function approvedRows(){
  const rows = [];
  (REV.general || []).forEach(g => rows.push({key: g.id, type: 'rule', ts: g.ts || '', g}));
  doneItems().forEach(i => rows.push({key: i.id, type: isName(i) ? 'names' : 'conflict', ts: (i.resolution || {}).ts || '', it: i}));
  return rows.sort((a, b) => String(b.ts).localeCompare(String(a.ts)));
}
function summary(r){
  if (r.type === 'rule') return short(r.g.text, 90);
  const it = r.it, mp = (it.resolution && it.resolution.map) || {}, ks = Object.keys(mp);
  if (isName(it) && ks.length){
    const k = ks[0], m = mp[k];
    return `${k} ${m.not_person ? 'is not a person' : '→ ' + m.canonical}${ks.length > 1 ? ` (+${ks.length - 1})` : ''}`;
  }
  return short(it.title, 90);
}
function approvedList(rows){
  return rows.map(r => {
    const on = openRule === r.key;
    const lab = r.type === 'rule' ? 'Rule' : r.type === 'names' ? 'Name' : (KINDLABEL[r.it.kind] || 'Check');
    return `<button class="arow" data-open="${esc(r.key)}" aria-expanded="${on}"><span class="rk">${esc(lab)}</span>
      <span class="as">${esc(summary(r))}</span>${r.type === 'rule' ? scopeChip(r.g) : `<span class="astat">${r.it.status === 'ignored' ? 'ignored' : 'approved'}</span>`}</button>` +
      (on ? (r.type === 'rule' ? ruleEditor(r.g) : `<div class="ed">${card(r.it)}</div>`) : '');
  }).join('');
}

/* ---------------------------------------------------------------- boxes on the settings page */
function secReviewTop(){
  const open = openItems(), parked = parkedItems().length;
  const it = open.length ? open[topSkip % open.length] : null;
  return `<h2 class="sec">Needs review <span class="cnt">${open.length} open &middot; ${parked} parked</span></h2>
    <div class="box sbox"><p class="hint first">Only what really needs you, the most important first. Granola is the base: checks where only Gemini differs are parked and Granola's version stands. Answer here, skip, or open the full list.</p>
    ${it ? card(it) : '<div class="none">Nothing needs review right now.</div>'}
    <div class="fact ract">${open.length > 1 ? '<button class="btn sm" data-skip="1">Skip, show next</button>' : ''}
      <button class="btn sm" data-hash="#settings/review">${open.length > 1 ? 'All ' + open.length + ' items' : 'Full list'} &rarr;</button></div></div>`;
}
function secApproved(){
  const rows = approvedRows(), shown = rows.slice(0, 6);
  if (openRule && !shown.some(r => r.key === openRule)){ const o = rows.find(r => r.key === openRule); if (o) shown.unshift(o); }
  return `<h2 class="sec">Approved rules <span class="cnt">${rows.length} in total</span></h2>
    <div class="box sbox"><p class="hint first">Click a rule to change it. Name answers apply at build time; your own rules are read by the middle layer.</p>
    <div class="alist">${approvedList(shown) || '<div class="hint">Nothing approved yet.</div>'}</div>
    <div class="fact ract"><button class="btn sm" data-hash="#settings/review/approved">All approved rules &rarr;</button>
      <button class="btn sm" data-newrule="1">+ Add a rule</button></div>${newRuleOpen ? ruleEditor(null) : ''}</div>`;
}
function secSensitive(){
  const s = SENSI, o = SET.overrides || {add: [], remove: []};
  return `<h2 class="sec">Sensitive content</h2><div class="box sbox">
    <p class="hint first">Describe in your own words what counts as sensitive. The sync reads this when it tags new notes. Sensitive meetings are marked with a crossed-out eye, and one switch in the dashboard header hides them everywhere.</p>
    <label class="rlab">What counts as sensitive<textarea id="s-def" rows="5"${dis}>${esc(s.definition)}</textarea></label>
    <div class="hint">${s.is_default ? 'This is the built-in default.' : 'You have changed it.'} <button class="lnk" id="s-reset"${dis}>Reset to default</button></div>
    <label class="rlab">Also mark a meeting when its title, tags or text contains (comma separated)<input id="s-kw" value="${esc((s.keywords || []).join(', '))}" placeholder="e.g. layoff, termination, salary"${dis}></label>
    <label class="rlab">Always sensitive when the title contains (comma separated)<input id="s-tp" value="${esc((s.title_patterns || []).join(', '))}"${dis}></label>
    <div class="hint">${nSensitive} sensitive now. Marked by hand: ${o.add.length}; unmarked by hand: ${o.remove.length}. Mark or unmark a meeting from its own page.</div>
    <div class="fact"><button class="btn" id="save-sens"${dis}>Save</button>
      <span class="hint inl">Keywords and title words apply to every note at once. The definition guides notes fetched from the next run; tags already on notes are not rewritten.</span></div></div>`;
}
function secWeights(){
  const must = openItems().filter(i => prio(i).level === 'must').length, parked = parkedItems().length;
  const rows = Object.keys(WLABEL).map(k => {
    const v = RV.weights[k] != null ? RV.weights[k] : 0;
    return `<div class="wrow"><span>${esc(WLABEL[k])}</span><input type="range" min="0" max="50" step="5" data-w="${k}" value="${esc(v)}"${dis}><b>${esc(v)}</b></div>`;
  }).join('');
  return `<h2 class="sec">Review priority <span class="cnt">${must} must resolve &middot; ${parked} parked</span></h2><div class="box sbox">
    <p class="hint first">Every check gets a score from 0 to 100: a small base for its kind plus the points of each factor below that applies. Only checks at or above the line are shown to you (<b>must resolve</b>); the rest are <b>parked</b> and Granola's version stands. When only Gemini's side differs, points are taken off.</p>
    ${rows}
    <div class="wrow th"><span>Show me checks from a score of</span><input type="range" min="10" max="100" step="5" id="w-th" value="${esc(RV.must_threshold)}"${dis}><b>${esc(RV.must_threshold)}</b></div>
    <div class="fact"><button class="btn" id="save-w"${dis}>Save weights</button> <button class="btn" id="reset-w"${dis}>Back to defaults</button>
      <span class="hint inl">Scores are worked out when the library is rebuilt. No model calls, no cost.</span></div></div>`;
}
function secDisplay(){
  return `<h2 class="sec">Display</h2><div class="box sbox">
    <label class="rlab">Tags that never appear as Active topics (comma separated)
      <input id="d-tags" value="${esc((SET.topic_exclude || []).join(', '))}"${dis}></label>
    <p class="hint">Capture tags like gemini-only describe how a note was made, not what it is about, so they are kept out of topics.</p>
    <div class="fact"><button class="btn" id="save-disp"${dis}>Save</button></div></div>`;
}

/* ---------------------------------------------------------------- the full review page */
function renderReview(pane, tab){
  tab = ['names', 'conflicts', 'approved'].includes(tab) ? tab : 'conflicts';
  const open = openItems(), names = open.filter(isName), must = open.filter(i => !isName(i));
  const nice = parkedItems(), conf = must;
  const T = (k, label, n) => `<a href="#settings/review/${k}" class="${tab === k ? 'on' : ''}">${label} ${n}</a>`;
  let body = '';
  if (tab === 'names'){
    body = `<p class="hint first">Spellings the library could not settle. These are quick: type the right name, or tick "not a person".</p>` +
      (names.map(card).join('') || '<div class="none">No names to check.</div>');
  } else if (tab === 'conflicts'){
    body = `<p class="hint first">Only the high-scoring conflicts are listed. Granola is the base of every note and Gemini an add-on, so where only Gemini's side differs the Granola version stands and the item is parked below. The score and its reasons show on each card; tune them under Review priority in settings.</p>
      <div class="grp">Must resolve <small>${must.length}</small></div>${must.map(card).join('') || '<div class="none">Nothing needs you here.</div>'}
      <details class="nice"><summary class="grp">Parked, Granola's version stands <small>${nice.length} &middot; click to show</small>
        ${nice.length ? `<button class="btn sm" data-bulkfine="1"${dis}>Accept all ${nice.length}</button>` : ''}</summary>
        ${nice.map(card).join('') || '<div class="none">Nothing parked.</div>'}</details>`;
  } else {
    const rows = approvedRows().filter(r => aprFilter === 'all' || (aprFilter === 'rules' ? r.type === 'rule' : aprFilter === 'names' ? r.type === 'names' : r.type === 'conflict'));
    const F = (k, l) => `<button class="chip${aprFilter === k ? ' on' : ''}" data-afil="${k}">${l}</button>`;
    body = `<p class="hint first">Everything you have approved or ignored, and your own rules. Click one to change it.</p>
      <div class="rfil">${F('all', 'All')}${F('names', 'Names')}${F('conflicts', 'Conflicts')}${F('rules', 'My rules')}<span class="rsp"></span>
        <button class="btn sm" data-newrule="1">+ Add a rule</button></div>
      ${newRuleOpen ? ruleEditor(null) : ''}<div class="alist">${approvedList(rows) || '<div class="none">Nothing here.</div>'}</div>`;
  }
  pane.innerHTML = `<div class="topbar"><button class="bk" data-hash="#settings">&larr; Settings</button><div class="bcrumb">needs review</div><div class="nav"></div></div>
    <div class="mhead"><h1>Needs review</h1>
      <div class="rtabs">${T('conflicts', 'Conflicts', conf.length)}${T('names', 'Names', names.length)}${T('approved', 'Approved', approvedRows().length)}</div><hr class="rule"></div>
    <div class="box sbox" style="margin-top:18px">${body}</div>`;
}

function renderSettings(pane){
  pane.classList.remove('wide');
  const sr = subRoute();
  pane.classList.toggle('sread', sr.page === 'review');
  if (sr.page === 'review'){ renderReview(pane, sr.tab); main.scrollTop = 0; return; }
  pane.innerHTML = `<div class="topbar"><button class="bk" data-clear="1">&larr; Dashboard</button>
      <div class="bcrumb">settings</div><div class="nav"></div></div>
    <div class="mhead"><h1>Settings</h1>
      <div class="pillrow"><span class="gp ${SRV ? 'ok' : ''}">${SRV ? '&#9679; server running: changes are saved' : '&#9675; read-only: start the server to save changes'}</span></div>
      ${SRV ? '' : '<div class="hint">Double-click <code>Start Meeting Library.command</code> in the library folder, then use the page it opens.</div>'}
      <hr class="rule"></div>
    <div class="sgrid">
      <section>${secConnectors()}</section><section>${secAdd()}</section>
      <section>${secSensitive()}</section><section>${secCap()}</section>
      <section>${secReviewTop()}</section><section>${secApproved()}</section>
      <section>${secWeights()}</section><section>${secDisplay()}</section>
    </div>`;
  main.scrollTop = 0;
  let want = ''; try { want = sessionStorage.getItem('ml.scroll') || ''; sessionStorage.removeItem('ml.scroll'); } catch(e){}
  const el = want && document.getElementById(want);
  if (el) el.scrollIntoView({block: 'center'});
}

function collect(item){
  const map = {};
  item.querySelectorAll('.vin').forEach(i => { map[i.dataset.v] = {canonical: i.value, not_person: false}; });
  item.querySelectorAll('.vnp').forEach(c => { map[c.dataset.v] = {...(map[c.dataset.v] || {canonical: ''}), not_person: c.checked}; });
  const rt = item.querySelector('.rtx');
  return {id: item.dataset.rid, response: rt ? rt.value : '', map};
}
const listVal = id => document.getElementById(id).value.split(',').map(x => x.trim()).filter(Boolean);
function ruleBody(ed){
  return {text: ed.querySelector('.g-text').value, scope: ed.querySelector('.g-scope').value,
    scope_value: ed.querySelector('.g-val').value, weight: ed.querySelector('.g-wt').value};
}

document.addEventListener('input', e => {
  const t = e.target;
  if (view !== 'settings') return;
  if ((t.dataset && t.dataset.w) || t.id === 'w-th') t.parentElement.querySelector('b').textContent = t.value;
});
document.addEventListener('change', e => {
  const t = e.target;
  if (view !== 'settings' || !t.classList || !t.classList.contains('g-scope')) return;
  const ed = t.closest('.rule-ed'), vw = ed.querySelector('.g-valw'), dl = ed.querySelector('datalist');
  vw.hidden = t.value === 'all'; ed.querySelector('.g-val').value = '';
  dl.innerHTML = listFor(t.value).map(x => `<option value="${esc(x)}">`).join('');
});

document.addEventListener('click', e => {
  const t = e.target.closest('button, a'); if (!t || view !== 'settings') return;
  const val = id => document.getElementById(id);
  if (t.dataset.hash) return void (location.hash = t.dataset.hash);
  if (t.id === 'save-cap') return void act(t, () => mlApi('/api/settings', {cap: {
      monthly_budget_usd: val('cap-m').value, warn_monthly_usd: val('cap-w').value, warn_run_usd: val('cap-r').value}}), 'Cap saved', true);
  if (t.id === 'save-conn') return void act(t, () => mlApi('/api/settings', {
      granola: {enabled: val('c-granola').checked},
      gemini: {enabled: val('c-gemini').checked, drive_safety_net: val('c-drive').checked,
        lookback_days: val('g-days').value, backfill_from: val('g-from').value, max_doc_kb: val('g-kb').value},
      local_files: {enabled: val('c-local').checked, max_mb: val('l-mb').value}}), 'Connector settings saved (no run started)', true);
  if (t.id === 'save-disp') return void act(t, () => mlApi('/api/settings',
      {topic_exclude: val('d-tags').value.split(',')}), 'Saved', true);
  if (t.id === 'save-sens') return void act(t, () => mlApi('/api/settings', {sensitive: {
      definition: val('s-def').value, keywords: listVal('s-kw'), title_patterns: listVal('s-tp')}}), 'Sensitive settings saved', true);
  if (t.id === 's-reset'){ val('s-def').value = SENSI.default || ''; return; }
  if (t.id === 'save-w') return void act(t, () => {
      const weights = {}; document.querySelectorAll('input[data-w]').forEach(i => weights[i.dataset.w] = i.value);
      return mlApi('/api/settings', {review: {weights, must_threshold: val('w-th').value}}); }, 'Priority weights saved', true);
  if (t.id === 'reset-w'){
    const d = (RV.defaults || {}).weights || {};
    document.querySelectorAll('input[data-w]').forEach(i => { if (d[i.dataset.w] != null) i.value = d[i.dataset.w]; i.parentElement.querySelector('b').textContent = i.value; });
    val('w-th').value = (RV.defaults || {}).must_threshold || 50; val('w-th').parentElement.querySelector('b').textContent = val('w-th').value; return; }
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
  /* review: skip, filters, bulk */
  if (t.dataset.skip){ topSkip++; return rerender(); }
  if (t.dataset.afil){ aprFilter = t.dataset.afil; return rerender(); }
  if (t.dataset.bulkfine){
    const ids = parkedItems().map(i => i.id);
    return void act(t, () => mlApi('/api/bulk', {ids, status: 'ignored'}), ids.length + ' accepted, Granola stands', true); }
  /* rules */
  if (t.dataset.open){ openRule = openRule === t.dataset.open ? null : t.dataset.open; newRuleOpen = false; return rerender(); }
  if (t.dataset.newrule){ newRuleOpen = !newRuleOpen; openRule = null; return rerender(); }
  if (t.dataset.closeed){ openRule = null; newRuleOpen = false; return rerender(); }
  const ed = t.closest('.rule-ed');
  if (ed && t.dataset.gsave != null){
    const gid = t.dataset.gsave, body = ruleBody(ed);
    return void act(t, () => mlApi('/api/general', gid ? {update: gid, ...body} : body), gid ? 'Rule saved' : 'Rule added', true); }
  if (ed && t.dataset.gdel) return void act(t, () => mlApi('/api/general', {delete: t.dataset.gdel}), 'Rule deleted', true);
  /* cards */
  const item = t.closest('.ritem');
  if (item && t.dataset.setall){
    const v = item.querySelector('.vall').value;
    item.querySelectorAll('.vin').forEach(i => i.value = v); return; }
  if (item && t.dataset.act){
    const a = t.dataset.act, id = item.dataset.rid, keep = 'rv-' + id, c = collect(item), nm = isName({kind: item.dataset.kind});
    if (a === 'save'){
      const named = Object.values(c.map).some(m => m.canonical || m.not_person);
      if (!nm && !c.response.trim()) return toast('Write what is right, or use the "as it is" button.', true);
      if (nm && !named && !c.response.trim()) return toast('Type the right name for at least one spelling.', true);
      return void act(t, () => mlApi('/api/answer', {...c, status: 'answered'}), 'Answer saved and applied', keep); }
    if (a === 'yes') return void act(t, () => mlApi('/api/answer', {id, response: 'Include this in the decisions.', map: {}, status: 'answered'}), 'Will be added to the decisions', true);
    if (a === 'no' || a === 'fine' || a === 'ignore') return void act(t, () => mlApi('/api/answer', {...c, status: 'ignored'}), 'Done', true);
    if (a === 'reopen') return void act(t, () => mlApi('/api/answer', {id, status: 'open'}), 'Reopened', true);
  }
});

if (view === 'settings') render();   /* the first render ran before this file loaded */
