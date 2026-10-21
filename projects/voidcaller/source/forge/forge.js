'use strict';
// THE FORGE. Ask a local model for content, check it against the game's own
// validator, look at it, keep what is good, and write it where the game reads.

let SETUP = null;
let KIND = 'monster';
let BATCH = [];          // {record, errors, warnings, keep, open, id}
let SEQ = 0;
let RUNNING = false;
let STOP = false;
let PICKED = { types: [], habitats: [], tones: [] };   // multi-select chips
let CONTENT_KIND = 'monster';
let CONTENT = [];
let CONTENT_SELECTED = null;   // {source, index, protected} or {draft:true}

const $ = s => document.querySelector(s);
const el = (tag, cls, html) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html !== undefined) n.innerHTML = html;
  return n;
};
const esc = s => String(s == null ? '' : s)
  .replace(/[&<>]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));

async function api(path, body) {
  const opts = body
    ? { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) }
    : {};
  const r = await fetch(path, opts);
  const text = await r.text();
  try { return JSON.parse(text); } catch { return { error: text.slice(0, 400) }; }
}

// ------------------------------------------------------------------ the rig
async function boot() {
  SETUP = await api('/api/setup');
  if (SETUP.ollama && SETUP.ollama.endpoint) $('#endpoint').value = SETUP.ollama.endpoint;
  drawKinds();
  drawOllama(SETUP.ollama);
  drawLibrary();
  drawForm();
  drawBatch();
  await loadContent();
}

function drawOllama(o) {
  const state = $('#ollamastate');
  const list = $('#modellist');
  list.innerHTML = '';
  if (o && o.ok && o.models.length) {
    o.models.forEach(m => {
      const opt = el('option');
      opt.value = m.name;
      opt.label = m.size ? `${m.size} GB` : '';
      list.appendChild(opt);
    });
    state.textContent = `${o.models.length} model${o.models.length === 1 ? '' : 's'}`;
    state.className = 'state on';
    if (!$('#model').value) $('#model').value = o.models[0].name;
    $('#model').placeholder = 'pick one, or type any name';
  } else {
    state.textContent = 'ollama not answering';
    state.className = 'state off';
    $('#model').placeholder = 'type a model name anyway';
  }
}

function drawKinds() {
  const box = $('#kinds');
  box.innerHTML = '';
  SETUP.kinds.forEach(k => {
    const b = el('button', k.key === KIND ? 'on' : '', k.label);
    b.onclick = () => { KIND = k.key; drawKinds(); drawForm(); drawBatch(); };
    box.appendChild(b);
  });
  const kind = SETUP.kinds.find(k => k.key === KIND) || {};
  $('#kindnote').textContent = kind.note || '';
  $('#dest').textContent = kind.note || '';
}

// ------------------------------------------------------------------- form
function field(name, label, opts = {}) {
  const wrap = el('label', opts.wide ? 'wide' : '');
  wrap.append(document.createTextNode(label));
  let input;
  if (opts.choices) {
    input = el('select');
    (opts.choices).forEach(c => {
      const o = el('option', '', esc(c));
      o.value = c;
      input.appendChild(o);
    });
    if (opts.value) input.value = opts.value;
  } else if (opts.area) {
    input = el('textarea');
    input.style.minHeight = '60px';
    if (opts.value) input.value = opts.value;
    if (opts.placeholder) input.placeholder = opts.placeholder;
  } else {
    input = el('input');
    if (opts.type) input.type = opts.type;
    if (opts.value !== undefined) input.value = opts.value;
    if (opts.placeholder) input.placeholder = opts.placeholder;
    if (opts.list) input.setAttribute('list', opts.list);
  }
  input.id = 'f_' + name;
  wrap.appendChild(input);
  return wrap;
}

function drawForm() {
  const f = $('#form');
  f.innerHTML = '';
  const lib = SETUP.library;
  if (KIND === 'monster') {
    f.append(
      field('levels', 'levels', { value: '10-20',
        placeholder: '14  ·  10-20  ·  5,12,30' }),
      field('spread', 'spread', { choices: ['even', 'random'] }),
      field('rarity', 'rarity', { choices: ['Common', 'Uncommon', 'Rare', 'Epic'], value: 'Common' }),
      field('family', 'family', { list: 'familylist', placeholder: '(any)' }),
      field('role', 'role', { choices: ['Mix', 'Tank', 'DPS', 'Support'], value: 'Mix' }),
      field('brief', 'anything else', { area: true, wide: true,
        placeholder: 'things that live in the flooded stacks and eat paper' }),
    );
    f.appendChild(chips('types', 'types — pick any, or none for all', lib.types));
    f.appendChild(chips('habitats', 'habitats — these become the regions',
      lib.habitats.map(h => h.name)));
    f.appendChild(chips('tones', 'tone', lib.tones));
    datalist('familylist', lib.families.map(h => h.name));
  } else if (KIND === 'item') {
    f.append(
      field('level', 'for around level', { type: 'number', value: 12 }),
      field('brief', 'what it does', { area: true, wide: true,
        placeholder: 'a salve that trades health for speed' }),
    );
  } else if (KIND === 'quest') {
    f.append(
      field('quest_kind', 'kind', { choices: ['fetch', 'slay', 'hunt'] }),
      field('level', 'for around level', { type: 'number', value: 12 }),
      field('area_id', 'operation area id', { list: 'arealist',
        placeholder: lib.areas && lib.areas.length ? 'choose an existing area' : 'create a Void Area first' }),
      field('brief', 'anything else', { area: true, wide: true,
        placeholder: 'someone who has lost a brother and will not say so' }),
    );
    datalist('arealist', (lib.areas || []).map(area => area.id));
  } else if (KIND === 'recipe') {
    f.append(
      field('station', 'station', { choices: ['craft_shop', 'farm_kitchen', 'soul_forge'] }),
      field('level', 'for around level', { type: 'number', value: 12 }),
      field('brief', 'what it should make', { area: true, wide: true,
        placeholder: 'a venom-tipped spear made from marsh materials' }),
    );
  } else if (KIND === 'move') {
    f.append(
      field('level', 'for around level', { type: 'number', value: 10 }),
      field('category', 'category', { choices: ['physical', 'magical', 'support'] }),
      field('type', 'combat Type', { choices: ['none'].concat(lib.types || []) }),
      field('role', 'combat role', { placeholder: 'melee, defence buff, heal…' }),
      field('brief', 'move idea', { area: true, wide: true,
        placeholder: 'a quick defensive stance that raises speed for two turns' }),
    );
  } else {
    f.append(
      field('level', 'chapter number', { type: 'number', value: 5 }),
      field('brief', 'what happens', { area: true, wide: true }),
    );
  }
}

function chips(key, label, values) {
  const wrap = el('div', 'wide');
  wrap.appendChild(el('div', '', label)).style.cssText =
    'font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint)';
  const box = el('div', 'multi');
  values.forEach(v => {
    const b = el('button', PICKED[key].includes(v) ? 'on' : '', esc(v));
    b.onclick = ev => {
      ev.preventDefault();
      const at = PICKED[key].indexOf(v);
      if (at >= 0) PICKED[key].splice(at, 1); else PICKED[key].push(v);
      b.className = PICKED[key].includes(v) ? 'on' : '';
      showPlan();
    };
    box.appendChild(b);
  });
  wrap.appendChild(box);
  wrap.style.gridColumn = '1/-1';
  return wrap;
}

function datalist(id, values) {
  let dl = document.getElementById(id);
  if (!dl) { dl = el('datalist'); dl.id = id; document.body.appendChild(dl); }
  dl.innerHTML = '';
  values.forEach(v => { const o = el('option'); o.value = v; dl.appendChild(o); });
}

function ask() {
  const out = {};
  document.querySelectorAll('[id^=f_]').forEach(i => {
    const v = String(i.value || '').trim();
    if (v && v !== '(any)') out[i.id.slice(2)] = i.type === 'number' ? Number(v) : v;
  });
  if (KIND === 'monster') {
    if (PICKED.types.length) out.types = PICKED.types;
    if (PICKED.habitats.length) out.habitats = PICKED.habitats;
    if (PICKED.tones.length) out.tones = PICKED.tones;
    out.count = Math.max(1, Math.min(200, Number($('#count').value) || 1));
  }
  return out;
}

// what the batch will actually ask for, before spending a minute a monster on it
async function showPlan(force) {
  if (KIND !== 'monster') { $('#planpreview').innerHTML = ''; return; }
  if (!force && !$('#planpreview').innerHTML) return;
  const res = await api('/api/plan', { kind: KIND, ask: ask() });
  const plan = res.plan || [];
  const tally = k => {
    const c = {};
    plan.forEach(p => { c[p[k]] = (c[p[k]] || 0) + 1; });
    return Object.entries(c).sort((a, b) => b[1] - a[1])
      .map(([v, n]) => `${esc(v)} ×${n}`).join(', ');
  };
  const lv = plan.map(p => p.level);
  $('#planpreview').innerHTML =
    `<div class="sum">${plan.length} monsters · levels ${Math.min(...lv)}–${Math.max(...lv)}
       <br>${tally('type')}<br>${tally('habitat')}</div>` +
    '<table>' + plan.map(p => `<tr>
       <td>${esc(p.id)}</td><td class="lv">L${p.level}</td>
       <td class="ty">${esc(p.type)}</td><td>${esc(p.habitat)}</td>
       <td>${esc(p.tone)}</td></tr>`).join('') + '</table>';
}

