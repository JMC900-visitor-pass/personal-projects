require('dotenv').config();
const path = require('path');
const express = require('express');
const session = require('express-session');

const userRoutes = require('./routes/user');
const adminRoutes = require('./routes/admin');

const app = express();

app.set('trust proxy', 1); // behind Apache reverse proxy
app.use(express.json({ limit: '100kb' }));

app.use(session({
  name: 'toner.sid',
  secret: process.env.SESSION_SECRET || 'dev-only-secret',
  resave: false,
  saveUninitialized: false,
  cookie: {
    httpOnly: true,
    sameSite: 'lax',
    maxAge: 8 * 60 * 60 * 1000 // 8 hours
  }
}));

// Static frontend
app.use(express.static(path.join(__dirname, '..', 'public')));

// API
app.use('/api', userRoutes);
app.use('/api/admin', adminRoutes);

// 404 for unknown API routes
app.use('/api', (req, res) => res.status(404).json({ error: 'Not found' }));

// Central error handler – never leak internals
app.use((err, req, res, next) => {
  console.error(err);
  res.status(500).json({ error: 'Something went wrong. Please try again.' });
});

const PORT = Number(process.env.PORT || 3000);
app.listen(PORT, () => console.log(`Toner Request System running on http://localhost:${PORT}`));
