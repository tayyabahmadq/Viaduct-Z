#!/usr/bin/env node
'use strict';

/**
 * Viaduct Pay — temporary mobile simulator.
 *
 * One process that:
 *   1. boots the real FastAPI app (server/) on 127.0.0.1:8010 with its own
 *      SQLite file (server/viaduct-sim.db),
 *   2. serves the phone-sized web client from sim/web on 0.0.0.0:8080,
 *   3. proxies /api/v1/* straight through to the API, so the UI in the browser
 *      is talking to the same ledger, guard rails and receipt tokens as the
 *      Android client,
 *   4. renders QR codes with Python's qrcode package.
 *
 * Nothing here changes the server or the Android app; delete sim/ and the
 * project is exactly as it was.
 */

const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const crypto = require('node:crypto');
const { spawn, spawnSync } = require('node:child_process');

const HERE = __dirname;
const REPO = path.resolve(HERE, '..');
const SERVER_DIR = path.join(REPO, 'server');
const WEB_DIR = path.join(HERE, 'web');
const QR_CACHE = path.join(HERE, '.cache', 'qr');
const DB_FILE = path.join(SERVER_DIR, 'viaduct-sim.db');

const API_PORT = Number(process.env.SIM_API_PORT || 8010);
const SIM_PORT = Number(process.env.SIM_PORT || 8080);
const BIND = process.env.SIM_BIND || '0.0.0.0';
const PYTHON = process.env.SIM_PYTHON || 'python';

fs.mkdirSync(QR_CACHE, { recursive: true });

/* ------------------------------------------------------------------ */
/* network helpers                                                     */
/* ------------------------------------------------------------------ */

function lanAddress() {
  const nets = os.networkInterfaces();
  const candidates = [];
  for (const name of Object.keys(nets)) {
    for (const net of nets[name] || []) {
      if (net.family !== 'IPv4' || net.internal) continue;
      if (net.address.startsWith('169.254.')) continue;
      candidates.push({ name, address: net.address });
    }
  }
  const wifi = candidates.find((c) => /wi-?fi|wlan|wireless/i.test(c.name));
  const private192 = candidates.find((c) => c.address.startsWith('192.168.'));
  return (wifi || private192 || candidates[0] || { address: '127.0.0.1' }).address;
}

const LAN_IP = lanAddress();
const PUBLIC_URL = `http://${LAN_IP}:${SIM_PORT}`;

/* ------------------------------------------------------------------ */
/* the real API                                                        */
/* ------------------------------------------------------------------ */

let api = null;

function startApi() {
  const env = {
    ...process.env,
    DATABASE_URL: 'sqlite:///./viaduct-sim.db',
    PUBLIC_BASE_URL: PUBLIC_URL,
    PYTHONUNBUFFERED: '1',
  };

  api = spawn(
    PYTHON,
    [
      '-m', 'uvicorn', 'app.main:app',
      '--host', '127.0.0.1',
      '--port', String(API_PORT),
      '--log-level', 'warning',
    ],
    { cwd: SERVER_DIR, env, stdio: ['ignore', 'pipe', 'pipe'], windowsHide: true }
  );

  const relay = (stream, tag) => {
    let buffer = '';
    stream.setEncoding('utf8');
    stream.on('data', (chunk) => {
      buffer += chunk;
      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() || '';
      for (const line of lines) {
        if (line.trim()) console.log(`[api] ${line}`);
      }
    });
  };
  relay(api.stdout, 'out');
  relay(api.stderr, 'err');

  api.on('exit', (code) => {
    if (code !== 0 && code !== null) {
      console.error(`[api] exited with code ${code}`);
    }
  });
}

function apiHealth() {
  return new Promise((resolve) => {
    const req = http.request(
      { host: '127.0.0.1', port: API_PORT, path: '/health', method: 'GET', timeout: 1500 },
      (res) => {
        let body = '';
        res.setEncoding('utf8');
        res.on('data', (c) => (body += c));
        res.on('end', () => resolve(res.statusCode === 200));
      }
    );
    req.on('error', () => resolve(false));
    req.on('timeout', () => {
      req.destroy();
      resolve(false);
    });
    req.end();
  });
}

async function waitForApi(timeoutMs = 45000) {
  const started = Date.now();
  while (Date.now() - started < timeoutMs) {
    if (await apiHealth()) return true;
    await new Promise((r) => setTimeout(r, 400));
  }
  return false;
}

/* ------------------------------------------------------------------ */
/* proxy                                                               */
/* ------------------------------------------------------------------ */

