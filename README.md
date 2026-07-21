# FilingDesk

Personal research desk for **US and India** markets, starting with a **global open-market insider feed**.

Phase 1 (this repo): **US Form 4 buys & sells** from free SEC EDGAR data, with rich filters.  
Phase 2: **India** insider activity (NSE + BSE / SEBI-SAST), then financials, then sector browse.

Legacy notes from earlier experiments live in `docs/legacy/`.

---

## Features (Phase 1)

- **US | India** market switch in the UI (India is a planned stub)
- **Global insider feed** of open-market **buys (P)** and **sells (S)** only
- Filters: side, role, ticker, insider, relationship, officer title, ownership form, tx/filing dates, shares, price, value, free-text search, sort
- Local SQLite cache + on-demand SEC sync
- Free data only (no paid SEC APIs)

---

## Quick start (local)

### 1. Backend

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # already includes a SEC User-Agent placeholder
python run.py          # http://127.0.0.1:5000
```

`SEC_USER_AGENT` is required by SEC fair-access rules (name/app + email).

### 2. Frontend

```bash
cd frontend
npm install
npm run dev            # http://127.0.0.1:5173
```

Open the app, click **Sync recent Form 4s**, then filter the feed.

---

## API (US)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/health` | Health check |
| `GET` | `/api/v1/markets` | US + India market metadata |
| `GET` | `/api/v1/insider/transactions` | Filtered insider feed |
| `GET` | `/api/v1/insider/meta` | Filter options + stats |
| `POST` | `/api/v1/insider/sync?market=US` | Pull recent Form 4s into SQLite |

Useful query params on `/insider/transactions`: `side`, `role`, `ticker`, `q`, `min_price`, `max_price`, `min_value`, `max_value`, `min_shares`, `max_shares`, `transaction_date_from`, `transaction_date_to`, `filing_date_from`, `filing_date_to`, `ownership_form`, `sort`, `page`, `page_size`.

---

## Data sources

| Market | Phase | Source |
|---|---|---|
| US | 1 | SEC EDGAR current Form 4 feed + ownership XML (free) |
| India | 2 | NSE + BSE public disclosures / SEBI-SAST (planned) |

---

## Tests

```bash
cd backend
source .venv/bin/activate
pytest -q
```

---

## Roadmap

1. **US insider desk** (done in Phase 1)
2. **US company financials** (SEC XBRL)
3. **India insider feed** (NSE + BSE)
4. **India financials**, then **sector explore** for both markets
