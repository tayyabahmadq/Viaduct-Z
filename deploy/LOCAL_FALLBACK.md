# Local fallback — run the whole demo on your laptop

Useful when the venue Wi-Fi is hostile, or when Render is cold and you do not
want to wait.

## Option A — Docker Compose (API + Postgres)

```bash
docker compose up --build
```

- API: <http://localhost:8000>
- Docs: <http://localhost:8000/docs>
- Health: <http://localhost:8000/health>

The compose file starts Postgres 16, waits for its healthcheck, then boots the
API with `SEED_ON_START=1` so six demo wallets exist immediately.

Stop and wipe the database:

```bash
docker compose down -v
```

## Option B — plain Python, SQLite (no Docker)

```powershell
cd server
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

No `DATABASE_URL` means SQLite at `server/viaduct.db`. Fine for one laptop;
not for two devices writing at once.

## Pointing a phone at the laptop

| Situation | Base URL in the app (Profile → Server) |
|---|---|
| Android emulator | `http://10.0.2.2:8000` |
| Physical phone, USB debugging | `adb reverse tcp:8000 tcp:8000` then `http://127.0.0.1:8000` |
| Same Wi-Fi | `http://<laptop-LAN-IP>:8000` |

Find the laptop IP with `ipconfig` (Windows) and look for the IPv4 address of
the active adapter. The phone and laptop must be on the same network, and the
Windows firewall must allow inbound TCP 8000 (or you will get a timeout, not a
refusal).

`10.0.2.2` is a special alias that exists **only** inside the Android emulator.
It does not work on a physical phone.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| App shows `Failed to connect` | Wrong base URL, or server not running | Open `/health` in the phone browser |
| Works on laptop, not on phone | Firewall / different network | Allow port 8000, join the same Wi-Fi |
| `E_UNKNOWN_PEER` | You pasted a token from a different deployment | Both devices must use the same server URL |
| Postgres refuses connections | Container still starting | `docker compose logs db` |
| Stale data after switching DB | Old SQLite file | Delete `server/viaduct.db` and restart |
