const $ = (id) => document.getElementById(id);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const sign = n => n >= 0 ? `+${n}` : String(n);
const number = n => Number(n).toLocaleString();
let current = null, monsters = [], busy = false, online = false, startedAt = 0;
const presets = {
  forest: {name:'The Hollow Antler', type:'fey', role:'skirmisher', cr:'3', description:'A stag-shaped guardian of a cursed forest, with a hollow wooden body and ghostly lanterns hanging from its antlers. It speaks in stolen memories, lures trespassers off the path, and vanishes into tangled roots. Give it an eerie signature ability and harvestable woodland loot.'},
  deep: {name:'The Bell Below', type:'aberration', role:'boss', cr:'7', description:'A deep-sea creature wearing the wreck of a sunken diving bell as its shell. Its toll summons spectral sailors, and its tentacles reach through flooded corridors. Include a pressure-based attack, a weakness clever players can exploit, and strange treasures from the wreck.'},
  clockwork: {name:'Copperwake Custodian', type:'construct', role:'brute', cr:'2', description:'A forgotten clockwork caretaker with gardening shears for hands and a furnace full of blue moths. It guards an abandoned glasshouse, repairs itself using broken tools, and mistakes intruders for weeds. Include salvageable components and a way to disrupt its gears.'}
};

async function api(path, options) {
  const response = await fetch(path, options);
  const result = await response.json();
  if (!response.ok) throw new Error(result.error || 'The request failed.');
  return result;
}
function showError(message) { $('error').textContent = message; $('error').hidden = !message; }
function setTab(tab) {
  $('workshop').hidden = tab !== 'forge'; $('library-view').hidden = tab !== 'library';
  $('forge-tab').classList.toggle('active', tab === 'forge'); $('library-tab').classList.toggle('active', tab === 'library');
  $('world-view').hidden = tab !== 'world';
  $('world-tab').classList.toggle('active', tab === 'world');
  if (tab === 'world') loadWorld();
  if (tab === 'library') renderLibrary();
}
function usePreset(key) {
  Object.entries(presets[key]).forEach(([field, value]) => { $(field).value = value; });
  $('description').focus();
}
async function refreshModels() {
  const selected = $('model').value || localStorage.getItem('monster-forge-model');
  $('refresh-models').disabled = true;
  try {
    const status = await api('/api/status'); online = status.online;
    $('connection-dot').classList.toggle('online', online);
    $('connection-text').textContent = online ? 'Ollama connected' : 'Ollama offline';
    $('dataset-count').textContent = number(status.dataset_count);
    $('model').replaceChildren(...status.models.map(model => new Option(model, model)));
    if (status.models.length) $('model').value = status.models.includes(selected) ? selected : status.default_model;
    else $('model').add(new Option(online ? 'No models installed' : 'Start Ollama to connect', ''));
    $('model-help').textContent = online ? (status.models.length ? 'Runs through your own Ollama server.' : 'Install a model with: ollama pull qwen2.5:14b') : 'Start Ollama, then press ↻ to reconnect.';
    $('generate').disabled = busy || !online || !status.models.length;
    if (!online) showError(status.error);
    else if (!busy) showError('');
  } catch (e) { online = false; showError(e.message); $('connection-text').textContent = 'App connection lost'; $('generate').disabled = true; }
  finally { $('refresh-models').disabled = false; }
}
function renderMonster(m) {
  current = m;
  $('empty-state').hidden = true; $('monster-card').hidden = false;
  ['export', 'export-md', 'print', 'remix'].forEach(id => { $(id).disabled = false; });
  const stat = (value, label) => `<div class="core-stat"><strong>${esc(value)}</strong><small>${label}</small></div>`;
  const detail = (label, value) => value && value !== 'None' ? `<p><b>${label}</b> ${esc(value)}</p>` : '';
  const features = (label, items) => items?.length ? `<section class="card-section"><h3>${label}</h3>${items.map(f => `<p class="feature"><b>${esc(f.name)}.</b> ${esc(f.description)}</p>`).join('')}</section>` : '';
  const lore = (label, text) => `<section class="card-section lore-section"><h3>${label}</h3><p>${esc(text)}</p></section>`;
  $('monster-card').innerHTML = `
    <div class="card-kicker"><span>FIELD JOURNAL / ${esc(m.type)}</span><span class="cr-badge">CR ${esc(m.cr)}</span></div>
    <h2>${esc(m.name)}</h2><p class="monster-subtitle">${esc(m.subtitle)}</p>
    <p class="monster-meta">${esc(m.size)} ${esc(m.type)} · ${esc(m.alignment)} · ${esc(m.role)}</p>
    <div class="core-stats">${stat(m.armor_class,'Armor class')}${stat(m.hit_points,'Hit points')}${stat(number(m.xp),'Experience')}${stat(sign(m.proficiency_bonus),'Proficiency')}</div>
    <p class="card-description">${esc(m.description)}</p>
    <div class="ability-grid">${['str','dex','con','int','wis','cha'].map(key => `<div class="ability"><small>${key.toUpperCase()}</small><strong>${esc(m.abilities[key])}</strong><span>${sign(m.ability_modifiers[key])}</span></div>`).join('')}</div>
    <div class="details">${detail('Speed',m.speed)}${detail('Saving throws',Object.entries(m.saving_throws).map(([k,v])=>`${k.toUpperCase()} ${sign(v)}`).join(', '))}${detail('Skills',m.skills)}${detail('Senses',m.senses)}${detail('Languages',m.languages)}${detail('Resistances',m.resistances)}${detail('Damage immunities',m.immunities)}${detail('Condition immunities',m.condition_immunities)}${detail('Vulnerabilities',m.vulnerabilities)}${detail('Habitat',m.habitat)}</div>
    ${features('Traits',m.traits)}${features('Actions',m.actions)}${features('Bonus actions',m.bonus_actions)}${features('Reactions',m.reactions)}${features('Legendary actions',m.legendary_actions)}
    ${lore('Running the encounter',m.tactics)}
    <section class="card-section"><h3 class="loot-heading">Spoils & salvage <span>${number(m.treasure_gp)} gp guaranteed</span></h3>${m.loot.map(item => `<div class="loot-item"><div class="loot-top"><b>${esc(item.name)}</b><span>${item.chance_percent}% drop</span></div><p>${esc(item.description)}</p><div class="loot-meta">${esc(item.quantity)} · ${esc(item.rarity)} · ${number(item.value_gp)} gp total value</div></div>`).join('')}</section>
    ${lore('From the old stories',m.lore)}${lore('An adventure waiting',m.adventure_hook)}
    <details class="review"><summary>Design notes & reference creatures</summary><p>${esc(m.balance_notes)}</p>${m.review_notes.filter(note=>!note.startsWith('Level is a campaign label')).map(note=>`<p>${esc(note)}</p>`).join('')}<p>${(m.detail_references || []).map(r=>`${esc(r.title)} · ${esc(r.license)} · row ${r.line}`).join("<br>")}</p><div class="reference-chips">${m.references.map(r=>`<span>${esc(r.name.replaceAll('-',' '))} · CR ${esc(r.cr)} · AC ${r.ac} · HP ${r.hp}</span>`).join('')}</div></details>
    <div class="card-footer"><span>MONSTER FORGE ✦ ${esc(m.ruleset)}</span><span>Forged with ${esc(m.model)}</span></div>`;
}
async function loadLibrary() {
  const data = await api('/api/monsters'); monsters = data.monsters;
  $('library-count').textContent = monsters.length; renderLibrary();
}
function renderLibrary() {
  const query = $('search').value.toLowerCase();
  const matches = monsters.filter(m => `${m.name} ${m.type} ${m.description}`.toLowerCase().includes(query));
  $('library-grid').innerHTML = matches.map(m => `<button class="library-card" data-id="${esc(m.id)}"><small>${esc(m.type)} / CR ${esc(m.cr)}</small><h3>${esc(m.name)}</h3><p>${esc(m.description.slice(0,150))}${m.description.length>150?'…':''}</p><div><span>CR ${esc(m.cr)} · ${number(m.xp)} XP</span><span>Open sheet ↗</span></div></button>`).join('');
  $('library-empty').hidden = matches.length > 0;
  $('library-empty').textContent = monsters.length ? 'No creatures match that search.' : 'Your bestiary is waiting. Forge your first monster in the workshop.';
}
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
let lastProgress = null;
function renderProgress(job) {
  lastProgress = job;
  const phases = ['references','draft','validate','save','complete'];
  const index = Math.max(0,phases.indexOf(job.phase));
  const failed = job.status === 'error', complete = job.status === 'complete';
  const percent = complete ? 100 : Math.min(99,Math.max(0,job.percent || 3));
  $('forge-progress').hidden = false;
  $('forge-progress').classList.toggle('is-complete',complete);
  $('forge-progress').classList.toggle('is-error',failed);
  $('progress-title').textContent = job.stage || 'Preparing the forge';
  $('progress-detail').textContent = failed ? (job.error || 'The forge stopped. Try again when ready.') : job.detail;
  $('progress-value').textContent = `${percent}%`;
  $('progress-estimate').textContent = complete ? 'complete' : failed ? 'stopped' : 'estimated';
  $('forge-meter').setAttribute('aria-valuenow',String(percent));
  $('forge-fill').setAttribute('width',String(percent));
  $('progress-steps').querySelectorAll('li').forEach((item,i)=>{
    const done=complete || i<index, active=!complete && i===index;
    item.classList.toggle('done',done); item.classList.toggle('active',active);
    if(active) item.setAttribute('aria-current','step'); else item.removeAttribute('aria-current');
    item.querySelector('span').textContent = done ? '✓' : String(i+1);
  });
  const elapsed=Math.max(0,Math.floor(Date.now()/1000-(job.started_at || startedAt/1000)));
  $('progress-elapsed').textContent=elapsed<60 ? `${elapsed}s elapsed` : `${Math.floor(elapsed/60)}m ${elapsed%60}s elapsed`;
  let activity = job.output_chars ? `${number(job.output_chars)} characters received` : 'Waiting for the first model output';
  if(job.completed_fields) activity += ` · ${job.completed_fields}/${job.total_fields} fields`;
  if(job.last_activity_at && !complete && !failed && Date.now()/1000-job.last_activity_at>15) activity += ' · Waiting for more output';
  $('progress-activity').textContent = complete ? 'Sheet saved · Markdown export ready' : failed ? (job.interrupted ? 'Job may still be running · refresh to reconnect' : 'Draft was not saved') : activity;
  const next = ['Draft stats, abilities, lore and loot.','Validate the sheet and calculate final stats.','Save your monster and source references.','Open your sheet and prepare exports.','Open the sheet below or export it to your Obsidian vault.'];
  $('progress-next').textContent = failed ? 'You can change the brief or model and try again.' : `${complete?'Ready:':'Next:'} ${next[index]}`;
  $('progress-events').innerHTML=(job.events || []).map(event=>`<li><span>${Math.max(0,Math.floor(event.at-(job.started_at || startedAt/1000)))}s</span>${esc(event.stage)}</li>`).join('');
}
async function watchJob(id) {
  let failures = 0;
  while (true) {
    let job;
    try { job = await api(`/api/jobs/${id}`); failures = 0; }
    catch (e) { if (++failures >= 4) throw new Error('Lost contact with the forge. Your job may still finish; refresh to check the saved bestiary.'); $('progress-detail').textContent='Reconnecting to the forge… Your job may still be running.'; await pause(2000); continue; }
    renderProgress(job);
    if (job.status === 'error') { localStorage.removeItem('monster-forge-job'); throw new Error(job.error); }
    if (job.status === 'complete') {
      localStorage.removeItem('monster-forge-job'); renderMonster(job.monster); await loadLibrary().catch(e=>showError('Monster saved. Could not refresh the bestiary list: '+e.message));
      $('status').hidden = true; return;
    }
    await pause(1500);
  }
}
function setBusy(value) {
  busy = value; $('generate').disabled = value || !online || !$('model').value;
  $('generate').innerHTML = value ? '<span>✦</span> Forging your monster…' : '<span>✦</span> Forge monster <span>↗</span>';
  $('monster-form').setAttribute('aria-busy',String(value));
}
$('monster-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return;
  showError(''); setBusy(true); $('status').hidden = true; startedAt = Date.now();
  renderProgress({phase:'references',percent:3,status:'running',stage:'Opening the bestiary',detail:'Finding creatures that match your concept and challenge rating.',started_at:startedAt/1000});
  $('forge-progress').scrollIntoView({behavior:'smooth',block:'center'});
  const data = Object.fromEntries(new FormData(event.target));
  localStorage.setItem('monster-forge-model',data.model);
  try { const job = await api('/api/generate', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}); localStorage.setItem('monster-forge-job',JSON.stringify({id:job.job_id,startedAt})); await watchJob(job.job_id); }
  catch (e) { showError(e.message); $('status').hidden = true; if(lastProgress?.status !== 'error') renderProgress({...lastProgress,status:'error',interrupted:true,stage:'Connection or request interrupted',error:e.message}); }
  finally { setBusy(false); }
});
$('forge-tab').onclick = () => setTab('forge'); $('library-tab').onclick = () => setTab('library');
$('refresh-models').onclick = refreshModels;
document.querySelectorAll('[data-preset]').forEach(b=>{b.onclick=()=>usePreset(b.dataset.preset);});
$('start-example').onclick = () => { usePreset('forest'); $('description').scrollIntoView({behavior:'smooth',block:'center'}); };
$('remix').onclick = () => { if (!current) return; Object.entries(current.brief).forEach(([k,v])=>{if($(k) && k !== 'model') $(k).value=v;}); $('description').focus(); $('monster-form').scrollIntoView({behavior:'smooth',block:'start'}); };
$('export').onclick = () => {
  if (!current) return;
  const url = URL.createObjectURL(new Blob([JSON.stringify(current,null,2)],{type:'application/json'}));
  const link = document.createElement('a'); link.href=url; link.download=`${current.name.toLowerCase().replace(/[^a-z0-9]+/g,'-') || 'monster'}.json`; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
};
$('print').onclick = () => { if(current) window.print(); };
let previewTimer, folderPath = '', markdownRequest = 0;
const exportTasks = new Map();
const exportRequest = async (endpoint, data) => {
  const task=Symbol(), labels={preview:'Preparing your Markdown note and source links…',save:data.include_guide?'Saving your monster note and usage guide…':'Saving your monster note…',folders:'Reading folders…'};
  const showWork=()=>{ $('export-progress').hidden=!exportTasks.size; $('export-progress').textContent=exportTasks.size ? [...exportTasks.values()].at(-1) : ''; };
  exportTasks.set(task,labels[endpoint]); showWork();
  try { return await api(`/api/export/${endpoint}`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)}); }
  finally { exportTasks.delete(task); showWork(); }
};
function exportError(message) { $('md-error').textContent=message; $('md-error').hidden=!message; }
function exportBrief() { return {monster_id:current.id,world_links:$('world-links').value}; }
async function updateMarkdownPreview() {
  const request = ++markdownRequest;
  try { const result = await exportRequest('preview',exportBrief()); if(request===markdownRequest) { $('markdown-preview').textContent=result.markdown; exportError(''); } }
  catch(e) { if(request===markdownRequest) exportError(e.message); }
}
$('export-md').onclick = () => {
  if(!current) return;
  $('export-folder').value=localStorage.getItem('monster-forge-export-folder') || '';
  $('world-links').value=localStorage.getItem(`monster-forge-links-${current.id}`) || '';
  $('folder-browser').hidden=true; $('md-message').hidden=true; exportError('');
  $('md-dialog').showModal(); updateMarkdownPreview();
};
$('close-md').onclick=()=>$('md-dialog').close();
$('world-links').oninput=()=>{ clearTimeout(previewTimer); $('md-message').hidden=true; previewTimer=setTimeout(updateMarkdownPreview,350); };
async function browseFolder(folder) {
  exportError(''); $('browse-folders').disabled=true;
  try {
    const result=await exportRequest('folders',{folder}); folderPath=result.path;
    $('folder-browser').hidden=false; $('folder-current').textContent=folderPath;
    $('folder-parent').disabled=result.path===result.parent; $('folder-parent').dataset.path=result.parent;
    $('folder-list').replaceChildren(...result.folders.map(item=>{
      const button=document.createElement('button'); button.type='button'; button.textContent=`▸ ${item.name}`;
      button.onclick=()=>browseFolder(item.path); return button;
    }));
    if(!result.folders.length) { const p=document.createElement('p'); p.textContent='No subfolders. You can save in this folder.'; $('folder-list').append(p); }
  } catch(e) { exportError(e.message); }
  finally { $('browse-folders').disabled=false; }
}
$('browse-folders').onclick=()=>browseFolder($('export-folder').value.trim());
$('folder-parent').onclick=()=>browseFolder($('folder-parent').dataset.path);
$('use-folder').onclick=()=>{ $('export-folder').value=folderPath; $('folder-browser').hidden=true; };
$('cancel-folder').onclick=()=>{ $('folder-browser').hidden=true; };
$('save-md').onclick=async()=>{
  if(!current) return;
  exportError(''); $('md-message').hidden=true; $('save-md').disabled=true;
  try {
    const folder=$('export-folder').value.trim();
    const result=await exportRequest('save',{...exportBrief(),folder,include_guide:$('include-guide').checked});
    localStorage.setItem('monster-forge-export-folder',folder);
    localStorage.setItem(`monster-forge-links-${current.id}`,$('world-links').value);
    $('md-message').textContent=`Saved: ${result.path}${result.guide_path ? '\nUsage guide: '+result.guide_path : ''}${result.warning ? '\n'+result.warning : ''}`; $('md-message').hidden=false;
  } catch(e) { exportError(e.message); }
  finally { $('save-md').disabled=false; }
};
$('download-md').onclick=async()=>{
  if(!current) return;
  exportError(''); $('download-md').disabled=true;
  try {
    const result=await exportRequest('preview',exportBrief());
    const blob=new Blob([result.markdown],{type:'text/markdown;charset=utf-8'});
    const url=URL.createObjectURL(blob), link=document.createElement('a'); link.href=url; link.download=result.filename; link.click(); setTimeout(()=>URL.revokeObjectURL(url),1000);
    localStorage.setItem(`monster-forge-links-${current.id}`,$('world-links').value);
  } catch(e) { exportError(e.message); }
  finally { $('download-md').disabled=false; }
};
$('search').oninput = renderLibrary;
$('library-grid').onclick = event => { const button = event.target.closest('[data-id]'); if(button) { renderMonster(monsters.find(m=>m.id===button.dataset.id)); setTab('forge'); $('monster-card').scrollIntoView({behavior:'smooth',block:'start'}); } };
['0','1/8','1/4','1/2',...Array.from({length:30},(_,i)=>String(i+1))].forEach(cr=>$('cr').add(new Option(cr,cr)));
$('cr').value='3';
(async()=>{
  await Promise.all([refreshModels(),loadLibrary().catch(e=>showError(e.message))]);
  if(monsters.length) renderMonster(monsters[0]);
  try { const pending = JSON.parse(localStorage.getItem('monster-forge-job') || 'null'); if(pending) { startedAt=pending.startedAt; setBusy(true); $('status').hidden=true; await watchJob(pending.id); } }
  catch(e) { showError(e.message); localStorage.removeItem('monster-forge-job'); $('status').hidden=true; }
  finally { setBusy(false); }
})();

