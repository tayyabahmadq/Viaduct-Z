# Viaduct-Z — Viaduct Pay

A demo credit ledger you can deploy for free and hand to two phones: a FastAPI
server on Render + Neon, and a Kotlin/Compose Android client that pays by
scanning a 48-digit token as a QR code. It tops up through PayPal's **sandbox**
and turns plain-English requests into payment intents with an OpenAI-compatible
model (with a deterministic fallback).

It is a **demo**, not a payment processor: no KYC, no real money, no card data.
What it does have is a real double-checked ledger, enforced guard rails, an
offline outbox, and receipt tokens that can be verified offline.

```
Viaduct-Z/
├── server/                     # FastAPI + SQLAlchemy (this folder is the Render repo)
│   ├── app/
│   │   ├── main.py             # app factory, CORS, routers, /health
│   │   ├── config.py           # env settings (no python-dotenv dependency)
│   │   ├── db.py               # engine, session, URL normalisation for Neon
│   │   ├── models.py           # Device, Payment
│   │   ├── schemas.py          # request/response contracts
│   │   ├── tokens.py           # the 48-digit receipt token
│   │   ├── guard.py            # screen() + db_guard()
│   │   ├── deps.py             # bearer auth + PayPal/AI factories
│   │   ├── paypal.py           # PayPal Orders v2 client (sandbox)
│   │   ├── assistant.py        # NL payment intent: model + rules fallback
│   │   ├── seed.py             # six demo wallets
│   │   └── routers/            # accounts, payments, peers, tokens, topups, assistant
│   ├── tests/                  # 116 passing tests (+1 deliberate skip)
│   ├── Dockerfile
│   ├── render.yaml
│   └── requirements.txt
├── android/                    # Kotlin + Jetpack Compose client
│   └── app/src/main/java/com/viaduct/pay/
│       ├── MainActivity.kt     # nav graph + theme
│       ├── data/               # Api.kt, LocalStorage.kt
│       ├── ui/                 # Screens.kt, TopUpScreen.kt, AssistantScreen.kt, Qr.kt, Format.kt
│       └── utils/TxGuard.kt    # client mirror of guard.py
├── fixtures/guard_fixtures.json   # 46 cases shared by Python and Kotlin tests
├── deploy/                     # smoke tests, Neon/Render steps, keep-alive
├── docker-compose.yml          # local API + Postgres
└── .github/workflows/android.yml  # APK build + unit tests + server tests
```

---

## 1. Run it locally (2 minutes)

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt
python -m uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000/docs> for the generated API console, or check
<http://localhost:8000/health>.

No `DATABASE_URL` means SQLite (`server/viaduct.db`). To use Postgres:

```powershell
$env:DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/viaduct"
```

Tests:

```powershell
cd server
python -m pytest          # 116 passed, 1 skipped
```

The same suite runs in CI (`.github/workflows/android.yml`, job `server-tests`).

---

## 2. Deploy the server (about 15 minutes)

### Step 1 — Neon

1. <https://console.neon.tech> → **Create project** → name `viaduct-db`,
   Postgres 16, US West (Oregon).
2. Copy the **pooled** connection string. It ends with `?sslmode=require`.

### Step 2 — Render

The Blueprint references an environment group, so create the group **first** —
Render rejects a Blueprint that points at a group which does not exist yet.

1. Render → **Environment Groups** → **New Environment Group**
   - Name: `viaduct-db-env`
   - `DATABASE_URL` = the Neon pooled string
2. Push the **contents of `server/`** to a GitHub repository. That folder
   contains `Dockerfile`, `render.yaml`, `requirements.txt` and `app/`, and
   Render resolves those paths from the repository root.
3. Render → **New** → **Blueprint** → select the repo → **Apply**.
4. Optional, for the two integrations: in the service's **Environment** tab add
   `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` (sandbox app from
   developer.paypal.com) and `AI_API_KEY`. They are read at boot; without them
   top-ups return 503 and the assistant uses its rules fallback.
5. Wait for the build, then:

```bash
curl https://viaduct-ledger.onrender.com/health
# {"status":"ok","service":"viaduct-ledger","version":"1.0.0"}
```

If you would rather push the whole monorepo, change two lines in
`server/render.yaml`:

```yaml
dockerfilePath: ./server/Dockerfile
dockerContext: ./server
```

and put `render.yaml` at the repository root.

### Step 3 — Android

1. Open the `android/` folder in Android Studio (it will offer to create the
   Gradle wrapper; accept, or run `gradle wrapper --gradle-version 8.9`).
2. Edit **one line** in
   `android/app/src/main/java/com/viaduct/pay/data/LocalStorage.kt`:

```kotlin
const val DEFAULT_SERVER_URL: String = "https://viaduct-ledger.onrender.com"
```

