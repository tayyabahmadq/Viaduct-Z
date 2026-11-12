# Keep-alive (optional, but do it before a live demo)

Render's free web services spin down after **15 minutes with no traffic**. The
next request then pays a **45–90 s** cold start, which looks like a broken app
if a judge or a colleague opens it first.

## UptimeRobot (free, 5-minute interval)

1. Create an account at <https://uptimerobot.com>.
2. **Add New Monitor**
   - Type: **HTTP(s)**
   - Friendly name: `viaduct-ledger-health`
   - URL: `https://viaduct-ledger.onrender.com/health`
   - Monitoring interval: **5 minutes** (free-tier minimum)
   - Alert contacts: your email
3. **Create Monitor**.

Every ping is a real request, so the container stays warm and the demo answers
instantly.

## Verify it worked

Leave the service idle for 20 minutes, then open the health URL in a private
window. If it answers immediately, the monitor is doing its job.

## Alternatives

- **cron-job.org** — same idea, free, 5-minute granularity.
- **GitHub Actions schedule** — a cron workflow that curls `/health` every 5
  minutes. Works, but burns Actions minutes and is easy to forget.

## What it costs

UptimeRobot's free plan includes 50 monitors at 5-minute intervals. One monitor
is plenty.
