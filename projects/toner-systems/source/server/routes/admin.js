const express = require('express');
const bcrypt = require('bcryptjs');
const db = require('../database/db');
const { requireAdmin } = require('../middleware/auth');

const router = express.Router();

/* ---------- Auth ---------- */

router.post('/login', async (req, res, next) => {
  try {
    const { username, password } = req.body || {};
    if (!username || !password) return res.status(400).json({ error: 'Username and password required' });
    const [[user]] = await db.query('SELECT * FROM users WHERE username = ?', [username]);
    const ok = user && await bcrypt.compare(password, user.password_hash);
    if (!ok) return res.status(401).json({ error: 'Invalid username or password' });
    req.session.adminId = user.id;
    req.session.adminName = user.username;
    res.json({ username: user.username });
  } catch (err) { next(err); }
});

router.post('/logout', (req, res) => {
  req.session.destroy(() => res.json({ ok: true }));
});

router.get('/session', (req, res) => {
  if (req.session && req.session.adminId) return res.json({ username: req.session.adminName });
  res.status(401).json({ error: 'Not authenticated' });
});

// Everything below requires login
router.use(requireAdmin);

/* ---------- Dashboard stats ---------- */

router.get('/stats', async (req, res, next) => {
  try {
    const [[counts]] = await db.query(
      `SELECT
         SUM(status = 'Pending') AS pending,
         SUM(status = 'In Progress') AS in_progress,
         SUM(status = 'Completed') AS completed
       FROM requests`
    );
    const [lowStock] = await db.query(
      'SELECT id, toner_name, toner_model, quantity, low_stock_threshold FROM toners WHERE quantity <= low_stock_threshold ORDER BY quantity'
    );
    res.json({
      pending: Number(counts.pending || 0),
      in_progress: Number(counts.in_progress || 0),
      completed: Number(counts.completed || 0),
      lowStock
    });
  } catch (err) { next(err); }
});

/* ---------- Tickets ---------- */

router.get('/requests', async (req, res, next) => {
  try {
    const { status, roomId, printerId } = req.query;
    const where = [];
    const params = [];
    if (status)    { where.push('q.status = ?');     params.push(status); }
    if (roomId)    { where.push('q.room_id = ?');    params.push(Number(roomId)); }
    if (printerId) { where.push('q.printer_id = ?'); params.push(Number(printerId)); }
    const [rows] = await db.query(
      `SELECT q.id, q.username, q.status, q.notes, q.created_at, q.completed_at,
              r.room_name, p.printer_name, p.printer_model, t.toner_name, t.toner_model
       FROM requests q
       JOIN rooms r ON r.id = q.room_id
       JOIN printers p ON p.id = q.printer_id
       JOIN toners t ON t.id = q.toner_id
       ${where.length ? 'WHERE ' + where.join(' AND ') : ''}
       ORDER BY q.created_at DESC
       LIMIT 500`,
      params
    );
    res.json(rows);
  } catch (err) { next(err); }
});

router.post('/request/update', async (req, res, next) => {
  try {
    const { id, status, notes } = req.body || {};
    const valid = ['Pending', 'In Progress', 'Completed'];
    if (!Number.isInteger(Number(id))) return res.status(400).json({ error: 'Invalid id' });
    if (status && !valid.includes(status)) return res.status(400).json({ error: 'Invalid status' });

    const [[current]] = await db.query('SELECT status, toner_id FROM requests WHERE id = ?', [Number(id)]);
    if (!current) return res.status(404).json({ error: 'Request not found' });

    const sets = [];
    const params = [];
    if (status) {
      sets.push('status = ?'); params.push(status);
      sets.push('completed_at = ' + (status === 'Completed' ? 'NOW()' : 'NULL'));
    }
    if (notes !== undefined) { sets.push('notes = ?'); params.push(String(notes).slice(0, 2000)); }
    if (!sets.length) return res.status(400).json({ error: 'Nothing to update' });
    params.push(Number(id));
    await db.query(`UPDATE requests SET ${sets.join(', ')} WHERE id = ?`, params);

    // Decrement stock once, when a ticket first becomes Completed
    if (status === 'Completed' && current.status !== 'Completed') {
      await db.query('UPDATE toners SET quantity = GREATEST(quantity - 1, 0) WHERE id = ?', [current.toner_id]);
    }
    res.json({ ok: true });
  } catch (err) { next(err); }
});

