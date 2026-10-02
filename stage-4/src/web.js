'use strict';

// Browser delivery (stage 2): the UI shell for HTML routes and bundled static
// files. Contract with surface: GET with Accept containing text/html on a UI
// route returns public/index.html; GET /static/<path> serves public/<path>.
// Nothing is fetched from outside at run time.

const fs = require('node:fs/promises');
const path = require('node:path');

const PUBLIC_DIR = path.resolve(__dirname, '..', 'public');
const UI_ROUTES = new Set(['/', '/requests', '/split', '/signup', '/login', '/authorizations']);
const TYPES = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.mjs': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.webp': 'image/webp',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.ttf': 'font/ttf',
  '.txt': 'text/plain; charset=utf-8',
};
// Same strict headers on the shell and every static file: only same-origin
// resources, no inline styles or scripts, no data: URLs, no framing.
const HEADERS = {
  'X-Content-Type-Options': 'nosniff',
  'X-Frame-Options': 'DENY',
  'Referrer-Policy': 'no-referrer',
  'Cache-Control': 'no-cache',
  'Content-Security-Policy': "default-src 'self'; img-src 'self'; style-src 'self'; font-src 'self'; connect-src 'self'; script-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
};

function wantsHtml(req, pathname) {
  if (req.method !== 'GET' || !UI_ROUTES.has(pathname)) return false;
  const accept = req.headers.accept;
  return typeof accept === 'string' && /(^|,)\s*text\/html\s*(;|,|$)/i.test(accept);
}

async function sendFile(res, file, headers) {
  let body;
  try {
    const st = await fs.stat(file);
    if (!st.isFile()) return false;
    body = await fs.readFile(file);
  } catch {
    return false;
  }
  res.writeHead(200, { ...headers, 'Content-Type': TYPES[path.extname(file).toLowerCase()] || 'application/octet-stream', 'Content-Length': body.length });
  res.end(body);
  return true;
}

function sendShell(req, res) {
  req.resume();
  return sendFile(res, path.join(PUBLIC_DIR, 'index.html'), HEADERS);
}

// Resolves true when a file was sent; false means 404.
function sendStatic(req, res, pathname) {
  req.resume();
  let rel;
  try {
    rel = decodeURIComponent(pathname.slice('/static/'.length));
  } catch {
    return Promise.resolve(false);
  }
  if (rel === '' || rel.includes('\0')) return Promise.resolve(false);
  const file = path.resolve(PUBLIC_DIR, rel);
  if (!file.startsWith(PUBLIC_DIR + path.sep)) return Promise.resolve(false);
  return sendFile(res, file, HEADERS);
}

module.exports = { wantsHtml, sendShell, sendStatic };
