#!/usr/bin/env bash
# Prints the exact Neon + Render click path. No API keys, nothing executed
# against your accounts. Run it, then follow the steps in your browser.

set -euo pipefail

cat <<'EOF'
=====================================================================
NEON — CREATE THE DATABASE (about 3 minutes)
=====================================================================
1. https://console.neon.tech  → sign in
2. "Create project"
     Project name : viaduct-db
     Postgres     : 16
     Region       : US West (Oregon) — same region as Render
3. Wait ~30 s. On the project dashboard open "Connect".
4. Copy the POOLED connection string. It looks like:
     postgresql://neondb_owner:PASSWORD@ep-xxx-pooler.us-west-2.aws.neon.tech/neondb?sslmode=require
   Keep "?sslmode=require" — the server passes it straight to psycopg.

=====================================================================
RENDER — ENVIRONMENT GROUP, THEN BLUEPRINT
=====================================================================
The Blueprint references the group, so the group must exist first.

5. Render Dashboard → Environment Groups → "+ New Environment Group"
     Name : viaduct-db-env
     Key  : DATABASE_URL
     Value: <the Neon pooled connection string from step 4>
6. Push the CONTENTS of the server/ folder to a GitHub repository.
   (Render reads dockerfilePath relative to the repo root.)
7. Render → New → Blueprint → pick that repository → Apply.
   The Blueprint creates the web service "viaduct-ledger" in Oregon, free plan.
8. Wait for the build (2–3 min). Then:
     https://viaduct-ledger.onrender.com/health
   should return: {"status":"ok","service":"viaduct-ledger","version":"1.0.0"}

If the service reports a database error, open the service → Environment and
confirm "viaduct-db-env" is listed. Linking a group after creation is allowed.
=====================================================================
EOF
