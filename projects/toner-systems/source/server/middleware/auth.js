// Admin session guard
function requireAdmin(req, res, next) {
  if (req.session && req.session.adminId) return next();
  return res.status(401).json({ error: 'Not authenticated' });
}

// Detect Windows username from reverse proxy header (e.g. Apache Kerberos / IIS).
// Falls back to "guest" so the system still works during setup/testing.
function detectUsername(req) {
  const header = (process.env.USERNAME_HEADER || 'x-remote-user').toLowerCase();
  let user = req.headers[header] || 'guest';
  // Strip DOMAIN\ prefix or @realm suffix
  user = String(user).split('\\').pop().split('@')[0];
  // Sanitise: allow letters, numbers, dot, dash, underscore
  return user.replace(/[^a-zA-Z0-9._-]/g, '').slice(0, 50) || 'guest';
}

module.exports = { requireAdmin, detectUsername };
