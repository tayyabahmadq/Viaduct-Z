# sim/ — temporary mobile simulation

A phone-sized web client for the Viaduct Pay demo, so the ledger can be shown on
real phones **right now**, without a Render deploy or an APK build. It talks to
the actual FastAPI app in `../server/` — same endpoints, same `db_guard`, same
48-digit receipt tokens. Only the UI is a stand-in for the Compose client.

```
sim/
├── serve.js              # one process: boots the API, serves the UI, proxies /api, renders QR PNGs
├── start.ps1             # Windows launcher (picks the firewall-friendly node.exe)
└── web/                  # the phone client (HTML/CSS/JS, no build step)
    ├── index.html
    ├── app.css
    ├── app.js
    ├── manifest.webmanifest
    ├── icons/
    └── vendor/jsQR.js    # MIT, photo-based QR decoding
```

## Run

```powershell
.\sim\start.ps1
```

| What | Where |
|---|---|
| Phone | `http://<lan-ip>:8080` — printed at startup, also `/join` as a QR |
| This PC | `http://localhost:8080` |
| API | `http://127.0.0.1:8010` (proxied, not exposed) |
| Database | `server/viaduct-sim.db` |

Port 8000 is avoided on purpose: another dev server on this machine already
owns it. Change with `SIM_PORT` / `SIM_API_PORT`.

## What works

- registration, seeded demo wallets, and instant "sign in as" for fast two-phone demos
- balance, activity (both directions), peer directory, online/offline
- send by 48-digit token, peer pick, uploaded QR photo, or a QR link opened by
  the phone's own camera app
- client-side guard mirror (`TxGuard`) **and** server enforcement (`db_guard`)
- offline outbox: a payment that fails to reach the API is queued and replayed
  through `/payments/batch-sync` the next time Home loads
- PayPal sandbox top-ups when `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` are set
- AI assistant (`/assistant/parse`), honest `source: rules` fallback
- a home-screen shortcut on the phone (a full standalone PWA install would need
  HTTPS; the manifest and icons are already in place for a TLS host)

## What it is not

- **Not HTTPS.** A LAN origin is insecure, so `getUserMedia` and
  `BarcodeDetector` are unavailable in-app; scanning works through a photo
  (jsQR), a pasted token, or the phone's native camera opening the QR link.
- **Not the APK.** Kotlin/Compose still needs Android Studio or CI.
- **Not durable.** SQLite on this PC, no backups; delete
  `server/viaduct-sim.db` for a clean reseed.
- Reachable only while this PC is awake and on the same Wi-Fi.

## Stop / reset

`Ctrl+C` in the simulator window stops the UI and the API together.

```powershell
Remove-Item server\viaduct-sim.db    # next start reseeds six demo wallets
```