function proxy(req, res) {
  const started = Date.now();
  const upstream = http.request(
    {
      host: '127.0.0.1',
      port: API_PORT,
      path: req.url,
      method: req.method,
      headers: { ...req.headers, host: `127.0.0.1:${API_PORT}` },
    },
    (up) => {
      res.writeHead(up.statusCode || 502, {
        ...up.headers,
        'cache-control': 'no-store',
      });
      up.pipe(res);
      res.on('finish', () => log(req, res, started));
    }
  );

  upstream.on('error', (err) => {
    if (res.headersSent) return;
    res.writeHead(502, { 'content-type': 'application/json; charset=utf-8' });
    res.end(
      JSON.stringify({
        detail: 'E_API_UNAVAILABLE',
        message: `The API on 127.0.0.1:${API_PORT} is not answering (${err.code || err.message}).`,
      })
    );
    log(req, res, started);
  });

  if (req.method === 'GET' || req.method === 'HEAD') {
    upstream.end();
  } else {
    req.pipe(upstream);
  }
}

function log(req, res, started) {
  const ms = Date.now() - started;
  const stamp = new Date().toTimeString().slice(0, 8);
  console.log(`${stamp}  ${String(res.statusCode).padEnd(3)} ${req.method.padEnd(4)} ${req.url}  ${ms}ms`);
}

/* ------------------------------------------------------------------ */
/* QR codes                                                            */
/* ------------------------------------------------------------------ */

const QR_SCRIPT = [
  'import sys, qrcode',
  'from PIL import Image',
  'data, out, size = sys.argv[1], sys.argv[2], int(sys.argv[3])',
  'qr = qrcode.QRCode(border=1, box_size=8, error_correction=qrcode.constants.ERROR_CORRECT_M)',
  'qr.add_data(data)',
  'qr.make(fit=True)',
  'img = qr.make_image(fill_color="#0B1220", back_color="#FFFFFF").convert("RGB")',
  'img = img.resize((size, size), Image.NEAREST)',
  'img.save(out)',
].join('\n');

function qrPng(data, size) {
  const key = crypto.createHash('sha1').update(`${data}|${size}`).digest('hex') + '.png';
  const file = path.join(QR_CACHE, key);
  if (!fs.existsSync(file)) {
    const result = spawnSync(PYTHON, ['-c', QR_SCRIPT, data, file, String(size)], {
      encoding: 'utf8',
      timeout: 15000,
    });
    if (result.status !== 0) {
      throw new Error((result.stderr || result.error || 'qr generation failed').toString().trim());
    }
  }
  return fs.readFileSync(file);
}

/* ------------------------------------------------------------------ */
/* demo wallets                                                        */
/* ------------------------------------------------------------------ */

const SEEDED = ['Aarav Shah', 'Mei Chen', 'Lucas Meyer', 'Sofia Rossi', 'Noah Kim', 'Aisha Khan'];

function demoAccounts() {
  let DatabaseSync;
  try {
    ({ DatabaseSync } = require('node:sqlite'));
  } catch {
    return { accounts: [], error: 'node:sqlite is unavailable in this Node build' };
  }

  if (!fs.existsSync(DB_FILE)) {
    return { accounts: [], error: 'the API has not created its database yet' };
  }

  let db;
  try {
    db = new DatabaseSync(DB_FILE, { readOnly: true });
    const rows = db
      .prepare(
        'SELECT id, name, token48, api_token, balance_cents, credit_ceiling_cents, seq, created_at FROM devices ORDER BY created_at ASC'
      )
      .all();
    const accounts = rows.map((r) => ({
      device_id: r.id,
      name: r.name,
      token: r.api_token,
      token48: r.token48,
      balance_cents: r.balance_cents,
      credit_ceiling_cents: r.credit_ceiling_cents,
      seq: r.seq,
      seeded: SEEDED.includes(r.name),
    }));
    return { accounts };
  } catch (err) {
    return { accounts: [], error: String(err.message || err) };
  } finally {
    if (db) db.close();
  }
}

/* ------------------------------------------------------------------ */
/* static files                                                        */
/* ------------------------------------------------------------------ */

const MIME = {
  '.html': 'text/html; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.webmanifest': 'application/manifest+json; charset=utf-8',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.ico': 'image/x-icon',
  '.woff2': 'font/woff2',
  '.txt': 'text/plain; charset=utf-8',
};

function serveFile(res, file, status = 200) {
  fs.readFile(file, (err, data) => {
    if (err) {
      res.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
      res.end('Not found');
      return;
    }
    res.writeHead(status, {
      'content-type': MIME[path.extname(file).toLowerCase()] || 'application/octet-stream',
      'cache-control': 'no-store',
      'content-length': data.length,
    });
    res.end(data);
  });
}

function serveStatic(req, res, pathname) {
  const relative = decodeURIComponent(pathname).replace(/^\/+/, '');
  const target = path.resolve(WEB_DIR, relative || 'index.html');
  if (!target.startsWith(WEB_DIR)) {
    res.writeHead(403).end('Forbidden');
    return;
  }
  if (fs.existsSync(target) && fs.statSync(target).isFile()) {
    serveFile(res, target);
    return;
  }
  // Unknown path: hand back the app shell so deep links keep working.
  serveFile(res, path.join(WEB_DIR, 'index.html'));
}

/* ------------------------------------------------------------------ */
/* join page                                                           */
/* ------------------------------------------------------------------ */

