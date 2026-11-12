# Viaduct-Z — submission answers

Copy each section into the matching form field. Everything below describes code
that is in this repository; the claims marked *verified* were executed on the
build machine, and `deploy/OUTPUT.md` lists what was not.

---

## 1. Elevator pitch

> Two phones, one 48-digit receipt: peer-to-peer demo payments with PayPal
> sandbox top-ups and an AI that turns plain English into a payment.

---

## 2. About the project

### What inspired it

I kept seeing "live in 30 minutes" payment kits that fell apart on contact: the
token was documented as 48 digits but the code built 40, one file authenticated
with a device header and another with a bearer token, receipts said `APPROVED`
in one place and `COMPLETED` in another. The interesting problem was not
another wallet UI — it was building a demo whose *ledger invariants* are real
even though the money is not. A payment demo should be able to answer three
questions without hand-waving: did this payment happen once, can I prove it
later, and what stops it from happening twice?

### What it does

Viaduct Pay gives every install a wallet and a public 48-digit payment address.
You pay by scanning that address as a QR code, pasting the token, or picking a
peer from the directory. Every transfer passes an ordered set of guard rules —
self-payment, unknown peer, per-transfer ceiling, balance, nonce replay,
velocity, receipt checksum — and a decline is recorded, not swallowed. History
is bilateral. If the network drops, the payment is queued locally and settled
later through an idempotent batch endpoint. Wallets can be topped up with
PayPal's **sandbox**, and a natural-language box turns "send $25 to Mei Chen"
into a structured payment intent before anything is sent.

### How it was built

The server is FastAPI + SQLAlchemy on Postgres (Neon in production, SQLite for
local tests), containerised and deployed as a Render web service. The client is
Kotlin + Jetpack Compose, Retrofit with kotlinx.serialization, ZXing for QR
generation and scanning.

Two design choices carried most of the weight.

**The receipt token is arithmetic, not a database lookup.** Its 48 digits are

$$
t \;=\; \underbrace{m}_{4}\;\|\;\underbrace{s}_{4}\;\|\;\underbrace{r}_{4}\;\|\;\underbrace{a}_{8}\;\|\;\underbrace{q}_{4}\;\|\;\underbrace{n}_{20}\;\|\;\underbrace{c}_{4},
\qquad
c \;=\; \operatorname{int}\!\left(m\|s\|r\|a\|q\|n\right) \bmod 97
$$

so anyone can verify a receipt offline with one modulo operation, and a single
changed digit is rejected. The layout also fixes a real bug in the source
material: its fields summed to 40 digits while the prose promised 44, so the
nonce is 20 digits, not 16.

**The guard is one function, tested twice.** `server/app/guard.py::screen` and
`android/.../utils/TxGuard.kt` are mirror implementations, and both are checked
against the same 30-case `fixtures/guard_fixtures.json`. A rule change that
lands on only one side fails the other side's tests. That file is the contract.

Idempotency is enforced twice as well: an `idempotency_key` lookup before the
write, and a unique constraint plus `IntegrityError` replay for the race that
slips through. Balances are updated under `SELECT … FOR UPDATE`.

### What I learned

- **A spec is only real when it is executable.** The guard fixtures caught
  disagreements that prose review missed; the smoke script caught deployment
  assumptions that unit tests could not.
- **Idempotency is a property of the write, not of the client.** A retry button
  and a network retry look identical to a server; only the stored key tells them
  apart.
- **Deployment semantics are part of the code.** Render resolves
  `dockerfilePath` from the repository root, and a Blueprint cannot reference an
  environment group that does not exist yet — both facts changed the file layout
  and the order of the runbook.
- **Honest scope is a feature.** The earlier draft advertised a mesh relay, a
  PWA and PayPal payouts that had no implementation. Deleting those claims and
  building one real integration was more work and a much better demo.

### Challenges

1. **Contradictory source artifacts.** Three drafts disagreed on routes, auth,
   status vocabulary and token length. I picked one contract, wrote it down, and
   made the tests enforce it.
2. **Cross-language parity.** Kotlin and Python now share fixtures, but the
   fixture file had to be authored carefully (two deliberately malformed tokens
   are exempt from the "must be 48 digits" invariant).
3. **Late PayPal + AI.** Both were added after the ledger was green. The design
   constraint was that neither may break the demo when credentials are absent:
   PayPal returns `503 E_PAYPAL_NOT_CONFIGURED`, and the assistant falls back to
   a deterministic parser and says so in `source`.
4. **Windows tooling.** `bash` on this machine is the WSL stub, PowerShell 5.1
   needs a BOM for `✓`, and `curl` is an alias. The deploy folder therefore
   ships both a `.sh` and a `.ps1` smoke test.
5. **What I could not verify.** No Android SDK, no Docker and no cloud
   credentials here, so the APK, the image and the live PayPal capture are
   unverified and documented as such rather than claimed.

---

## 3. Built with (24 tags)