// ------------------------------------------------------------------ library
function drawLibrary() {
  const lib = SETUP.library;
  const box = $('#library');
  box.innerHTML = '';
  box.appendChild(el('div', 'stat', `<span>species loaded</span><b>${lib.species}</b>`));
  box.appendChild(el('div', 'stat', `<span>Void Areas</span><b>${(lib.areas || []).length}</b>`));
  const authoredTypes = Object.values(lib.type_counts || {}).filter(n => n > 0).length;
  box.appendChild(el('div', 'stat',
    `<span>Types represented</span><b>${authoredTypes}/${(lib.types || []).length}</b>`));
  box.appendChild(el('div', 'stat',
    `<span>moves in creatures</span><b>${lib.move_count || 0}</b>`));

  const h = el('div', '', '<h5 class="phead" style="margin-top:14px">VOID AREAS</h5>');
  const chips = el('div', 'chips');
  (lib.areas || []).slice(0, 24).forEach(x => {
    const c = el('span', 'chip', `${esc(x.name)}<b>${esc(x.id)}</b>`);
    c.onclick = () => { const f = $('#f_area_id'); if (f) { f.value = x.id; f.focus(); } };
    chips.appendChild(c);
  });
  h.appendChild(chips);
  if (!(lib.areas || []).length) h.appendChild(el('p', 'warnline',
    'No Void Areas yet. Create one, assign a monster, then make an operation.'));
  box.appendChild(h);

  if (lib.thin_habitats.length) {
    box.appendChild(el('p', 'warnline',
      `${lib.thin_habitats.length} regions have fewer than three species in them, which makes them
       thin to walk through: ${esc(lib.thin_habitats.slice(0, 6).join(', '))}. Generating into those
       names is the fastest way to make the map feel full.`));
  }
  if (authoredTypes < (lib.types || []).length) {
    const missing = Object.entries(lib.type_counts || {}).filter(([, n]) => !n).map(([name]) => name);
    box.appendChild(el('p', 'warnline',
      `No authored creature uses: ${esc(missing.join(', ') || 'none')}. Fill those Types when you want a broader Atlas.`));
  }
}

// -------------------------------------------------------------------- forge
async function forgeBatch() {
  if (RUNNING) return;
  const model = $('#model').value.trim();
  if (!model) { note('type or pick a model first.'); return; }
  const brief = ask();
  const n = Math.max(1, Math.min(200, Number($('#count').value) || 1));

  // one concrete request per monster, spread across everything you picked
  let plan = [{}];
  if (KIND === 'monster') {
    const res = await api('/api/plan', { kind: KIND, ask: brief });
    plan = res.plan || [];
  } else {
    plan = Array.from({ length: n }, () => brief);
  }

  RUNNING = true; STOP = false;
  $('#forge').disabled = true;
  $('#stop').hidden = false;
  const started = Date.now();
  let made = 0, dropped = 0;
  const seenNames = BATCH.map(b => String(b.record.name || '').toLowerCase());
  const seenPrints = BATCH.map(b => b.print).filter(Boolean);

  for (let i = 0; i < plan.length; i++) {
    if (STOP) { note(`stopped after ${i} of ${plan.length}`); break; }
    const per = made ? (Date.now() - started) / made : 0;
    const left = per ? ` · about ${Math.round(per * (plan.length - i) / 1000)}s left` : '';
    note(`forging ${i + 1} of ${plan.length}${left}`);
    const res = await api('/api/generate', {
      kind: KIND, model, endpoint: $('#endpoint').value.trim(),
      temperature: Number($('#temp').value) || 0.9,
      strict: $('#strict').checked,
      ask: plan[i], seen_names: seenNames, seen_prints: seenPrints,
    });
    if (res.error && !res.record) {
      note(res.error);
      if (String(res.error).includes('could not reach')) break;
      continue;
    }
    made++;
    if (res.duplicate && $('#skipdupes').checked) {
      dropped++;
      note(`forging ${i + 1} of ${plan.length} — skipped a repeat (${res.duplicate})`);
      continue;
    }
    if (res.record && res.record.name) seenNames.push(String(res.record.name).toLowerCase());
    if (res.fingerprint) seenPrints.push(res.fingerprint);
    add(res);
    drawBatch();
  }
  const kept = BATCH.filter(b => b.keep && !b.errors.length).length;
  note(`done — ${kept} worth keeping of ${BATCH.length}`
    + (dropped ? `, ${dropped} repeats thrown away` : ''));
  RUNNING = false; STOP = false;
  $('#forge').disabled = false;
  $('#stop').hidden = true;
  drawBatch();
}

function note(text) { $('#progress').textContent = text; }

function add(res) {
  BATCH.push({
    id: ++SEQ, record: res.record, errors: res.errors || [],
    warnings: res.warnings || [], keep: !(res.errors || []).length, open: false,
    took: res.took || 0, duplicate: res.duplicate || '', print: res.fingerprint || null,
  });
}

// -------------------------------------------------------------------- batch
function title(rec) {
  if (!rec || typeof rec !== 'object') return '(not an object)';
  if (KIND === 'item') {
    const k = Object.keys(rec).filter(x => !x.startsWith('_'))[0];
    return k || '(unnamed item)';
  }
  return rec.name || rec.title || rec.id || '(unnamed)';
}

function subtitle(rec) {
  if (!rec || typeof rec !== 'object') return '';
  if (KIND === 'monster') {
    const t = (rec.types || {});
    const moves = (rec.base_moves || []).length + (rec.moves || []).length;
    return `L${rec.level ?? '?'} · ${esc(rec.rarity || '?')} · ${esc(t.primary || '?')}${rec.family ? ' · ' + esc(rec.family) : ''}
      · ${esc((rec.habitat || [])[0] || 'unmapped')} · ${moves} move${moves === 1 ? '' : 's'}`;
  }
  if (KIND === 'move') return `${esc(rec.category || '?')} · ${esc(rec.type || 'neutral')} · PW ${rec.power ?? 0} · PP ${rec.pp ?? 0}`;
  if (KIND === 'quest') return `${esc(rec.kind || '?')} · ${esc(rec.target || '?')} ×${rec.qty ?? '?'} · ${rec.gold ?? 0}g`;
  if (KIND === 'recipe') return `${esc(rec.station || '?')} · ${esc((rec.ingredients || []).length)} ingredients · ${esc((rec.result || {}).item || '?')}`;
  if (KIND === 'story') return `chapter ${rec.id ?? '?'} · ${(rec.scenes || []).length} scenes`;
  const k = Object.keys(rec).filter(x => !x.startsWith('_'))[0];
  const body = rec[k] || {};
  return `${esc(body.kind || 'item')} · ${body.buy ? body.buy + 'g to buy' : 'not for sale'}`;
}

function drawBatch() {
  const box = $('#batch');
  box.innerHTML = '';
  const kept = BATCH.filter(b => b.keep && !b.errors.length).length;
  $('#batchcount').textContent = BATCH.length ? `${kept} kept of ${BATCH.length}` : '';
  $('#save').disabled = !kept;
  if (!BATCH.length) {
    box.appendChild(el('div', 'panel',
      `<p class="note">Nothing forged yet. Pick a model, say what you want, and press FORGE —
       or drop a file onto this page to check one you already have.</p>`));
    return;
  }
  BATCH.forEach(entry => box.appendChild(card(entry)));
}

function card(entry) {
  const grade = entry.errors.length ? 'broken' : entry.duplicate ? 'dupe'
    : entry.warnings.length ? 'warned' : 'clean';
  const c = el('div', `card ${grade}${entry.open ? ' open' : ''}${entry.keep ? '' : ' dropped'}`);
  const badge = entry.errors.length ? `${entry.errors.length} will not load`
    : entry.duplicate ? esc(entry.duplicate)
    : entry.warnings.length ? `${entry.warnings.length} ignored` : 'clean';
  const top = el('div', 'top', `
    <span class="nm">${esc(title(entry.record))}</span>
    <span class="meta">${subtitle(entry.record)}</span>
    <span class="badge ${grade}">${badge}</span>`);
  top.onclick = ev => {
    if (ev.target.tagName === 'INPUT' || ev.target.tagName === 'BUTTON') return;
    entry.open = !entry.open; drawBatch();
  };
  c.appendChild(top);

  const body = el('div', 'body');
  if (entry.errors.length) {
    body.appendChild(el('h5', '', 'THESE STOP IT LOADING'));
    body.appendChild(el('ul', '', entry.errors.map(e => `<li class="err">${esc(e)}</li>`).join('')));
  }
  if (entry.warnings.length) {
    body.appendChild(el('h5', '', 'THESE LOAD, BUT ARE IGNORED'));
    body.appendChild(el('ul', '', entry.warnings.map(e => `<li>${esc(e)}</li>`).join('')));
  }
  body.appendChild(el('h5', '', 'THE RECORD — EDIT IT AND RE-CHECK'));
  const ta = el('textarea');
  ta.value = JSON.stringify(entry.record, null, 2);
  ta.spellcheck = false;
  body.appendChild(ta);

  const row = el('div', 'row');
  const recheck = el('button', 'ghost', 're-check');
  recheck.onclick = async () => {
    let rec;
    try { rec = JSON.parse(ta.value); }
    catch (err) { note('that is not valid JSON: ' + err.message); return; }
    const res = await api('/api/validate', { kind: KIND, records: [rec] });
    const r = (res.results || [])[0] || {};
    entry.record = rec;
    entry.errors = r.errors || [];
    entry.warnings = r.warnings || [];
    entry.open = true;
    drawBatch();
  };
  const keep = el('label', 'keep');
  const box = el('input');
  box.type = 'checkbox';
  box.checked = entry.keep;
  box.onchange = () => { entry.keep = box.checked; drawBatch(); };
  keep.append(box, document.createTextNode('keep this one'));
  const drop = el('button', 'ghost', 'throw away');
  drop.onclick = () => { BATCH = BATCH.filter(b => b.id !== entry.id); drawBatch(); };
  row.append(recheck, keep, drop);
  if (entry.took) row.appendChild(el('span', 'note', `${entry.took}s`));
  body.appendChild(row);
  c.appendChild(body);
  return c;
}

