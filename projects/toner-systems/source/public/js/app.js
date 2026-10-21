(function () {
  'use strict';

  const $ = (s, el) => (el || document).querySelector(s);
  const $$ = (s, el) => [...(el || document).querySelectorAll(s)];
  const app = document.getElementById('app');

  let me = null;
  let page = 'new';
  let queueFilter = '';
  let editingId = null;

  // ---- helpers ---------------------------------------------------------------
  function esc(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
  }

  function fmtDate(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return '';
    return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' }) +
      ', ' + d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  }

  async function api(method, url, body) {
    const opts = { method, headers: {} };
    if (body !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(body);
    }
    const res = await fetch(url, opts);
    const text = await res.text();
    const data = text ? JSON.parse(text) : null;
    if (!res.ok) throw new Error((data && data.error) || `Request failed (${res.status})`);
    return data;
  }

  function flash(type, msg) {
    const el = $('#flash');
    if (!el) return;
    const icon = type === 'error' ? '✕' : '✓';
    el.innerHTML = `<div class="flash flash--${type === 'error' ? 'err' : 'ok'}">${icon}&ensp;${esc(msg)}</div>`;
    if (type !== 'error') setTimeout(() => { if (el) el.innerHTML = ''; }, 3500);
  }

  function clearFlash() { const el = $('#flash'); if (el) el.innerHTML = ''; }

  function printerOpts(printers, selectedId) {
    const none = `<option value="">— None —</option>`;
    return none + printers.map(p =>
      `<option value="${p.id}" ${p.id == selectedId ? 'selected' : ''}>${esc(p.name)}</option>`
    ).join('');
  }

  // ---- login page ------------------------------------------------------------
  async function showLogin() {
    const users = await api('GET', '/api/users');
    const opts = users.map(u => `<option value="${u.id}">${esc(u.full_name)} (${esc(u.username)})</option>`).join('');

    app.innerHTML = `
      <div class="login-page">
        <div class="login-card">
          <svg class="login-card__logo" viewBox="0 0 56 56" fill="none">
            <rect x="6" y="18" width="44" height="22" rx="5" fill="#4f46e5"/>
            <rect x="16" y="10" width="16" height="10" rx="3" fill="#312e81"/>
            <circle cx="40" cy="29" r="3" fill="#e0e7ff"/>
          </svg>
          <div class="login-card__title">Toner Desk</div>
          <div class="login-card__sub">Select your name to sign in</div>
          <select id="loginUser">
            <option value="" disabled selected>Choose your name…</option>
            ${opts}
          </select>
          <button class="btn btn--primary" id="loginBtn">Sign in</button>
        </div>
      </div>`;

    $('#loginBtn').addEventListener('click', async () => {
      const userId = parseInt($('#loginUser').value, 10);
      if (!userId) return;
      try {
        me = await api('POST', '/api/login', { userId });
        render();
      } catch (e) { alert(e.message); }
    });
  }

  // ---- main layout -----------------------------------------------------------
  function render() {
    if (!me) { showLogin(); return; }
    clearFlash();

    const adminLinks = me.isAdmin ? `
      <a class="topbar__link ${page === 'queue'    ? 'active' : ''}" data-page="queue">Queue</a>
      <a class="topbar__link ${page === 'rooms'    ? 'active' : ''}" data-page="rooms">Rooms</a>
      <a class="topbar__link ${page === 'printers' ? 'active' : ''}" data-page="printers">Printers</a>
      <a class="topbar__link ${page === 'toners'   ? 'active' : ''}" data-page="toners">Toners</a>
      <a class="topbar__link ${page === 'users'    ? 'active' : ''}" data-page="users">Users</a>
    ` : '';

    app.innerHTML = `
      <header class="topbar">
        <a class="topbar__brand" data-page="new" style="cursor:pointer">
          <svg viewBox="0 0 32 32"><rect x="3" y="10" width="26" height="13" rx="3" fill="#fff"/>
          <rect x="9" y="5" width="10" height="6" rx="1.5" fill="rgba(255,255,255,.5)"/>
          <circle cx="23" cy="16.5" r="2" fill="#4f46e5"/></svg>
          Toner Desk
        </a>
        <button class="topbar__toggle" id="menuToggle">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
            <path d="M3 6h18M3 12h18M3 18h18"/>
          </svg>
        </button>
        <nav class="topbar__nav" id="topNav">
          <a class="topbar__link ${page === 'new' ? 'active' : ''}" data-page="new">New Request</a>
          ${adminLinks}
          <div class="topbar__user">
            <span class="topbar__user-name">${esc(me.fullName)}</span>
            ${me.isAdmin ? '<span class="badge badge--admin">Admin</span>' : ''}
            <button class="topbar__logout" id="logoutBtn">Sign out</button>
          </div>
        </nav>
      </header>
      <div class="page">
        <div id="flash"></div>
        <div id="view"></div>
      </div>`;

    $$('[data-page]').forEach(el => {
      el.addEventListener('click', e => {
        e.preventDefault();
        page = el.dataset.page;
        editingId = null;
        render();
      });
    });

    $('#logoutBtn').addEventListener('click', async () => {
      await api('POST', '/api/logout');
      me = null; page = 'new'; render();
    });

    $('#menuToggle').addEventListener('click', () => {
      $('#topNav').classList.toggle('open');
    });

    const adminPages = ['queue', 'rooms', 'printers', 'toners', 'users'];
    if (!me.isAdmin && adminPages.includes(page)) { page = 'new'; }

    const pages = { new: pageNew, queue: pageQueue, rooms: pageRooms, printers: pagePrinters, toners: pageToners, users: pageUsers };
    (pages[page] || pageNew)();
  }

  // ---- page: new request -----------------------------------------------------
  async function pageNew() {
    const v = $('#view');
    v.innerHTML = '<div class="empty">Loading…</div>';

    try {
      const [rooms, mine, toners] = await Promise.all([
        api('GET', '/api/rooms'),
        api('GET', '/api/requests/mine'),
        api('GET', '/api/toner-types')
      ]);

      function buildTonerOpts(filteredToners) {
        if (!filteredToners.length) return '<option value="" disabled selected>No toners for this printer</option>';
        return '<option value="" disabled selected>Choose a toner…</option>' +
          filteredToners.map(t =>
            `<option value="${t.id}">${esc(t.name)}${t.model_number ? ' (' + esc(t.model_number) + ')' : ''}</option>`
          ).join('');
      }

      const recentHtml = mine.length
        ? `<ul class="req-list">${mine.map(r => `
            <li class="req-item">
              <div class="req-item__main">
                <span class="req-item__toner">${esc(r.toner_name)}</span>
                <span class="req-item__room">${esc(r.room_name)}</span>
                ${r.notes ? `<span class="req-item__notes">${esc(r.notes)}</span>` : ''}
              </div>
              <div class="req-item__meta">
                <span class="badge badge--${r.status === 'Completed' ? 'done' : 'pending'}">${r.status}</span>
                <span class="req-item__date">${fmtDate(r.created_at)}</span>
              </div>
            </li>`).join('')}</ul>`
        : '<div class="empty"><span class="empty__icon">📋</span>No requests yet — submit your first one above!</div>';

      v.innerHTML = `
        <div class="card card--accent">
          <div class="card__title">Request Toner</div>
          <div class="card__subtitle">Pick the room and toner you need. IT will handle the rest.</div>
          <form id="reqForm">
            <div class="form-row">
              <div class="form-group">
                <label>Room</label>
                <div class="combo" id="roomCombo">
                  <input id="fRoom" type="text" placeholder="Search rooms…" autocomplete="off" role="combobox" aria-expanded="false" aria-haspopup="listbox">
                  <button class="combo__arrow" type="button" tabindex="-1" aria-label="Show all rooms">
                    <svg viewBox="0 0 20 20" fill="currentColor" width="16" height="16"><path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/></svg>
                  </button>
                  <ul class="combo__list" id="roomDropdown" role="listbox" hidden></ul>
                </div>
              </div>
              <div class="form-group">
                <label>Toner Type</label>
                <select id="fToner" required disabled>
                  <option value="" disabled selected>Pick a room first…</option>
                </select>
              </div>
            </div>
            <div class="form-group">
              <label>Notes <span class="opt">(optional)</span></label>
              <textarea id="fNotes" rows="2" maxlength="1000" placeholder="e.g. Completely out, urgent"></textarea>
            </div>
            <button type="submit" class="btn btn--primary">Submit Request</button>
          </form>
        </div>
        <div class="card">
          <div class="card__title">Your Recent Requests</div>
          ${recentHtml}
        </div>`;

      // ---- room combobox ----
      let selectedRoomId = null;
      const roomInput   = document.getElementById('fRoom');
      const roomDropdown = document.getElementById('roomDropdown');
      const roomCombo   = document.getElementById('roomCombo');
      const roomArrow   = roomCombo.querySelector('.combo__arrow');
      const tonerSel    = document.getElementById('fToner');

      function roomLabel(r) { return r.name + (r.building ? ' \u2014 ' + r.building : ''); }

      function openRoomDropdown(filter) {
        const q = (filter || '').toLowerCase().trim();
        const filtered = q ? rooms.filter(r => roomLabel(r).toLowerCase().includes(q)) : rooms;
        roomDropdown.innerHTML = filtered.length
          ? filtered.map(r => `<li class="combo__item" role="option" data-id="${r.id}">${esc(roomLabel(r))}</li>`).join('')
          : '<li class="combo__none">No rooms match</li>';
        roomDropdown.hidden = false;
        roomInput.setAttribute('aria-expanded', 'true');
        roomArrow.classList.add('combo__arrow--open');
      }

      function closeRoomDropdown() {
        roomDropdown.hidden = true;
        roomInput.setAttribute('aria-expanded', 'false');
        roomArrow.classList.remove('combo__arrow--open');
      }

      function selectRoom(roomId) {
        selectedRoomId = roomId;
        const room = rooms.find(r => r.id === roomId);
        // Filter toners to those matching this room's printer
        const filtered = (room && room.printer_id != null)
          ? toners.filter(t => t.printer_id == room.printer_id)
          : toners;
        tonerSel.innerHTML = buildTonerOpts(filtered);
        tonerSel.disabled = false;
      }

      roomInput.addEventListener('focus', () => openRoomDropdown(roomInput.value));
      roomInput.addEventListener('click', () => openRoomDropdown(roomInput.value));
      roomInput.addEventListener('input', () => {
        selectedRoomId = null;
        tonerSel.innerHTML = '<option value="" disabled selected>Pick a room first…</option>';
        tonerSel.disabled = true;
        openRoomDropdown(roomInput.value);
      });
      roomInput.addEventListener('blur', () => setTimeout(closeRoomDropdown, 150));

      roomArrow.addEventListener('click', () => {
        if (roomDropdown.hidden) { roomInput.focus(); openRoomDropdown(''); }
        else { roomInput.focus(); closeRoomDropdown(); }
      });

      roomDropdown.addEventListener('mousedown', e => {
        const li = e.target.closest('.combo__item');
        if (!li) return;
        e.preventDefault();
        roomInput.value = li.textContent;
        selectRoom(parseInt(li.dataset.id));
        closeRoomDropdown();
      });

      roomInput.addEventListener('keydown', e => {
        if (e.key === 'Escape') { closeRoomDropdown(); return; }
        if (e.key === 'ArrowDown') {
          e.preventDefault();
          if (roomDropdown.hidden) openRoomDropdown('');
          roomDropdown.querySelector('.combo__item')?.focus();
        }
      });

      roomDropdown.addEventListener('keydown', e => {
        const items = [...roomDropdown.querySelectorAll('.combo__item')];
        const idx = items.indexOf(document.activeElement);
        if (e.key === 'ArrowDown') { e.preventDefault(); items[idx + 1]?.focus(); }
        else if (e.key === 'ArrowUp') { e.preventDefault(); idx > 0 ? items[idx - 1].focus() : roomInput.focus(); }
        else if (e.key === 'Enter' && idx >= 0) {
          e.preventDefault();
          roomInput.value = items[idx].textContent;
          selectRoom(parseInt(items[idx].dataset.id));
          closeRoomDropdown();
          roomInput.focus();
        }
        else if (e.key === 'Escape') { closeRoomDropdown(); roomInput.focus(); }
      });

      // ---- form submit ----
      $('#reqForm').addEventListener('submit', async e => {
        e.preventDefault();
        const tonerTypeId = parseInt(tonerSel.value, 10);
        const notes = $('#fNotes').value.trim();
        if (!selectedRoomId || !tonerTypeId) { flash('error', 'Pick a room and toner.'); return; }
        const btn = e.target.querySelector('button[type="submit"]');
        btn.disabled = true;
        try {
          await api('POST', '/api/requests', { roomId: selectedRoomId, tonerTypeId, notes: notes || null });
          flash('ok', 'Request submitted! IT will handle it from here.');
          await pageNew();
        } catch (err) { btn.disabled = false; flash('error', err.message); }
      });

    } catch (err) { v.innerHTML = `<div class="empty">Error loading: ${esc(err.message)}</div>`; }
  }

  // ---- page: admin queue -----------------------------------------------------
  async function pageQueue() {
    const v = $('#view');
    v.innerHTML = '<div class="empty">Loading…</div>';

    try {
      const qs = queueFilter ? `?status=${queueFilter}` : '';
      const data = await api('GET', `/api/admin/requests${qs}`);
      const c = data.counts;

      const tabHtml = (label, val, count) => {
        const active = queueFilter === val ? ' active' : '';
        return `<button class="tab${active}" data-filter="${val}">${label} <span class="tab__count">${count}</span></button>`;
      };

      const rowsHtml = data.requests.length
        ? `<div class="table-wrap"><table>
            <thead><tr><th>#</th><th>Date</th><th>Requested By</th><th>Room</th><th>Toner</th><th>Notes</th><th>Status</th><th>Action</th></tr></thead>
            <tbody>${data.requests.map(r => {
              const action = r.status === 'Pending'
                ? `<button class="btn btn--success btn--sm" data-complete="${r.id}">✓ Complete</button>`
                : `<button class="btn btn--ghost btn--sm" data-reopen="${r.id}">↩ Reopen</button>`;
              return `<tr>
                <td>${r.id}</td>
                <td style="white-space:nowrap">${fmtDate(r.created_at)}</td>
                <td>${esc(r.requested_by_name)}</td>
                <td>${esc(r.room_name)}</td>
                <td>${esc(r.toner_name)}${r.model_number ? `<br><small style="color:var(--gray-400)">${esc(r.model_number)}</small>` : ''}</td>
                <td>${r.notes ? esc(r.notes) : '—'}</td>
                <td><span class="badge badge--${r.status === 'Completed' ? 'done' : 'pending'}">${r.status}</span></td>
                <td class="td-actions">${action}</td>
              </tr>`;
            }).join('')}</tbody></table></div>`
        : '<div class="empty"><span class="empty__icon">📭</span>No requests here.</div>';

      v.innerHTML = `
        <div class="card">
          <div class="card__title">Request Queue</div>
          <div class="card__subtitle">All toner requests from staff</div>
          <div class="tabs">
            ${tabHtml('All', '', c.total)}
            ${tabHtml('Pending', 'Pending', c.pending)}
            ${tabHtml('Completed', 'Completed', c.completed)}
          </div>
          ${rowsHtml}
        </div>`;

      $$('[data-filter]', v).forEach(b => b.addEventListener('click', () => { queueFilter = b.dataset.filter; pageQueue(); }));
      $$('[data-complete]', v).forEach(b => b.addEventListener('click', async () => {
        try { await api('POST', `/api/admin/requests/${b.dataset.complete}/complete`); flash('ok', 'Marked complete.'); pageQueue(); }
        catch (e) { flash('error', e.message); }
      }));
      $$('[data-reopen]', v).forEach(b => b.addEventListener('click', async () => {
        try { await api('POST', `/api/admin/requests/${b.dataset.reopen}/reopen`); flash('ok', 'Reopened.'); pageQueue(); }
        catch (e) { flash('error', e.message); }
      }));
    } catch (err) { v.innerHTML = `<div class="empty">Error: ${esc(err.message)}</div>`; }
  }

  // ---- page: admin rooms (custom — needs printer dropdown) -------------------
  async function pageRooms() {
    const v = $('#view');
    v.innerHTML = '<div class="empty">Loading…</div>';

    try {
      const [items, printers] = await Promise.all([
        api('GET', '/api/rooms?all=1'),
        api('GET', '/api/printers')
      ]);

      const rowsHtml = items.length
        ? `<div class="table-wrap"><table>
            <thead><tr><th>Room Name</th><th>Building</th><th>Printer</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>${items.map(item => {
              if (editingId === item.id) {
                return `<tr class="edit-row">
                  <td><input id="edName" type="text" value="${esc(item.name)}" maxlength="100"></td>
                  <td><input id="edCol2" type="text" value="${esc(item.building || '')}" maxlength="100"></td>
                  <td><select id="edPrinter">${printerOpts(printers, item.printer_id)}</select></td>
                  <td><label><input id="edActive" type="checkbox" ${item.is_active ? 'checked' : ''}> Active</label></td>
                  <td class="td-actions">
                    <button class="btn btn--primary btn--sm" data-save="${item.id}">Save</button>
                    <button class="btn btn--ghost btn--sm" data-cancel>Cancel</button>
                  </td>
                </tr>`;
              }
              return `<tr class="${item.is_active ? '' : 'inactive'}">
                <td>${esc(item.name)}</td>
                <td>${item.building ? esc(item.building) : '—'}</td>
                <td>${item.printer_name ? esc(item.printer_name) : '<span style="color:var(--gray-400)">None</span>'}</td>
                <td><span class="badge badge--${item.is_active ? 'done' : 'muted'}">${item.is_active ? 'Active' : 'Hidden'}</span></td>
                <td class="td-actions">
                  <button class="btn btn--ghost btn--sm" data-edit="${item.id}">Edit</button>
                  <button class="btn btn--ghost btn--sm" data-toggle="${item.id}">${item.is_active ? 'Hide' : 'Show'}</button>
                </td>
              </tr>`;
            }).join('')}</tbody></table></div>`
        : '<div class="empty"><span class="empty__icon">📦</span>No rooms yet. Add one above.</div>';

      v.innerHTML = `
        <div class="card card--accent">
          <div class="card__title">Add Room</div>
          <div class="inline-add">
            <div class="form-group"><label>Room Name</label><input id="addName" type="text" maxlength="100" placeholder="e.g. Room 203"></div>
            <div class="form-group"><label>Building <span class="opt">(optional)</span></label><input id="addCol2" type="text" maxlength="100" placeholder="e.g. Main Building"></div>
            <div class="form-group"><label>Printer <span class="opt">(optional)</span></label><select id="addPrinter">${printerOpts(printers, null)}</select></div>
            <button class="btn btn--primary" id="addBtn">Add</button>
          </div>
        </div>
        <div class="card">
          <div class="card__title">All Rooms</div>
          ${rowsHtml}
        </div>`;

      $('#addBtn').addEventListener('click', async () => {
        const name      = $('#addName').value.trim();
        const building  = $('#addCol2').value.trim();
        const printer_id = parseInt($('#addPrinter').value) || null;
        if (!name) { flash('error', 'Enter a room name.'); return; }
        try { await api('POST', '/api/rooms', { name, building: building || null, printer_id }); flash('ok', `${name} added.`); pageRooms(); }
        catch (e) { flash('error', e.message); }
      });

      $$('[data-edit]', v).forEach(b => b.addEventListener('click', () => { editingId = parseInt(b.dataset.edit); pageRooms(); }));
      $$('[data-cancel]', v).forEach(b => b.addEventListener('click', () => { editingId = null; pageRooms(); }));
      $$('[data-save]', v).forEach(b => b.addEventListener('click', async () => {
        const name      = $('#edName').value.trim();
        const building  = $('#edCol2').value.trim();
        const is_active = $('#edActive').checked;
        const printer_id = parseInt($('#edPrinter').value) || null;
        if (!name) { flash('error', 'Name required.'); return; }
        try {
          await api('PUT', `/api/rooms/${b.dataset.save}`, { name, building: building || null, is_active, printer_id });
          editingId = null; flash('ok', 'Saved.'); pageRooms();
        } catch (e) { flash('error', e.message); }
      }));
      $$('[data-toggle]', v).forEach(b => b.addEventListener('click', async () => {
        try { await api('POST', `/api/rooms/${b.dataset.toggle}/toggle`); pageRooms(); }
        catch (e) { flash('error', e.message); }
      }));
    } catch (err) { v.innerHTML = `<div class="empty">Error: ${esc(err.message)}</div>`; }
  }

  // ---- page: admin printers --------------------------------------------------
  async function pagePrinters() {
    const v = $('#view');
    v.innerHTML = '<div class="empty">Loading…</div>';

    try {
      const items = await api('GET', '/api/printers?all=1');

      const rowsHtml = items.length
        ? `<div class="table-wrap"><table>
            <thead><tr><th>Printer Model</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>${items.map(item => {
              if (editingId === item.id) {
                return `<tr class="edit-row">
                  <td><input id="edName" type="text" value="${esc(item.name)}" maxlength="100"></td>
                  <td><label><input id="edActive" type="checkbox" ${item.is_active ? 'checked' : ''}> Active</label></td>
                  <td class="td-actions">
                    <button class="btn btn--primary btn--sm" data-save="${item.id}">Save</button>
                    <button class="btn btn--ghost btn--sm" data-cancel>Cancel</button>
                  </td>
                </tr>`;
              }
              return `<tr class="${item.is_active ? '' : 'inactive'}">
                <td>${esc(item.name)}</td>
                <td><span class="badge badge--${item.is_active ? 'done' : 'muted'}">${item.is_active ? 'Active' : 'Hidden'}</span></td>
                <td class="td-actions">
                  <button class="btn btn--ghost btn--sm" data-edit="${item.id}">Edit</button>
                  <button class="btn btn--ghost btn--sm" data-toggle="${item.id}">${item.is_active ? 'Hide' : 'Show'}</button>
                </td>
              </tr>`;
            }).join('')}</tbody></table></div>`
        : '<div class="empty"><span class="empty__icon">🖨️</span>No printers yet. Add one above.</div>';

      v.innerHTML = `
        <div class="card card--accent">
          <div class="card__title">Add Printer</div>
          <div class="inline-add">
            <div class="form-group"><label>Printer Model</label><input id="addName" type="text" maxlength="100" placeholder="e.g. HP Color LaserJet Pro M254"></div>
            <button class="btn btn--primary" id="addBtn">Add</button>
          </div>
        </div>
        <div class="card">
          <div class="card__title">All Printers</div>
          ${rowsHtml}
        </div>`;

      $('#addBtn').addEventListener('click', async () => {
        const name = $('#addName').value.trim();
        if (!name) { flash('error', 'Enter a printer model name.'); return; }
        try { await api('POST', '/api/printers', { name }); flash('ok', `${name} added.`); pagePrinters(); }
        catch (e) { flash('error', e.message); }
      });

      $$('[data-edit]', v).forEach(b => b.addEventListener('click', () => { editingId = parseInt(b.dataset.edit); pagePrinters(); }));
      $$('[data-cancel]', v).forEach(b => b.addEventListener('click', () => { editingId = null; pagePrinters(); }));
      $$('[data-save]', v).forEach(b => b.addEventListener('click', async () => {
        const name      = $('#edName').value.trim();
        const is_active = $('#edActive').checked;
        if (!name) { flash('error', 'Name required.'); return; }
        try {
          await api('PUT', `/api/printers/${b.dataset.save}`, { name, is_active });
          editingId = null; flash('ok', 'Saved.'); pagePrinters();
        } catch (e) { flash('error', e.message); }
      }));
      $$('[data-toggle]', v).forEach(b => b.addEventListener('click', async () => {
        try { await api('POST', `/api/printers/${b.dataset.toggle}/toggle`); pagePrinters(); }
        catch (e) { flash('error', e.message); }
      }));
    } catch (err) { v.innerHTML = `<div class="empty">Error: ${esc(err.message)}</div>`; }
  }

  // ---- page: admin toners (custom — needs printer dropdown) ------------------
  async function pageToners() {
    const v = $('#view');
    v.innerHTML = '<div class="empty">Loading…</div>';

    try {
      const [items, printers] = await Promise.all([
        api('GET', '/api/toner-types?all=1'),
        api('GET', '/api/printers')
      ]);

      const rowsHtml = items.length
        ? `<div class="table-wrap"><table>
            <thead><tr><th>Toner Name</th><th>Model #</th><th>Printer</th><th>Status</th><th>Actions</th></tr></thead>
            <tbody>${items.map(item => {
              if (editingId === item.id) {
                return `<tr class="edit-row">
                  <td><input id="edName" type="text" value="${esc(item.name)}" maxlength="100"></td>
                  <td><input id="edCol2" type="text" value="${esc(item.model_number || '')}" maxlength="100"></td>
                  <td><select id="edPrinter">${printerOpts(printers, item.printer_id)}</select></td>
                  <td><label><input id="edActive" type="checkbox" ${item.is_active ? 'checked' : ''}> Active</label></td>
                  <td class="td-actions">
                    <button class="btn btn--primary btn--sm" data-save="${item.id}">Save</button>
                    <button class="btn btn--ghost btn--sm" data-cancel>Cancel</button>
                  </td>
                </tr>`;
              }
              const printer = printers.find(p => p.id == item.printer_id);
              return `<tr class="${item.is_active ? '' : 'inactive'}">
                <td>${esc(item.name)}</td>
                <td>${item.model_number ? esc(item.model_number) : '—'}</td>
                <td>${printer ? esc(printer.name) : '<span style="color:var(--gray-400)">None</span>'}</td>
                <td><span class="badge badge--${item.is_active ? 'done' : 'muted'}">${item.is_active ? 'Active' : 'Hidden'}</span></td>
                <td class="td-actions">
                  <button class="btn btn--ghost btn--sm" data-edit="${item.id}">Edit</button>
                  <button class="btn btn--ghost btn--sm" data-toggle="${item.id}">${item.is_active ? 'Hide' : 'Show'}</button>
                </td>
              </tr>`;
            }).join('')}</tbody></table></div>`
        : '<div class="empty"><span class="empty__icon">📦</span>No toner types yet. Add one above.</div>';

      v.innerHTML = `
        <div class="card card--accent">
          <div class="card__title">Add Toner Type</div>
          <div class="inline-add">
            <div class="form-group"><label>Toner Name</label><input id="addName" type="text" maxlength="100" placeholder="e.g. HP 207A Black"></div>
            <div class="form-group"><label>Model # <span class="opt">(optional)</span></label><input id="addCol2" type="text" maxlength="100" placeholder="e.g. W2210A"></div>
            <div class="form-group"><label>Printer <span class="opt">(optional)</span></label><select id="addPrinter">${printerOpts(printers, null)}</select></div>
            <button class="btn btn--primary" id="addBtn">Add</button>
          </div>
        </div>
        <div class="card">
          <div class="card__title">All Toner Types</div>
          ${rowsHtml}
        </div>`;

      $('#addBtn').addEventListener('click', async () => {
        const name        = $('#addName').value.trim();
        const model_number = $('#addCol2').value.trim();
        const printer_id  = parseInt($('#addPrinter').value) || null;
        if (!name) { flash('error', 'Enter a toner name.'); return; }
        try { await api('POST', '/api/toner-types', { name, model_number: model_number || null, printer_id }); flash('ok', `${name} added.`); pageToners(); }
        catch (e) { flash('error', e.message); }
      });

      $$('[data-edit]', v).forEach(b => b.addEventListener('click', () => { editingId = parseInt(b.dataset.edit); pageToners(); }));
      $$('[data-cancel]', v).forEach(b => b.addEventListener('click', () => { editingId = null; pageToners(); }));
      $$('[data-save]', v).forEach(b => b.addEventListener('click', async () => {
        const name         = $('#edName').value.trim();
        const model_number = $('#edCol2').value.trim();
        const is_active    = $('#edActive').checked;
        const printer_id   = parseInt($('#edPrinter').value) || null;
        if (!name) { flash('error', 'Name required.'); return; }
        try {
          await api('PUT', `/api/toner-types/${b.dataset.save}`, { name, model_number: model_number || null, is_active, printer_id });
          editingId = null; flash('ok', 'Saved.'); pageToners();
        } catch (e) { flash('error', e.message); }
      }));
      $$('[data-toggle]', v).forEach(b => b.addEventListener('click', async () => {
        try { await api('POST', `/api/toner-types/${b.dataset.toggle}/toggle`); pageToners(); }
        catch (e) { flash('error', e.message); }
      }));
    } catch (err) { v.innerHTML = `<div class="empty">Error: ${esc(err.message)}</div>`; }
  }

  // ---- page: manage users ----------------------------------------------------
  async function pageUsers() {
    const v = $('#view');
    v.innerHTML = '<div class="empty">Loading…</div>';

    try {
      const users = await api('GET', '/api/admin/users');

      v.innerHTML = `
        <div class="card card--accent">
          <div class="card__title">Add User</div>
          <div class="inline-add">
            <div class="form-group"><label>Username</label><input id="addUn" type="text" maxlength="50" placeholder="e.g. jsmith"></div>
            <div class="form-group"><label>Full Name</label><input id="addFn" type="text" maxlength="100" placeholder="e.g. John Smith"></div>
            <div class="form-group"><label>&nbsp;</label><label style="font-weight:400"><input id="addAdmin" type="checkbox"> Admin</label></div>
            <button class="btn btn--primary" id="addUserBtn">Add</button>
          </div>
        </div>
        <div class="card">
          <div class="card__title">All Users</div>
          <div class="table-wrap"><table>
            <thead><tr><th>Username</th><th>Full Name</th><th>Role</th><th>Actions</th></tr></thead>
            <tbody>${users.map(u => {
              if (editingId === u.id) {
                return `<tr class="edit-row">
                  <td>${esc(u.username)}</td>
                  <td><input id="edFn" type="text" value="${esc(u.full_name)}" maxlength="100"></td>
                  <td><label><input id="edAdmin" type="checkbox" ${u.is_admin ? 'checked' : ''}> Admin</label></td>
                  <td class="td-actions">
                    <button class="btn btn--primary btn--sm" data-save-user="${u.id}">Save</button>
                    <button class="btn btn--ghost btn--sm" data-cancel>Cancel</button>
                  </td>
                </tr>`;
              }
              return `<tr>
                <td>${esc(u.username)}</td>
                <td>${esc(u.full_name)}</td>
                <td>${u.is_admin ? '<span class="badge badge--admin">Admin</span>' : 'Staff'}</td>
                <td class="td-actions"><button class="btn btn--ghost btn--sm" data-edit="${u.id}">Edit</button></td>
              </tr>`;
            }).join('')}</tbody></table></div>
        </div>`;

      $('#addUserBtn').addEventListener('click', async () => {
        const username  = $('#addUn').value.trim();
        const full_name = $('#addFn').value.trim();
        const is_admin  = $('#addAdmin').checked;
        if (!username || !full_name) { flash('error', 'Username and name required.'); return; }
        try { await api('POST', '/api/admin/users', { username, full_name, is_admin }); flash('ok', `${full_name} added.`); pageUsers(); }
        catch (e) { flash('error', e.message); }
      });

      $$('[data-edit]', v).forEach(b => b.addEventListener('click', () => { editingId = parseInt(b.dataset.edit); pageUsers(); }));
      $$('[data-cancel]', v).forEach(b => b.addEventListener('click', () => { editingId = null; pageUsers(); }));
      $$('[data-save-user]', v).forEach(b => b.addEventListener('click', async () => {
        const full_name = $('#edFn').value.trim();
        const is_admin  = $('#edAdmin').checked;
        if (!full_name) { flash('error', 'Name required.'); return; }
        try {
          await api('PUT', `/api/admin/users/${b.dataset.saveUser}`, { full_name, is_admin });
          editingId = null; flash('ok', 'Updated.'); pageUsers();
        } catch (e) { flash('error', e.message); }
      }));
    } catch (err) { v.innerHTML = `<div class="empty">Error: ${esc(err.message)}</div>`; }
  }

  // ---- boot ------------------------------------------------------------------
  (async function boot() {
    try {
      me = await api('GET', '/api/me');
      render();
    } catch {
      showLogin();
    }
  })();
})();