3. Plug in a phone (or start an emulator) and press **Run**. The debug APK is
   installed directly.

You can also change the server at runtime: **Profile → Server → Save server
URL**. That is the fastest fix if you demo on a laptop hotspot.

### Step 4 — Smoke test

From the repository root, against your live service:

```powershell
$env:BASE_URL = "https://viaduct-ledger.onrender.com"
.\deploy\seed_and_smoke.ps1
```

Bash (macOS / Linux / WSL, or Git Bash). On this Windows machine a bare `bash`
is the WSL stub, so call Git's bash explicitly:

```powershell
$env:BASE_URL = "https://viaduct-ledger.onrender.com"
& "C:\Program Files\Git\bin\bash.exe" ./deploy/seed_and_smoke.sh
```

Inside Git Bash the usual form works:

```bash
BASE_URL=https://viaduct-ledger.onrender.com ./deploy/seed_and_smoke.sh
```

Expected output:

```
[14:02:15] /health OK
[14:02:18] Device A: 1ca954a0-… (token: 4f2a19…c8d1)
[14:02:21] Payment 1 COMPLETED, receipt: 2c0f0956-…
[14:02:24] Payment 2 DECLINED with E_CEILING_EXCEEDED as expected
[14:02:27] Payment 3 returned identical receipt: 2c0f0956-…
[14:02:30] All three payments behaved exactly as specified ✓
```

Exit code `0` means every check passed: registration, a settled payment, a
ceiling decline, an idempotent replay, and server-side receipt-token
verification. The script derives the amounts from the deployment's own ceiling,
so it works whether the ceiling is $5 or $5,000.

### Step 5 — Keep it warm

Render free services sleep after 15 idle minutes. Follow
[`deploy/keepalive.md`](deploy/keepalive.md) to point UptimeRobot at
`/health` every 5 minutes.

---

## 3. API

All authenticated routes take `Authorization: Bearer <api_token>`; the token is
returned by registration as `token`. `token48` is the **public payment
address** — it goes in QR codes and must never be used as a credential.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| `GET` | `/health` | no | Liveness |
| `POST` | `/api/v1/devices/register` | no | Create (or re-fetch) a wallet |
| `GET` | `/api/v1/me` | yes | Balance, ceiling, token48 |
| `GET` | `/api/v1/peers` | yes | Directory, optional `?q=` |
| `GET` | `/api/v1/peers/resolve?token48=` | no | Token → peer |
| `POST` | `/api/v1/payments` | yes | Send money |
| `GET` | `/api/v1/payments?limit=&offset=` | yes | Bilateral history |
| `POST` | `/api/v1/payments/batch-sync` | yes | Settle the offline outbox |
| `POST` | `/api/v1/tokens/verify` | yes | Verify a receipt token |
| `POST` | `/api/v1/topups/paypal/order` | yes | Create a PayPal sandbox order |
| `POST` | `/api/v1/topups/paypal/capture` | yes | Capture it and credit the wallet |
| `GET` | `/api/v1/topups` | yes | Top-up history |
| `POST` | `/api/v1/assistant/parse` | yes | Natural language → payment intent |
| `GET` | `/api/v1/ledger/summary` | yes | Double-entry journal totals and balance check |

Receipt status is `COMPLETED` or `DECLINED`; a decline always carries a
`reason_code`.

### Guard rules (enforced by `db_guard`, mirrored client-side by `TxGuard`)

| Rule | Code | Score |
|---|---|---|
| Self payment | `E_SELF_PAY` | 10 |
| Recipient quarantined | `E_QUARANTINED_PEER` | 100 |
| Receipt-token checksum | `E_GUARDRAIL_BLOCKED` / `checksum` | 45 |
| Nonce replay | `E_DUPLICATE_TOKEN` | 45 |
| Velocity (>5 per minute) | `E_GUARDRAIL_BLOCKED` / `velocity` | 25 |
| Per-transfer ceiling | `E_CEILING_EXCEEDED` | 100 |
| Insufficient balance | `E_INSUFFICIENT_BALANCE` | 45 |
| Malformed input | `E_MALFORMED` | 100 |

The 46-case fixture file (30 canonical + 16 generated) is the contract between the Python and Kotlin
implementations; both test suites read it, so a rule change cannot silently
apply to only one side.

### The 48-digit token

```
time 4 | sender 4 | receiver 4 | amount 8 | seq 4 | nonce 20 | checksum 4
        44-digit payload, int(payload) % 97 zero-padded to 4
```

The token is a receipt artefact, not a bearer credential. `POST
/api/v1/tokens/verify` recomputes the checksum and returns the decoded parts.

---

## 4. PayPal sandbox and the AI assistant

