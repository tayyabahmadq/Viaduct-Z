# Zero-to-live click path

Adapted from F5. Every step here is a dashboard action; record what you actually
see in `deploy/evidence_log.md` (create it on demo day).

## Phase 1 — Neon

Follow [`neon_runbook.md`](neon_runbook.md). Output: one pooled
`postgresql://…?sslmode=require` string.

## Phase 2 — Render environment group (before the Blueprint)

1. Render → **Environment Groups** → **New Environment Group**.
2. Name: `viaduct-db-env`.
3. `DATABASE_URL` = the Neon pooled string.
4. Create.

> Order matters: `render.yaml` references this group with `fromGroup`, and a
> Blueprint cannot create a group variable with `sync: false`.

## Phase 3 — Apply the Blueprint

1. Push the **contents of `server/`** to a GitHub repository.
2. Render → **New** → **Blueprint** → connect that repository.
3. Render finds `render.yaml`; review the service `viaduct-ledger`.
4. Confirm `viaduct-db-env` is linked. If it is not, link it before applying.
5. **Apply**. Wait for build + deploy.

## Phase 4 — First boot

1. Open the service **Logs**.
2. Expect the seed to create six wallets only on an empty database.
3. `curl https://viaduct-ledger.onrender.com/health` → `{"status":"ok",...}`.

## Phase 5 — Optional integrations

Service → **Environment**:

- `PAYPAL_CLIENT_ID` / `PAYPAL_CLIENT_SECRET` (sandbox app)
- `AI_API_KEY` (any OpenAI-compatible provider)

Redeploy. Without these, top-ups return `503 E_PAYPAL_NOT_CONFIGURED` and the
assistant returns `source: "rules"` — both are correct, documented behaviour.

## Phase 6 — Smoke test from the laptop

```powershell
$env:BASE_URL = "https://viaduct-ledger.onrender.com"
.\deploy\seed_and_smoke.ps1
```

Expect the five log lines ending in `All three payments behaved exactly as
specified ✓`. Exit code 0 is the gate.

## Phase 7 — Phone demo

1. Open `android/` in Android Studio, set
   `LocalStorage.DEFAULT_SERVER_URL` to the Render URL, Run.
2. Or open the LAN simulator: `.\sim\start.ps1` → `http://192.168.1.3:8080`.
3. Register, copy the receive token, pay a seeded wallet $25, show the
   `COMPLETED` receipt, then try $6,000 and show `E_CEILING_EXCEEDED`.

## Phase 8 — Keep-alive

Follow [`keepalive.md`](keepalive.md) and point UptimeRobot at `/health` every
5 minutes. Do this **before** the demo, not during it.
