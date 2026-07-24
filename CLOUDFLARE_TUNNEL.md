# Cloudflare Tunnel + phone push for FilingDesk (no custom domain)

Expose local **FilingDesk** so you can open it from anywhere, and get a **phone notification** when the public URL changes.

## Which ntfy app?

There are many similarly named apps. Install **only this one**:

| Phone | App | Developer |
|---|---|---|
| **iPhone / iPad** | [ntfy on the App Store](https://apps.apple.com/us/app/ntfy/id1625396347) | **Philipp C. Heckel** |
| **Android** | [ntfy on Google Play](https://play.google.com/store/apps/details?id=io.heckel.ntfy) or [F-Droid](https://f-droid.org/en/packages/io.heckel.ntfy/) | package id **`io.heckel.ntfy`** |

Official docs: https://docs.ntfy.sh/subscribe/phone/

Do **not** install other “notify / ntfy / push” lookalikes.

Subscribe to the exact `NTFY_TOPIC` from `backend/.env`. You can reuse the **same topic** as PodSnip so one phone subscription gets all apps (titles differ: FilingDesk / PodSnip / Equity).

## What gets exposed?

| Piece | Where |
|---|---|
| React UI | Laptop `:5173` (tunnel target) |
| Flask API | Laptop `:5000` (proxied by Vite `/api`) |
| Data / DB | Stays on laptop — tunnel only forwards HTTPS |

## One-time setup

1. `backend/.env` — add:
   ```env
   NTFY_TOPIC=your-secret-topic
   # NTFY_SERVER=https://ntfy.sh
   # NTFY_TOKEN=
   ```
2. Phone: install ntfy (Philipp C. Heckel) → Subscribe to that topic → allow notifications.
3. Power: sleep **Never** when plugged in.
4. `cloudflared` once: `winget install --id Cloudflare.cloudflared`
5. Install keep-alive:
   ```powershell
   cd C:\DevWork\InvestmentProject
   .\scripts\install_ensure_online.ps1          # logon + every 30 min
   .\scripts\ensure_online.ps1 -NotifyAlways    # test now
   ```

## What the job does

1. Health-check API `:5000/api/health` — start if down  
2. Health-check UI `:5173` — start if down  
3. Start Cloudflare quick tunnel to `:5173` if down  
4. ntfy push **only when** the public URL changes  

Log: `data/ensure_online.log`  
Task Scheduler name: **FilingDesk Ensure Online**

## Manual commands

```powershell
.\scripts\ensure_online.ps1
.\scripts\ensure_online.ps1 -NotifyAlways
.\scripts\run_tunnel.ps1
.\scripts\stop_tunnel.ps1
.\scripts\install_ensure_online.ps1 -Uninstall
```

## Limits

- Quick-tunnel URL changes when `cloudflared` restarts (ntfy tells you the new link).
- Laptop must stay awake and logged in.
- If tunnel log shows `tls: access denied` to `api.trycloudflare.com`, the network is blocking Cloudflare quick tunnels (try hotspot / disable VPN).