/* ---------- Rooms CRUD ---------- */

router.get('/rooms', async (req, res, next) => {
  try {
    const [rows] = await db.query('SELECT * FROM rooms ORDER BY building, room_name');
    res.json(rows);
  } catch (err) { next(err); }
});

router.post('/rooms', async (req, res, next) => {
  try {
    const { room_name, building = '', notes = '' } = req.body || {};
    if (!room_name || !room_name.trim()) return res.status(400).json({ error: 'Room name required' });
    const [r] = await db.query(
      'INSERT INTO rooms (room_name, building, notes) VALUES (?, ?, ?)',
      [room_name.trim().slice(0, 100), String(building).slice(0, 100), String(notes).slice(0, 2000)]
    );
    res.status(201).json({ id: r.insertId });
  } catch (err) { next(err); }
});

router.put('/rooms/:id', async (req, res, next) => {
  try {
    const { room_name, building = '', notes = '' } = req.body || {};
    if (!room_name || !room_name.trim()) return res.status(400).json({ error: 'Room name required' });
    await db.query(
      'UPDATE rooms SET room_name = ?, building = ?, notes = ? WHERE id = ?',
      [room_name.trim().slice(0, 100), String(building).slice(0, 100), String(notes).slice(0, 2000), Number(req.params.id)]
    );
    res.json({ ok: true });
  } catch (err) { next(err); }
});

router.delete('/rooms/:id', async (req, res, next) => {
  try {
    await db.query('DELETE FROM rooms WHERE id = ?', [Number(req.params.id)]);
    res.json({ ok: true });
  } catch (err) {
    if (err.code === 'ER_ROW_IS_REFERENCED_2') {
      return res.status(409).json({ error: 'Room has request history – remove its printers first or keep it.' });
    }
    next(err);
  }
});

/* ---------- Printers CRUD ---------- */

router.get('/printers', async (req, res, next) => {
  try {
    const [rows] = await db.query(
      `SELECT p.*, r.room_name, t.toner_name, t.toner_model
       FROM printers p
       JOIN rooms r ON r.id = p.room_id
       JOIN toners t ON t.id = p.toner_id
       ORDER BY r.room_name, p.printer_name`
    );
    res.json(rows);
  } catch (err) { next(err); }
});

function printerFields(body) {
  const { printer_name, printer_model = '', ip_address = '', room_id, toner_id } = body || {};
  if (!printer_name || !printer_name.trim()) return null;
  if (!Number.isInteger(Number(room_id)) || !Number.isInteger(Number(toner_id))) return null;
  return [
    printer_name.trim().slice(0, 100),
    String(printer_model).slice(0, 100),
    String(ip_address).slice(0, 45),
    Number(room_id),
    Number(toner_id)
  ];
}

router.post('/printers', async (req, res, next) => {
  try {
    const f = printerFields(req.body);
    if (!f) return res.status(400).json({ error: 'Printer name, room and toner are required' });
    const [r] = await db.query(
      'INSERT INTO printers (printer_name, printer_model, ip_address, room_id, toner_id) VALUES (?, ?, ?, ?, ?)', f
    );
    res.status(201).json({ id: r.insertId });
  } catch (err) { next(err); }
});

router.put('/printers/:id', async (req, res, next) => {
  try {
    const f = printerFields(req.body);
    if (!f) return res.status(400).json({ error: 'Printer name, room and toner are required' });
    await db.query(
      'UPDATE printers SET printer_name=?, printer_model=?, ip_address=?, room_id=?, toner_id=? WHERE id = ?',
      [...f, Number(req.params.id)]
    );
    res.json({ ok: true });
  } catch (err) { next(err); }
});

router.delete('/printers/:id', async (req, res, next) => {
  try {
    await db.query('DELETE FROM printers WHERE id = ?', [Number(req.params.id)]);
    res.json({ ok: true });
  } catch (err) {
    if (err.code === 'ER_ROW_IS_REFERENCED_2') {
      return res.status(409).json({ error: 'Printer has request history and cannot be deleted.' });
    }
    next(err);
  }
});

/* ---------- Toners CRUD ---------- */