// --------------------------------------------------------------------- save
async function saveBatch() {
  const records = BATCH.filter(b => b.keep && !b.errors.length).map(b => b.record);
  if (!records.length) return;
  const res = await api('/api/save', {
    kind: KIND, records, filename: $('#filename').value.trim() || 'forged',
  });
  if (res.error) { note('could not save: ' + res.error); return; }
  const result = KIND === 'monster'
    ? `the game now sees ${res.species} species`
    : `ready in the Forge's ${KIND} collection`;
  note(`wrote ${res.written} into ${res.path} — ${result}`);
  BATCH = BATCH.filter(b => !(b.keep && !b.errors.length));
  SETUP = await api('/api/setup?endpoint=' + encodeURIComponent($('#endpoint').value));
  drawLibrary();
  drawBatch();
}

// --------------------------------------------------------------- by hand
async function checkHand(text) {
  const raw = (text !== undefined ? text : $('#hand').value).trim();
  if (!raw) return;
  let records = [];
  try {
    if (raw.includes('\n') && raw.trimStart().startsWith('{') && raw.includes('}\n')) {
      // might be jsonl; try line by line first and fall back to one object
      const lines = raw.split('\n').map(l => l.trim()).filter(Boolean);
      try { records = lines.map(l => JSON.parse(l)); }
      catch { records = [JSON.parse(raw)]; }
    } else {
      records = [JSON.parse(raw)];
    }
  } catch (err) { note('that is not valid JSON: ' + err.message); return; }
  const res = await api('/api/validate', { kind: KIND, records });
  (res.results || []).forEach(r => add({ record: r.record, errors: r.errors, warnings: r.warnings }));
  note(`checked ${(res.results || []).length}`);
  drawBatch();
}

// ------------------------------------------------------------ content desk
// A small local editor for the two files a player will normally author.  It
// intentionally calls the same validator as generated content, so a typo
// cannot quietly make a monster or contract vanish from the game at startup.
function contentTitle(row) {
  const record = row.record || {};
  return row.name || record.name || record.title || record.label || record.id || 'Untitled';
}

function contentStatus(text, kind = '') {
  const box = $('#contentstatus');
  box.textContent = text || '';
  box.className = 'manager-status' + (kind ? ' ' + kind : '');
}

function contentRecord() {
  const raw = $('#contentjson').value.trim();
  if (!raw) { contentStatus('Paste or choose a JSON record first.', 'error'); return null; }
  try { return JSON.parse(raw); }
  catch (err) { contentStatus('That is not valid JSON: ' + err.message, 'error'); return null; }
}

function readContentQuietly() {
  try { return JSON.parse($('#contentjson').value || '{}'); }
  catch { return null; }
}

function writeContent(record) {
  $('#contentjson').value = JSON.stringify(record, null, 2);
}

function changeContent(change) {
  const record = readContentQuietly();
  if (!record) {
    contentStatus('Fix the advanced JSON before editing the guided fields.', 'error');
    return false;
  }
  change(record);
  writeContent(record);
  return true;
}

function valueAt(record, path, fallback = '') {
  return path.split('.').reduce((value, key) =>
    value && value[key] !== undefined ? value[key] : undefined, record) ?? fallback;
}

function setAt(record, path, value) {
  const keys = path.split('.');
  let here = record;
  keys.slice(0, -1).forEach(key => {
    if (!here[key] || typeof here[key] !== 'object') here[key] = {};
    here = here[key];
  });
  here[keys[keys.length - 1]] = value;
}

function formHeading(box, title, note = '') {
  const wrap = el('div', 'form-heading');
  wrap.appendChild(el('h3', '', title));
  if (note) wrap.appendChild(el('p', '', note));
  box.appendChild(wrap);
}

function guidedField(box, record, options) {
  const wrap = el('label', `guided-field${options.wide ? ' wide' : ''}`);
  const label = el('span', '', options.label);
  wrap.appendChild(label);
  let input;
  const current = valueAt(record, options.path, options.value ?? '');
  if (options.choices) {
    input = el('select');
    options.choices.forEach(choice => {
      const row = typeof choice === 'object' ? choice : { value: choice, label: choice };
      const option = el('option', '', esc(row.label));
      option.value = row.value;
      input.appendChild(option);
    });
    input.value = String(current);
  } else if (options.multiline) {
    input = el('textarea');
    input.rows = options.rows || 3;
    input.value = String(current || '');
  } else {
    input = el('input');
    input.type = options.type || 'text';
    input.value = current == null ? '' : String(current);
  }
  if (options.placeholder) input.placeholder = options.placeholder;
  input.oninput = () => {
    const value = options.type === 'number' ? Number(input.value || 0) : input.value;
    changeContent(row => setAt(row, options.path, value));
  };
  input.onchange = () => {
    if (changeContent(row => setAt(row, options.path, options.type === 'number' ? Number(input.value || 0) : input.value))) {
      if (options.onchange) options.onchange();
    }
  };
  wrap.appendChild(input);
  if (options.note) wrap.appendChild(el('small', '', options.note));
  box.appendChild(wrap);
  return input;
}

function moveId(name = 'new_move') {
  return String(name).toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, '') || 'new_move';
}

function newMove(index = 1) {
  return { id: `move_${String(index).padStart(2, '0')}`, name: 'New Move', category: 'physical', type: null,
    power: 40, accuracy: 95, pp: 25, target: 'single', priority: 0, crit: 0,
    effects: [], tags: ['melee'], description: '' };
}

function generatedMove(record) {
  // A visible deterministic draft, never a replacement for authorship.
  const primary = String(record?.types?.primary || 'Primal');
  const names = {
    Fire: ['Cinder Rush', 'Flare Jab', 'Ash Kick'], Water: ['Tidal Bash', 'Current Cut', 'Undertow'],
    Electric: ['Static Lunge', 'Arc Snap', 'Charge Bite'], Nature: ['Vine Lash', 'Thorn Volley', 'Root Snare'],
    Earth: ['Stone Knuckle', 'Fault Step', 'Gravel Shot'], Wind: ['Gale Cut', 'Wingbeat', 'Draft Lunge'],
    Light: ['Lumen Strike', 'Dawn Pulse', 'Halo Cut'], Dark: ['Night Rend', 'Gloom Claw', 'Shade Bite'],
    Cosmic: ['Orbit Pulse', 'Star Needle', 'Comet Palm'], Spirit: ['Pale Touch', 'Wisp Lash', 'Soul Pin'],
    Primal: ['Feral Rush', 'Pounce', 'Rending Bite'], Arcane: ['Rune Bolt', 'Sigil Break', 'Aether Lash']
  };
  const existing = new Set([...(record?.base_moves || []), ...(record?.moves || [])]
    .map(move => String(move.name || '').toLowerCase()));
  const options = names[primary] || ['Void Pulse', 'Hunter’s Mark', 'Measured Strike'];
  const name = options.find(option => !existing.has(option.toLowerCase())) || `${options[0]} II`;
  const magical = Number(record?.base_stats?.mag || 0) > Number(record?.base_stats?.atk || 0) * 1.15;
  return {
    id: moveId(name), name, category: magical ? 'magical' : 'physical',
    type: magical ? primary : null, power: Math.max(42, Math.min(85, 30 + Number(record?.level || 1) * 3)),
    accuracy: magical ? 92 : 96, pp: magical ? 18 : 25, target: 'single', priority: 0, crit: 0,
    effects: [], tags: magical ? ['type', 'ranged'] : ['melee'], description: `A ${primary.toLowerCase()} technique.`
  };
}

