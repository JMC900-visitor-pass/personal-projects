'use strict';

const byId = id => document.getElementById(id);
const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const ROLES = ['', 'minion', 'guard', 'hunter', 'shooter', 'brute', 'boss'];
let token = '';

async function api(path, body) {
  const options = body ? {method: 'POST', headers: {'Content-Type': 'application/json', 'X-Raid-Token': token}, body: JSON.stringify(body)} : {};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed');
  return data;
}

function showError(message) {
  byId('error').hidden = !message;
  byId('error').textContent = message || '';
}

function showPanel(id) {
  document.querySelectorAll('.panel').forEach(panel => panel.hidden = panel.id !== id);
  document.querySelectorAll('.tab').forEach(tab => tab.classList.toggle('active', tab.dataset.panel === id));
}

// Steps from the entrance to every square; walls take the distance of their nearest open neighbour.
function distancesFromEntrance(rows) {
  const height = rows.length, width = rows[0].length;
  const dist = rows.map(row => [...row].map(() => Infinity));
  const start = rows.findIndex(row => row.includes('E'));
  const queue = [[start, rows[start].indexOf('E')]];
  dist[queue[0][0]][queue[0][1]] = 0;
  const around = [[1, 0], [-1, 0], [0, 1], [0, -1]];
  while (queue.length) {
    const [y, x] = queue.shift();
    for (const [dy, dx] of around) {
      const ny = y + dy, nx = x + dx;
      if (ny >= 0 && ny < height && nx >= 0 && nx < width && rows[ny][nx] !== '#' && dist[ny][nx] === Infinity) {
        dist[ny][nx] = dist[y][x] + 1;
        queue.push([ny, nx]);
      }
    }
  }
  return dist.map((row, y) => row.map((value, x) => {
    if (value !== Infinity) return value;
    const near = [...around, [1, 1], [1, -1], [-1, 1], [-1, -1]].map(([dy, dx]) => dist[y + dy]?.[x + dx]).filter(Number.isFinite);
    return near.length ? Math.min(...near) : null;
  }));
}

function renderMap(target, rows, legend, animate = false) {
  const width = rows[0].length;
  const dist = animate ? distancesFromEntrance(rows) : null;
  const deepest = animate ? Math.max(1, ...dist.flat().filter(Number.isFinite)) : 1;
  const step = Math.min(70, 2200 / deepest);
  target.style.setProperty('--columns', width);
  target.style.aspectRatio = `${width}/${rows.length}`;
  target.classList.toggle('reveal', animate);
  const kind = symbol => ({'#':'wall','.':'floor','+':'door','E':'entrance','O':'objective'})[symbol] || 'enemy';
  target.innerHTML = rows.flatMap((row, y) => [...row].map((symbol, x) => {
    const label = legend[symbol] || (symbol === '.' ? 'Open floor' : 'Wall');
    const visible = '.#'.includes(symbol) ? '' : `<b>${escapeHtml(symbol)}</b>`;
    const delay = animate ? ` style="--d:${dist[y][x] === null ? deepest * step : dist[y][x] * step}ms"` : '';
    return `<span class="${kind(symbol)}"${delay} title="${escapeHtml(label)} · ${x + 1},${y + 1}" aria-label="${escapeHtml(label)}">${visible}</span>`;
  })).join('');
  return deepest * step;
}

function renderLegend(legend) {
  byId('legend').innerHTML = Object.entries(legend).map(([symbol, label]) => `<span><b>${escapeHtml(symbol)}</b>${escapeHtml(label)}</span>`).join('');
}

function renderAttack(attack) {
  return `<b>${escapeHtml(attack.name)}</b> · range ${attack.range}<br>
    Hit: ${escapeHtml(attack.test)}<br>
    On hit: roll ${escapeHtml(attack.damage_die)} − target DEF = HP lost (minimum 0).`;
}