// World settings, canon index and durable background growth.
const worldFields = ['name', 'vault', 'folder', 'seed', 'tone', 'geography', 'factions', 'canon_constraints', 'model'];
let worldLoaded = false, worldBrowseTarget = '', worldBrowseState = null;
function worldError(message) { $('world-error').textContent = message; $('world-error').hidden = !message; }
function renderWorldGraph(graph) {
  $('world-index').disabled = !$('world-folder').value;
  if (!graph) { $('world-summary').textContent = 'No index yet.'; $('world-entities').replaceChildren(); $('world-diagnostics').replaceChildren(); return; }
  $('world-summary').textContent = `${graph.entities.length} notes · ${graph.relationships.length} relationships · Indexed ${new Date(graph.indexed_at).toLocaleString()}`;
  $('world-entities').innerHTML = graph.entities.map(e => `<details><summary>${esc(e.name)} <small>${esc(e.kind)}</small></summary><p>${esc(e.path)}</p><p>ID: ${esc(e.id)}</p><p>SHA-256: ${esc(e.hash)}</p><pre>${esc(JSON.stringify(e.properties, null, 2))}</pre></details>`).join('');
  $('world-diagnostics').innerHTML = graph.diagnostics.length ? graph.diagnostics.map(d => `<li>${esc(d)}</li>`).join('') : '<li>No issues found.</li>';
}
async function loadWorld() {
  if (worldLoaded) return;
  try {
    const state = await api('/api/world');
    syncWorldModels(state.settings?.model || state.growth?.model);
    renderGrowth(state.growth);
    if (state.settings) worldFields.forEach(k => { $('world-' + k).value = state.settings[k] || ''; });
    $('world-schemas').innerHTML = Object.entries(state.schemas).map(([kind, schema]) => `<p><strong>${esc(kind)}</strong>: ${schema.required.map(esc).join(', ')}${kind === 'creature' ? ' (challenge_rating uses CR: 0, 1/8, 1/4, 1/2, 1–30)' : ''}</p>`).join('');
    renderWorldGraph(state.graph); worldLoaded = true;
    if (state.settings) $('world-message').textContent = 'World settings restored. Refresh to read your latest notes.';
  } catch (e) { worldError(e.message); }
}
async function worldPost(path, data = {}) {
  return api(path, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(data)});
}
async function refreshWorldIndex() {
  $('world-index').disabled = true; $('world-save').disabled = true; worldError('');
  $('world-message').textContent = 'Reading notes and rebuilding canon links…';
  try { const state = await worldPost('/api/world/index'); renderWorldGraph(state.graph); $('world-message').textContent = 'Canon index refreshed. Your notes are unchanged.'; }
  catch (e) { worldError(e.message); $('world-message').textContent = 'Index refresh failed. The previous index is retained.'; }
  finally { $('world-index').disabled = false; $('world-save').disabled = false; }
}
$('world-tab').onclick = () => setTab('world');
$('world-index').onclick = refreshWorldIndex;
$('world-form').onsubmit = async event => {
  event.preventDefault(); worldError(''); $('world-save').disabled = true;
  try {
    const state = await worldPost('/api/world/settings', {...Object.fromEntries(worldFields.map(k => [k, $('world-' + k).value])), ...growthOptions()});
    worldFields.forEach(k => { $('world-' + k).value = state.settings[k] || ''; });
    renderWorldGraph(state.graph); renderGrowth(state.growth); $('world-message').textContent = 'Settings saved. World growth started in the background.';
  } catch (e) { worldError(e.message); }
  finally { $('world-save').disabled = false; }
};
async function browseWorldLocation(folder) {
  worldError('');
  try {
    const state = await worldPost('/api/export/folders', {folder});
    worldBrowseState = state; $('world-location').textContent = state.path;
    $('world-browser').hidden = false; $('world-up').disabled = !state.parent;
    $('world-folders').replaceChildren(...state.folders.map(f => { const b = document.createElement('button'); b.type = 'button'; b.textContent = f.name; b.onclick = () => browseWorldLocation(f.path); return b; }));
  } catch (e) { worldError(e.message); }
}
document.querySelectorAll('[data-world-browse]').forEach(b => { b.onclick = () => { worldBrowseTarget = b.dataset.worldBrowse; browseWorldLocation($('world-' + worldBrowseTarget).value || $('world-vault').value); }; });
$('world-up').onclick = () => { if (worldBrowseState?.parent) browseWorldLocation(worldBrowseState.parent); };
$('world-choose').onclick = () => { if (worldBrowseState) $('world-' + worldBrowseTarget).value = worldBrowseState.path; $('world-browser').hidden = true; };
$('world-cancel').onclick = () => { $('world-browser').hidden = true; };

