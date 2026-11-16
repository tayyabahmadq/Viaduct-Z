# Neon runbook — Postgres for the Render free tier

Adapted from F5's `neon_runbook.md`; names aligned with the deployed service
(`viaduct-ledger`) and the environment group this repo's `render.yaml` expects
(`viaduct-db-env`).

## 1. Create the project

1. <https://console.neon.tech> → sign in.
2. **Create project**.
3. Project name: `viaduct-db`.
4. Postgres: **16** (default).
5. Region: **US West (Oregon)** — same region as the Render service.
6. Create and wait ~30 s.

## 2. Get the pooled connection string

1. Open the project → **Connect** (or **Connection details**).
2. Enable **Pooled connection**.
3. Copy the full URI:

```
postgresql://<user>:<password>@ep-xxxx-pooler.us-west-2.aws.neon.tech/neondb?sslmode=require
```

Keep `?sslmode=require`. The server normalises `postgres://` and
`postgresql://` to `postgresql+psycopg://` and passes the query string through.

## 3. Create the Render environment group

Render Blueprints cannot define `sync: false` inside an environment group, and
the service references the group by name, so create it **before** applying the
Blueprint.

1. Render Dashboard → **Environment Groups** → **New Environment Group**.
2. Name: `viaduct-db-env`.
3. Add `DATABASE_URL` = the pooled string from step 2.
4. Create.

## 4. Apply the Blueprint

1. Push the **contents of `server/`** as the repository root (Render resolves
   `dockerfilePath` from there).
2. Render → **New** → **Blueprint** → select the repo → **Apply**.
3. The service is `viaduct-ledger`, plan `free`, region `oregon`.
4. Wait for the build, then:

```bash
curl -fsS https://viaduct-ledger.onrender.com/health
# {"status":"ok","service":"viaduct-ledger","version":"1.0.0"}
```

## 5. Optional integrations

In the service's **Environment** tab add, as needed:

| Key | Purpose |
|---|---|
| `PAYPAL_CLIENT_ID`, `PAYPAL_CLIENT_SECRET` | Enables sandbox top-ups (otherwise 503) |
| `AI_API_KEY` | Enables the model path (otherwise rules fallback) |
| `AI_BASE_URL`, `AI_MODEL` | Point at Groq/OpenRouter/OpenAI and a model id |

## 6. Verify the database is the one you think it is

```bash
python deploy/seed_and_smoke.ps1   # registers two devices; they persist across redeploys
```

If the second run still sees the first run's devices in `/api/v1/peers`, the
Neon URL is wired correctly. If data vanishes on redeploy, `DATABASE_URL` is
missing and the app fell back to SQLite inside the container.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `FATAL: password authentication failed` | Placeholder or truncated URI | Re-copy the pooled string |
| `relation "devices" does not exist` | App failed before `create_all` | Read the deploy log; usually a bad `DATABASE_URL` |
| Blueprint apply: group not found | Group created after the Blueprint | Create `viaduct-db-env` first, then re-apply |
| Data resets on every deploy | No `DATABASE_URL` | Check the service env and that the group is linked |