function joinPage() {
  const qr = `/qr.png?size=460&data=${encodeURIComponent(PUBLIC_URL + '/')}`;
  return `<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Join the Viaduct Pay simulation</title>
<style>
  :root{color-scheme:light}
  body{margin:0;min-height:100vh;display:grid;place-items:center;background:#F6F8FB;color:#0B1220;
       font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
  main{background:#fff;border:1px solid #E2E8F0;border-radius:24px;padding:32px 28px;max-width:420px;
       width:calc(100% - 40px);text-align:center;box-shadow:0 18px 40px -24px rgba(15,23,42,.35)}
  h1{font-size:22px;margin:0 0 6px}
  p{margin:0;color:#64748B;font-size:14px;line-height:1.5}
  img{width:100%;max-width:300px;margin:20px auto 12px;display:block;border-radius:16px}
  code{display:block;background:#F1F5F9;border-radius:12px;padding:12px;font-size:15px;letter-spacing:.02em}
  .hint{margin-top:14px;font-size:12.5px;color:#94A3B8}
</style></head>
<body><main>
  <h1>Viaduct Pay — live simulation</h1>
  <p>Scan this with your phone camera, or type the address into the browser.</p>
  <img src="${qr}" alt="QR code with the simulation address">
  <code>${PUBLIC_URL}</code>
  <p class="hint">Phone and this PC must be on the same Wi-Fi. Works only while this computer is on.</p>
</main></body></html>`;
}

/* ------------------------------------------------------------------ */
/* server                                                              */
/* ------------------------------------------------------------------ */

const server = http.createServer((req, res) => {
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  const pathname = url.pathname;

  if (pathname === '/favicon.ico') {
    serveFile(res, path.join(WEB_DIR, 'icons', 'icon-192.png'));
    return;
  }

  if (pathname === '/health' || pathname.startsWith('/api/') || pathname.startsWith('/paypal/') ||
      pathname === '/docs' || pathname.startsWith('/docs/') || pathname === '/openapi.json') {
    proxy(req, res);
    return;
  }

  if (pathname === '/sim/info') {
    res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
    res.end(JSON.stringify({ lan_ip: LAN_IP, url: PUBLIC_URL, api_port: API_PORT, sim_port: SIM_PORT }));
    return;
  }

  if (pathname === '/sim/demo-accounts') {
    const payload = demoAccounts();
    res.writeHead(200, { 'content-type': 'application/json; charset=utf-8', 'cache-control': 'no-store' });
    res.end(JSON.stringify(payload));
    return;
  }

  if (pathname === '/qr.png') {
    const data = (url.searchParams.get('data') || PUBLIC_URL).slice(0, 512);
    const size = Math.min(Math.max(Number(url.searchParams.get('size')) || 300, 120), 900);
    try {
      const png = qrPng(data, size);
      res.writeHead(200, { 'content-type': 'image/png', 'cache-control': 'no-store', 'content-length': png.length });
      res.end(png);
    } catch (err) {
      console.error('[qr]', err.message);
      res.writeHead(500, { 'content-type': 'application/json; charset=utf-8' });
      res.end(JSON.stringify({ detail: 'E_QR_FAILED', message: err.message }));
    }
    return;
  }

  if (pathname === '/join') {
    res.writeHead(200, { 'content-type': 'text/html; charset=utf-8', 'cache-control': 'no-store' });
    res.end(joinPage());
    return;
  }

  if (req.method !== 'GET' && req.method !== 'HEAD') {
    res.writeHead(405, { 'content-type': 'text/plain; charset=utf-8' });
    res.end('Method not allowed');
    return;
  }

  serveStatic(req, res, pathname);
});

function shutdown() {
  console.log('\n[sim] shutting down…');
  try {
    if (api && !api.killed) api.kill();
  } catch {
    /* ignore */
  }
  server.close(() => process.exit(0));
  setTimeout(() => process.exit(0), 1500);
}

process.on('SIGINT', shutdown);
process.on('SIGTERM', shutdown);

(async () => {
  console.log('[sim] starting the Viaduct Pay API…');
  startApi();

  const ready = await waitForApi();
  if (!ready) {
    console.error(`[sim] API did not come up on 127.0.0.1:${API_PORT}. Is another process using it?`);
  } else {
    console.log(`[sim] API ready on http://127.0.0.1:${API_PORT}`);
  }

  server.listen(SIM_PORT, BIND, () => {
    console.log('');
    console.log('  Viaduct Pay — mobile simulation');
    console.log(`  open on this PC : http://localhost:${SIM_PORT}`);
    console.log(`  open on a phone : ${PUBLIC_URL}`);
    console.log(`  join QR page    : ${PUBLIC_URL}/join`);
    console.log(`  database        : ${path.relative(REPO, DB_FILE)}`);
    console.log('');
    console.log('  Phone must be on the same Wi-Fi. Ctrl+C stops both processes.');
    console.log('');
  });
})();
