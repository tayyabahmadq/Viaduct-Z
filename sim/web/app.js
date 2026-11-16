'use strict';

/* ===================================================================== */
/* Viaduct Pay — temporary mobile simulation                             */
/* Talks to the real FastAPI ledger through the /api/v1 proxy.           */
/* ===================================================================== */

const API = '/api/v1';
const K = {
  account: 'viaduct.account',
  outbox: 'viaduct.outbox',
  velocity: 'viaduct.velocity',
};

const S = {
  account: null,
  route: { name: null, params: [], query: new URLSearchParams(), requested: null },
  main: document.getElementById('main'),
  appbar: document.getElementById('appbar'),
  tabbar: document.getElementById('tabbar'),
  toastEl: document.getElementById('toast'),
  toastTimer: null,
  cameraStream: null,
  demoAccounts: { seeded: [], others: [] },
};

/* ---------------------------------------------------------------- utils */

const LS = {
  get(key, fallback) {
    try {
      const raw = localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* private mode */
    }
  },
  del(key) {
    try {
      localStorage.removeItem(key);
    } catch {
      /* ignore */
    }
  },
};

function esc(value) {
  return String(value ?? '').replace(/[&<>"']/g, (c) => (
    { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]
  ));
}

const MONEY = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const money = (cents) => '$' + MONEY.format((Number(cents) || 0) / 100);

function initials(name) {
  const parts = String(name || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '··';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

function firstName(name) {
  return String(name || 'there').trim().split(/\s+/)[0];
}

function fmtTime(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return String(iso || '');
  const now = new Date();
  const sameDay = d.toDateString() === now.toDateString();
  const time = d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return sameDay ? time : `${d.toLocaleDateString([], { day: 'numeric', month: 'short' })} · ${time}`;
}

function dayLabel(iso) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return 'Earlier';
  const today = new Date();
  const yesterday = new Date();
  yesterday.setDate(today.getDate() - 1);
  if (d.toDateString() === today.toDateString()) return 'Today';
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday';
  return d.toLocaleDateString([], { weekday: 'short', day: 'numeric', month: 'short' });
}

function chunkToken(token) {
  return String(token || '').replace(/(\d{4})(?=\d)/g, '$1 ');
}

function uuid() {
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    try {
      return window.crypto.randomUUID();
    } catch {
      /* fall through */
    }
  }
  const bytes = new Uint8Array(16);
  if (window.crypto && window.crypto.getRandomValues) {
    window.crypto.getRandomValues(bytes);
  } else {
    for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  }
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function toast(message) {
  if (!message) return;
  S.toastEl.textContent = message;
  S.toastEl.classList.add('show');
  clearTimeout(S.toastTimer);
  S.toastTimer = setTimeout(() => S.toastEl.classList.remove('show'), 2800);
}

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    toast('Copied to clipboard');
    return;
  } catch {
    /* insecure origin on the LAN — fall back */
  }
  const area = document.createElement('textarea');
  area.value = text;
  area.setAttribute('readonly', '');
  area.style.position = 'fixed';
  area.style.opacity = '0';
  document.body.appendChild(area);
  area.select();
  try {
    document.execCommand('copy');
    toast('Copied to clipboard');
  } catch {
    toast('Copy failed — select the text manually');
  }
  document.body.removeChild(area);
}

/* ----------------------------------------------------------------- icons */

const ICONS = {
  home: '<path d="M3 10.6 12 3l9 7.6V20a1 1 0 0 1-1 1h-5.1v-6H9.1v6H4a1 1 0 0 1-1-1z"/>',
  scan: '<path d="M4 8.5V6a2 2 0 0 1 2-2h2.5"/><path d="M15.5 4H18a2 2 0 0 1 2 2v2.5"/><path d="M20 15.5V18a2 2 0 0 1-2 2h-2.5"/><path d="M8.5 20H6a2 2 0 0 1-2-2v-2.5"/><path d="M4 12h16"/>',
  activity: '<path d="M4 6h16"/><path d="M4 12h16"/><path d="M4 18h9"/>',
  user: '<circle cx="12" cy="8.2" r="3.6"/><path d="M4.8 20a7.2 7.2 0 0 1 14.4 0"/>',
  refresh: '<path d="M20 11.2A8 8 0 1 0 17.7 17"/><path d="M20 5v6h-6"/>',
  back: '<path d="M14.8 18 8.8 12l6-6"/>',
  chevron: '<path d="M9.5 18l6-6-6-6"/>',
  plus: '<path d="M12 5v14"/><path d="M5 12h14"/>',
  sparkle: '<path d="M12 3.5 13.7 9l5.5 1.7-5.5 1.7L12 18l-1.7-5.6L4.8 10.7 10.3 9z"/><path d="M18.5 16.5l.7 2 2 .7-2 .7-.7 2-.7-2-2-.7 2-.7z"/>',
  copy: '<rect x="9" y="9" width="11" height="11" rx="2.4"/><path d="M15 6.5V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v7a2 2 0 0 0 2 2h.5"/>',
  camera: '<path d="M4 8.5h2.6L8 6.2h8l1.4 2.3H20a1 1 0 0 1 1 1v9a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13.6" r="3.4"/>',
  upload: '<path d="M12 16.5V4.5"/><path d="M7.4 9.1 12 4.5l4.6 4.6"/><path d="M4.5 16.5v2a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2v-2"/>',
  backspace: '<path d="M9 5.5h10.5a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H9L3.5 12z"/><path d="M16.5 9.5l-5 5"/><path d="M11.5 9.5l5 5"/>',
  logout: '<path d="M15 4.5h3.5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1H15"/><path d="M10 8.5 6.5 12l3.5 3.5"/><path d="M6.5 12H16"/>',
  info: '<circle cx="12" cy="12" r="8.4"/><path d="M12 11v5.4"/><path d="M12 7.9h.01"/>',
  wifiOff: '<path d="M3 4l18 16"/><path d="M7 9.5a11 11 0 0 1 3.6-1.9"/><path d="M16.2 8.3A11 11 0 0 1 21 9.5"/><path d="M9.2 13a6.5 6.5 0 0 1 5.6-.2"/><path d="M12 17.6h.01"/>',
  send: '<path d="M20.5 3.5 3.8 10.2l6.2 2.3 2.3 6.2z"/><path d="M10 13.6 20.5 3.5"/>',
  check: '<path d="M4.5 12.5 9.5 17.5 19.5 7"/>',
  clock: '<circle cx="12" cy="12" r="8.4"/><path d="M12 7.6V12l3 1.8"/>',
};