function renderMonster(monster) {
  const {stats, attack} = monster;
  return `<article class="monster-card">
    <div><span>${escapeHtml(monster.symbol)} · ${escapeHtml(monster.role)} · ×${monster.count}</span><strong>${escapeHtml(monster.name)}</strong></div>
    <p>${escapeHtml(monster.brief)}</p>
    <dl><div><dt>HP</dt><dd>${stats.hp}</dd></div><div><dt>ATK</dt><dd>${stats.atk}</dd></div><div><dt>SPD</dt><dd>${stats.spd}</dd></div><div><dt>DEF</dt><dd>${stats.def}</dd></div><div><dt>Target TN</dt><dd>${monster.tn}</dd></div></dl>
    <p class="monster-rule">${renderAttack(attack)}</p>
    <p class="monster-rule">${escapeHtml(monster.behaviour)}</p>
  </article>`;
}

function render(packet) {
  const scenario = packet.scenario;
  const base = packet.base_character;
  const generation = packet.generation;
  byId('version').textContent = packet.rules_version;
  byId('scenario-meta').textContent = generation
    ? `${generation.backend.toUpperCase()}${generation.model ? ' · ' + generation.model : ''} · SEED ${generation.seed} · PARTY ${generation.party_size} · ${generation.difficulty.toUpperCase()} · THREAT ${generation.threat_total}/${generation.threat_budget}`
    : 'BUNDLED EXAMPLE';
  byId('scenario-name').textContent = scenario.name;
  byId('story').textContent = scenario.story;
  byId('objective').textContent = scenario.objective;
  byId('completion').textContent = scenario.completion;
  renderMap(byId('map'), scenario.map, scenario.legend);
  renderLegend(scenario.legend);
  byId('monsters').innerHTML = packet.monsters.map(renderMonster).join('');
  byId('base-stats').innerHTML = Object.entries(base.stats).map(([name, value]) => `<article><span>${escapeHtml(name.toUpperCase())}</span><strong>${value}</strong></article>`).join('');
  byId('base-stats').innerHTML += `<article><span>Target TN</span><strong>${base.tn}</strong></article>`;
  byId('combat-rules').innerHTML = Object.entries(packet.combat_rules).map(([name, rule]) =>
    `<p><b>${escapeHtml(name === 'damage' ? 'Damage' : name.toUpperCase())}:</b> ${escapeHtml(rule)}</p>`).join('');
  byId('level-rule').textContent = `${base.rule} ${packet.level_up.trigger} Everyone who started, including Down or removed characters, gains +${packet.level_up.levels_gained} Level and +${packet.level_up.build_points_gained} Build Point once per victory. Level caps at ${packet.level_up.maximum_level}; Build Points continue. A loss grants neither.`;
  byId('basic-attack').innerHTML = `<span>STARTING ACTION</span><p>${renderAttack(base.attack)}</p>`;
  byId('choices').innerHTML = packet.level_up.choices.map(choice => `<article class="choice ${choice.available === false ? 'locked' : ''}"><span>${escapeHtml(choice.track)}</span><strong>${escapeHtml(choice.name)}</strong><p>${escapeHtml(choice.effect)}</p>${choice.available === false ? '<small>LATER PASS</small>' : '<small>1 BUILD POINT</small>'}</article>`).join('');
}

function inlineMarkdown(value) {
  return escapeHtml(value)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+?)\*/g, '<em>$1</em>');
}

function tableRow(line) {
  return line.trim().replace(/^\||\|$/g, '').split('|').map(cell => cell.trim());
}

function isTableDivider(line) {
  return tableRow(line).every(cell => /^:?-{3,}:?$/.test(cell));
}

