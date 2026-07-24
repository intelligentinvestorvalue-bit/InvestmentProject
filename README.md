# FilingDesk

Personal research desk for **US and India** markets.

## What's live

| Area | US | India |
|---|---|---|
| Insider open-market buy/sell feed | SEC Form 4 (P/S) | NSE PIT Market Purchase / Sale (NSE+BSE reported) |
| Pledge / SAST views | — | NSE pledge + SAST Reg.29 |
| Company research | SEC XBRL multi-year statements (expanded GAAP tags + FCF proxy) | Yahoo Finance annual statements (.NS / .BO) |
| Sector explore | SIC-based sectors from SEC submissions | Yahoo sector/industry metadata |
| Watchlists | Saved ticker screens | Saved ticker screens |
| Unusual options (UOA) | Yahoo delayed chains: watchlist + liquid universe, call/put + bid/ask direction, in-app alerts | Planned (India F&O later) |
| Scheduled sync | Auto Form 4 refresh + UOA poll/EOD | Auto PIT + pledge/SAST refresh |

Legacy notes from earlier experiments live in `docs/legacy/`.

---

## Quick start (local)

### Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python run.py          # http://127.0.0.1:5000
```

`SEC_USER_AGENT` is required by SEC fair-access rules.

### Frontend

```bash
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173
```

Suggested first-run flow:
1. **US → Insider feed → Sync recent Form 4s**
2. **India → Insider feed → Sync NSE/BSE open-market PIT**
3. **Research** a ticker (e.g. `AAPL` / `RELIANCE`)
4. **Explore → Enrich sector metadata**
5. **US → Options → Scan sample** (Yahoo delayed UOA; in-app bell for alerts)

### Remote access (Cloudflare + ntfy)

Keep API + UI + tunnel up at Windows logon and every 30 minutes; push the public URL to your phone when it changes. Phone app: **ntfy by Philipp C. Heckel** only — see [CLOUDFLARE_TUNNEL.md](./CLOUDFLARE_TUNNEL.md).

```powershell
# backend\.env: NTFY_TOPIC=...
.\scripts\install_ensure_online.ps1
.\scripts\ensure_online.ps1 -NotifyAlways
```

---

## API map

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Health |
| `GET` | `/api/v1/markets` | Market status |
| `GET` | `/api/v1/insider/transactions` | Filtered insider feed (`market=US\|IN`) |
| `GET` | `/api/v1/insider/meta` | Filter options + stats |
| `POST` | `/api/v1/insider/sync` | Pull recent insider filings |
| `GET` | `/api/v1/insider/disclosures` | India pledge / SAST views (`kind=pledge\|sast`) |
| `GET` | `/api/v1/financials/<ticker>` | Financials / summary |
| `GET` | `/api/v1/explore/sectors` | Sector list |
| `GET` | `/api/v1/explore/industries` | Industry list |
| `GET` | `/api/v1/explore/companies` | Company browse |
| `POST` | `/api/v1/explore/sync` | Enrich sector metadata |
| `GET/POST` | `/api/v1/watchlists` | List / create watchlists |
| `GET/PATCH/DELETE` | `/api/v1/watchlists/<id>` | Watchlist detail / rename / delete |
| `POST/DELETE` | `/api/v1/watchlists/<id>/items` | Add / remove tickers |
| `GET` | `/api/v1/options/unusual` | Unusual options alerts (`market=US`) |
| `POST` | `/api/v1/options/unusual/scan` | Manual Yahoo chain UOA scan |
| `GET` | `/api/v1/options/unusual/meta` | UOA thresholds + timing |
| `GET` | `/api/v1/notifications` | In-app notifications |
| `POST` | `/api/v1/notifications/<id>/read` | Mark one notification read |
| `POST` | `/api/v1/notifications/read-all` | Mark all notifications read |

---

## Tests

```bash
cd backend
source .venv/bin/activate
pytest -q
```

---

## Data sources

| Market | Insider | Financials / explore | Options |
|---|---|---|---|
| US | SEC Form 4 atom + ownership XML (free) | SEC XBRL companyfacts + submissions SIC | Yahoo/yfinance delayed chains (UOA) |
| India | NSE corporates-pit Market Purchase/Sale (free; includes BSE-reported rows) | Yahoo Finance annual statements + sector/industry (free) | Planned |

---

## Roadmap remaining

- Optional Postgres for longer-term local use
- Optional Docker packaging