function drawMoves(box, record, moveKey = 'moves', options = {}) {
  const section = el('section', 'guided-section moves-section');
  const fixed = !!options.fixed;
  formHeading(section, options.title || 'Moves', options.note ||
    'PP is the only move resource. Each card shows its own power, accuracy, priority and critical chance.');
  const skills = Array.isArray(record[moveKey]) ? record[moveKey] : [];
  if (!skills.length) {
    const empty = el('p', 'form-empty', fixed
      ? 'This creature needs its two starting moves.'
      : 'No moves here yet. Add or attach one when it makes sense.');
    section.appendChild(empty);
  }
  skills.forEach((move, index) => {
    const row = el('div', 'move-row');
    const title = el('div', 'move-number', `MOVE ${String(index + 1).padStart(2, '0')}`);
    if (!fixed) {
      const remove = el('button', 'ghost move-remove', 'Remove');
      remove.type = 'button';
      remove.onclick = () => {
        changeContent(edited => { edited[moveKey] = (edited[moveKey] || []).filter((_, at) => at !== index); });
        drawContentForm();
      };
      title.appendChild(remove);
    }
    row.appendChild(title);
    const fields = el('div', 'move-fields');
    const config = [
      ['ID', 'id'], ['Name', 'name'], ['Category', 'category', ['physical', 'magical', 'support']],
      ['Combat Type', 'type', ['none'].concat((SETUP.library && SETUP.library.types) || [])],
      ['Power', 'power', null, 'number'], ['Accuracy', 'accuracy', null, 'number'], ['PP', 'pp', null, 'number'],
      ['Target', 'target', ['single', 'all_enemies', 'all_allies', 'self', 'random']],
      ['Priority', 'priority', null, 'number'], ['Crit %', 'crit', null, 'number'], ['Tags (comma-separated)', 'tags_text']
    ];
    config.forEach(([label, fieldKey, choices, type]) => {
      const field = el('label', 'move-field');
      field.appendChild(el('span', '', label));
      const input = choices ? el('select') : el('input');
      if (!choices) input.type = type || 'text';
      (choices || []).forEach(value => {
        const option = el('option', '', esc(value.replaceAll('_', ' ')));
        option.value = value;
        input.appendChild(option);
      });
      input.value = fieldKey === 'tags_text' ? (move.tags || []).join(', ') : (move[fieldKey] == null ? '' : String(move[fieldKey]));
      input.oninput = () => changeContent(edited => {
        if (!Array.isArray(edited[moveKey])) edited[moveKey] = [];
        if (!edited[moveKey][index]) edited[moveKey][index] = newMove(index + 1);
        if (fieldKey === 'type') edited[moveKey][index][fieldKey] = input.value === 'none' ? null : input.value;
        else if (fieldKey === 'tags_text') edited[moveKey][index].tags = input.value.split(',').map(tag => tag.trim()).filter(Boolean);
        else edited[moveKey][index][fieldKey] = type === 'number' ? Number(input.value || 0) : input.value;
      });
      fields.appendChild(field);
    });
    const effects = el('label', 'move-field');
    effects.appendChild(el('span', '', 'Effects (structured JSON)'));
    const effectInput = el('textarea');
    effectInput.rows = 2;
    effectInput.value = JSON.stringify(move.effects || []);
    effectInput.onchange = () => {
      try {
        const value = JSON.parse(effectInput.value || '[]');
        if (!Array.isArray(value)) throw new Error('must be a list');
        changeContent(edited => { edited[moveKey][index].effects = value; });
        contentStatus('Structured effects updated.', 'ok');
      } catch (err) { contentStatus('Effects must be valid JSON list: ' + err.message, 'error'); }
    };
    effects.appendChild(effectInput);
    fields.appendChild(effects);
    const description = el('label', 'move-field');
    description.appendChild(el('span', '', 'Description'));
    const descriptionInput = el('input');
    descriptionInput.value = move.description || '';
    descriptionInput.oninput = () => changeContent(edited => { edited[moveKey][index].description = descriptionInput.value; });
    description.appendChild(descriptionInput);
    fields.appendChild(description);
    row.appendChild(fields);
    section.appendChild(row);
  });
  if (!fixed) {
    const add = el('button', 'ghost add-move', '+ Add blank move');
    add.type = 'button';
    add.onclick = () => {
      changeContent(edited => { edited[moveKey] = Array.isArray(edited[moveKey]) ? edited[moveKey] : []; edited[moveKey].push(newMove(edited[moveKey].length + 1)); });
      drawContentForm();
    };
    section.appendChild(add);
    const generate = el('button', 'ghost add-move', '✦ Draft move');
    generate.type = 'button';
    generate.onclick = () => {
      changeContent(edited => {
        edited[moveKey] = Array.isArray(edited[moveKey]) ? edited[moveKey] : [];
        edited[moveKey].push(generatedMove(edited));
      });
      drawContentForm();
    };
    section.appendChild(generate);
  }
  box.appendChild(section);
}

function copyLibraryMove(move) {
  return JSON.parse(JSON.stringify(move || {}));
}

async function drawMoveLibrary(box, record) {
  const section = el('section', 'guided-section');
  formHeading(section, 'Move library', 'Reusable moves live in their own Forge collection. Attach a copy here, then tune it for this creature if needed.');
  const res = await api('/api/content?kind=move');
  const rows = res.records || [];
  if (!rows.length) {
    section.appendChild(el('p', 'form-empty', 'No library moves yet. Use the Move generator or add one in CONTENT › MOVES.'));
    box.appendChild(section);
    return;
  }
  const line = el('div', 'guided-grid');
  const select = el('select');
  rows.forEach(row => {
    const move = row.record || {};
    const option = el('option', '', esc(`${move.name || move.id} · ${move.category || 'move'} · ${move.type || 'neutral'} · PP ${move.pp || 0}`));
    option.value = String(move.id || '');
    select.appendChild(option);
  });
  const wrap = el('label', 'guided-field wide');
  wrap.appendChild(el('span', '', 'Attach generated move'));
  wrap.appendChild(select);
  line.appendChild(wrap);
  section.appendChild(line);
  const add = el('button', 'ghost add-move', '+ Add selected library move');
  add.type = 'button';
  add.onclick = () => {
    const row = rows.find(entry => String((entry.record || {}).id || '') === select.value);
    if (!row) return;
    changeContent(edited => {
      edited.moves = Array.isArray(edited.moves) ? edited.moves : [];
      edited.moves.push(copyLibraryMove(row.record || {}));
    });
    drawContentForm();
  };
  section.appendChild(add);
  box.appendChild(section);
}

function newTreeNode(branchId = 'branch', index = 1) {
  return {
    id: `${moveId(branchId)}_${String(index).padStart(2, '0')}`,
    name: 'New growth node', max_rank: 3, cost_per_rank: 1, prerequisites: [],
    effects_per_rank: [{ kind: 'stat_pct', stat: 'atk', amount: 0.05 }],
    description: '+5% ATK per rank.'
  };
}

function newTreeBranch(index = 1) {
  const id = `branch_${index}`;
  return { id, name: `Path ${index}`, nodes: [newTreeNode(id, 1)] };
}

function treeInput(label, value, type, choices, onChange) {
  const wrap = el('label', 'move-field');
  wrap.appendChild(el('span', '', label));
  const input = choices ? el('select') : el('input');
  if (!choices) input.type = type || 'text';
  (choices || []).forEach(choice => {
    const option = el('option', '', esc(String(choice).replaceAll('_', ' ')));
    option.value = choice;
    input.appendChild(option);
  });
  input.value = value == null ? '' : String(value);
  input.oninput = () => onChange(type === 'number' ? Number(input.value || 0) : input.value);
  input.onchange = input.oninput;
  wrap.appendChild(input);
  return wrap;
}

function v2Tree(record) {
  if (!record.skill_tree || Array.isArray(record.skill_tree) || typeof record.skill_tree !== 'object') {
    record.skill_tree = { branches: [newTreeBranch(1), newTreeBranch(2), newTreeBranch(3)] };
  }
  if (!Array.isArray(record.skill_tree.branches)) record.skill_tree.branches = [];
  return record.skill_tree;
}

function treeEffect(node) {
  if (!Array.isArray(node.effects_per_rank)) node.effects_per_rank = [];
  if (!node.effects_per_rank[0] || typeof node.effects_per_rank[0] !== 'object') {
    node.effects_per_rank[0] = { kind: 'stat_pct', stat: 'atk', amount: 0.05 };
  }
  return node.effects_per_rank[0];
}

