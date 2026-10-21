const express = require('express');
const initSqlJs = require('sql.js');
const fs = require('fs');
const path = require('path');
const crypto = require('crypto');
const nodemailer = require('nodemailer');

// ---------------------------------------------------------------------------
// Email
// ---------------------------------------------------------------------------
const ICT_EMAIL = 'developer@example.invalid';

const mailer = process.env.SMTP_HOST ? nodemailer.createTransport({
  host: process.env.SMTP_HOST,
  port: parseInt(process.env.SMTP_PORT) || 587,
  secure: process.env.SMTP_SECURE === 'true',
  auth: process.env.SMTP_USER ? { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS } : undefined,
  tls: { rejectUnauthorized: process.env.SMTP_REJECT_UNAUTHORIZED !== 'false' }
}) : null;

function htmlEsc(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);
}

async function sendRequestEmail(user, room, toner, notes) {
  if (!mailer) return;
  const appUrl = (process.env.APP_URL || 'http://localhost:3000').replace(/\/$/, '');
  const subject = `Toner Request \u2014 ${room.name} \u2014 ${toner.name}`;
  const html = `
<!DOCTYPE html>
<html>
<body style="margin:0;padding:0;background:#f0f2f5;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

        <!-- Header -->
        <tr><td style="background:#4f46e5;padding:20px 28px;border-radius:10px 10px 0 0;">
          <span style="color:#fff;font-size:20px;font-weight:700;">&#128424;&#65039; Toner Request</span>
        </td></tr>

        <!-- Body -->
        <tr><td style="background:#fff;padding:28px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 10px 10px;">

          <p style="margin:0 0 20px;font-size:16px;color:#111827;">
            <strong>${htmlEsc(user.full_name)}</strong>
            <span style="color:#6b7280;font-size:14px;"> (${htmlEsc(user.username)})</span>
            has requested a toner change.
          </p>

          <!-- Details table -->
          <table width="100%" cellpadding="0" cellspacing="0" style="border:1px solid #e5e7eb;border-radius:8px;overflow:hidden;margin-bottom:24px;">
            <tr>
              <td style="background:#f9fafb;padding:10px 16px;font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.5px;width:110px;border-bottom:1px solid #e5e7eb;">Room</td>
              <td style="background:#fff;padding:10px 16px;font-size:15px;color:#111827;border-bottom:1px solid #e5e7eb;">${htmlEsc(room.name)}${room.building ? ' &mdash; ' + htmlEsc(room.building) : ''}</td>
            </tr>
            <tr>
              <td style="background:#f9fafb;padding:10px 16px;font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.5px;${notes ? 'border-bottom:1px solid #e5e7eb;' : ''}">Toner</td>
              <td style="background:#fff;padding:10px 16px;font-size:15px;color:#111827;${notes ? 'border-bottom:1px solid #e5e7eb;' : ''}">${htmlEsc(toner.name)}${toner.model_number ? ' <span style="color:#9ca3af;font-size:13px;">(' + htmlEsc(toner.model_number) + ')</span>' : ''}</td>
            </tr>
            ${notes ? `<tr>
              <td style="background:#f9fafb;padding:10px 16px;font-size:12px;font-weight:700;color:#6b7280;text-transform:uppercase;letter-spacing:.5px;">Notes</td>
              <td style="background:#fff;padding:10px 16px;font-size:15px;color:#374151;">${htmlEsc(notes)}</td>
            </tr>` : ''}
          </table>

          <!-- CTA button -->
          <table width="100%" cellpadding="0" cellspacing="0">
            <tr><td align="center" style="padding:4px 0 20px;">
              <a href="${appUrl}" style="display:inline-block;background:#4f46e5;color:#fff;text-decoration:none;padding:13px 32px;border-radius:7px;font-size:15px;font-weight:700;">
                View Admin Queue &rarr;
              </a>
            </td></tr>
          </table>

          <p style="margin:0;font-size:12px;color:#9ca3af;text-align:center;">
            Toner Desk &middot; Davison ICT &middot; <a href="${appUrl}" style="color:#9ca3af;">${appUrl}</a>
          </p>

        </td></tr>
      </table>
    </td></tr>
  </table>
</body>
</html>`;

  try {
    await mailer.sendMail({
      from: process.env.SMTP_FROM || `"Toner Desk" <developer@example.invalid>`,
      to: ICT_EMAIL,
      subject,
      html
    });
  } catch (err) {
    console.error('[email] Send failed:', err.message);
    // Never block the request — email failure is non-fatal
  }
}

