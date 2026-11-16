# deploy/

| File | Purpose |
|---|---|
| `neon_setup.sh` | Prints the Neon + Render click path (creates nothing) |
| `neon_runbook.md` | Complete Neon project + pooled-connection + env-group steps |
| `clickpath_runbook.md` | Zero-to-live dashboard sequence, in the order Render requires |
| `backups_rollback.md` | Neon branch snapshots and three rollback paths |
| `live_verification_checklist.md` | Ten live checks with copy-paste commands |
| `cloudflared_extra.md` | Optional HTTPS tunnel for the LAN simulator |
| `F1-F7_INTEGRATION.md` | What was adopted from the module pack, and what was not |
| `seed_and_smoke.sh` | End-to-end smoke test, bash (Git Bash / WSL / macOS / Linux) |
| `seed_and_smoke.ps1` | Same test, Windows PowerShell |
| `keepalive.md` | UptimeRobot setup so Render does not sleep |
| `LOCAL_FALLBACK.md` | Run API + Postgres on a laptop, point phones at it |
| `OUTPUT.md` | Verified vs. unverified, and the demo's real limitations |

The main runbook is the repository root `README.md`.