function drawSkillTree(box, record, title = 'Skill tree') {
  const section = el('section', 'guided-section moves-section');
  formHeading(section, title, 'Finite build paths: spend one Skill Point per level, choose a branch, and grow it to Level 50. Use Advanced JSON for specialist effects or move unlocks.');
  const tree = v2Tree(record);
  writeContent(record);
  const branches = tree.branches;
  branches.forEach((branch, branchIndex) => {
    if (!Array.isArray(branch.nodes)) branch.nodes = [];
    const branchCard = el('div', 'move-row');
    const heading = el('div', 'move-number', `PATH ${String(branchIndex + 1).padStart(2, '0')}`);
    const removeBranch = el('button', 'ghost move-remove', 'Remove path');
    removeBranch.type = 'button';
    removeBranch.disabled = branches.length <= 3;
    removeBranch.onclick = () => {
      changeContent(edited => { v2Tree(edited).branches.splice(branchIndex, 1); });
      drawContentForm();
    };
    heading.appendChild(removeBranch);
    branchCard.appendChild(heading);
    const branchFields = el('div', 'move-fields');
    branchFields.append(
      treeInput('Path ID', branch.id, 'text', null, value => changeContent(edited => { v2Tree(edited).branches[branchIndex].id = moveId(value); })),
      treeInput('Path name', branch.name, 'text', null, value => changeContent(edited => { v2Tree(edited).branches[branchIndex].name = value; }))
    );
    branchCard.appendChild(branchFields);
    branch.nodes.forEach((node, nodeIndex) => {
      const nodeCard = el('div', 'move-row');
      const nodeHeading = el('div', 'move-number', `NODE ${branchIndex + 1}.${nodeIndex + 1}`);
      const removeNode = el('button', 'ghost move-remove', 'Remove');
      removeNode.type = 'button';
      removeNode.onclick = () => {
        changeContent(edited => { v2Tree(edited).branches[branchIndex].nodes.splice(nodeIndex, 1); });
        drawContentForm();
      };
      nodeHeading.appendChild(removeNode);
      nodeCard.appendChild(nodeHeading);
      const fields = el('div', 'move-fields');
      const effect = treeEffect(node);
      const update = change => changeContent(edited => {
        const editedNode = v2Tree(edited).branches[branchIndex].nodes[nodeIndex];
        change(editedNode, treeEffect(editedNode));
      });
      fields.append(
        treeInput('Node ID', node.id, 'text', null, value => update(edited => { edited.id = moveId(value); })),
        treeInput('Name', node.name, 'text', null, value => update(edited => { edited.name = value; })),
        treeInput('Max rank', node.max_rank, 'number', null, value => update(edited => { edited.max_rank = Math.max(1, Math.min(5, value)); })),
        treeInput('Cost / rank', node.cost_per_rank, 'number', null, value => update(edited => { edited.cost_per_rank = Math.max(1, Math.min(5, value)); })),
        treeInput('Stat', effect.stat || 'atk', 'text', ['hp', 'atk', 'def', 'mag', 'res', 'spd'], value => update((edited, fx) => { fx.kind = 'stat_pct'; fx.stat = value; })),
        treeInput('% per rank', effect.amount ?? 0.05, 'number', null, value => update((edited, fx) => { fx.kind = 'stat_pct'; fx.amount = Math.max(-0.5, Math.min(0.5, value)); })),
        treeInput('Description', node.description || '', 'text', null, value => update(edited => { edited.description = value; }))
      );
      nodeCard.appendChild(fields);
      branchCard.appendChild(nodeCard);
    });
    const addNode = el('button', 'ghost add-move', '+ Add node');
    addNode.type = 'button';
    addNode.onclick = () => {
      changeContent(edited => {
        const target = v2Tree(edited).branches[branchIndex];
        target.nodes.push(newTreeNode(target.id, target.nodes.length + 1));
      });
      drawContentForm();
    };
    branchCard.appendChild(addNode);
    section.appendChild(branchCard);
  });
  const addBranch = el('button', 'ghost add-move', '+ Add path');
  addBranch.type = 'button';
  addBranch.disabled = branches.length >= 4;
  addBranch.onclick = () => {
    changeContent(edited => { v2Tree(edited).branches.push(newTreeBranch(v2Tree(edited).branches.length + 1)); });
    drawContentForm();
  };
  section.appendChild(addBranch);
  box.appendChild(section);
}

function parseIngredients(text) {
  return String(text || '').split('\n').map(line => line.trim()).filter(Boolean).map(line => {
    const matched = line.match(/^(.*?)(?:\s*(?:x|×|:)\s*)(\d+)$/i);
    return matched ? { item: matched[1].trim(), qty: Number(matched[2]) } : { item: line, qty: 1 };
  }).filter(row => row.item);
}

function projectItemChoices() {
  const rows = (SETUP?.library?.item_options || []);
  return [{ value: '', label: 'Choose an existing item…' }].concat(rows.map(row => ({
    value: row.name, label: `${row.name}  ·  ${String(row.kind || 'material').toUpperCase()}`
  })));
}

function recipeIngredientLinks(box, record) {
  const choices = projectItemChoices();
  const section = el('section', 'guided-section');
  formHeading(section, 'Ingredients', 'Every ingredient is selected from real Item Forge records. Make materials, seeds, potions, weapons, and armour in Items first.');
  const rows = Array.isArray(record.ingredients) ? record.ingredients : [];
  if (!choices.slice(1).length) section.appendChild(el('p', 'warnline', 'No Item records exist yet. Create the items first, then link this recipe.'));
  rows.forEach((ingredient, index) => {
    const line = el('div', 'guided-grid');
    guidedField(line, record, { label: `Ingredient ${index + 1}`, path: `ingredients.${index}.item`, choices, wide: true });
    guidedField(line, record, { label: 'Quantity', path: `ingredients.${index}.qty`, type: 'number' });
    const remove = el('button', 'ghost', 'Remove');
    remove.type = 'button';
    remove.onclick = () => { changeContent(edited => edited.ingredients.splice(index, 1)); drawContentForm(); };
    line.appendChild(remove);
    section.appendChild(line);
  });
  const add = el('button', 'ghost add-move', '+ Add item ingredient');
  add.type = 'button';
  add.disabled = !choices.slice(1).length || rows.length >= 5;
  add.onclick = () => { changeContent(edited => { edited.ingredients = edited.ingredients || []; edited.ingredients.push({ item: choices[1].value, qty: 1 }); }); drawContentForm(); };
  section.appendChild(add);
  box.appendChild(section);
}