const app = express();
const PORT = process.env.PORT || 3000;
const DB_PATH = path.join(__dirname, 'toner.db');

// ---------------------------------------------------------------------------
// Database helpers
// ---------------------------------------------------------------------------
let db;

function query(sql, params = []) {
  const stmt = db.prepare(sql);
  stmt.bind(params);
  const rows = [];
  while (stmt.step()) rows.push(stmt.getAsObject());
  stmt.free();
  return rows;
}

function queryOne(sql, params = []) {
  return query(sql, params)[0] || null;
}

function run(sql, params = []) {
  db.run(sql, params);
  return { lastId: db.exec("SELECT last_insert_rowid()")[0]?.values[0]?.[0] };
}

function save() {
  const data = db.export();
  fs.writeFileSync(DB_PATH, Buffer.from(data));
}

// ---------------------------------------------------------------------------
// Middleware
// ---------------------------------------------------------------------------
app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

const SECRET = process.env.SESSION_SECRET || crypto.randomBytes(32).toString('hex');

function makeToken(userId) {
  const payload = Buffer.from(JSON.stringify({ id: userId, t: Date.now() })).toString('base64url');
  const sig = crypto.createHmac('sha256', SECRET).update(payload).digest('base64url');
  return payload + '.' + sig;
}

function parseToken(token) {
  if (!token) return null;
  const [payload, sig] = token.split('.');
  if (!payload || !sig) return null;
  const expected = crypto.createHmac('sha256', SECRET).update(payload).digest('base64url');
  if (sig !== expected) return null;
  try { return JSON.parse(Buffer.from(payload, 'base64url').toString()); }
  catch { return null; }
}

function getUser(req) {
  const cookie = (req.headers.cookie || '').split(';').find(c => c.trim().startsWith('sid='));
  if (!cookie) return null;
  const token = cookie.split('=')[1];
  const data = parseToken(token);
  if (!data) return null;
  return queryOne('SELECT id, username, full_name, is_admin FROM users WHERE id = ?', [data.id]);
}

function requireAuth(req, res, next) {
  const user = getUser(req);
  if (!user) return res.status(401).json({ error: 'Not signed in.' });
  req.user = user;
  next();
}

function requireAdmin(req, res, next) {
  if (!req.user.is_admin) return res.status(403).json({ error: 'Admin access required.' });
  next();
}

// ---------------------------------------------------------------------------
// Auth routes
// ---------------------------------------------------------------------------
app.get('/api/me', (req, res) => {
  const user = getUser(req);
  if (!user) return res.status(401).json({ error: 'Not signed in.' });
  res.json({ id: user.id, username: user.username, fullName: user.full_name, isAdmin: !!user.is_admin });
});

app.get('/api/users', (req, res) => {
  res.json(query('SELECT id, username, full_name FROM users ORDER BY full_name'));
});

app.post('/api/login', (req, res) => {
  const { userId } = req.body;
  const user = queryOne('SELECT id, username, full_name, is_admin FROM users WHERE id = ?', [userId]);
  if (!user) return res.status(400).json({ error: 'User not found.' });
  const token = makeToken(user.id);
  res.setHeader('Set-Cookie', `sid=${token}; Path=/; HttpOnly; SameSite=Strict; Max-Age=86400`);
  res.json({ id: user.id, username: user.username, fullName: user.full_name, isAdmin: !!user.is_admin });
});

app.post('/api/logout', (req, res) => {
  res.setHeader('Set-Cookie', 'sid=; Path=/; HttpOnly; Max-Age=0');
  res.json({ ok: true });
});

// ---------------------------------------------------------------------------
// Printers
// ---------------------------------------------------------------------------
app.get('/api/printers', requireAuth, (req, res) => {
  const sql = req.query.all === '1'
    ? 'SELECT * FROM printers ORDER BY name'
    : 'SELECT * FROM printers WHERE is_active = 1 ORDER BY name';
  res.json(query(sql));
});

app.post('/api/printers', requireAuth, requireAdmin, (req, res) => {
  const { name } = req.body;
  if (!name || !name.trim()) return res.status(400).json({ error: 'Name required.' });
  const result = run('INSERT INTO printers (name) VALUES (?)', [name.trim()]);
  save();
  res.json({ id: result.lastId });
});

app.put('/api/printers/:id', requireAuth, requireAdmin, (req, res) => {
  const { name, is_active } = req.body;
  if (!name || !name.trim()) return res.status(400).json({ error: 'Name required.' });
  run('UPDATE printers SET name = ?, is_active = ? WHERE id = ?',
    [name.trim(), is_active ? 1 : 0, req.params.id]);
  save();
  res.json({ ok: true });
});