function markdownToHtml(markdown) {
  const lines = markdown.replace(/\r/g, '').split('\n');
  const html = [];
  let paragraph = [];
  let list = null;
  const flushParagraph = () => {
    if (paragraph.length) html.push(`<p>${inlineMarkdown(paragraph.join(' '))}</p>`);
    paragraph = [];
  };
  const closeList = () => {
    if (list) html.push(`</${list}>`);
    list = null;
  };
  const flush = () => { flushParagraph(); closeList(); };

  for (let index = 0; index < lines.length; index += 1) {
    const line = lines[index];
    if (!line.trim()) { flush(); continue; }
    if (/^\|.*\|$/.test(line) && index + 1 < lines.length && isTableDivider(lines[index + 1])) {
      flush();
      const header = tableRow(line);
      const rows = [];
      index += 2;
      while (index < lines.length && /^\|.*\|$/.test(lines[index])) {
        rows.push(tableRow(lines[index]));
        index += 1;
      }
      index -= 1;
      html.push(`<div class="rules-table-wrap"><table><thead><tr>${header.map(cell => `<th>${inlineMarkdown(cell)}</th>`).join('')}</tr></thead><tbody>${rows.map(row => `<tr>${row.map(cell => `<td>${inlineMarkdown(cell)}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
      continue;
    }
    const heading = line.match(/^(#{1,3})\s+(.+)$/);
    if (heading) {
      flush();
      const level = Math.min(heading[1].length + 1, 4);
      html.push(`<h${level}>${inlineMarkdown(heading[2])}</h${level}>`);
      continue;
    }
    if (/^---+$/.test(line.trim())) {
      flush();
      html.push('<hr>');
      continue;
    }
    const bullet = line.match(/^[-*]\s+(.+)$/);
    const numbered = line.match(/^\d+\.\s+(.+)$/);
    if (bullet || numbered) {
      flushParagraph();
      const type = bullet ? 'ul' : 'ol';
      if (list !== type) { closeList(); html.push(`<${type}>`); list = type; }
      html.push(`<li>${inlineMarkdown((bullet || numbered)[1])}</li>`);
      continue;
    }
    closeList();
    paragraph.push(line.trim());
  }
  flush();
  return html.join('');
}

async function loadRules() {
  try {
    const {markdown} = await api('/api/rules');
    byId('rules-content').innerHTML = markdownToHtml(markdown);
  } catch (error) {
    byId('rules-content').textContent = `Could not load the rules: ${error.message}`;
  }
}

async function loadSaved(selected) {
  const entries = await api('/api/skirmishes');
  byId('saved').innerHTML = entries.map(entry => `<option value="${escapeHtml(entry.id)}">${escapeHtml(entry.name)} · ${entry.monsters} monsters</option>`).join('');
  byId('saved').value = selected || entries[0].id;
  render(await api('/api/skirmishes/' + encodeURIComponent(byId('saved').value)));
}

function addMonsterRow(name = '', count = '', role = '') {
  const row = document.createElement('div');
  row.className = 'monster-row';
  row.innerHTML = `<input class="m-name" maxlength="60" placeholder="Exact name, e.g. Zombie" aria-label="Monster name" value="${escapeHtml(name)}">
    <input class="m-count" type="number" min="1" max="8" placeholder="Qty" aria-label="Quantity" value="${escapeHtml(count)}">
    <select class="m-role" aria-label="Role">${ROLES.map(r => `<option value="${r}" ${r === role ? 'selected' : ''}>${r || 'Role: auto'}</option>`).join('')}</select>
    <button type="button" class="ghost remove" aria-label="Remove monster">×</button>`;
  byId('monster-rows').append(row);
}

async function loadModels() {
  try {
    const status = await api('/api/models');
    byId('model-status').textContent = status.available ? `Ollama · ${status.models.length} local models` : 'Ollama offline · templates only';
    byId('model-dot').classList.toggle('off', !status.available);
    byId('model').innerHTML = status.models.map(m => `<option>${escapeHtml(m)}</option>`).join('') || '<option value="">No local models</option>';
    if (!status.available) byId('backend').querySelector('[value=ollama]').disabled = true;
  } catch (error) {
    byId('model-status').textContent = 'Model check failed';
  }
}

document.addEventListener('click', event => {
  const tab = event.target.closest('[data-panel]');
  if (tab) showPanel(tab.dataset.panel);
  if (event.target.closest('.remove')) event.target.closest('.monster-row').remove();
});
byId('add-monster').addEventListener('click', () => addMonsterRow());
byId('saved').addEventListener('change', async () => {
  try { showError(); render(await api('/api/skirmishes/' + encodeURIComponent(byId('saved').value))); }
  catch (error) { showError(error.message); }
});

byId('brief-form').addEventListener('submit', async event => {
  event.preventDefault();
  const button = byId('generate');
  const monsters = [...document.querySelectorAll('.monster-row')].map(row => ({
    name: row.querySelector('.m-name').value, count: row.querySelector('.m-count').value || null, role: row.querySelector('.m-role').value || null,
  })).filter(monster => monster.name.trim());
  button.disabled = true;
  button.textContent = 'Forging…';
  showError();
  try {
    const {job_id} = await api('/api/generate', {
      concept: byId('concept').value, title: byId('title').value, seed: byId('seed').value || null, monsters,
      party_size: byId('party').value, difficulty: byId('difficulty').value, backend: byId('backend').value,
      model: byId('model').value, think: byId('think').checked,
    });
    watchJob(job_id, byId('backend').value === 'ollama' ? byId('model').value : null);
    showPanel('forge');
  } catch (error) {
    showError(error.message);
    button.disabled = false;
    button.textContent = 'Generate skirmish →';
  }
});

// ---------------------------------------------------------------- live forge

const forge = {started: 0, clock: null, steps: {}, tokens: 0, firstToken: 0, thinking: 0, savedId: null};

function clockText(ms) {
  const seconds = Math.floor(ms / 1000);
  return `${String(Math.floor(seconds / 60)).padStart(2, '0')}:${String(seconds % 60).padStart(2, '0')}`;
}

function appendTo(id, text) {
  const element = byId(id);
  const follow = element.scrollHeight - element.scrollTop - element.clientHeight < 40;
  element.append(text);
  if (follow) element.scrollTop = element.scrollHeight;
}

function typeOut(id, text, speed = 12) {
  return new Promise(resolve => {
    let index = 0;
    const tick = () => {
      appendTo(id, text.slice(index, index + 3));
      index += 3;
      index < text.length ? setTimeout(tick, speed) : resolve();
    };
    tick();
  });
}

function renderSteps() {
  byId('steps').innerHTML = Object.entries(forge.steps).map(([id, step]) => {
    const took = step.finished ? ` · ${((step.finished - step.began) / 1000).toFixed(1)}s` : step.began ? ` · ${clockText(Date.now() - step.began)}` : '';
    return `<li class="${step.status}"><b></b><span>${escapeHtml(step.label)}<small>${escapeHtml(step.detail || '')}${took}</small></span></li>`;
  }).join('');
}

function renderChips(monsters) {
  byId('roster-chips').innerHTML = monsters.map(m => `<span class="chip ${m.role || ''}">${m.symbol ? `<b>${escapeHtml(m.symbol)}</b>` : ''}${escapeHtml(m.name)}<small>${escapeHtml(m.role || 'role pending')}${m.count ? ' ×' + m.count : ''}</small></span>`).join('');
}

function resetForge(model) {
  Object.assign(forge, {started: Date.now(), steps: {}, tokens: 0, firstToken: 0, thinking: 0, savedId: null, model});
  ['output', 'thinking', 'agent-log'].forEach(id => byId(id).textContent = '');
  byId('output').classList.add('cursor');
  byId('thinking-console').hidden = true;
  byId('forge-map-card').hidden = true;
  byId('forge-done').hidden = true;
  byId('roster-chips').innerHTML = '';
  byId('token-rate').textContent = '';
  byId('output-label').textContent = model ? `MODEL OUTPUT · ${model}` : 'WRITER OUTPUT · OFFLINE TEMPLATES';
  byId('forge-title').textContent = 'Forging…';
  byId('forge-dot').hidden = false;
  clearInterval(forge.clock);
  forge.clock = setInterval(() => {
    byId('forge-clock').textContent = clockText(Date.now() - forge.started);
    renderSteps();
  }, 250);
}

function finishForge() {
  clearInterval(forge.clock);
  renderSteps();
  byId('forge-dot').hidden = true;
  byId('output').classList.remove('cursor');
  byId('generate').disabled = false;
  byId('generate').textContent = 'Generate skirmish →';
}

const handlers = {
  plan(event) {
    for (const step of [...event.steps, {id: 'save', label: 'Save to the library'}]) forge.steps[step.id] = {label: step.label, status: 'pending'};
    byId('forge-meta').textContent = `GENERATION AGENT · ${event.writer.toUpperCase()} · SEED ${event.seed}`;
    renderSteps();
  },
  step(event) {
    const step = forge.steps[event.id];
    if (!step) return;
    step.status = event.status;
    step.detail = event.detail;
    if (event.status === 'running') step.began = Date.now();
    if (event.status === 'done') step.finished = Date.now();
    renderSteps();
  },
  log(event) { appendTo('agent-log', `› ${event.text}\n`); },
  token(event) {
    if (event.channel === 'thinking') {
      byId('thinking-console').hidden = false;
      forge.thinking += 1;
      byId('thinking-count').textContent = `${forge.thinking} tokens`;
      appendTo('thinking', event.text);
      return;
    }
    if (forge.streamStep !== event.step) {
      appendTo('output', `${byId('output').textContent ? '\n\n' : ''}── ${event.step === 'roster' ? 'proposing monsters' : 'writing story and cards'} ──\n`);
      forge.streamStep = event.step;
    }
    forge.tokens += 1;
    forge.firstToken ||= Date.now();
    const seconds = (Date.now() - forge.firstToken) / 1000;
    byId('token-rate').textContent = `${forge.tokens} tokens${seconds > 1 ? ` · ${(forge.tokens / seconds).toFixed(1)}/s` : ''}`;
    appendTo('output', event.text);
  },
  roster(event) { renderChips(event.monsters); },
  scenario(event) {
    byId('forge-title').textContent = event.name;
    if (!forge.model) typeOut('output', `${event.name}\n\n${event.story}\n\nObjective: ${event.goal}\n`);
  },
  map(event) {
    byId('forge-map-card').hidden = false;
    byId('forge-map-size').textContent = `${event.map[0].length} × ${event.map.length}`;
    renderMap(byId('forge-map'), event.map, event.legend, true);
  },
  async complete(event) {
    forge.savedId = event.saved_id;
    finishForge();
    byId('forge-done').hidden = false;
    await loadSaved(event.saved_id);
  },
  error(event) {
    const running = Object.values(forge.steps).find(step => step.status === 'running');
    if (running) { running.status = 'error'; running.detail = 'failed'; }
    appendTo('agent-log', `✗ ${event.message}\n`);
    byId('forge-title').textContent = 'Generation failed';
    finishForge();
    showError(event.message);
  },
};

function watchJob(jobId, model) {
  resetForge(model);
  forge.streamStep = null;
  const source = new EventSource(`/api/jobs/${encodeURIComponent(jobId)}/events`);
  source.onmessage = message => {
    const event = JSON.parse(message.data);
    handlers[event.type]?.(event);
    if (event.type === 'complete' || event.type === 'error') source.close();
  };
  // No auto-reconnect: the server replays every event, which would duplicate the output.
  source.onerror = () => {
    source.close();
    if (!byId('forge-dot').hidden) handlers.error({message: 'Lost connection to the generator. Is the server still running?'});
  };
}

byId('open-result').addEventListener('click', () => {
  byId('saved').value = forge.savedId;
  byId('saved').dispatchEvent(new Event('change'));
  showPanel('skirmish');
});

(async () => {
  addMonsterRow('Zombie', '', '');
  try {
    token = (await api('/api/session')).token;
    await Promise.all([loadSaved(), loadModels(), loadRules()]);
  } catch (error) {
    showError(error.message);
  }
})();
