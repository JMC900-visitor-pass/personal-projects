const express = require('express');
const db = require('../database/db');
const { detectUsername } = require('../middleware/auth');
const { sendRequestEmail } = require('../email/mailer');

const router = express.Router();

// Who am I (auto-detected from proxy header)
router.get('/me', (req, res) => {
  res.json({ username: detectUsername(req) });
});

// All rooms
router.get('/rooms', async (req, res, next) => {
  try {
    const [rows] = await db.query(
      'SELECT id, room_name, building FROM rooms ORDER BY building, room_name'
    );
    res.json(rows);
  } catch (err) { next(err); }
});

// Printers in a room (with toner info pre-joined)
router.get('/printers/:roomId', async (req, res, next) => {
  try {
    const roomId = Number(req.params.roomId);
    if (!Number.isInteger(roomId)) return res.status(400).json({ error: 'Invalid room id' });
    const [rows] = await db.query(
      `SELECT p.id, p.printer_name, p.printer_model,
              t.id AS toner_id, t.toner_name, t.toner_model, t.quantity
       FROM printers p
       JOIN toners t ON t.id = p.toner_id
       WHERE p.room_id = ?
       ORDER BY p.printer_name`,
      [roomId]
    );
    res.json(rows);
  } catch (err) { next(err); }
});

// Submit a toner request
router.post('/request', async (req, res, next) => {
  try {
    const username = detectUsername(req);
    const printerId = Number(req.body.printerId);
    if (!Number.isInteger(printerId)) return res.status(400).json({ error: 'Invalid printer' });

    // Server looks up everything itself – the client can't fake room/toner.
    const [[printer]] = await db.query(
      `SELECT p.id, p.printer_name, p.printer_model, p.room_id, p.toner_id,
              r.room_name, t.toner_name, t.toner_model
       FROM printers p
       JOIN rooms r ON r.id = p.room_id
       JOIN toners t ON t.id = p.toner_id
       WHERE p.id = ?`,
      [printerId]
    );
    if (!printer) return res.status(404).json({ error: 'Printer not found' });

    const [result] = await db.query(
      'INSERT INTO requests (username, room_id, printer_id, toner_id) VALUES (?, ?, ?, ?)',
      [username, printer.room_id, printer.id, printer.toner_id]
    );

    // Don't await – email must not slow the user down.
    sendRequestEmail({
      ticketId: result.insertId,
      username,
      room: printer.room_name,
      printer: `${printer.printer_name} (${printer.printer_model})`,
      toner: `${printer.toner_name} (${printer.toner_model})`
    });

    res.status(201).json({ ticketId: result.insertId });
  } catch (err) { next(err); }
});

module.exports = router;