app.post('/api/printers/:id/toggle', requireAuth, requireAdmin, (req, res) => {
  run('UPDATE printers SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id = ?', [req.params.id]);
  save();
  const p = queryOne('SELECT is_active FROM printers WHERE id = ?', [req.params.id]);
  res.json({ is_active: p.is_active });
});

// ---------------------------------------------------------------------------
// Lookups — return printer_id so client can filter toners by room's printer
// ---------------------------------------------------------------------------
app.get('/api/rooms', requireAuth, (req, res) => {
  const sql = req.query.all === '1'
    ? `SELECT r.*, p.name as printer_name
       FROM rooms r LEFT JOIN printers p ON r.printer_id = p.id
       ORDER BY r.name`
    : `SELECT r.*, p.name as printer_name
       FROM rooms r LEFT JOIN printers p ON r.printer_id = p.id
       WHERE r.is_active = 1 ORDER BY r.name`;
  res.json(query(sql));
});

app.get('/api/toner-types', requireAuth, (req, res) => {
  const sql = req.query.all === '1'
    ? 'SELECT * FROM toner_types ORDER BY name'
    : 'SELECT * FROM toner_types WHERE is_active = 1 ORDER BY name';
  res.json(query(sql));
});

// ---------------------------------------------------------------------------
// Requests (staff)
// ---------------------------------------------------------------------------
app.get('/api/requests/mine', requireAuth, (req, res) => {
  res.json(query(`
    SELECT r.*, rooms.name as room_name, toner_types.name as toner_name
    FROM requests r
    JOIN rooms ON r.room_id = rooms.id
    JOIN toner_types ON r.toner_type_id = toner_types.id
    WHERE r.user_id = ?
    ORDER BY r.created_at DESC LIMIT 50
  `, [req.user.id]));
});

app.post('/api/requests', requireAuth, (req, res) => {
  const { roomId, tonerTypeId, notes } = req.body;
  if (!roomId || !tonerTypeId) return res.status(400).json({ error: 'Room and toner type required.' });

  const room  = queryOne('SELECT * FROM rooms WHERE id = ? AND is_active = 1', [roomId]);
  const toner = queryOne('SELECT * FROM toner_types WHERE id = ? AND is_active = 1', [tonerTypeId]);
  if (!room || !toner) return res.status(400).json({ error: 'Invalid room or toner type.' });

  const result = run(
    "INSERT INTO requests (user_id, room_id, toner_type_id, notes, created_at) VALUES (?, ?, ?, ?, datetime('now','localtime'))",
    [req.user.id, roomId, tonerTypeId, notes || null]
  );
  save();
  res.json({ id: result.lastId });

  // Send email notification — non-blocking, failure never affects the response
  sendRequestEmail(req.user, room, toner, notes || '').catch(() => {});
});

// ---------------------------------------------------------------------------
// Admin: request queue
// ---------------------------------------------------------------------------
app.get('/api/admin/requests', requireAuth, requireAdmin, (req, res) => {
  const { status } = req.query;
  let sql = `
    SELECT r.*, rooms.name as room_name, rooms.building,
           toner_types.name as toner_name, toner_types.model_number,
           users.full_name as requested_by_name
    FROM requests r
    JOIN rooms ON r.room_id = rooms.id
    JOIN toner_types ON r.toner_type_id = toner_types.id
    JOIN users ON r.user_id = users.id
  `;
  const params = [];
  if (status) { sql += ' WHERE r.status = ?'; params.push(status); }
  sql += " ORDER BY CASE r.status WHEN 'Pending' THEN 0 ELSE 1 END, r.created_at DESC";

  const requests = query(sql, params);
  const pending   = queryOne("SELECT COUNT(*) as c FROM requests WHERE status = 'Pending'").c;
  const completed = queryOne("SELECT COUNT(*) as c FROM requests WHERE status = 'Completed'").c;

  res.json({ requests, counts: { pending, completed, total: pending + completed } });
});

app.post('/api/admin/requests/:id/complete', requireAuth, requireAdmin, (req, res) => {
  const r = queryOne('SELECT * FROM requests WHERE id = ?', [req.params.id]);
  if (!r) return res.status(404).json({ error: 'Not found.' });
  run("UPDATE requests SET status = 'Completed', completed_at = datetime('now','localtime'), completed_by = ? WHERE id = ?",
    [req.user.full_name, req.params.id]);
  save();
  res.json({ ok: true });
});