function icon(name) {
  return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name] || ''}</svg>`;
}

/* ------------------------------------------------------------------- api */

class ApiError extends Error {
  constructor(message, { code = null, status = 0 } = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = code;
    this.status = status;
  }
}

async function api(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { accept: 'application/json' };
  if (body !== undefined) headers['content-type'] = 'application/json';
  if (auth && S.account) headers.authorization = `Bearer ${S.account.token}`;

  let response;
  try {
    response = await fetch(API + path, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: 'no-store',
    });
  } catch (err) {
    throw new ApiError('Network unreachable', { status: 0 });
  }

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    if (response.status === 401 && S.account) {
      signOut();
      toast('Session expired — sign in again');
      go('join');
    }
    const detail = data && data.detail;
    const code = typeof detail === 'string' ? detail : null;
    let message = code || `Request failed (${response.status})`;
    if (Array.isArray(detail) && detail.length) {
      message = detail[0].msg || message;
    }
    throw new ApiError(message, { code, status: response.status });
  }
  return data;
}

/* ---------------------------------------------------------------- reasons */

const REASONS = {
  E_SELF_PAY: 'You cannot pay your own wallet.',
  E_QUARANTINED_PEER: 'That wallet is quarantined.',
  E_CEILING_EXCEEDED: 'Above the per-transfer ceiling.',
  E_INSUFFICIENT_BALANCE: 'Not enough balance for this transfer.',
  E_DUPLICATE_TOKEN: 'Duplicate nonce — this payment was already submitted.',
  E_GUARDRAIL_BLOCKED: 'Guard rail blocked it (velocity or token checksum).',
  E_UNKNOWN_PEER: 'No wallet matches that 48-digit token.',
  E_RATE_LIMIT: 'Too many payments in the last minute.',
  E_MALFORMED: 'Malformed payment request.',
  E_PAYPAL_NOT_CONFIGURED: 'PayPal sandbox keys are not configured on this PC.',
};

const reasonText = (code) => REASONS[code] || code || 'Unknown reason';

/* ------------------------------------------------ client guard (TxGuard) */

function localScreen(cents, token) {
  if (!/^\d{48}$/.test(String(token || '')) || !Number.isInteger(cents) || cents <= 0) {
    return { code: 'E_MALFORMED' };
  }
  if (!S.account) return { code: 'E_MALFORMED' };
  if (token === S.account.token48) return { code: 'E_SELF_PAY' };
  if (cents > S.account.credit_ceiling_cents) return { code: 'E_CEILING_EXCEEDED' };
  if (cents > S.account.balance_cents) return { code: 'E_INSUFFICIENT_BALANCE' };
  const now = Date.now();
  const recent = (LS.get(K.velocity, []) || []).filter((t) => now - t < 60000);
  if (recent.length >= 5) return { code: 'E_GUARDRAIL_BLOCKED', why: 'velocity' };
  return null;
}

function rememberVelocity() {
  const now = Date.now();
  const recent = (LS.get(K.velocity, []) || []).filter((t) => now - t < 60000);
  recent.push(now);
  LS.set(K.velocity, recent);
}

/* --------------------------------------------------------------- outbox */

function enqueue(body) {
  const queue = LS.get(K.outbox, []);
  queue.push(body);
  LS.set(K.outbox, queue);
}

async function syncOutbox() {
  const queued = LS.get(K.outbox, []);
  if (!queued.length) return null;
  const result = await api('/payments/batch-sync', { method: 'POST', body: { items: queued } });
  LS.set(K.outbox, []);
  return result;
}

/* -------------------------------------------------------------- elements */

const notice = (code, extra = '') => `
  <div class="notice bad">
    <span class="title">${esc(code)}</span>
    ${esc(reasonText(code))}${extra ? `<br><span style="opacity:.8">${esc(extra)}</span>` : ''}
  </div>`;

const offlineNotice = (err) => `
  <div class="notice bad">
    <span class="title">Can't reach the local API</span>
    ${esc(err && err.message ? err.message : 'Network unreachable')} — check that the simulator window is still running on this PC.
    <div style="margin-top:8px"><button class="btn ghost sm" data-retry>Retry</button></div>
  </div>`;

/* ---------------------------------------------------------------- router */

function parseRoute() {
  const raw = location.hash.replace(/^#\/?/, '');
  const [pathPart, queryPart] = raw.split('?');
  const parts = pathPart.split('/').filter(Boolean).map((p) => decodeURIComponent(p));
  return {
    name: parts[0] || null,
    params: parts.slice(1),
    query: new URLSearchParams(queryPart || ''),
  };
}

function go(path, { replace = false } = {}) {
  const target = '#/' + String(path).replace(/^#?\/?/, '');
  if (location.hash === target) {
    render();
    return;
  }
  if (replace) location.replace(target);
  else location.hash = target;
}

function back() {
  if (history.length > 1) history.back();
  else go('home');
}

/* ---------------------------------------------------------------- screens */

function JoinScreen() {
  const wanted = S.route.requested === 'send';
  return {
    appbar: { title: 'Viaduct Pay', sub: 'SIM' },
    tabs: false,
    html: `
      <div class="brand">
        <div class="brand-mark">V</div>
        <div>
          <h1>Viaduct Pay</h1>
          <p>Demo credit ledger · no KYC · no real money</p>
        </div>
      </div>

      ${wanted ? `<div class="notice ok"><span class="title">Almost there</span>Sign in first — we'll open the payment you scanned straight after.</div>` : ''}

      <div class="card join-card">
        <label class="field">
          <span>Display name</span>
          <input id="join-name" maxlength="64" placeholder="e.g. Dev Patel" autocomplete="name" autocapitalize="words">
        </label>
        <button class="btn primary block" id="join-create">Create my wallet</button>
        <p class="hint">Registers a real wallet on this PC's ledger with a $2,500.00 starting balance.</p>
      </div>

      <div class="section-head"><h2>Join a demo wallet</h2><span class="pill soft">instant</span></div>
      <div class="card flush list" id="join-demos">
        <div class="empty">Loading demo wallets…</div>
      </div>
      <div id="join-others"></div>

      <p class="fineprint">
        Temporary simulation of the Viaduct Pay Android demo. The ledger, guard rails and
        receipt tokens are the real server in <code>server/</code>; only the screen in front of
        you is a web stand-in. Reachable while this PC stays on and on the same Wi-Fi.
      </p>
    `,
    mount: mountJoin,
  };
}

async function mountJoin() {
  const nameInput = document.getElementById('join-name');
  const createBtn = document.getElementById('join-create');

  const create = async () => {
    createBtn.disabled = true;
    createBtn.innerHTML = '<span class="spin"></span> Creating…';
    try {
      const account = await api('/devices/register', {
        method: 'POST',
        auth: false,
        body: { device_id: uuid(), name: nameInput.value.trim() || null },
      });
      setAccount(account);
      toast(`Wallet created — ${account.name}`);
      afterSignIn();
    } catch (err) {
      createBtn.disabled = false;
      createBtn.textContent = 'Create my wallet';
      toast(err.message || 'Could not create the wallet');
    }
  };

  createBtn.addEventListener('click', create);
  nameInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') create();
  });

  try {
    const res = await fetch('/sim/demo-accounts', { cache: 'no-store' });
    const data = await res.json();
    const accounts = data.accounts || [];
    S.demoAccounts.seeded = accounts.filter((a) => a.seeded);
    S.demoAccounts.others = accounts.filter((a) => !a.seeded).reverse().slice(0, 6);
    paintDemoWallets();
  } catch {
    const box = document.getElementById('join-demos');
    if (box) box.innerHTML = '<div class="empty">Demo wallets are unavailable — create a wallet above instead.</div>';
  }
}

function walletRow(account) {
  return `
    <button class="list-row" data-wallet="${esc(account.token)}">
      <div class="avatar">${esc(initials(account.name))}</div>
      <div class="row-main">
        <strong>${esc(account.name)}</strong>
        <span>${money(account.balance_cents)} balance</span>
      </div>
      <div class="row-end"><span class="chev">${icon('chevron')}</span></div>
    </button>`;
}

function paintDemoWallets() {
  const box = document.getElementById('join-demos');
  if (!box) return;
  const seeded = S.demoAccounts.seeded;
  box.innerHTML = seeded.length
    ? seeded.map(walletRow).join('')
    : '<div class="empty">No seeded wallets yet — the API seeds them on first boot.</div>';

  box.querySelectorAll('[data-wallet]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const account = [...S.demoAccounts.seeded, ...S.demoAccounts.others].find(
        (a) => a.token === btn.dataset.wallet
      );
      if (!account) return;
      setAccount(account);
      toast(`Signed in as ${account.name}`);
      afterSignIn();
    });
  });

  const others = S.demoAccounts.others;
  const holder = document.getElementById('join-others');
  if (holder && others.length) {
    holder.innerHTML = `
      <div class="section-head"><h2>Created on this PC</h2></div>
      <div class="card flush list" id="join-others-list">${others.map(walletRow).join('')}</div>`;
    holder.querySelectorAll('[data-wallet]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const account = others.find((a) => a.token === btn.dataset.wallet);
        if (!account) return;
        setAccount(account);
        toast(`Signed in as ${account.name}`);
        afterSignIn();
      });
    });
  }
}

/* ------------------------------------------------------------------ home */

function HomeScreen() {
  const account = S.account;
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';

  return {
    appbar: {
      title: 'Viaduct Pay',
      sub: 'SIM',
      actions: [{ icon: 'refresh', label: 'Refresh', act: 'refresh' }],
    },
    tabs: true,
    html: `
      <div class="hello">
        <h1>${greeting}, ${esc(firstName(account.name))}</h1>
        <p>${new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</p>
      </div>

      <div class="balance-card">
        <div class="balance-top">
          <span class="label">Total balance</span>
          <span class="pill">Demo</span>
        </div>
        <div class="balance-amount" id="home-balance">${money(account.balance_cents)}</div>
        <div class="balance-meta" id="home-ceiling">Ceiling per transfer · ${money(account.credit_ceiling_cents)}</div>
        <div class="balance-foot">
          <span>wallet ${esc(account.token48.slice(0, 4))} ${esc(account.token48.slice(4, 8))}</span>
          <span id="home-seq">seq ${account.seq}</span>
        </div>
      </div>

      <div class="actions">
        <button class="action" data-go="scan">
          <span class="glyph">${icon('scan')}</span>
          <strong>Scan &amp; pay</strong>
          <span>QR, token or nearby wallet</span>
        </button>
        <button class="action" data-go="activity">
          <span class="glyph">${icon('activity')}</span>
          <strong>Activity</strong>
          <span>Both sides of the ledger</span>
        </button>
        <button class="action" data-go="topup">
          <span class="glyph">${icon('plus')}</span>
          <strong>Top up</strong>
          <span>PayPal sandbox</span>
        </button>
        <button class="action" data-go="assistant">
          <span class="glyph">${icon('sparkle')}</span>
          <strong>Assistant</strong>
          <span>“send $25 to Mei”</span>
        </button>
      </div>

      <div id="home-note" style="margin-top:14px"></div>

      <div class="section-head">
        <h2>Recent activity</h2>
        <button class="link" data-go="activity">See all</button>
      </div>
      <div class="card flush list" id="home-recent">
        <div class="empty">Loading activity…</div>
      </div>
    `,
    mount: mountHome,
  };
}

function paintBalance(account) {
  const balance = document.getElementById('home-balance');
  if (balance) balance.textContent = money(account.balance_cents);
  const ceiling = document.getElementById('home-ceiling');
  if (ceiling) ceiling.textContent = `Ceiling per transfer · ${money(account.credit_ceiling_cents)}`;
  const seq = document.getElementById('home-seq');
  if (seq) seq.textContent = `seq ${account.seq}`;
}

async function mountHome() {
  const recent = document.getElementById('home-recent');
  const note = document.getElementById('home-note');

  try {
    const synced = await syncOutbox();
    if (synced) {
      toast(`${synced.accepted.length} queued payment(s) settled, ${synced.declined.length} declined`);
    }
    const [account, rows] = await Promise.all([api('/me'), api('/payments?limit=6')]);
    setAccount(account);
    paintBalance(account);
    if (note) note.innerHTML = '';
    if (recent) recent.innerHTML = rows.length ? rows.map(txRow).join('') : emptyActivity();
  } catch (err) {
    if (recent) {
      recent.innerHTML = `<div class="empty">Activity isn't available right now.</div>`;
    }
    if (note) {
      note.innerHTML = offlineNotice(err);
      note.querySelector('[data-retry]')?.addEventListener('click', mountHome);
    }
  }
}