`Python` · `FastAPI` · `SQLAlchemy` · `Pydantic` · `Uvicorn` · `PostgreSQL` ·
`Neon` · `SQLite` · `Render` · `Docker` · `Kotlin` · `Jetpack Compose` ·
`Android` · `Retrofit` · `OkHttp` · `kotlinx.serialization` · `ZXing` ·
`PayPal REST API` · `PayPal Sandbox` · `OAuth 2.0` · `OpenAI API` ·
`GitHub Actions` · `pytest` · `JUnit`

---

## 4. Upload file

`Viaduct-Z-submission.zip` (repository + this document). Contains the FastAPI
server with tests, the Android client source, the shared guard fixtures, the
deploy kit (Docker, Render Blueprint, smoke tests), CI workflow and the runbook.
Excludes build output, virtualenvs, databases and tool scratch files.

---

## 5. How the project meets the technology requirement

The project integrates the **PayPal developer platform (sandbox)** and an
**AI model/service** at runtime, not just in the pitch.

### PayPal tools

| Tool | What it does in Viaduct-Z |
|---|---|
| **PayPal REST Orders v2 API** (`POST /v2/checkout/orders`) | Creates a `CAPTURE` order for a wallet top-up and returns the buyer approval link. Implemented in `server/app/paypal.py::create_order`. |
| **PayPal Orders v2 Capture** (`POST /v2/checkout/orders/{id}/capture`) | Captures the approved sandbox payment and returns the capture id and captured amount; only then is the demo wallet credited. `paypal.py::capture_order`. |
| **PayPal OAuth 2.0 client credentials** (`POST /v1/oauth2/token`) | Server-to-server authentication. The client secret stays on the server; the Android app never sees it. |
| **PayPal Sandbox environment + sandbox buyer approval** | All orders target `https://api-m.sandbox.paypal.com`. A sandbox buyer approves in PayPal's hosted flow, the app returns via `/paypal/return`, then taps "I approved — capture". No live money. |
| **`PayPal-Request-Id` idempotency header** | Ties PayPal's order creation to the local top-up id, so a retried create cannot produce two orders. |

Endpoints: `POST /api/v1/topups/paypal/order`, `POST /api/v1/topups/paypal/capture`,
`GET /api/v1/topups`. The capture path is idempotent per order: replaying it
returns the same balance instead of crediting twice (tested).

Configuration is environment-only: `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET`,
`PAYPAL_BASE_URL` (defaults to sandbox). Without credentials the endpoints fail
closed with `503 E_PAYPAL_NOT_CONFIGURED` and the rest of the app still works.

### AI tool

| Tool | What it does in Viaduct-Z |
|---|---|
| **OpenAI-compatible Chat Completions API** with JSON mode (`response_format: {"type":"json_object"}`) | `POST /api/v1/assistant/parse` sends the user's sentence plus the caller's peer list to the model and receives `{action, receiver_name, amount_cents, memo, confidence}`. The server resolves the name against real peers, so the model cannot invent a payee. Implemented in `server/app/assistant.py`. |
| **Model** | Default `gpt-5-nano` on `https://api.openai.com/v1`; any OpenAI-compatible host works (e.g. Groq `https://api.groq.com/openai/v1` with `openai/gpt-oss-20b`). Selected with `AI_MODEL` / `AI_BASE_URL`. |
| **Deterministic fallback parser** | If no key is configured, the call fails, or the JSON is unusable, a regex/peer-match parser answers instead. The response carries `source: "rules"` or `source: "model"`, so the demo never pretends an LLM answered when it did not. |

The Android **AI assistant** screen calls this endpoint, shows the parsed
recipient, amount, confidence and source, and only then navigates to the send
screen. Nothing is paid automatically.

**Why this is an integration, not a mention:** both paths are exercised by the
test suite (PayPal client contract via `httpx.MockTransport`, top-up endpoints
with a fake PayPal client, assistant model path with a mocked completion, plus
the rules fallback), and the live server was manually verified for the rules
path, the `503` fail-closed behaviour and the `/paypal/return` page. A real
sandbox capture and a real model call require credentials that were not
available on the build machine; `deploy/OUTPUT.md` says so explicitly.

---

## 6. Additional sponsor tools

**None.** Beyond PayPal, the stack uses open-source libraries only (FastAPI,
SQLAlchemy, Retrofit, OkHttp, ZXing, kotlinx.serialization). No other sponsor
SDK or hosted service is integrated. The AI provider is any OpenAI-compatible
endpoint, not a sponsor-specific SDK.

---

## 7. AI tools leveraged while working on this project

- **AutoClaw** — an agentic coding assistant used for the implementation,
  test generation, documentation, and two independent static review passes (one
  on the original Android client, one on the PayPal/AI additions). It also ran
  the test suites and the live smoke tests.
- **OpenAI-compatible model endpoint (runtime)** — the product's payment-intent
  parser, configurable via `AI_MODEL`; optional at runtime, with a deterministic
  fallback when no key is present.

No other AI coding tools were used.