app.post('/api/admin/requests/:id/reopen', requireAuth, requireAdmin, (req, res) => {
  const r = queryOne('SELECT * FROM requests WHERE id = ?', [req.params.id]);
  if (!r) return res.status(404).json({ error: 'Not found.' });
  run("UPDATE requests SET status = 'Pending', completed_at = NULL, completed_by = NULL WHERE id = ?",
    [req.params.id]);
  save();
  res.json({ ok: true });
});

// ---------------------------------------------------------------------------
// Admin: manage rooms
// ---------------------------------------------------------------------------
app.post('/api/rooms', requireAuth, requireAdmin, (req, res) => {
  const { name, building, printer_id } = req.body;
  if (!name || !name.trim()) return res.status(400).json({ error: 'Name required.' });
  const result = run(
    'INSERT INTO rooms (name, building, printer_id) VALUES (?, ?, ?)',
    [name.trim(), building || null, printer_id || null]
  );
  save();
  res.json({ id: result.lastId });
});

app.put('/api/rooms/:id', requireAuth, requireAdmin, (req, res) => {
  const { name, building, is_active, printer_id } = req.body;
  if (!name || !name.trim()) return res.status(400).json({ error: 'Name required.' });
  run(
    'UPDATE rooms SET name = ?, building = ?, is_active = ?, printer_id = ? WHERE id = ?',
    [name.trim(), building || null, is_active ? 1 : 0, printer_id || null, req.params.id]
  );
  save();
  res.json({ ok: true });
});

app.post('/api/rooms/:id/toggle', requireAuth, requireAdmin, (req, res) => {
  run('UPDATE rooms SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id = ?', [req.params.id]);
  save();
  const room = queryOne('SELECT is_active FROM rooms WHERE id = ?', [req.params.id]);
  res.json({ is_active: room.is_active });
});

// ---------------------------------------------------------------------------
// Admin: manage toner types
// ---------------------------------------------------------------------------
app.post('/api/toner-types', requireAuth, requireAdmin, (req, res) => {
  const { name, model_number, printer_id } = req.body;
  if (!name || !name.trim()) return res.status(400).json({ error: 'Name required.' });
  const result = run(
    'INSERT INTO toner_types (name, model_number, printer_id) VALUES (?, ?, ?)',
    [name.trim(), model_number || null, printer_id || null]
  );
  save();
  res.json({ id: result.lastId });
});

app.put('/api/toner-types/:id', requireAuth, requireAdmin, (req, res) => {
  const { name, model_number, is_active, printer_id } = req.body;
  if (!name || !name.trim()) return res.status(400).json({ error: 'Name required.' });
  run(
    'UPDATE toner_types SET name = ?, model_number = ?, is_active = ?, printer_id = ? WHERE id = ?',
    [name.trim(), model_number || null, is_active ? 1 : 0, printer_id || null, req.params.id]
  );
  save();
  res.json({ ok: true });
});

app.post('/api/toner-types/:id/toggle', requireAuth, requireAdmin, (req, res) => {
  run('UPDATE toner_types SET is_active = CASE is_active WHEN 1 THEN 0 ELSE 1 END WHERE id = ?', [req.params.id]);
  save();
  const t = queryOne('SELECT is_active FROM toner_types WHERE id = ?', [req.params.id]);
  res.json({ is_active: t.is_active });
});

// ---------------------------------------------------------------------------
// Admin: manage users
// ---------------------------------------------------------------------------
app.get('/api/admin/users', requireAuth, requireAdmin, (req, res) => {
  res.json(query('SELECT id, username, full_name, is_admin FROM users ORDER BY full_name'));
});

app.post('/api/admin/users', requireAuth, requireAdmin, (req, res) => {
  const { username, full_name, is_admin } = req.body;
  if (!username || !full_name) return res.status(400).json({ error: 'Username and name required.' });
  const existing = queryOne('SELECT id FROM users WHERE username = ? COLLATE NOCASE', [username.trim()]);
  if (existing) return res.status(400).json({ error: 'Username already exists.' });
  const result = run('INSERT INTO users (username, full_name, is_admin) VALUES (?, ?, ?)',
    [username.trim(), full_name.trim(), is_admin ? 1 : 0]);
  save();
  res.json({ id: result.lastId });
});

app.put('/api/admin/users/:id', requireAuth, requireAdmin, (req, res) => {
  const { full_name, is_admin } = req.body;
  if (!full_name) return res.status(400).json({ error: 'Name required.' });
  run('UPDATE users SET full_name = ?, is_admin = ? WHERE id = ?',
    [full_name.trim(), is_admin ? 1 : 0, req.params.id]);
  save();
  res.json({ ok: true });
});