function emptyActivity() {
  return `<div class="empty">No payments yet.<br>Scan a wallet's QR or pick a peer from Scan &amp; pay.</div>`;
}

function txRow(item) {
  const incoming = item.direction === 'IN';
  const raw = item.counterparty || '';
  const numeric = /^\d{12,}$/.test(raw);
  const name = numeric ? 'Unknown wallet' : raw || 'Wallet';
  const lead = numeric ? `${raw.slice(0, 4)}…${raw.slice(-4)}` : item.memo ? esc(item.memo) : incoming ? 'Received' : 'Sent';
  return `
    <div class="list-row static">
      <div class="avatar ${incoming ? '' : 'alt'}">${numeric ? '?' : esc(initials(name))}</div>
      <div class="row-main">
        <strong>${esc(name)}</strong>
        <span>${lead} · ${esc(fmtTime(item.created_at))}</span>
      </div>
      <div class="row-end">
        <div class="amount ${incoming ? 'in' : ''}">${incoming ? '+' : '−'}${money(item.amount_cents)}</div>
        <div class="meta ${item.status === 'DECLINED' ? 'declined' : ''}">${esc(item.status)}</div>
      </div>
    </div>`;
}

/* -------------------------------------------------------------- activity */

function ActivityScreen() {
  return {
    appbar: {
      title: 'Activity',
      actions: [{ icon: 'refresh', label: 'Refresh', act: 'refresh' }],
    },
    tabs: true,
    html: `<div class="card flush list" id="act-list"><div class="empty">Loading…</div></div>
           <p class="fineprint">Every row is a real ledger entry on this PC — declines included.</p>`,
    mount: async () => {
      const list = document.getElementById('act-list');
      try {
        const rows = await api('/payments?limit=100');
        if (!rows.length) {
          list.innerHTML = emptyActivity();
          return;
        }
        let html = '';
        let day = '';
        for (const item of rows) {
          const label = dayLabel(item.created_at);
          if (label !== day) {
            html += `<div class="day">${esc(label)}</div>`;
            day = label;
          }
          html += txRow(item);
        }
        list.innerHTML = html;
      } catch (err) {
        list.innerHTML = `<div class="empty">Could not load activity.<br>${esc(err.message)}</div>`;
      }
    },
  };
}