Both integrations are optional at boot and fail closed, so the ledger demo keeps
running without any credentials.

### PayPal wallet top-ups (sandbox)

`server/app/paypal.py` is a small Orders v2 client:

1. `POST /v1/oauth2/token` — OAuth2 client-credentials, server-side only; the
   client secret never reaches the app.
2. `POST /v2/checkout/orders` — a CAPTURE order for the requested amount, with
   `PayPal-Request-Id` set to the local top-up id (idempotency).
3. `POST /v2/checkout/orders/{id}/capture` — after the buyer approves in the
   PayPal sandbox, capture and credit the wallet.

`POST /api/v1/topups/paypal/order` returns the `approve_url`; the Android app
opens it, then calls `POST /api/v1/topups/paypal/capture`. Capturing the same
order twice returns the same balance instead of crediting twice.

Set `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` from
**developer.paypal.com → Apps & Credentials → Sandbox**. Without them the
endpoints return `503 E_PAYPAL_NOT_CONFIGURED`; every other route still works.
`PAYPAL_BASE_URL` defaults to `https://api-m.sandbox.paypal.com`.

### AI payment assistant

`POST /api/v1/assistant/parse` turns "send $25 to Mei Chen" into a structured
intent. `server/app/assistant.py` calls any OpenAI-compatible
`/chat/completions` endpoint with `response_format: json_object`, then resolves
the recipient against the caller's peer list — the model can never invent a
payee. If no key is set, the call fails, or the JSON is unusable, a
deterministic parser answers instead and the response says `source: "rules"`
rather than pretending a model was involved.

```bash
curl -X POST http://localhost:8000/api/v1/assistant/parse \
  -H "authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -d '{"text":"send $25 to Mei Chen"}'
```

Configuration: `AI_API_KEY`, `AI_BASE_URL` (Groq is
`https://api.groq.com/openai/v1`), `AI_MODEL` (default `gpt-5-nano`).

---

## 5. Configuration

| Variable | Default | Meaning |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./viaduct.db` | Postgres/Neon URL is normalised automatically |
| `SEED_ON_START` | `1` | Create six demo wallets when the table is empty |
| `START_BALANCE_CENTS` | `250000` | $2,500.00 on registration |
| `CREDIT_CEILING_CENTS` | `500000` | $5,000.00 per transfer |
| `RATE_LIMIT_PER_MINUTE` | `20` | Payments per sender per minute |
| `PEER_ONLINE_SECONDS` | `180` | "online" window in the peer list |
| `PUBLIC_BASE_URL` | `http://localhost:8000` | Used for the PayPal return URL |
| `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` | empty | Sandbox credentials; empty disables top-ups |
| `PAYPAL_BASE_URL` | `https://api-m.sandbox.paypal.com` | PayPal API host |
| `PAYPAL_CURRENCY` | `USD` | Order currency |
| `AI_API_KEY` | empty | Enables the model path; empty uses rules |
| `AI_BASE_URL` | `https://api.openai.com/v1` | Any OpenAI-compatible host |
| `AI_MODEL` | `gpt-5-nano` | Model id for the assistant |

Copy `server/.env.example` to `server/.env` for local overrides; real
environment variables always win.

---

## 6. What is verified, and what is not

`deploy/OUTPUT.md` is the honest ledger of this build. Summary:

- **Verified:** the server boots, 116 tests pass (1 deliberate skip), both smoke scripts pass against
  a live instance, the guard fixtures pass in Python, the token checksum works.
- **Not verified here:** Kotlin compilation, the APK, the Docker image, Render
  and Neon provisioning — this machine has no Android SDK, no Docker and no
  cloud credentials. CI builds the APK and runs the Kotlin guard tests.
- **Not implemented at all:** the mesh relay, PayPal sandbox and PWA that an
  earlier draft of this package advertised. They were prose, not code.

---

## 7. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `/health` 502 on first hit | Render cold start | Wait 60–90 s, or add the uptime monitor |
| `FATAL: password authentication failed` | Neon URL pasted with placeholder | Re-copy the pooled string |
| `relation "devices" does not exist` | Tables not created | The app creates them on boot; check the deploy log for the real error |
| App can't reach the server | `DEFAULT_SERVER_URL` still local | Edit `LocalStorage.kt` or set it in Profile |
| Emulator can't reach laptop | Wrong host alias | `10.0.2.2`, not `localhost` |
| `E_UNKNOWN_PEER` | Two devices on different servers | Same `BASE_URL` on both |
| PayPal top-up returns 503 | No sandbox credentials in the service env | Set `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` |
| Assistant always says `source: rules` | No `AI_API_KEY`, or the model call failed | Set the key; the fallback is intentional |
| CI APK job fails at SDK step | First run downloads the SDK | Re-run; it is cached afterwards |