function syncWorldModels(selected) {
  const model = $('world-model'), wanted = selected || model.value || $('model').value;
  model.replaceChildren(...Array.from($('model').options).filter(o => o.value).map(o => new Option(o.text, o.value)));
  if (wanted && !Array.from(model.options).some(o => o.value === wanted)) model.add(new Option(wanted, wanted));
  if (wanted) model.value = wanted;
}
function growthOptions() { return {model: $('world-model').value, note_budget: Number($('world-note-budget').value), delay: Number($('world-delay').value), time_budget: Number($('world-time-budget').value)}; }
let lastGraphAt = '', growthPolling = false;
function renderGrowth(run) {
  if (!run) return;
  $('growth-status').textContent = `${run.status} · ${run.completed || 0} notes created · ${run.message}${run.output_chars ? ` · ${run.output_chars} characters received` : ''}`;
  $('growth-start').disabled = run.status === 'running' || run.worker_active;
  $('growth-pause').disabled = run.status !== 'running';
  $('growth-stop').disabled = !['running', 'paused'].includes(run.status);
  $('world-save').disabled = !!run.worker_active;
  $('growth-log').innerHTML = (run.log || []).slice().reverse().map(n => `<li><strong>${esc(n.name)}</strong> · ${esc(n.path)} · ${esc(n.model)}</li>`).join('');
}
for (const action of ['start', 'pause', 'stop']) $('growth-' + action).onclick = async () => {
  worldError('');
  try { const result = await worldPost('/api/world/' + action, action === 'start' ? growthOptions() : {}); renderGrowth(result.growth); }
  catch (e) { worldError(e.message); }
};
setInterval(async () => {
  if ($('world-view').hidden || !worldLoaded || growthPolling) return;
  growthPolling = true;
  try {
    const state = await api('/api/world'); renderGrowth(state.growth);
    if (state.graph?.indexed_at !== lastGraphAt) { renderWorldGraph(state.graph); lastGraphAt = state.graph?.indexed_at; }
    if (!$('world-model').options.length) syncWorldModels(state.settings?.model);
  } catch (e) { worldError(e.message); }
  finally { growthPolling = false; }
}, 1500);
