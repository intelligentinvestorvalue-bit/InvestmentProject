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
| Unusual options (UOA) | Yahoo delayed chains: watchlist + liquid universe, call/put + bid/ask direction, in-app alerts | NSE F&O option-chain-v3: indices + equity FO, same direction model, in-app alerts |
| Officer buy → deep dive | Auto-detect ≥$100k CEO/CFO/management buys → confirm banner → Equity Research Agent full pack | — |
| Scheduled sync | Auto Form 4 refresh + UOA poll/EOD + deep-dive confirm tick | Auto PIT + pledge/SAST refresh + India UOA poll/EOD |

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
6. **India → Options → Scan sample** (NSE F&O option-chain UOA)

### Remote access (Cloudflare + ntfy)

Keep API + UI + tunnel up at Windows logon and every 30 minutes; push the public URL to your phone when it changes. Phone app: **ntfy by Philipp C. Heckel** only — see [CLOUDFLARE_TUNNEL.md](./CLOUDFLARE_TUNNEL.md).

```powershell
# backend\.env: NTFY_TOPIC=...
.\scripts\install_ensure_online.ps1
.\scripts\ensure_online.ps1 -NotifyAlways
```

### Officer buy → Equity Research deep dive

Fully background when keep-alive keeps both apps running (no browser required):

1. Hourly US Form 4 sync finds open-market **officer / C-suite buys ≥ $100k**.
2. Skips tickers already in the Equity overnight queue, actively researching, or with existing reports/docs.
3. FilingDesk optional confirm banner/ntfy, then pushes to Equity **research queue**.
4. Equity queue mode (`DEEP_DIVE_QUEUE_START_POLICY`):
   - **`prompt_now`** (default): laptop ntfy — auto-start deep dive in ~1 min; Cancel → stay deferred for overnight/manual Start overnight
   - **`overnight`**: park only until you hit **Start overnight** (or API)
5. Equity queue page/API: add tickers, remove ticker, start overnight, pause/resume.

Config: `DEEP_DIVE_*` in `backend/.env.example`. Set `NTFY_TOPIC` on both apps for laptop alerts.

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
| `GET` | `/api/v1/deep-dive/pending` | Pending auto-push confirmations + backlog count |
| `GET` | `/api/v1/deep-dive/candidates` | Deep-dive candidate history (`status=` filter) |
| `POST` | `/api/v1/deep-dive/<id>/cancel` | Cancel → backlog (retry ~1h) |
| `POST` | `/api/v1/deep-dive/<id>/confirm` | Push now to Equity Research Agent |
| `POST` | `/api/v1/deep-dive/scan` | Re-scan cached insider buys for signals |
| `POST` | `/api/v1/deep-dive/tick` | Process expired confirm windows |

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
| India | NSE corporates-pit Market Purchase/Sale (free; includes BSE-reported rows) | Yahoo Finance annual statements + sector/industry (free) | NSE option-chain-v3 F&O (indices + equities) |

---

## Roadmap remaining

- Optional Postgres for longer-term local use
- Optional Docker packaging