/* ------------------------------------------------------------------ scan */

function ScanScreen() {
  const cameraSupported = 'BarcodeDetector' in window && window.isSecureContext;
  const canDecodePhoto = typeof window.jsQR === 'function';

  return {
    appbar: { title: 'Scan & pay' },
    tabs: true,
    html: `
      <div class="card">
        ${cameraSupported ? `
        <div class="scan-frame" id="scan-frame">
          <video id="scan-video" playsinline muted hidden></video>
          <div class="scan-idle" id="scan-idle">
            ${icon('scan')}
            <div>Point the camera at a Viaduct QR code.</div>
          </div>
        </div>` : `
        <div class="scan-idle" id="scan-idle" style="padding:4px 0 10px">
          ${icon('scan')}
          <div>Scan a Viaduct QR code</div>
        </div>`}
        <div class="row wrap">
          ${cameraSupported ? '<button class="btn primary grow" id="scan-camera">Open camera</button>' : ''}
          ${canDecodePhoto ? '<label class="btn soft grow" for="scan-photo">Upload a photo</label>' : ''}
          <input id="scan-photo" type="file" accept="image/*" capture="environment" hidden>
        </div>
        <p class="hint" id="scan-hint">
          ${cameraSupported
            ? 'If the preview stays black, use a photo or paste the token instead.'
            : 'In-app camera needs HTTPS, which this LAN server does not have. Photograph the QR, paste the token, or let the phone camera app open the code as a link.'}
        </p>
      </div>

      <div class="card">
        <label class="field">
          <span>Paste a 48-digit token</span>
          <input id="scan-token" inputmode="numeric" autocomplete="off" placeholder="0000 0000 0000 …" maxlength="48">
        </label>
        <button class="btn primary block" id="scan-go" disabled style="margin-top:12px">Continue</button>
        <p class="hint" id="scan-count">0 / 48 digits</p>
      </div>

      <div class="section-head"><h2>Wallets nearby</h2><span class="pill soft" id="peer-count">—</span></div>
      <div class="card flush list" id="scan-peers"><div class="empty">Loading wallets…</div></div>
    `,
    mount: mountScan,
  };
}

async function mountScan() {
  const input = document.getElementById('scan-token');
  const goBtn = document.getElementById('scan-go');
  const count = document.getElementById('scan-count');

  const updateInput = () => {
    const digits = input.value.replace(/\D/g, '').slice(0, 48);
    if (digits !== input.value) input.value = digits;
    count.textContent = `${digits.length} / 48 digits`;
    goBtn.disabled = digits.length !== 48;
  };

  input.addEventListener('input', updateInput);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && input.value.length === 48) goBtn.click();
  });
  goBtn.addEventListener('click', () => handleScan(input.value));

  document.getElementById('scan-camera')?.addEventListener('click', openCamera);
  document.getElementById('scan-photo')?.addEventListener('change', async (e) => {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    toast('Reading the photo…');
    try {
      const text = await decodePhoto(file);
      if (!text) {
        toast('No QR code found in that photo — try a closer shot.');
        return;
      }
      handleScan(text);
    } catch (err) {
      toast(`Could not read that photo: ${err.message}`);
    } finally {
      e.target.value = '';
    }
  });

  try {
    const peers = await api('/peers');
    S.peers = peers;
    const box = document.getElementById('scan-peers');
    const badge = document.getElementById('peer-count');
    if (badge) badge.textContent = String(peers.length);
    box.innerHTML = peers.length
      ? peers
          .map(
            (peer) => `
        <button class="list-row" data-token="${esc(peer.token48)}" data-name="${esc(peer.name)}">
          <div class="avatar ${peer.online ? '' : 'alt'}">${esc(initials(peer.name))}</div>
          <div class="row-main">
            <strong>${esc(peer.name)}</strong>
            <span><span class="dot ${peer.online ? '' : 'off'}"></span>${peer.online ? 'online' : 'offline'} · ${esc(peer.token48.slice(0, 4))} ${esc(peer.token48.slice(4, 8))}</span>
          </div>
          <div class="row-end"><span class="chev">${icon('chevron')}</span></div>
        </button>`
          )
          .join('')
      : '<div class="empty">No other wallets yet. Sign in on a second phone — or create another wallet here.</div>';

    box.querySelectorAll('[data-token]').forEach((btn) => {
      btn.addEventListener('click', () => {
        go(`send/${btn.dataset.token}?to=${encodeURIComponent(btn.dataset.name)}`);
      });
    });
  } catch (err) {
    document.getElementById('scan-peers').innerHTML =
      `<div class="empty">Could not load wallets.<br>${esc(err.message)}</div>`;
  }
}