router.get('/toners', async (req, res, next) => {
  try {
    const [rows] = await db.query('SELECT * FROM toners ORDER BY toner_name');
    res.json(rows);
  } catch (err) { next(err); }
});

function tonerFields(body) {
  const { toner_name, toner_model = '', quantity = 0, cost = 0, low_stock_threshold = 2 } = body || {};
  if (!toner_name || !toner_name.trim()) return null;
  return [
    toner_name.trim().slice(0, 100),
    String(toner_model).slice(0, 100),
    Math.max(0, Number(quantity) || 0),
    Math.max(0, Number(cost) || 0),
    Math.max(0, Number(low_stock_threshold) || 0)
  ];
}

router.post('/toners', async (req, res, next) => {
  try {
    const f = tonerFields(req.body);
    if (!f) return res.status(400).json({ error: 'Toner name required' });
    const [r] = await db.query(
      'INSERT INTO toners (toner_name, toner_model, quantity, cost, low_stock_threshold) VALUES (?, ?, ?, ?, ?)', f
    );
    res.status(201).json({ id: r.insertId });
  } catch (err) { next(err); }
});

router.put('/toners/:id', async (req, res, next) => {
  try {
    const f = tonerFields(req.body);
    if (!f) return res.status(400).json({ error: 'Toner name required' });
    await db.query(
      'UPDATE toners SET toner_name=?, toner_model=?, quantity=?, cost=?, low_stock_threshold=? WHERE id = ?',
      [...f, Number(req.params.id)]
    );
    res.json({ ok: true });
  } catch (err) { next(err); }
});

router.delete('/toners/:id', async (req, res, next) => {
  try {
    await db.query('DELETE FROM toners WHERE id = ?', [Number(req.params.id)]);
    res.json({ ok: true });
  } catch (err) {
    if (err.code === 'ER_ROW_IS_REFERENCED_2') {
      return res.status(409).json({ error: 'Toner is linked to printers or requests and cannot be deleted.' });
    }
    next(err);
  }
});

/* ---------- Reports ---------- */

// Monthly usage + cost (completed requests), most requested printers
router.get('/reports/summary', async (req, res, next) => {
  try {
    const [monthly] = await db.query(
      `SELECT DATE_FORMAT(q.completed_at, '%Y-%m') AS month,
              COUNT(*) AS toner_used,
              ROUND(SUM(t.cost), 2) AS total_cost
       FROM requests q
       JOIN toners t ON t.id = q.toner_id
       WHERE q.status = 'Completed' AND q.completed_at IS NOT NULL
       GROUP BY month
       ORDER BY month DESC
       LIMIT 12`
    );
    const [topPrinters] = await db.query(
      `SELECT p.printer_name, r.room_name, COUNT(*) AS request_count
       FROM requests q
       JOIN printers p ON p.id = q.printer_id
       JOIN rooms r ON r.id = q.room_id
       GROUP BY q.printer_id
       ORDER BY request_count DESC
       LIMIT 10`
    );
    res.json({ monthly, topPrinters });
  } catch (err) { next(err); }
});

// CSV export of all requests
router.get('/reports/requests.csv', async (req, res, next) => {
  try {
    const [rows] = await db.query(
      `SELECT q.id, q.username, r.room_name, p.printer_name, t.toner_name, t.cost,
              q.status, q.created_at, q.completed_at
       FROM requests q
       JOIN rooms r ON r.id = q.room_id
       JOIN printers p ON p.id = q.printer_id
       JOIN toners t ON t.id = q.toner_id
       ORDER BY q.created_at DESC`
    );
    const esc = (v) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const header = 'Ticket,User,Room,Printer,Toner,Cost,Status,Created,Completed';
    const lines = rows.map(r =>
      [r.id, r.username, r.room_name, r.printer_name, r.toner_name, r.cost, r.status,
       r.created_at?.toISOString?.() || r.created_at, r.completed_at?.toISOString?.() || r.completed_at || '']
      .map(esc).join(',')
    );
    res.setHeader('Content-Type', 'text/csv');
    res.setHeader('Content-Disposition', 'attachment; filename="toner-requests.csv"');
    res.send([header, ...lines].join('\n'));
  } catch (err) { next(err); }
});

module.exports = router;