async function drawContentForm() {
  const box = $('#contentform');
  box.innerHTML = '';
  const record = readContentQuietly();
  if (!CONTENT_SELECTED || !record) return;
  box.dataset.kind = CONTENT_KIND;

  if (CONTENT_KIND === 'monster') {
    formHeading(box, 'Creature profile', 'A compact, data-first species sheet. Rarity owns the BST budget; Level 1–50 scales the final combat line. Type and Family are different things.');
    box.appendChild(el('p', 'warnline', record.portrait_seed
      ? `PIXEL IDENTITY · ${esc(record.portrait_seed.toUpperCase())} · saving writes this creature’s permanent 16×16 sprite.`
      : 'PIXEL IDENTITY · assigned automatically on save; it becomes this creature’s permanent 16×16 sprite.'));
    const basics = el('div', 'guided-grid');
    guidedField(basics, record, { label: 'Name', path: 'name' });
    guidedField(basics, record, { label: 'Title', path: 'title' });
    guidedField(basics, record, { label: 'ID', path: 'id', note: 'Used by Void Area rosters.' });
    guidedField(basics, record, { label: 'Level', path: 'level', type: 'number', note: '1–50.' });
    guidedField(basics, record, { label: 'Rarity', path: 'rarity', choices: ['Common', 'Uncommon', 'Rare', 'Epic'], note: 'Explicit BST tier.' });
    guidedField(basics, record, { label: 'Role', path: 'role', choices: ['Striker', 'Caster', 'Tank', 'Bruiser', 'Support', 'Controller', 'Swarm'] });
    guidedField(basics, record, { label: 'Primary Type', path: 'types.primary', choices: (SETUP.library.types || []) });
    guidedField(basics, record, { label: 'Secondary Type', path: 'types.secondary', choices: [{ value: '', label: 'None' }].concat((SETUP.library.types || [])) });
    guidedField(basics, record, { label: 'Family', path: 'family', placeholder: 'Canine, fungus, automaton…' });
    guidedField(basics, record, { label: 'Sprite silhouette', path: 'sprite_archetype', choices: ['Core', 'Brute', 'Wisp', 'Crawler', 'Tall', 'Hound', 'Wing', 'Mask'], note: 'Visual only; it does not alter stats.' });
    guidedField(basics, record, { label: 'Size', path: 'size', choices: ['Tiny', 'Small', 'Medium', 'Large', 'Huge', 'Gargantuan'] });
    guidedField(basics, record, { label: 'Capture rate', path: 'capture_rate', type: 'number', note: '0.05–1.00 base chance.' });
    box.appendChild(basics);
    const stats = el('section', 'guided-section');
    formHeading(stats, 'Stat shape', 'Exactly six permanent stats. Common 200–230 BST · Uncommon 240–270 · Rare 280–310 · Epic 320–350.');
    const statGrid = el('div', 'stat-grid');
    [['HP', 'hp'], ['ATK', 'atk'], ['DEF', 'def'], ['MAG', 'mag'], ['RES', 'res'], ['SPD', 'spd']].forEach(([label, key]) =>
      guidedField(statGrid, record, { label, path: `base_stats.${key}`, type: 'number' }));
    stats.appendChild(statGrid);
    box.appendChild(stats);
    if (!Array.isArray(record.base_moves)) {
      record.base_moves = [
        { id: 'tackle', name: 'Tackle', category: 'physical', type: null, power: 44, accuracy: 100, pp: 20, target: 'single', priority: 0, crit: 0, effects: [], tags: ['basic', 'melee'], description: 'A reliable close-range strike.' },
        { id: 'dodge', name: 'Dodge', category: 'support', type: null, power: 0, accuracy: 100, pp: 12, target: 'self', priority: 1, crit: 0, effects: [], tags: ['basic', 'guard'], description: 'Brace and reduce incoming damage this round.' }
      ];
      writeContent(record);
    }
    drawMoves(box, record, 'base_moves', { fixed: true, title: 'Starting kit',
      note: 'Exactly two fundamentals: one physical melee move and one self defensive/support move. Tackle and Dodge are dependable defaults.' });
    drawMoves(box, record, 'moves', { title: 'Extra moves',
      note: 'Optional authored techniques. They use PP only and can be attached from the Move Library.' });
    await drawMoveLibrary(box, record);
    await drawSkillTree(box, record, 'Creature skill tree');
    const evolution = el('section', 'guided-section');
    formHeading(evolution, 'Evolution', 'Optional: show an evolution line on this creature’s record.');
    const evoGrid = el('div', 'guided-grid');
    guidedField(evoGrid, record, { label: 'Evolves into', path: 'evolution.into', placeholder: 'Existing creature name' });
    guidedField(evoGrid, record, { label: 'At level', path: 'evolution.at_level', type: 'number' });
    evolution.appendChild(evoGrid);
    box.appendChild(evolution);
    const flavour = el('section', 'guided-section');
    formHeading(flavour, 'Field notes');
    const flavourGrid = el('div', 'guided-grid');
    guidedField(flavourGrid, record, { label: 'Appearance', path: 'appearance', multiline: true, wide: true });
    guidedField(flavourGrid, record, { label: 'Lore', path: 'lore', multiline: true, wide: true });
    flavour.appendChild(flavourGrid);
    box.appendChild(flavour);
  } else if (CONTENT_KIND === 'area') {
    formHeading(box, 'Void Area', 'An area owns an exact creature roster. Only assigned creatures can appear there.');
    const grid = el('div', 'guided-grid');
    guidedField(grid, record, { label: 'Area name', path: 'name' });
    guidedField(grid, record, { label: 'Area ID', path: 'id', note: 'Missions select this.' });
    guidedField(grid, record, { label: 'Atlas description', path: 'description', multiline: true, wide: true });
    box.appendChild(grid);
  } else if (CONTENT_KIND === 'quest') {
    const areas = await api('/api/content?kind=area');
    const areaChoices = [{ value: '', label: 'Choose a Void Area…' }].concat((areas.records || []).map(row => ({
      value: row.record.id, label: `${row.record.name}  (${row.record.id})`
    })));
    formHeading(box, 'Operation', 'Signing this mission takes the hunter directly into this exact Void Area. Finish its objective, then report in.');
    const grid = el('div', 'guided-grid');
    guidedField(grid, record, { label: 'Mission title', path: 'title' });
    guidedField(grid, record, { label: 'Posted by', path: 'giver' });
    guidedField(grid, record, { label: 'Operation area', path: 'area_id', choices: areaChoices, wide: true,
      note: 'Create the area first; this is the location the mission deploys into.' });
    guidedField(grid, record, { label: 'Objective', path: 'kind', choices: ['fetch', 'slay', 'hunt'] });
    guidedField(grid, record, { label: 'Target', path: 'target', placeholder: 'Monster name, family:Name, or item' });
    guidedField(grid, record, { label: 'Quantity', path: 'qty', type: 'number' });
    guidedField(grid, record, { label: 'Gold', path: 'gold', type: 'number' });
    guidedField(grid, record, { label: 'Shards', path: 'shards', type: 'number' });
    guidedField(grid, record, { label: 'Experience', path: 'xp', type: 'number' });
    guidedField(grid, record, { label: 'Suggested level', path: 'level', type: 'number' });
    guidedField(grid, record, { label: 'Briefing', path: 'text', multiline: true, wide: true });
    box.appendChild(grid);
  } else if (CONTENT_KIND === 'item') {
    formHeading(box, 'Item', 'Use weapons and armour as stat-bearing gear, consumables for usable inventory, materials for crafting drops, and seeds for the farm. Anything with a shop price appears on the stall shelf.');
    const grid = el('div', 'guided-grid');
    guidedField(grid, record, { label: 'Name', path: 'name' });
    guidedField(grid, record, { label: 'Kind', path: 'kind', choices: ['consumable', 'seed', 'material', 'weapon', 'armor', 'accessory', 'treasure', 'key'] });
    guidedField(grid, record, { label: 'Sell value', path: 'value', type: 'number' });
    guidedField(grid, record, { label: 'Shop price', path: 'buy', type: 'number' });
    guidedField(grid, record, { label: 'Description', path: 'desc', multiline: true, wide: true });
    box.appendChild(grid);
    const equipment = el('section', 'guided-section');
    formHeading(equipment, 'Equipment bonus', 'For weapons, armour, and accessories. Leave a bonus at 0 when it should not change that stat.');
    const bonusGrid = el('div', 'stat-grid');
    [['HP', 'hp'], ['ATK', 'atk'], ['DEF', 'def'], ['MAG', 'mag'], ['RES', 'res'], ['SPD', 'spd']]
      .forEach(([label, key]) => guidedField(bonusGrid, record, { label, path: `stats.${key}`, type: 'number' }));
    equipment.appendChild(bonusGrid);
    box.appendChild(equipment);
    const use = el('section', 'guided-section');
    formHeading(use, 'Consumable use', 'For a usable item. Values are fractions: 0.50 restores half a bar. PP is the only move resource.');
    const useGrid = el('div', 'guided-grid');
    guidedField(useGrid, record, { label: 'Heal HP', path: 'use.heal_pct', type: 'number', note: '0.50 means 50% health.' });
    guidedField(useGrid, record, { label: 'Restore PP', path: 'use.pp_restore', type: 'number', note: 'Restores this many PP across the active move kit.' });
    guidedField(useGrid, record, { label: 'Revive HP', path: 'use.revive_pct', type: 'number' });
    use.appendChild(useGrid);
    box.appendChild(use);
    if (['weapon', 'armor', 'accessory', 'equipment'].includes(String(record.kind || '').toLowerCase())) {
      await drawSkillTree(box, record, 'Equipment skill tree');
    } else {
      const note = el('section', 'guided-section');
      formHeading(note, 'Equipment skill tree', 'Choose Weapon, Armour, or Accessory above to author a finite equipment path. Consumables and materials do not carry build nodes.');
      box.appendChild(note);
    }
  } else if (CONTENT_KIND === 'move') {
    formHeading(box, 'Reusable move', 'A move here can be attached to any creature or skill-tree node. PP is the whole move resource system; its effects are explicit and inspectable.');
    const grid = el('div', 'guided-grid');
    guidedField(grid, record, { label: 'Move ID', path: 'id' });
    guidedField(grid, record, { label: 'Name', path: 'name' });
    guidedField(grid, record, { label: 'Category', path: 'category', choices: ['physical', 'magical', 'support'] });
    guidedField(grid, record, { label: 'Combat Type', path: 'type', choices: [{ value: '', label: 'Neutral' }].concat(SETUP.library.types || []) });
    guidedField(grid, record, { label: 'Power', path: 'power', type: 'number' });
    guidedField(grid, record, { label: 'Accuracy %', path: 'accuracy', type: 'number' });
    guidedField(grid, record, { label: 'PP', path: 'pp', type: 'number', note: '10–40 is a normal move pool; only Struggle is unlimited.' });
    guidedField(grid, record, { label: 'Target', path: 'target', choices: ['single', 'all_enemies', 'all_allies', 'self', 'random'] });
    guidedField(grid, record, { label: 'Priority', path: 'priority', type: 'number', note: '-7 to +7.' });
    guidedField(grid, record, { label: 'Crit %', path: 'crit', type: 'number', note: 'Additional chance, capped at 40.' });
    const effects = guidedField(grid, record, { label: 'Effects (JSON list)', path: '_effects_text', multiline: true, wide: true,
      value: JSON.stringify(record.effects || []), note: 'Example: [{"kind":"stat","stat":"spd","amount":0.25,"rounds":2,"target":"self"}]' });
    effects.oninput = () => {
      try { const value = JSON.parse(effects.value || '[]'); if (!Array.isArray(value)) throw new Error('must be a list'); changeContent(edited => { edited.effects = value; }); }
      catch { /* keep typing; the checker gives the final exact error */ }
    };
    const tags = guidedField(grid, record, { label: 'Tags (comma-separated)', path: '_tags_text', value: (record.tags || []).join(', ') });
    tags.oninput = () => changeContent(edited => { edited.tags = tags.value.split(',').map(tag => tag.trim()).filter(Boolean); });
    guidedField(grid, record, { label: 'Description', path: 'description', multiline: true, wide: true });
    box.appendChild(grid);
  } else if (CONTENT_KIND === 'starter') {
    formHeading(box, 'Starter selection', 'Choose exactly three Forge creatures. Every new hunt sees these three and takes one; their authored order is preserved.');
    const grid = el('div', 'guided-grid');
    guidedField(grid, record, { label: 'Selection label', path: 'label' });
    box.appendChild(grid);
    const res = await api('/api/content?kind=monster');
    const choices = (res.records || []).map(row => row.record || {}).filter(monster => monster.id && !monster.encounter?.is_boss && monster.role !== 'Boss');
    const selected = new Set(Array.isArray(record.monster_ids) ? record.monster_ids.map(String) : []);
    const panel = el('section', 'guided-section');
    panel.appendChild(el('p', '', `Selected ${selected.size}/3. Pick three distinct, non-boss creatures.`));
    const roster = el('div', 'area-monsters');
    choices.forEach(monster => {
      const label = el('label', 'area-monster');
      const input = el('input');
      input.type = 'checkbox';
      input.checked = selected.has(String(monster.id));
      input.onchange = () => {
        if (input.checked && selected.size >= 3) {
          input.checked = false;
          contentStatus('Choose only three starter candidates.', 'error');
          return;
        }
        input.checked ? selected.add(String(monster.id)) : selected.delete(String(monster.id));
        changeContent(edited => { edited.monster_ids = [...selected]; });
        contentStatus(`Starter choices: ${selected.size}/3 — save to apply.`, selected.size === 3 ? 'ok' : '');
        drawContentForm();
      };
      label.append(input, document.createTextNode(`${monster.name || monster.id}  [${monster.id}]`));
      roster.appendChild(label);
    });
    panel.appendChild(roster);
    box.appendChild(panel);
  } else if (CONTENT_KIND === 'recipe') {
    formHeading(box, 'Recipe', 'Recipes stay hidden until the hunter owns the required craft book.');
    const grid = el('div', 'guided-grid');
    guidedField(grid, record, { label: 'Recipe name', path: 'name' });
    guidedField(grid, record, { label: 'Recipe ID', path: 'id' });
    guidedField(grid, record, { label: 'Station', path: 'station', choices: ['craft_shop', 'farm_kitchen', 'soul_forge'] });
    guidedField(grid, record, { label: 'Craft book', path: 'book', placeholder: 'field_manual' });
    guidedField(grid, record, { label: 'Level', path: 'level', type: 'number' });
    guidedField(grid, record, { label: 'Gold cost', path: 'gold_cost', type: 'number' });
    guidedField(grid, record, { label: 'Result item', path: 'result.item', choices: projectItemChoices(), wide: true,
      note: 'Create the result item in ITEMS first, then link it here.' });
    guidedField(grid, record, { label: 'Result quantity', path: 'result.qty', type: 'number' });
    guidedField(grid, record, { label: 'Description', path: 'description', multiline: true, wide: true });
    box.appendChild(grid);
    recipeIngredientLinks(box, record);
  } else if (CONTENT_KIND === 'crop') {
    formHeading(box, 'Farm crop', 'A crop is a seed, a harvest, a grow time, a grid mark, and a permanent 16×16 growth sprite set.');
    const grid = el('div', 'guided-grid');
    guidedField(grid, record, { label: 'Label', path: 'label' });
    guidedField(grid, record, { label: 'Crop ID', path: 'id' });
    guidedField(grid, record, { label: 'Sprite family', path: 'sprite_family', choices: (SETUP.library.types || []), note: 'Visual palette only.' });
    guidedField(grid, record, { label: 'Seed item', path: 'seed', choices: projectItemChoices() });
    guidedField(grid, record, { label: 'Harvest item', path: 'item', choices: projectItemChoices() });
    guidedField(grid, record, { label: 'Grow time (seconds)', path: 'cycle', type: 'number' });
    guidedField(grid, record, { label: 'Yield', path: 'yield', type: 'number' });
    guidedField(grid, record, { label: 'Grid mark', path: 'mark' });
    box.appendChild(grid);
    const harvest = el('section', 'guided-section');
    formHeading(harvest, 'What the harvest does',
      'Leave every field blank and the produce is a crafting material — a perfectly good crop. Fill one in and it becomes something you can eat. Grow time is the price of the effect.');
    const useGrid = el('div', 'guided-grid');
    guidedField(useGrid, record, { label: 'Heals (fraction of max HP)', path: 'use.heal_pct', type: 'number', note: '0.3 is a third of a health bar.' });
    guidedField(useGrid, record, { label: 'Restores PP', path: 'use.pp_restore', type: 'number' });
    guidedField(useGrid, record, { label: 'Revives at (fraction)', path: 'use.revive_pct', type: 'number' });
    guidedField(useGrid, record, { label: 'Cures status', path: 'use.cleanse', choices: ['', 'true'] });
    harvest.appendChild(useGrid);
    box.appendChild(harvest);
  }
}

