/* Toner Admin – dashboard logic */
(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c =>
    ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));

  const api = async (url, opts = {}) => {
    if (opts.body) opts.headers = { 'Content-Type': 'application/json', ...(opts.headers || {}) };
    const res = await fetch(url, opts);
    if (res.status === 401 && !url.endsWith('/login')) { showLogin(); throw new Error('Session expired'); }
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.error || 'Request failed');
    return data;
  };

  const fmtDate = (d) => d ? new Date(d).toLocaleString('en-GB', { dateStyle: 'short', timeStyle: 'short' }) : '';
  const emptyRow = (tbody, cols, msg = 'Nothing here yet') =>
    tbody.innerHTML = `<tr><td class="empty" colspan="${cols}">${msg}</td></tr>`;

  /* ===================== Login ===================== */

  function showLogin() { $('loginScreen').hidden = false; $('app').hidden = true; }
  function showApp(name) {
    $('loginScreen').hidden = true;
    $('app').hidden = false;
    $('adminName').textContent = name;
    loadTab('dashboard');
  }

  $('loginBtn').addEventListener('click', doLogin);
  $('loginPass').addEventListener('keydown', (e) => { if (e.key === 'Enter') doLogin(); });

  async function doLogin() {
    const err = $('loginError');
    err.hidden = true;
    try {
      const data = await api('/api/admin/login', {
        method: 'POST',
        body: JSON.stringify({ username: $('loginUser').value.trim(), password: $('loginPass').value })
      });
      $('loginPass').value = '';
      showApp(data.username);
    } catch (e) {
      err.textContent = e.message;
      err.hidden = false;
    }
  }

  $('logoutBtn').addEventListener('click', async () => {
    await api('/api/admin/logout', { method: 'POST' }).catch(() => {});
    showLogin();
  });

  /* ===================== Tabs ===================== */

  document.querySelectorAll('.tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.tab').forEach(b => b.classList.toggle('active', b === btn));
      document.querySelectorAll('.tab-panel').forEach(p => p.hidden = p.id !== 'tab-' + btn.dataset.tab);
      loadTab(btn.dataset.tab);
    });
  });

  const loaders = {
    dashboard: loadDashboard,
    tickets: loadTickets,
    rooms: loadRooms,
    printers: loadPrinters,
    toners: loadToners,
    reports: loadReports
  };
  const loadTab = (name) => loaders[name] && loaders[name]().catch(console.error);

  /* ===================== Dashboard ===================== */

  async function loadDashboard() {
    const s = await api('/api/admin/stats');
    $('statPending').textContent = s.pending;
    $('statProgress').textContent = s.in_progress;
    $('statCompleted').textContent = s.completed;
    $('statLow').textContent = s.lowStock.length;
    const tbody = $('lowStockTable').tBodies[0];
    if (!s.lowStock.length) return emptyRow(tbody, 4, 'All toner stock is healthy');
    tbody.innerHTML = s.lowStock.map(t => `
      <tr>
        <td>${esc(t.toner_name)}</td><td>${esc(t.toner_model)}</td>
        <td class="low">${t.quantity}</td><td>${t.low_stock_threshold}</td>
      </tr>`).join('');
  }

  /* ===================== Tickets ===================== */

  ['filterStatus', 'filterRoom', 'filterPrinter'].forEach(id =>
    $(id).addEventListener('change', loadTickets));

  let filtersLoaded = false;
  async function loadTickets() {
    if (!filtersLoaded) {
      const [rooms, printers] = await Promise.all([api('/api/admin/rooms'), api('/api/admin/printers')]);
      $('filterRoom').innerHTML = '<option value="">All rooms</option>' +
        rooms.map(r => `<option value="${r.id}">${esc(r.room_name)}</option>`).join('');
      $('filterPrinter').innerHTML = '<option value="">All printers</option>' +
        printers.map(p => `<option value="${p.id}">${esc(p.printer_name)}</option>`).join('');
      filtersLoaded = true;
    }
    const params = new URLSearchParams();
    if ($('filterStatus').value) params.set('status', $('filterStatus').value);
    if ($('filterRoom').value) params.set('roomId', $('filterRoom').value);
    if ($('filterPrinter').value) params.set('printerId', $('filterPrinter').value);
    const rows = await api('/api/admin/requests?' + params);
    const tbody = $('ticketsTable').tBodies[0];
    if (!rows.length) return emptyRow(tbody, 8, 'No tickets match');
    tbody.innerHTML = rows.map(q => `
      <tr data-id="${q.id}">
        <td>#${q.id}</td>
        <td>${esc(q.username)}</td>
        <td>${esc(q.room_name)}</td>
        <td>${esc(q.printer_name)}</td>
        <td>${esc(q.toner_name)}</td>
        <td>
          <select class="inline status-select">
            ${['Pending','In Progress','Completed'].map(s =>
              `<option ${s === q.status ? 'selected' : ''}>${s}</option>`).join('')}
          </select>
        </td>
        <td>${fmtDate(q.created_at)}</td>
        <td><input class="inline notes-input" value="${esc(q.notes || '')}" placeholder="Add note…"></td>
      </tr>`).join('');

    tbody.querySelectorAll('.status-select').forEach(sel =>
      sel.addEventListener('change', async (e) => {
        const id = e.target.closest('tr').dataset.id;
        await api('/api/admin/request/update', { method: 'POST', body: JSON.stringify({ id, status: e.target.value }) });
        loadDashboard().catch(() => {});
      }));
    tbody.querySelectorAll('.notes-input').forEach(inp =>
      inp.addEventListener('change', async (e) => {
        const id = e.target.closest('tr').dataset.id;
        await api('/api/admin/request/update', { method: 'POST', body: JSON.stringify({ id, notes: e.target.value }) });
      }));
  }

  /* ===================== Generic modal ===================== */

  let modalSaveHandler = null;
  function openModal(title, fieldsHtml, onSave) {
    $('modalTitle').textContent = title;
    $('modalFields').innerHTML = fieldsHtml;
    $('modalError').hidden = true;
    $('modal').hidden = false;
    modalSaveHandler = onSave;
    const first = $('modalFields').querySelector('input,select');
    if (first) first.focus();
  }
  const closeModal = () => { $('modal').hidden = true; modalSaveHandler = null; };
  $('modalCancel').addEventListener('click', closeModal);
  $('modal').addEventListener('click', (e) => { if (e.target === $('modal')) closeModal(); });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });
  $('modalSave').addEventListener('click', async () => {
    if (!modalSaveHandler) return;
    try { await modalSaveHandler(); closeModal(); }
    catch (e) { $('modalError').textContent = e.message; $('modalError').hidden = false; }
  });
  const field = (id, label, value = '', type = 'text') => `
    <label class="field-label" for="${id}">${label}</label>
    <input id="${id}" type="${type}" value="${esc(value)}">`;

  /* ===================== Rooms ===================== */

  $('addRoomBtn').addEventListener('click', () => roomModal());

  function roomModal(room = null) {
    openModal(room ? 'Edit room' : 'Add room',
      field('fRoomName', 'Room name', room?.room_name) +
      field('fBuilding', 'Building', room?.building) +
      field('fNotes', 'Notes', room?.notes),
      async () => {
        const body = JSON.stringify({
          room_name: $('fRoomName').value, building: $('fBuilding').value, notes: $('fNotes').value
        });
        if (room) await api(`/api/admin/rooms/${room.id}`, { method: 'PUT', body });
        else await api('/api/admin/rooms', { method: 'POST', body });
        loadRooms();
      });
  }

  async function loadRooms() {
    const rows = await api('/api/admin/rooms');
    const tbody = $('roomsTable').tBodies[0];
    if (!rows.length) return emptyRow(tbody, 4, 'No rooms yet – add one above');
    tbody.innerHTML = rows.map(r => `
      <tr>
        <td>${esc(r.room_name)}</td><td>${esc(r.building)}</td><td>${esc(r.notes || '')}</td>
        <td>
          <button class="icon-btn edit" data-id="${r.id}">Edit</button>
          <button class="icon-btn danger del" data-id="${r.id}">Delete</button>
        </td>
      </tr>`).join('');
    tbody.querySelectorAll('.edit').forEach(b => b.addEventListener('click', () =>
      roomModal(rows.find(r => r.id == b.dataset.id))));
    tbody.querySelectorAll('.del').forEach(b => b.addEventListener('click', async () => {
      if (!confirm('Delete this room? Its printers will also be removed.')) return;
      try { await api(`/api/admin/rooms/${b.dataset.id}`, { method: 'DELETE' }); loadRooms(); }
      catch (e) { alert(e.message); }
    }));
  }

  /* ===================== Printers ===================== */

  $('addPrinterBtn').addEventListener('click', () => printerModal());

  async function printerModal(printer = null) {
    const [rooms, toners] = await Promise.all([api('/api/admin/rooms'), api('/api/admin/toners')]);
    const sel = (id, label, items, fmt, current) => `
      <label class="field-label" for="${id}">${label}</label>
      <select id="${id}">${items.map(i =>
        `<option value="${i.id}" ${i.id == current ? 'selected' : ''}>${esc(fmt(i))}</option>`).join('')}
      </select>`;
    openModal(printer ? 'Edit printer' : 'Add printer',
      field('fPName', 'Printer name', printer?.printer_name) +
      field('fPModel', 'Printer model', printer?.printer_model) +
      field('fPIp', 'IP address', printer?.ip_address) +
      sel('fPRoom', 'Room', rooms, r => r.room_name + (r.building ? ' · ' + r.building : ''), printer?.room_id) +
      sel('fPToner', 'Toner', toners, t => `${t.toner_name} (${t.toner_model})`, printer?.toner_id),
      async () => {
        const body = JSON.stringify({
          printer_name: $('fPName').value, printer_model: $('fPModel').value,
          ip_address: $('fPIp').value, room_id: $('fPRoom').value, toner_id: $('fPToner').value
        });
        if (printer) await api(`/api/admin/printers/${printer.id}`, { method: 'PUT', body });
        else await api('/api/admin/printers', { method: 'POST', body });
        loadPrinters();
      });
  }

  async function loadPrinters() {
    const rows = await api('/api/admin/printers');
    const tbody = $('printersTable').tBodies[0];
    if (!rows.length) return emptyRow(tbody, 6, 'No printers yet – add one above');
    tbody.innerHTML = rows.map(p => `
      <tr>
        <td>${esc(p.printer_name)}</td><td>${esc(p.printer_model)}</td><td>${esc(p.ip_address)}</td>
        <td>${esc(p.room_name)}</td><td>${esc(p.toner_name)}</td>
        <td>
          <button class="icon-btn edit" data-id="${p.id}">Edit</button>
          <button class="icon-btn danger del" data-id="${p.id}">Delete</button>
        </td>
      </tr>`).join('');
    tbody.querySelectorAll('.edit').forEach(b => b.addEventListener('click', () =>
      printerModal(rows.find(p => p.id == b.dataset.id))));
    tbody.querySelectorAll('.del').forEach(b => b.addEventListener('click', async () => {
      if (!confirm('Delete this printer?')) return;
      try { await api(`/api/admin/printers/${b.dataset.id}`, { method: 'DELETE' }); loadPrinters(); }
      catch (e) { alert(e.message); }
    }));
  }

  /* ===================== Toners ===================== */

  $('addTonerBtn').addEventListener('click', () => tonerModal());

  function tonerModal(toner = null) {
    openModal(toner ? 'Edit toner' : 'Add toner',
      field('fTName', 'Toner name', toner?.toner_name) +
      field('fTModel', 'Toner model', toner?.toner_model) +
      field('fTQty', 'Quantity in stock', toner?.quantity ?? 0, 'number') +
      field('fTCost', 'Cost per unit', toner?.cost ?? 0, 'number') +
      field('fTLow', 'Low stock alert threshold', toner?.low_stock_threshold ?? 2, 'number'),
      async () => {
        const body = JSON.stringify({
          toner_name: $('fTName').value, toner_model: $('fTModel').value,
          quantity: $('fTQty').value, cost: $('fTCost').value, low_stock_threshold: $('fTLow').value
        });
        if (toner) await api(`/api/admin/toners/${toner.id}`, { method: 'PUT', body });
        else await api('/api/admin/toners', { method: 'POST', body });
        loadToners();
        loadDashboard().catch(() => {});
      });
  }

  async function loadToners() {
    const rows = await api('/api/admin/toners');
    const tbody = $('tonersTable').tBodies[0];
    if (!rows.length) return emptyRow(tbody, 6, 'No toners yet – add one above');
    tbody.innerHTML = rows.map(t => `
      <tr>
        <td>${esc(t.toner_name)}</td><td>${esc(t.toner_model)}</td>
        <td class="${t.quantity <= t.low_stock_threshold ? 'low' : ''}">${t.quantity}</td>
        <td>£${Number(t.cost).toFixed(2)}</td><td>${t.low_stock_threshold}</td>
        <td>
          <button class="icon-btn edit" data-id="${t.id}">Edit</button>
          <button class="icon-btn danger del" data-id="${t.id}">Delete</button>
        </td>
      </tr>`).join('');
    tbody.querySelectorAll('.edit').forEach(b => b.addEventListener('click', () =>
      tonerModal(rows.find(t => t.id == b.dataset.id))));
    tbody.querySelectorAll('.del').forEach(b => b.addEventListener('click', async () => {
      if (!confirm('Delete this toner?')) return;
      try { await api(`/api/admin/toners/${b.dataset.id}`, { method: 'DELETE' }); loadToners(); }
      catch (e) { alert(e.message); }
    }));
  }

  /* ===================== Reports ===================== */

  async function loadReports() {
    const data = await api('/api/admin/reports/summary');
    const mBody = $('monthlyTable').tBodies[0];
    if (!data.monthly.length) emptyRow(mBody, 3, 'No completed requests yet');
    else mBody.innerHTML = data.monthly.map(m =>
      `<tr><td>${esc(m.month)}</td><td>${m.toner_used}</td><td>£${Number(m.total_cost).toFixed(2)}</td></tr>`).join('');
    const pBody = $('topPrintersTable').tBodies[0];
    if (!data.topPrinters.length) emptyRow(pBody, 3, 'No requests yet');
    else pBody.innerHTML = data.topPrinters.map(p =>
      `<tr><td>${esc(p.printer_name)}</td><td>${esc(p.room_name)}</td><td>${p.request_count}</td></tr>`).join('');
  }

  /* ===================== Boot ===================== */

  api('/api/admin/session')
    .then(d => showApp(d.username))
    .catch(() => showLogin());
})();