// ---------------------------------------------------------------------------
// SPA fallback
// ---------------------------------------------------------------------------
app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

// ---------------------------------------------------------------------------
// Start
// ---------------------------------------------------------------------------
async function start() {
  const SQL = await initSqlJs();

  if (fs.existsSync(DB_PATH)) {
    const buf = fs.readFileSync(DB_PATH);
    db = new SQL.Database(buf);
  } else {
    db = new SQL.Database();
  }

  db.run('PRAGMA foreign_keys = ON');

  // Core tables
  db.run(`CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE COLLATE NOCASE,
    full_name TEXT NOT NULL,
    is_admin INTEGER NOT NULL DEFAULT 0
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS printers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS rooms (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    building TEXT,
    printer_id INTEGER REFERENCES printers(id),
    is_active INTEGER NOT NULL DEFAULT 1
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS toner_types (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    model_number TEXT,
    printer_id INTEGER REFERENCES printers(id),
    is_active INTEGER NOT NULL DEFAULT 1
  )`);

  db.run(`CREATE TABLE IF NOT EXISTS requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id),
    room_id INTEGER NOT NULL REFERENCES rooms(id),
    toner_type_id INTEGER NOT NULL REFERENCES toner_types(id),
    notes TEXT,
    status TEXT NOT NULL DEFAULT 'Pending',
    created_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    completed_at TEXT,
    completed_by TEXT
  )`);

  // Migrate existing databases — add columns if they don't exist yet
  const migrations = [
    'ALTER TABLE rooms ADD COLUMN printer_id INTEGER REFERENCES printers(id)',
    'ALTER TABLE toner_types ADD COLUMN printer_id INTEGER REFERENCES printers(id)',
  ];
  for (const sql of migrations) {
    try { db.run(sql); } catch { /* column already exists — safe to ignore */ }
  }

  // Seed if empty
  const cnt = queryOne('SELECT COUNT(*) as c FROM users');
  if (cnt.c === 0) {
    run('INSERT INTO users (username, full_name, is_admin) VALUES (?, ?, ?)', ['admin', 'IT Administrator', 1]);
    run('INSERT INTO users (username, full_name, is_admin) VALUES (?, ?, ?)', ['jsmith', 'John Smith', 0]);
    run('INSERT INTO users (username, full_name, is_admin) VALUES (?, ?, ?)', ['jdoe', 'Jane Doe', 0]);

    const p1 = run('INSERT INTO printers (name) VALUES (?)', ['HP Color LaserJet Pro M254']).lastId;
    const p2 = run('INSERT INTO printers (name) VALUES (?)', ['Brother HL-L2350DW']).lastId;

    run('INSERT INTO rooms (name, building, printer_id) VALUES (?,?,?)', ['Room 101',    'Main Building', p1]);
    run('INSERT INTO rooms (name, building, printer_id) VALUES (?,?,?)', ['Room 203',    'Main Building', p1]);
    run('INSERT INTO rooms (name, building, printer_id) VALUES (?,?,?)', ['Reception',   'Front Office',  p2]);
    run('INSERT INTO rooms (name, building, printer_id) VALUES (?,?,?)', ['IT Office',   'Main Building', p1]);
    run('INSERT INTO rooms (name, building, printer_id) VALUES (?,?,?)', ['Meeting Room A', 'Annex',      p2]);

    run('INSERT INTO toner_types (name, model_number, printer_id) VALUES (?,?,?)', ['HP 207A Black',   'W2210A', p1]);
    run('INSERT INTO toner_types (name, model_number, printer_id) VALUES (?,?,?)', ['HP 207A Cyan',    'W2211A', p1]);
    run('INSERT INTO toner_types (name, model_number, printer_id) VALUES (?,?,?)', ['HP 207A Yellow',  'W2212A', p1]);
    run('INSERT INTO toner_types (name, model_number, printer_id) VALUES (?,?,?)', ['HP 207A Magenta', 'W2213A', p1]);
    run('INSERT INTO toner_types (name, model_number, printer_id) VALUES (?,?,?)', ['Brother TN-2420', 'TN2420', p2]);

    save();
  }

  app.listen(PORT, () => {
    console.log(`\n  Toner Desk running at http://localhost:${PORT}\n`);
  });
}

start().catch(err => { console.error('Failed to start:', err); process.exit(1); });