function drawContentKinds() {
  const box = $('#contentkinds');
  box.innerHTML = '';
  [['monster', 'MONSTERS'], ['move', 'MOVES'], ['starter', 'STARTERS'], ['area', 'VOID AREAS'], ['quest', 'MISSIONS'],
   ['item', 'ITEMS'], ['recipe', 'RECIPES'], ['crop', 'FARM CROPS']].forEach(([key, label]) => {
    const b = el('button', key === CONTENT_KIND ? 'on' : '', label);
    b.onclick = async () => { CONTENT_KIND = key; CONTENT_SELECTED = null; await loadContent(); };
    box.appendChild(b);
  });
}

function drawContent() {
  drawContentKinds();
  const list = $('#contentlist');
  const query = ($('#contentsearch').value || '').trim().toLowerCase();
  const rows = CONTENT.filter(row => !query ||
    JSON.stringify(row.record).toLowerCase().includes(query) ||
    String(row.source).toLowerCase().includes(query));
  list.innerHTML = '';
  $('#contentcount').textContent = `${rows.length}/${CONTENT.length} ${CONTENT_KIND}${CONTENT.length === 1 ? '' : 's'}`;
  if (!rows.length) {
    list.appendChild(el('div', 'note', query ? 'Nothing matches that search.' : 'Nothing here yet. Make one.'));
  }
  rows.forEach((row, position) => {
    const selected = CONTENT_SELECTED && !CONTENT_SELECTED.draft &&
      CONTENT_SELECTED.source === row.source && CONTENT_SELECTED.index === row.index;
    const b = el('button', `content-row${selected ? ' on' : ''}${row.protected ? ' protected' : ''}`);
    b.append(el('span', 'content-name', esc(contentTitle(row))),
             el('span', 'content-source', `${row.source} · #${position + 1}`));
    b.onclick = () => selectContent(row);
    list.appendChild(b);
  });

  const chosen = CONTENT_SELECTED;
  const protectedRecord = chosen && !chosen.draft && chosen.protected;
  $('#contentsave').disabled = !chosen || protectedRecord;
  $('#contentdelete').disabled = !chosen || !!chosen.draft || protectedRecord || CONTENT_KIND === 'starter';
  $('#contentcopy').disabled = !chosen || !!chosen.draft || CONTENT_KIND === 'starter';
  $('#contentrename').disabled = !chosen;
  if (!chosen) $('#contentmeta').textContent = 'Choose a record to view or edit it.';
  if (!chosen) $('#contentform').innerHTML = '';
  if (CONTENT_KIND !== 'area' || !chosen) {
    $('#areaassignment').hidden = true;
    $('#areaassignment').innerHTML = '';
  }
}

async function drawAreaAssignments(record = null) {
  const box = $('#areaassignment');
  if (CONTENT_KIND !== 'area') {
    box.hidden = true;
    box.innerHTML = '';
    return;
  }
  let area = record;
  if (!area) {
    const raw = $('#contentjson').value.trim();
    try { area = raw ? JSON.parse(raw) : {}; }
    catch { area = {}; }
  }
  box.hidden = false;
  box.innerHTML = '';
  box.appendChild(el('h5', '', 'AREA MONSTER ROSTER'));
  box.appendChild(el('p', '', 'Tick a monster to add its id to monster_ids. This is the exact spawn list for this Void area.'));
  const res = await api('/api/content?kind=monster');
  if (res.error) {
    box.appendChild(el('p', '', 'Could not load monsters: ' + esc(res.error)));
    return;
  }
  const rows = res.records || [];
  if (!rows.length) {
    box.appendChild(el('p', '', 'Forge a monster first, then return here to assign it.'));
    return;
  }
  const selected = new Set(Array.isArray(area.monster_ids) ? area.monster_ids.map(String) : []);
  const roster = el('div', 'area-monsters');
  rows.forEach(row => {
    const monster = row.record || {};
    const id = String(monster.id || '');
    if (!id) return;
    const label = el('label', 'area-monster');
    const input = el('input');
    input.type = 'checkbox';
    input.checked = selected.has(id);
    input.dataset.monsterId = id;
    input.onchange = () => {
      let edited;
      try { edited = JSON.parse($('#contentjson').value); }
      catch {
        contentStatus('Fix the JSON before changing the area roster.', 'error');
        input.checked = !input.checked;
        return;
      }
      edited.monster_ids = [...roster.querySelectorAll('input:checked')]
        .map(box => box.dataset.monsterId);
      $('#contentjson').value = JSON.stringify(edited, null, 2);
      contentStatus(`${edited.monster_ids.length} monster${edited.monster_ids.length === 1 ? '' : 's'} assigned — save to apply.`, 'ok');
    };
    label.append(input, document.createTextNode(`${monster.name || id}  [${id}]`));
    roster.appendChild(label);
  });
  box.appendChild(roster);
}

async function loadContent(choose = null) {
  const res = await api('/api/content?kind=' + encodeURIComponent(CONTENT_KIND));
  if (res.error) { contentStatus('Could not load content: ' + res.error, 'error'); return; }
  CONTENT = res.records || [];
  if (choose) {
    CONTENT_SELECTED = CONTENT.find(row => row.source === choose.source && row.index === choose.index) || null;
    if (CONTENT_SELECTED) $('#contentjson').value = JSON.stringify(CONTENT_SELECTED.record, null, 2);
  }
  drawContent();
  if (CONTENT_SELECTED) await drawContentForm();
  if (CONTENT_KIND === 'area' && CONTENT_SELECTED) await drawAreaAssignments(CONTENT_SELECTED.record);
}

function selectContent(row) {
  CONTENT_SELECTED = { source: row.source, index: row.index, protected: !!row.protected };
  $('#contentjson').value = JSON.stringify(row.record, null, 2);
  $('#contentmeta').textContent = CONTENT_KIND === 'area'
    ? `Void area roster: edit monster_ids to control exactly which monsters spawn there.`
    : `Editable source: ${row.source}. Changes save directly into this project.`;
  contentStatus('');
  drawContent();
  drawContentForm();
  if (CONTENT_KIND === 'area') drawAreaAssignments(row.record);
}

