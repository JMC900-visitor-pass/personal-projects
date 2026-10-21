const nodemailer = require('nodemailer');

let transporter = null;

function getTransporter() {
  if (transporter) return transporter;
  const config = {
    host: process.env.SMTP_HOST,
    port: Number(process.env.SMTP_PORT || 25),
    secure: process.env.SMTP_SECURE === 'true'
  };
  if (process.env.SMTP_USER) {
    config.auth = { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS };
  }
  transporter = nodemailer.createTransport(config);
  return transporter;
}

// Fire-and-forget: a failed email must never block a ticket.
async function sendRequestEmail({ ticketId, username, room, printer, toner }) {
  if (!process.env.SMTP_HOST || !process.env.ICT_EMAIL) {
    console.warn('Email not configured (SMTP_HOST / ICT_EMAIL missing) – skipping notification.');
    return;
  }
  const date = new Date().toLocaleString('en-GB');
  try {
    await getTransporter().sendMail({
      from: process.env.EMAIL_FROM || 'toner-system@localhost',
      to: process.env.ICT_EMAIL,
      subject: `Printer Toner Request – Room ${room}`,
      text:
`User: ${username}
Room: ${room}
Printer: ${printer}
Toner: ${toner}
Date: ${date}
Ticket ID: #${ticketId}`
    });
  } catch (err) {
    console.error('Email failed:', err.message);
  }
}

module.exports = { sendRequestEmail };