async function openCamera() {
  const video = document.getElementById('scan-video');
  const idle = document.getElementById('scan-idle');
  const hint = document.getElementById('scan-hint');
  const button = document.getElementById('scan-camera');

  try {
    S.cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    });
    video.srcObject = S.cameraStream;
    video.hidden = false;
    idle.hidden = true;
    await video.play();
    button.textContent = 'Stop camera';
    button.onclick = () => {
      stopCamera();
      render();
    };

    const detector = new BarcodeDetector({ formats: ['qr_code'] });
    const tick = async () => {
      if (!S.cameraStream) return;
      try {
        const codes = await detector.detect(video);
        if (codes.length) {
          const value = codes[0].rawValue;
          stopCamera();
          handleScan(value);
          return;
        }
      } catch {
        /* keep polling */
      }
      setTimeout(tick, 320);
    };
    tick();
  } catch (err) {
    if (hint) hint.textContent = `Camera unavailable (${err.message}). Use a photo or paste the token below.`;
  }
}

function stopCamera() {
  if (!S.cameraStream) return;
  for (const track of S.cameraStream.getTracks()) track.stop();
  S.cameraStream = null;
  const video = document.getElementById('scan-video');
  if (video) {
    video.srcObject = null;
    video.hidden = true;
  }
  const idle = document.getElementById('scan-idle');
  if (idle) idle.hidden = false;
}

async function decodePhoto(file) {
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1400 / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.round(bitmap.width * scale));
  canvas.height = Math.max(1, Math.round(bitmap.height * scale));
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  const image = ctx.getImageData(0, 0, canvas.width, canvas.height);
  if (typeof window.jsQR !== 'function') return null;
  const found = window.jsQR(image.data, image.width, image.height, { inversionAttempts: 'attemptBoth' });
  return found ? found.data : null;
}

async function handleScan(raw) {
  const text = String(raw || '').trim();
  const match = text.match(/\d{48}/);
  if (!match) {
    toast('That is not a Viaduct token — a token is 48 digits.');
    return;
  }
  const token = match[0];
  let name = 'Scanned wallet';
  try {
    const peer = await api(`/peers/resolve?token48=${token}`, { auth: false });
    if (peer && peer.name) name = peer.name;
  } catch {
    /* unknown peer: let the server answer */
  }
  go(`send/${token}?to=${encodeURIComponent(name)}`);
}

/* ------------------------------------------------------------------ send */

function SendScreen(route) {
  const token = String(route.params[0] || '').trim();
  const payee = route.query.get('to') || '';
  const initial = Number(route.query.get('amount') || 0) || 0;

  return {
    appbar: { title: 'Send money', back: true },
    tabs: false,
    html: `
      <div id="pay-form">
        <div class="card">
          <div class="payee">
            <div class="avatar">${esc(initials(payee || 'VW'))}</div>
            <div class="grow">
              <div class="name">${esc(payee || 'Viaduct wallet')}</div>
              <div class="token">${esc(chunkToken(token))}</div>
            </div>
          </div>
        </div>

        <div class="amount-display"><span class="cur">$</span><span id="pay-amount">0.00</span></div>
        <div class="amount-sub" id="pay-sub">Balance ${money(S.account.balance_cents)}</div>
        <div id="pay-notice"></div>

        <div class="keypad" id="pay-pad">
          ${['1', '2', '3', '4', '5', '6', '7', '8', '9', '00', '0', 'del']
            .map((key) => `<button class="key" data-key="${key}">${key === 'del' ? icon('backspace') : key}</button>`)
            .join('')}
        </div>

        <label class="field">
          <span>Note (optional)</span>
          <input id="pay-memo" maxlength="140" placeholder="Dinner, rent, coffee…">
        </label>

        <button class="btn primary block lg" id="pay-send" style="margin-top:14px" disabled>Send $0.00</button>
        <p class="fineprint">
          Guard rails run twice: this screen mirrors the client <code>TxGuard</code>, the server
          runs <code>db_guard</code>. A decline is still recorded in the ledger.
        </p>
      </div>
    `,
    mount: () => mountSend(token, payee, initial),
  };
}

function mountSend(token, payee, initial) {
  let digits = initial > 0 ? String(initial) : '';
  const amountEl = document.getElementById('pay-amount');
  const subEl = document.getElementById('pay-sub');
  const noticeEl = document.getElementById('pay-notice');
  const sendBtn = document.getElementById('pay-send');
  const memoEl = document.getElementById('pay-memo');
  let busy = false;

  const cents = () => (digits ? Number(digits) : 0);

  const update = () => {
    const value = cents();
    amountEl.textContent = MONEY.format(value / 100);
    subEl.textContent = `Balance ${money(S.account.balance_cents)} · after send ${money(Math.max(0, S.account.balance_cents - value))}`;
    sendBtn.textContent = `Send ${money(value)}`;
    sendBtn.disabled = value <= 0 || busy;

    const blocked = value > 0 ? localScreen(value, token) : null;
    noticeEl.innerHTML = blocked ? notice(blocked.code) : '';
  };

  document.getElementById('pay-pad').addEventListener('click', (e) => {
    const key = e.target.closest('[data-key]');
    if (!key || busy) return;
    const value = key.dataset.key;
    if (value === 'del') digits = digits.slice(0, -1);
    else if (digits.length < 9) digits += value;
    digits = digits.replace(/^0+(?=\d)/, '');
    update();
  });

  memoEl.addEventListener('input', () => {
    if (memoEl.value.length > 140) memoEl.value = memoEl.value.slice(0, 140);
  });

  const send = async () => {
    const value = cents();
    if (value <= 0 || busy) return;
    const blocked = localScreen(value, token);
    if (blocked) {
      noticeEl.innerHTML = notice(blocked.code);
      toast(reasonText(blocked.code));
      return;
    }

    busy = true;
    sendBtn.innerHTML = '<span class="spin"></span> Sending…';
    sendBtn.disabled = true;
    const body = {
      to_token48: token,
      amount_cents: value,
      memo: memoEl.value.trim() || null,
      idempotency_key: uuid(),
    };

    try {
      const receipt = await api('/payments', { method: 'POST', body });
      rememberVelocity();
      if (S.account) S.account.balance_cents = receipt.sender_balance;
      showReceipt(receipt, payee, value);
      api('/me').then(setAccount).catch(() => {});
    } catch (err) {
      busy = false;
      if (!err.status) {
        enqueue(body);
        showQueued(value);
        return;
      }
      sendBtn.textContent = `Send ${money(value)}`;
      sendBtn.disabled = false;
      noticeEl.innerHTML = notice(err.code || `HTTP_${err.status}`, err.message);
      toast(err.message || 'Payment failed');
    }
  };

  sendBtn.addEventListener('click', send);
  update();
}

