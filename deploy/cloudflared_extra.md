# Optional: cloudflared quick tunnel for the LAN simulator

Adapted from F5, which shipped this file truncated after "Start the local API
stack:". The simulator here is the Node UI/proxy on `0.0.0.0:8080` plus the API
on `127.0.0.1:8010` (see `sim/start.ps1`), not `localhost:8000`.

## Why you might want it

- PWA install prompts require a secure context (HTTPS or localhost).
- In-app camera access requires a secure context; the simulator works around
  this with photo upload + jsQR.
- PayPal's approve/return flow is happiest with an HTTPS origin, although the
  app captures the order explicitly and does not depend on the redirect.

Render already gives you HTTPS at `https://viaduct-ledger.onrender.com`, so this
is only for a local demo that needs a public HTTPS URL.

## Steps

1. Install cloudflared:
   - Windows: `winget install --id Cloudflare.cloudflared`
   - macOS: `brew install cloudflared`
   - Linux: see Cloudflare's install docs.
2. Start the simulator:

```powershell
.\sim\start.ps1
# UI/proxy: http://0.0.0.0:8080   API: http://127.0.0.1:8010
```

3. In a second terminal:

```powershell
cloudflared tunnel --url http://localhost:8080
```

4. cloudflared prints a `https://<random>.trycloudflare.com` URL. Open it on the
   phone. The proxy forwards `/api/*` to the API on 8010, so the whole app works
   over HTTPS.

## Cautions

- A quick tunnel is public while it runs; anyone with the URL can register a
  demo wallet. Do not enable PayPal live credentials behind it.
- The tunnel dies with the terminal. For a judged demo, prefer the Render URL.
- `PUBLIC_BASE_URL` should match the tunnel URL if you want PayPal's return page
  to land on the tunnel rather than `localhost`:

```powershell
$env:PUBLIC_BASE_URL = "https://<random>.trycloudflare.com"
```

Restart the API after changing it.