async function newContent() {
  const r = await fetch('/api/template?kind=' + CONTENT_KIND);
  const raw = await r.text();
  let record;
  try { record = JSON.parse(raw); }
  catch { contentStatus('The blank template could not be read.', 'error'); return; }
  if (CONTENT_KIND === 'monster') {
    record.id = (SETUP && SETUP.next_id) || 'mon_0000';
    record.name = 'Untitled Monster';
    record.title = 'A new creature';
    record.habitat = [];
  } else if (CONTENT_KIND === 'quest') {
    // The file template has a { quests: [...] } wrapper; edit one contract.
    if (Array.isArray(record.quests)) record = record.quests[0];
    record.title = 'Untitled Contract';
    record.giver = 'Unknown';
    record.text = 'A new job waits at the board.';
    record.area_id = '';
  } else if (CONTENT_KIND === 'item') {
    const entries = Object.entries(record).filter(([key, value]) => !key.startsWith('_') && value && typeof value === 'object');
    const [name, spec] = entries[0] || ['Untitled Item', { kind: 'consumable', value: 10, buy: 25, desc: '' }];
    record = { name: 'Untitled Item', ...spec };
  } else if (CONTENT_KIND === 'area') {
    record.id = 'new_void_area';
    record.name = 'New Void Area';
    record.description = 'An area waiting for monsters to be assigned.';
    record.monster_ids = [];
  } else if (CONTENT_KIND === 'crop') {
    record.id = 'new_crop';
    record.label = 'NEW CROP';
    const first = projectItemChoices()[1]?.value || '';
    record.seed = first;
    record.item = first;
  } else if (CONTENT_KIND === 'recipe') {
    record.id = 'new_recipe';
    record.name = 'New Recipe';
    const first = projectItemChoices()[1]?.value || '';
    record.ingredients = first ? [{ item: first, qty: 1 }] : [];
    record.result = { item: first, qty: 1 };
  } else if (CONTENT_KIND === 'move') {
    record.id = 'move_0000';
    record.name = 'New Technique';
  }
  CONTENT_SELECTED = { draft: true, protected: false };
  $('#contentjson').value = JSON.stringify(record, null, 2);
  $('#contentmeta').textContent = 'New draft — complete it, check it, then save it to your collection.';
  contentStatus('This has not been added to the game yet.', '');
  drawContent();
  await drawContentForm();
  if (CONTENT_KIND === 'area') drawAreaAssignments(record);
}

async function checkContent() {
  const record = contentRecord();
  if (!record) return;
  const res = await api('/api/validate', { kind: CONTENT_KIND, records: [record] });
  const report = (res.results || [])[0];
  if (!report) { contentStatus(res.error || 'The checker did not answer.', 'error'); return; }
  if (report.errors && report.errors.length) {
    contentStatus('Needs fixing: ' + report.errors.slice(0, 4).join(' · '), 'error');
  } else if (report.warnings && report.warnings.length) {
    contentStatus('Valid. Notes: ' + report.warnings.slice(0, 3).join(' · '), 'ok');
  } else {
    contentStatus('Valid — ready to save.', 'ok');
  }
}

async function saveContent() {
  const record = contentRecord();
  if (!record || !CONTENT_SELECTED) return;
  const selected = CONTENT_SELECTED;
  const path = selected.draft ? '/api/content/create' : '/api/content/update';
  const body = { kind: CONTENT_KIND, record };
  if (!selected.draft) Object.assign(body, { source: selected.source, index: selected.index });
  const res = await api(path, body);
  if (res.error) { contentStatus('Could not save: ' + res.error, 'error'); return; }
  if (CONTENT_KIND === 'monster' && SETUP) SETUP.next_id = res.record && res.record.id || SETUP.next_id;
  $('#contentmeta').textContent = `Saved in ${res.source} — the game can use it next time it starts.`;
  contentStatus('Saved. Your game data is updated.', 'ok');
  await loadContent(res);
}

function renameContent() {
  const record = contentRecord();
  if (!record || !CONTENT_SELECTED) return;
  const field = CONTENT_KIND === 'quest' ? 'title' : (CONTENT_KIND === 'crop' || CONTENT_KIND === 'starter') ? 'label' : 'name';
  const label = CONTENT_KIND === 'quest' ? 'quest title' : (CONTENT_KIND === 'crop' || CONTENT_KIND === 'starter') ? 'selection label' : `${CONTENT_KIND} name`;
  const name = window.prompt(`New ${label}:`, record[field] || '');
  if (name == null) return;
  if (!name.trim()) { contentStatus('A name cannot be empty.', 'error'); return; }
  record[field] = name.trim();
  writeContent(record);
  contentStatus('Renamed in the editor — save changes to make it permanent.', 'ok');
  drawContentForm();
}

async function copyContent() {
  if (!CONTENT_SELECTED || CONTENT_SELECTED.draft) return;
  const res = await api('/api/content/copy', { kind: CONTENT_KIND,
    source: CONTENT_SELECTED.source, index: CONTENT_SELECTED.index });
  if (res.error) { contentStatus('Could not copy: ' + res.error, 'error'); return; }
  $('#contentjson').value = JSON.stringify(res.record, null, 2);
  $('#contentmeta').textContent = `Copied into ${res.source}. Rename it and save when you are ready.`;
  contentStatus('Copy created in your collection.', 'ok');
  await loadContent(res);
}

async function deleteContent() {
  if (!CONTENT_SELECTED || CONTENT_SELECTED.draft) return;
  const record = contentRecord();
  const name = record && (record.name || record.title || record.label) || 'this record';
  if (!window.confirm(`Remove ${name}? This deletes it from your collection.`)) return;
  const res = await api('/api/content/delete', { kind: CONTENT_KIND,
    source: CONTENT_SELECTED.source, index: CONTENT_SELECTED.index });
  if (res.error) { contentStatus('Could not remove it: ' + res.error, 'error'); return; }
  CONTENT_SELECTED = null;
  $('#contentjson').value = '';
  $('#contentform').innerHTML = '';
  contentStatus('Removed from your collection.', 'ok');
  await loadContent();
}

// ------------------------------------------------------------------- wiring
$('#forge').onclick = forgeBatch;
$('#stop').onclick = () => { STOP = true; note('stopping after this one…'); };
$('#preview').onclick = () => showPlan(true);
const fillGaps = $('#fillgaps');
if (fillGaps) fillGaps.onclick = async () => {
  const g = await api('/api/gaps', { count: Number($('#count').value) || 20 });
  KIND = 'monster'; drawKinds(); drawForm();
  PICKED.types = g.types || [];
  PICKED.habitats = g.habitats || [];
  PICKED.tones = [];
  drawForm();
  if ($('#f_levels')) $('#f_levels').value = g.levels || '';
  if ($('#f_brief')) $('#f_brief').value = g.brief || '';
  $('#count').value = g.count || 20;
  note((g.why || []).join(' · '));
  showPlan(true);
};
$('#save').onclick = saveBatch;
$('#clear').onclick = () => { BATCH = []; drawBatch(); note(''); };
$('#checkhand').onclick = () => checkHand();
$('#refresh').onclick = async () => {
  drawOllama(await api('/api/models?endpoint=' + encodeURIComponent($('#endpoint').value)));
};
$('#loadtemplate').onclick = async () => {
  const r = await fetch('/api/template?kind=' + KIND);
  $('#hand').value = await r.text();
};
$('#showprompt').onclick = async () => {
  const res = await api('/api/prompt', { kind: KIND, ask: ask() });
  $('#psys').textContent = res.system || '';
  $('#puser').textContent = res.user || '';
  $('#promptbox').showModal();
};
$('#closeprompt').onclick = () => $('#promptbox').close();
$('#contentrefresh').onclick = () => loadContent();
$('#contentnew').onclick = newContent;
$('#contentcheck').onclick = checkContent;
$('#contentsave').onclick = saveContent;
$('#contentrename').onclick = renameContent;
$('#contentcopy').onclick = copyContent;
$('#contentdelete').onclick = deleteContent;
$('#contentformrefresh').onclick = () => {
  if (readContentQuietly()) drawContentForm();
};
$('#contentsearch').oninput = drawContent;

let dragDepth = 0;
window.addEventListener('dragenter', e => { e.preventDefault(); if (++dragDepth === 1) $('#drop').classList.add('on'); });
window.addEventListener('dragover', e => e.preventDefault());
window.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; $('#drop').classList.remove('on'); } });
window.addEventListener('drop', async e => {
  e.preventDefault();
  dragDepth = 0;
  $('#drop').classList.remove('on');
  for (const file of e.dataTransfer.files) {
    const text = await file.text();
    if (file.name.endsWith('.jsonl')) {
      const rows = text.split('\n').map(l => l.trim()).filter(Boolean);
      const res = await api('/api/validate', { kind: KIND, records: rows.map(r => JSON.parse(r)) });
      (res.results || []).forEach(r => add({ record: r.record, errors: r.errors, warnings: r.warnings }));
    } else {
      const res = await api('/api/validate', { kind: KIND, records: JSON.parse(text) });
      (res.results || []).forEach(r => add({ record: r.record, errors: r.errors, warnings: r.warnings }));
    }
    note(`read ${file.name}`);
  }
  drawBatch();
});

boot();
