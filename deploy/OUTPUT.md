# OUTPUT.md — what is verified, and what is not

This file exists so nobody has to guess which claims were actually executed on
this machine.

## Verified here

| Item | How |
|---|---|
| Server imports and boots | `uvicorn app.main:app` on port 8011, `/health` returned `ok` |
| 84 server tests | `python -m pytest` in `server/` → **84 passed** |
| Guard fixtures (30 cases) | `server/tests/test_guard.py`, parametrised over `fixtures/guard_fixtures.json` |
| Token layout | 48 digits, mod-97 checksum, decode round-trip, tamper rejection |
| Live payment flow | `deploy/seed_and_smoke.sh` and `deploy/seed_and_smoke.ps1` both exited 0 against the live server |
| Ceiling decline | Smoke test expects and received `E_CEILING_EXCEEDED` |
| Idempotent replay | Smoke test received the identical `transaction_id` |
| Receipt-token verification | `/api/v1/tokens/verify` returned `valid: true` for the issued token |
| Fixture JSON parses | 30 fixtures, unique names, 47-digit and non-numeric cases intentional |
| PayPal client contract | Unit-tested with `httpx.MockTransport`: token call, order body (`25.00`), `PayPal-Request-Id`, approval link, capture id/amount parsing, 422 error mapping |
| PayPal top-up endpoints | Tested with a fake PayPal client: wallet credited once, capture replay does not double-credit, another user's order is rejected, 503 without credentials, 502 on PayPal errors |
| AI assistant | Rules path live-verified against a seeded peer; model path tested with a mocked OpenAI-compatible response; invalid JSON falls back to rules |
| Kotlin source review | Independent static review of imports, Compose BOM 2024.09.03 signatures, Retrofit paths and DTO field/type parity with `schemas.py`: no compile blockers found. This is a review, **not** a compiler. |

## Not verified here — no Android SDK, no Docker, no cloud account

| Item | Status | What would verify it |
|---|---|---|
| Kotlin compiles | **Not compiled.** No Android SDK / Gradle on this machine. | `gradle assembleDebug` locally, or the `apk` CI job |
| Kotlin `TxGuard` fixture parity | Written to mirror `guard.py`; not executed. | `gradle testDebugUnitTest` (CI does this) |
| `app-debug.apk` | **Not built.** Binary cannot be produced without the SDK. | CI artifact `viaduct-pay-debug` |
| Docker image | **Not built.** Docker is not installed here. | `docker compose up --build` |
| Render Blueprint apply | **Not executed.** No Render account. | Render dashboard, per `neon_setup.sh` |
| Neon connection | **Not executed.** No Neon account. | `/health` plus the smoke test against the live URL |
| Camera QR scan | **Not tested.** No device. | Install the APK, scan the Profile QR of another install |
| A real PayPal sandbox capture | **Not executed.** No sandbox app credentials or buyer account here. | Set `PAYPAL_CLIENT_ID`/`PAYPAL_CLIENT_SECRET`, create a sandbox buyer, top up $25 in the app |
| A real model call | **Not executed.** No API key here. | Set `AI_API_KEY`; the response should flip to `source: "model"` |

## Deliberate non-features

The earlier draft of this package mentioned a mesh relay ("Scout") and an
installable PWA. **Neither exists in this code.** They were prose in a marketing
draft, not implementation.

What *does* exist now, and did not before, is the PayPal sandbox top-up flow and
the AI payment assistant — both gated by environment variables and both tested
without live credentials. PayPal is used only as a sandbox funding source for a
demo balance: no real money moves, and no live PayPal host is contacted unless
`PAYPAL_BASE_URL` is deliberately changed.

## Known limitations of the demo design

- **Not money.** No KYC, no settlement, no reconciliation, no PCI scope. Balances
  are rows in a demo database.
- **Single writer semantics.** Postgres row locks (`SELECT ... FOR UPDATE`)
  protect balances, but there is no double-entry journal, no reversal flow, and
  no idempotency table separate from `payments`.
- **Global idempotency keys.** `payments.idempotency_key` is unique across all
  devices, not per sender. Two devices that generate the same key collide.
- **In-process rate limiting.** The 20/minute rule is a `COUNT(*)` per request;
  it degrades under real concurrency and is per instance.
- **No token refresh.** `api_token` is issued once at registration and never
  rotated; `LocalStorage` keeps it in plain `SharedPreferences` (not
  EncryptedSharedPreferences) so the demo has one less dependency.
- **Free-tier cold starts.** Render sleeps; see `keepalive.md`.