function showReceipt(receipt, payee, amount) {
  const form = document.getElementById('pay-form');
  if (!form) return;
  const ok = receipt.status === 'COMPLETED';
  form.innerHTML = `
    <div class="card">
      <div class="receipt-head">
        <span class="pill ${ok ? 'ok' : 'bad'}">${esc(receipt.status)}</span>
        <span style="font-size:11.5px;color:var(--faint)">${esc(fmtTime(new Date().toISOString()))}</span>
      </div>
      <div class="receipt-amount">${money(receipt.amount_cents)}</div>
      <dl class="receipt-lines">
        <div class="receipt-line"><dt>To</dt><dd>${esc(payee || 'Viaduct wallet')}</dd></div>
        <div class="receipt-line"><dt>Your balance</dt><dd>${money(receipt.sender_balance)}</dd></div>
        ${receipt.reason_code ? `<div class="receipt-line"><dt>Reason</dt><dd>${esc(receipt.reason_code)}</dd></div>` : ''}
        ${receipt.token48 ? `<div class="receipt-line"><dt>Receipt token</dt><dd class="mono">${esc(receipt.token48.slice(0, 6))}…${esc(receipt.token48.slice(-4))}</dd></div>` : ''}
        <div class="receipt-line"><dt>Ref</dt><dd class="mono">${esc(String(receipt.transaction_id).slice(0, 8))}</dd></div>
      </dl>
      ${ok
        ? '<p class="hint">Settled by the local ledger. The receipt token can be verified later with <code>POST /api/v1/tokens/verify</code>.</p>'
        : `<p class="hint">${esc(reasonText(receipt.reason_code))}</p>`}
      <button class="btn primary block lg" id="pay-done" style="margin-top:16px">Done</button>
    </div>
  `;
  document.getElementById('pay-done').addEventListener('click', () => go('home'));
}

function showQueued(amount) {
  const form = document.getElementById('pay-form');
  if (!form) return;
  form.innerHTML = `
    <div class="card">
      <div class="receipt-head"><span class="pill soft">QUEUED</span></div>
      <div class="receipt-amount">${money(amount)}</div>
      <p class="hint">
        The API isn't reachable, so this payment is sitting in the phone's outbox.
        It settles automatically the next time the wallet loads with a connection —
        same behaviour as the Android client.
      </p>
      <button class="btn ghost block" id="queued-back" style="margin-top:16px">Back to wallet</button>
    </div>`;
  document.getElementById('queued-back').addEventListener('click', () => go('home'));
}

/* --------------------------------------------------------------- top-up */

function TopUpScreen() {
  return {
    appbar: { title: 'Top up', back: true },
    tabs: false,
    html: `
      <div class="card">
        <div style="text-align:center">
          <span class="label">Top up amount</span>
          <div class="receipt-amount" id="topup-amount" style="margin-top:8px">$25.00</div>
        </div>
      </div>
      <div class="row" id="topup-presets">
        ${[[1000, '$10'], [2500, '$25'], [5000, '$50']]
          .map(([cents, label]) => `<button class="btn ${cents === 2500 ? 'primary' : 'ghost'} grow" data-cents="${cents}">${label}</button>`)
          .join('')}
      </div>
      <p class="hint">Pay with PayPal sandbox, then capture the order to credit the wallet.</p>
      <div id="topup-body" style="margin-top:14px"></div>
      <p class="fineprint">
        Requires <code>PAYPAL_CLIENT_ID</code> and <code>PAYPAL_CLIENT_SECRET</code> in the
        simulator's environment. Without them the endpoint answers
        <code>503 E_PAYPAL_NOT_CONFIGURED</code> and nothing else breaks.
      </p>
    `,
    mount: mountTopUp,
  };
}

function mountTopUp() {
  let cents = 2500;
  let order = null;
  let busy = false;
  const amountEl = document.getElementById('topup-amount');
  const body = document.getElementById('topup-body');

  const paint = () => {
    amountEl.textContent = money(cents);
    document.querySelectorAll('#topup-presets [data-cents]').forEach((btn) => {
      const active = Number(btn.dataset.cents) === cents;
      btn.className = `btn ${active ? 'primary' : 'ghost'} grow`;
    });
  };

  document.getElementById('topup-presets').addEventListener('click', (e) => {
    const btn = e.target.closest('[data-cents]');
    if (!btn || busy) return;
    cents = Number(btn.dataset.cents);
    order = null;
    body.innerHTML = '';
    paint();
  });

  const createOrder = async () => {
    busy = true;
    body.innerHTML = '<div class="notice">Creating a PayPal sandbox order…</div>';
    try {
      order = await api('/topups/paypal/order', { method: 'POST', body: { amount_cents: cents } });
      body.innerHTML = `
        <div class="card">
          <div class="receipt-head"><span class="pill soft">${esc(order.status || 'CREATED')}</span></div>
          <div class="receipt-amount">${money(order.amount_cents)}</div>
          <dl class="receipt-lines">
            <div class="receipt-line"><dt>Order</dt><dd class="mono">${esc(order.order_id)}</dd></div>
            <div class="receipt-line"><dt>Currency</dt><dd>${esc(order.currency)}</dd></div>
          </dl>
          <div class="row" style="margin-top:14px">
            ${order.approve_url ? `<a class="btn primary grow" href="${esc(order.approve_url)}" target="_blank" rel="noreferrer">Open PayPal</a>` : ''}
            <button class="btn ghost grow" id="topup-capture">I approved — capture</button>
          </div>
        </div>`;
      document.getElementById('topup-capture').addEventListener('click', capture);
    } catch (err) {
      body.innerHTML = err.code === 'E_PAYPAL_NOT_CONFIGURED'
        ? `<div class="notice bad"><span class="title">PayPal sandbox isn't configured</span>
             This PC has no <code>PAYPAL_CLIENT_ID</code> / <code>PAYPAL_CLIENT_SECRET</code>.
             Start the simulator with them set, or demo the ledger without top-ups.</div>`
        : `<div class="notice bad"><span class="title">${esc(err.code || 'TOPUP_FAILED')}</span>${esc(err.message)}</div>`;
    } finally {
      busy = false;
    }
  };

  const capture = async () => {
    if (!order) return;
    busy = true;
    try {
      const result = await api('/topups/paypal/capture', { method: 'POST', body: { order_id: order.order_id } });
      api('/me').then(setAccount).catch(() => {});
      body.innerHTML = `
        <div class="card">
          <div class="receipt-head"><span class="pill ${result.status === 'COMPLETED' ? 'ok' : 'bad'}">${esc(result.status)}</span></div>
          <div class="receipt-amount">${money(result.amount_cents)}</div>
          <dl class="receipt-lines">
            <div class="receipt-line"><dt>New balance</dt><dd>${money(result.balance_cents)}</dd></div>
            <div class="receipt-line"><dt>Order</dt><dd class="mono">${esc(result.order_id)}</dd></div>
            ${result.capture_id ? `<div class="receipt-line"><dt>Capture</dt><dd class="mono">${esc(String(result.capture_id).slice(0, 12))}…</dd></div>` : ''}
          </dl>
          <button class="btn primary block" id="topup-done" style="margin-top:16px">Done</button>
        </div>`;
      document.getElementById('topup-done').addEventListener('click', () => go('home'));
    } catch (err) {
      body.innerHTML = `<div class="notice bad"><span class="title">${esc(err.code || 'CAPTURE_FAILED')}</span>${esc(err.message)}</div>`;
    } finally {
      busy = false;
    }
  };

  body.innerHTML = '<button class="btn primary block lg" id="topup-create">Continue with PayPal</button>';
  document.getElementById('topup-create').addEventListener('click', createOrder);
  paint();
}

