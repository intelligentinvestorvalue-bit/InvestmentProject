# FilingDesk

Personal research desk for **US and India** markets.

## What's live

| Area | US | India |
|---|---|---|
| Insider open-market buy/sell feed | SEC Form 4 (P/S) | NSE PIT Market Purchase / Sale (NSE+BSE reported) |
| Company research | SEC XBRL multi-year statements | Yahoo Finance annual statements (.NS / .BO) |
| Sector explore | SIC-based sectors from SEC submissions | Yahoo sector/industry metadata |

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

---

## API map

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Health |
| `GET` | `/api/v1/markets` | Market status |
| `GET` | `/api/v1/insider/transactions` | Filtered insider feed (`market=US\|IN`) |
| `GET` | `/api/v1/insider/meta` | Filter options + stats |
| `POST` | `/api/v1/insider/sync` | Pull recent insider filings |
| `GET` | `/api/v1/financials/<ticker>` | Financials / summary |
| `GET` | `/api/v1/explore/sectors` | Sector list |
| `GET` | `/api/v1/explore/industries` | Industry list |
| `GET` | `/api/v1/explore/companies` | Company browse |
| `POST` | `/api/v1/explore/sync` | Enrich sector metadata |

---

## Tests

```bash
cd backend
source .venv/bin/activate
pytest -q
```

---

## Data sources

| Market | Insider | Financials / explore |
|---|---|---|
| US | SEC Form 4 atom + ownership XML (free) | SEC XBRL companyfacts + submissions SIC |
| India | NSE corporates-pit Market Purchase/Sale (free; includes BSE-reported rows) | Yahoo Finance annual statements + sector/industry (free) |

---

## Roadmap remaining

- Watchlists / saved screens
- Deeper India PIT coverage windows / scheduled sync
- Optional Postgres for longer-term local use
