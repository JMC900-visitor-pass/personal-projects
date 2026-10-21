// Creates (or resets) an admin account.
// Interactive:  npm run create-admin
// Scripted:     node server/database/create-admin.js <username> <password>
require('dotenv').config();
const bcrypt = require('bcryptjs');
const db = require('./db');

async function save(username, password) {
  username = String(username || '').trim();
  password = String(password || '').trim();
  if (!username || password.length < 8) {
    console.error('Username is required and password must be at least 8 characters.');
    process.exit(1);
  }
  const hash = await bcrypt.hash(password, 12);
  await db.query(
    'INSERT INTO users (username, password_hash) VALUES (?, ?) ON DUPLICATE KEY UPDATE password_hash = VALUES(password_hash)',
    [username, hash]
  );
  console.log(`Admin "${username}" created/updated.`);
  process.exit(0);
}

const [, , argUser, argPass] = process.argv;

if (argUser && argPass) {
  save(argUser, argPass).catch((e) => { console.error('Failed:', e.message); process.exit(1); });
} else {
  const readline = require('readline');
  const rl = readline.createInterface({ input: process.stdin, output: process.stdout });
  rl.question('Admin username: ', (u) => {
    rl.question('Admin password: ', (p) => {
      rl.close();
      save(u, p).catch((e) => { console.error('Failed:', e.message); process.exit(1); });
    });
  });
}