/* ------------------------------------------------------------- assistant */

function AssistantScreen() {
  return {
    appbar: { title: 'AI assistant' },
    tabs: false,
    html: `
      <p class="hint" style="margin:6px 2px 14px">
        Describe a payment in plain English. The server turns it into an instruction and
        resolves the recipient against your peer list — nothing is sent until you continue.
      </p>
      <div class="card">
        <label class="field">
          <span>Request</span>
          <textarea id="ai-text" rows="3" maxlength="280" placeholder="send $25 to Mei Chen"></textarea>
        </label>
        <div class="chips" id="ai-chips">
          <button class="chip">send $25 to Mei Chen</button>
          <button class="chip">pay Sofia Rossi $12.50 for coffee</button>
          <button class="chip">give Lucas 40</button>
        </div>
        <button class="btn primary block" id="ai-parse" style="margin-top:14px">Parse</button>
      </div>
      <div id="ai-result"></div>
      <p class="fineprint">
        With no <code>AI_API_KEY</code> the server's deterministic parser answers and reports
        <code>source: "rules"</code> instead of pretending a model was involved.
      </p>
    `,
    mount: mountAssistant,
  };
}

function mountAssistant() {
  const input = document.getElementById('ai-text');
  const button = document.getElementById('ai-parse');
  const result = document.getElementById('ai-result');

  document.getElementById('ai-chips').addEventListener('click', (e) => {
    const chip = e.target.closest('.chip');
    if (!chip) return;
    input.value = chip.textContent;
    input.focus();
  });

  const parse = async () => {
    const text = input.value.trim();
    if (text.length < 3) {
      toast('Write at least a few words');
      return;
    }
    button.disabled = true;
    button.innerHTML = '<span class="spin"></span> Parsing…';
    result.innerHTML = '';
    try {
      const intent = await api('/assistant/parse', { method: 'POST', body: { text } });
      result.innerHTML = `
        <div class="card">
          <div class="receipt-head">
            <span class="pill ${intent.action === 'PAY' ? 'ok' : 'soft'}">${esc(intent.action)}</span>
            <span style="font-size:11.5px;color:var(--faint)">${Math.round((intent.confidence || 0) * 100)}% · ${esc(intent.source)}</span>
          </div>
          <dl class="receipt-lines">
            <div class="receipt-line"><dt>To</dt><dd>${esc(intent.receiver_name || '—')}</dd></div>
            <div class="receipt-line"><dt>Amount</dt><dd>${intent.amount_cents ? money(intent.amount_cents) : '—'}</dd></div>
            ${intent.token48 ? `<div class="receipt-line"><dt>Token</dt><dd class="mono">…${esc(intent.token48.slice(4, 12))}</dd></div>` : ''}
            ${intent.memo ? `<div class="receipt-line"><dt>Note</dt><dd>${esc(intent.memo)}</dd></div>` : ''}
          </dl>
          <p class="hint">${esc(intent.explanation || '')}</p>
          <div id="ai-continue"></div>
        </div>`;
      if (intent.action === 'PAY' && intent.token48 && intent.amount_cents) {
        const holder = document.getElementById('ai-continue');
        holder.innerHTML = '<button class="btn primary block" style="margin-top:12px">Review &amp; send</button>';
        holder.querySelector('button').addEventListener('click', () => {
          go(`send/${intent.token48}?to=${encodeURIComponent(intent.receiver_name || '')}&amount=${intent.amount_cents}`);
        });
      }
    } catch (err) {
      result.innerHTML = `<div class="notice bad"><span class="title">${esc(err.code || 'PARSE_FAILED')}</span>${esc(err.message)}</div>`;
    } finally {
      button.disabled = false;
      button.textContent = 'Parse';
    }
  };

  button.addEventListener('click', parse);
  input.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) parse();
  });
}

/* --------------------------------------------------------------- profile */

function ProfileScreen() {
  const account = S.account;
  return {
    appbar: { title: 'Profile' },
    tabs: true,
    html: `
      <div class="card">
        <div class="payee">
          <div class="avatar" style="width:48px;height:48px;border-radius:16px;font-size:15px">${esc(initials(account.name))}</div>
          <div class="grow">
            <div class="name">${esc(account.name)}</div>
            <div class="token">demo wallet · seq ${account.seq}</div>
          </div>
          <span class="pill soft">SIM</span>
        </div>
        <hr class="sep">
        <dl class="receipt-lines">
          <div class="receipt-line"><dt>Balance</dt><dd>${money(account.balance_cents)}</dd></div>
          <div class="receipt-line"><dt>Ceiling per transfer</dt><dd>${money(account.credit_ceiling_cents)}</dd></div>
          <div class="receipt-line"><dt>Device</dt><dd class="mono">${esc(account.device_id.slice(0, 8))}</dd></div>
        </dl>
      </div>

      <div class="card">
        <div class="row" style="justify-content:space-between;margin-bottom:12px">
          <strong style="font-size:14px">Your receive QR</strong>
          <span class="pill soft">scan to pay</span>
        </div>
        <div class="qr-wrap">
          <img id="profile-qr" alt="QR code for this wallet" src="/qr.png?size=460&amp;data=${encodeURIComponent(qrPayload(account))}">
        </div>
        <div class="token-text">${esc(chunkToken(account.token48))}</div>
        <div class="row" style="margin-top:12px">
          <button class="btn soft grow" id="profile-copy">${icon('copy')} Copy token</button>
          <button class="btn ghost grow" id="profile-refresh-qr">${icon('refresh')} Refresh</button>
        </div>
        <p class="hint">Any phone camera opens this as a payment link; the app's own scanner reads the same code.</p>
      </div>

      <div class="row" style="margin-bottom:14px">
        <button class="btn ghost grow" data-go="topup">${icon('plus')} Top up</button>
        <button class="btn ghost grow" data-go="assistant">${icon('sparkle')} Assistant</button>
      </div>

      <div class="card">
        <div class="row" style="justify-content:space-between">
          <div>
            <div style="font-size:13.5px;font-weight:650">Server</div>
            <div class="token">${esc(location.origin)}</div>
          </div>
          <span class="pill soft" id="api-state">checking…</span>
        </div>
      </div>

      <div class="card">
        <div class="row" style="gap:8px;margin-bottom:8px">
          <span style="color:var(--muted)">${icon('info')}</span>
          <strong style="font-size:13.5px">About this simulation</strong>
        </div>
        <p class="hint" style="margin:0">
          A web stand-in for the Viaduct Pay Android client, running against the real FastAPI
          ledger on this PC. Same endpoints, same <code>db_guard</code> rules, same 48-digit
          receipt tokens. Data lives in <code>server/viaduct-sim.db</code>; stop the simulator
          and the session ends. The APK itself is built by CI (artifact
          <code>viaduct-pay-debug</code>); this machine has no Android SDK.
        </p>
      </div>

      <button class="btn danger block" id="profile-signout">${icon('logout')} Sign out of this wallet</button>
      <p class="fineprint">
        Viaduct Pay · demo ledger · no KYC, no real money, no card data.
        Payments settle locally; there is no payment processor behind them.
      </p>
    `,
    mount: mountProfile,
  };
}

