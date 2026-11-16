# Backups and rollback

Adapted from F5. The demo writes no real money, but a corrupted ledger still
ruins a demo, so treat the database as if it mattered.

## Before a demo day: Neon branch snapshot

1. Neon Dashboard → your project → **Branches**.
2. **New branch**.
3. Name: `pre-demo-YYYY-MM-DD`.
4. Branch from: `main` (current data).
5. Create. Copy its pooled connection string.

A Neon branch is a copy-on-write snapshot: isolated, instant, and free on the
free tier within storage limits.

## Rollback path A — point Render at the snapshot

1. Render → `viaduct-ledger` → **Environment**.
2. Change `DATABASE_URL` to the snapshot branch's pooled string.
3. Save; Render redeploys.
4. Verify:

```bash
curl -fsS https://viaduct-ledger.onrender.com/health
python deploy/seed_and_smoke.ps1
```

5. When the incident is over, point `DATABASE_URL` back at the primary branch.

## Rollback path B — local export

If you have `psql` and the pooled URI:

```bash
pg_dump "$DATABASE_URL" --no-owner --no-acl -f viaduct-backup.sql
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f viaduct-backup.sql
```

Do not restore a dump over a database that is still serving traffic; stop the
Render service first.

## Rollback path C — rebuild from seed

The demo can always restart empty:

1. Point `DATABASE_URL` at a fresh Neon branch/database.
2. Redeploy with `SEED_ON_START=1`.
3. The six demo wallets are recreated.

Payments, top-ups and receipts from before the reset are gone — say so out loud
rather than pretending the ledger survived.

## What is not covered

- No automated PITR configuration beyond Neon's defaults.
- No backup of the PayPal sandbox state (PayPal owns it).
- No backup of device-local state (`SharedPreferences` / browser storage);
  reinstalling the app creates a new demo wallet by design.