function qrPayload(account) {
  const base = `${location.origin}/#/send/${account.token48}`;
  return `${base}?to=${encodeURIComponent(account.name)}`;
}

async function mountProfile() {
  const account = S.account;
  document.getElementById('profile-copy').addEventListener('click', () => copyText(account.token48));
  document.getElementById('profile-refresh-qr').addEventListener('click', () => {
    const img = document.getElementById('profile-qr');
    img.src = `/qr.png?size=460&t=${Date.now()}&data=${encodeURIComponent(qrPayload(account))}`;
    toast('QR refreshed');
  });
  document.getElementById('profile-signout').addEventListener('click', () => {
    signOut();
    go('join');
  });

  const state = document.getElementById('api-state');
  try {
    const health = await fetch('/health', { cache: 'no-store' }).then((r) => {
      if (!r.ok) throw new Error(`health ${r.status}`);
      return r.json();
    });
    state.textContent = health.status === 'ok' ? 'online' : 'degraded';
    state.className = `pill ${health.status === 'ok' ? 'ok' : 'bad'}`;
  } catch {
    state.textContent = 'offline';
    state.className = 'pill bad';
  }
}

/* --------------------------------------------------------------- session */

function setAccount(account) {
  S.account = account;
  LS.set(K.account, account);
}

function signOut() {
  S.account = null;
  LS.del(K.account);
  LS.del(K.outbox);
  LS.del(K.velocity);
}

function afterSignIn() {
  if (S.route.requested === 'send') render();
  else go('home');
}

/* --------------------------------------------------------------- chrome */

function renderAppBar({ title = 'Viaduct Pay', sub = null, back: showBack = false, actions = [] }) {
  S.appbar.innerHTML = `
    ${showBack ? `<button class="icon-btn" data-nav="back" aria-label="Back">${icon('back')}</button>` : ''}
    <div class="title">${esc(title)}${sub ? `<small>${esc(sub)}</small>` : ''}</div>
    ${actions
      .map((a) => `<button class="icon-btn" data-nav="${esc(a.act)}" aria-label="${esc(a.label)}">${icon(a.icon)}</button>`)
      .join('')}
  `;
}

const TAB_ITEMS = [
  { key: 'home', label: 'Home', icon: 'home' },
  { key: 'scan', label: 'Scan', icon: 'scan' },
  { key: 'activity', label: 'Activity', icon: 'activity' },
  { key: 'profile', label: 'Profile', icon: 'user' },
];

function renderTabBar(active) {
  S.tabbar.hidden = false;
  S.tabbar.innerHTML = TAB_ITEMS.map(
    (tab) => `
      <button class="tab" data-tab="${tab.key}" aria-current="${tab.key === active}">
        ${icon(tab.icon)}<span>${tab.label}</span>
      </button>`
  ).join('');
}

/* --------------------------------------------------------------- screens */

const Screens = {
  join: JoinScreen,
  home: HomeScreen,
  scan: ScanScreen,
  activity: ActivityScreen,
  send: SendScreen,
  topup: TopUpScreen,
  assistant: AssistantScreen,
  profile: ProfileScreen,
};

const TITLES = {
  home: 'Viaduct Pay',
  scan: 'Scan & pay',
  activity: 'Activity',
  send: 'Send money',
  topup: 'Top up',
  assistant: 'AI assistant',
  profile: 'Profile',
  join: 'Viaduct Pay',
};

/* ---------------------------------------------------------------- render */

function render() {
  stopCamera();

  const requested = parseRoute();
  let name = requested.name;

  if (!S.account) name = 'join';
  else if (!name || name === 'join') name = 'home';
  if (!Screens[name]) name = S.account ? 'home' : 'join';

  S.route = { name, params: requested.params, query: requested.query, requested: requested.name };

  const screen = Screens[name](S.route);
  document.title = `${TITLES[name] || 'Viaduct Pay'} · Viaduct Pay`;

  S.main.innerHTML = screen.html;
  S.main.classList.toggle('no-tabs', !screen.tabs);
  renderAppBar(screen.appbar || {});

  if (screen.tabs) renderTabBar(name);
  else {
    S.tabbar.hidden = true;
    S.tabbar.innerHTML = '';
  }

  S.main.scrollTop = 0;
  if (screen.mount) {
    Promise.resolve()
      .then(screen.mount)
      .catch((err) => toast(err.message || 'Something went wrong'));
  }
}

document.addEventListener('click', (e) => {
  const nav = e.target.closest('[data-nav]');
  if (nav) {
    if (nav.dataset.nav === 'back') back();
    if (nav.dataset.nav === 'refresh') render();
    return;
  }
  const tab = e.target.closest('[data-tab]');
  if (tab) {
    go(tab.dataset.tab);
    return;
  }
  const jump = e.target.closest('[data-go]');
  if (jump) go(jump.dataset.go);
});

window.addEventListener('hashchange', render);

document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && S.account) {
    const { name } = S.route;
    if (name === 'home' || name === 'activity') render();
  }
});

/* ------------------------------------------------------------------ boot */

S.account = LS.get(K.account, null);
render();
