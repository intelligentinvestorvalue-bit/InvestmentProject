# Investment Tracker US

A full-stack web application that pulls **live US stock data directly from the SEC (Securities and Exchange Commission) EDGAR system** — no paid API keys required. Search any US-listed company by ticker symbol to view multi-year financial statements and recent insider buy transactions.

---

## What It Does

| Feature | Details |
|---|---|
| **Financial Statements** | Income Statement, Balance Sheet, and Cash Flow for up to 10 years, sourced from XBRL/GAAP filings |
| **Insider Trading** | Recent insider **buy** transactions parsed from SEC Form 4 filings |
| **Ticker Search** | Look up any US-listed company by its ticker symbol (e.g. `AAPL`, `MSFT`, `NVDA`) |
| **No paid API** | All data comes directly from `data.sec.gov` and `efts.sec.gov` — completely free |

---

## Tech Stack

### Backend — `sec_data_api/`
| Layer | Technology |
|---|---|
| Framework | Python · Flask |
| Database | SQLite (via SQLAlchemy + Flask-Migrate / Alembic) |
| Data source | SEC EDGAR REST API (XBRL company facts + Form 4 XML) |
| ORM | Flask-SQLAlchemy |

### Frontend — `my-sec-frontend/`
| Layer | Technology |
|---|---|
| Framework | React 19 + Vite 6 |
| UI Library | Material UI (MUI v7) |
| Data Grid | `@mui/x-data-grid` |
| HTTP Client | Axios |
| Routing | React Router v7 |

---

## Project Structure

```
Investment_Tracker_US/
├── sec_data_api/                  # Flask backend
│   ├── run.py                     # Entry point — starts Flask on port 5000
│   ├── requirements.txt
│   └── app/
│       ├── __init__.py            # App factory (create_app)
│       ├── app.py                 # Flask app + blueprint registration
│       ├── config.py              # Config class — reads .env
│       ├── models.py              # SQLAlchemy models (Company, AnnualFinancial, InsiderTrade)
│       ├── edgar_parser.py        # Additional EDGAR parsing helpers
│       ├── routes/
│       │   ├── financials.py      # GET /api/v1/financials/<ticker>
│       │   └── insider_trading.py # GET /api/v1/insider-trading/<ticker>/buys
│       ├── services/
│       │   └── sec_api_service.py # Calls data.sec.gov; parses XBRL JSON & Form 4 XML
│       └── utils/
│           └── helpers.py         # Ticker → CIK lookup (cached, refreshes every 24 h)
│
└── my-sec-frontend/               # React frontend
    ├── index.html
    ├── vite.config.js
    └── src/
        ├── main.jsx
        ├── App.jsx
        ├── pages/
        │   ├── HomePage.jsx
        │   ├── FinancialsPage.jsx
        │   └── InsiderTradingPage.jsx
        ├── components/
        │   ├── SearchBar.jsx
        │   ├── FinancialsTable.jsx
        │   ├── InsiderTradingTable.jsx
        │   ├── Navbar.jsx
        │   └── ErrorBoundary.jsx
        └── services/
            └── api.js             # Axios calls to the Flask backend
```

---

## API Endpoints

### `GET /api/v1/financials/<ticker>`
Returns multi-year financial statements parsed from SEC XBRL data.

**Query params**
| Param | Default | Description |
|---|---|---|
| `years` | `10` | Number of fiscal years to return |

**Response shape**
```json
{
  "ticker": "AAPL",
  "cik": "0000320193",
  "company_name": "Apple Inc.",
  "retrieved_utc": "2026-07-21T12:00:00",
  "statements": {
    "income_statement": [ { "year": 2023, "Revenues": 383285000000, ... } ],
    "balance_sheet":    [ { "year": 2023, "Assets": 352583000000, ... } ],
    "cash_flow":        [ { "year": 2023, "NetCashProvidedByUsedInOperatingActivities": 114000000000, ... } ]
  }
}
```

---

### `GET /api/v1/insider-trading/<ticker>/buys`
Returns recent insider **purchase** transactions (Form 4, transaction code `P`).

**Query params**
| Param | Default | Description |
|---|---|---|
| `limit` | `50` | Max number of Form 4 filings to process |

**Response shape**
```json
{
  "ticker": "AAPL",
  "buy_transactions": [
    {
      "insider_name": "John Doe",
      "relationship": "Director",
      "transaction_date": "2026-06-15",
      "shares": 10000,
      "price_per_share": 195.30,
      "total_value": 1953000,
      "transaction_code": "P",
      "filing_date": "2026-06-17",
      "accession_number": "0000320193-26-000123"
    }
  ]
}
```

---

## Database Models

| Model | Key Columns | Purpose |
|---|---|---|
| `Company` | `cik`, `ticker`, `name` | Stores resolved ticker → CIK mappings |
| `AnnualFinancial` | `company_cik`, `year`, `metric_name`, `metric_value` | Caches annual XBRL metrics |
| `InsiderTrade` | `stock_symbol`, `transaction_type`, `transaction_date`, `insider_name` | Stores parsed Form 4 trade records |

---

## Setup & Run

### Prerequisites
- Python 3.10+
- Node.js 18+
- A free SEC EDGAR User-Agent string (your name + email — required by SEC ToS)

---

### 1. Backend

```bash
cd sec_data_api

# Create and activate virtual environment
python -m venv venv
venv\Scripts\activate          # Windows
# source venv/bin/activate     # macOS/Linux

# Install dependencies
pip install -r requirements.txt
```

Create a `.env` file inside `sec_data_api/`:

```env
SECRET_KEY=your-secret-key-here
DATABASE_URL=sqlite:///../instance/app.db
SEC_USER_AGENT=Your Name YourEmail@example.com
FLASK_DEBUG=1
```

> **Important:** `SEC_USER_AGENT` is **required**. The SEC blocks requests without a valid User-Agent. Use your real name and email, e.g. `Jane Smith jane@example.com`.

Initialize the database and run:

```bash
flask db upgrade        # Run Alembic migrations
python run.py           # Start server on http://localhost:5000
```

---

### 2. Frontend

```bash
cd my-sec-frontend

npm install
npm run dev             # Start Vite dev server on http://localhost:5173
```

The frontend proxies API requests to `http://localhost:5000` — make sure the backend is running first.

---

## How the Data Pipeline Works

```
User searches "AAPL"
        │
        ▼
Frontend (React) → GET /api/v1/financials/AAPL
        │
        ▼
Backend resolves ticker → CIK
  helpers.py fetches https://www.sec.gov/files/company_tickers.json
  (cached in memory, refreshed every 24 hours)
        │
        ▼
sec_api_service.py fetches XBRL facts
  GET https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json
        │
        ▼
parse_financial_statements() extracts
  Income Statement / Balance Sheet / Cash Flow
  using common US-GAAP XBRL tags
        │
        ▼
JSON response → Frontend renders MUI DataGrid tables
```

For insider trading, the pipeline fetches the company's submission index from EDGAR, filters for Form 4 filings, downloads and parses each Form 4 XML, and filters for transaction code `P` (open-market purchases). A 110 ms delay is added between requests to respect the SEC's 10 req/sec rate limit.

---

## Replicating This Project with a Different LLM / AI Assistant

This project was built by prompting an LLM to scaffold each layer. Here is the exact sequence of prompts / tasks to give to any LLM to reproduce it:

### Phase 1 — Backend Scaffold
1. *"Create a Flask REST API project called `sec_data_api` with SQLAlchemy, Flask-Migrate, and python-dotenv. Use an app factory pattern (`create_app`). Add a `Config` class that reads `SECRET_KEY`, `DATABASE_URL`, and `SEC_USER_AGENT` from a `.env` file and raises a `ValueError` if `SEC_USER_AGENT` is missing."*
2. *"Add SQLAlchemy models: `Company` (cik, ticker, name, last_financials_update), `AnnualFinancial` (company_cik FK, year, metric_name, metric_value, unit, filed_date), and `InsiderTrade` (stock_symbol, transaction_type, transaction_date, transaction_amount, insider_name, filing_date, source_url). Generate the initial Alembic migration."*
3. *"Create a `helpers.py` utility that fetches the SEC ticker-to-CIK mapping from `https://www.sec.gov/files/company_tickers.json`, caches it in memory, and refreshes it every 24 hours. Expose a `get_cik_from_ticker(ticker)` function."*
4. *"Create `sec_api_service.py` with: (a) `fetch_company_facts(cik)` that calls `https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json`; (b) `parse_financial_statements(facts_json, years=10)` that extracts Income Statement, Balance Sheet, and Cash Flow line items using common US-GAAP XBRL tags and returns them as lists of year-keyed dicts."*
5. *"Create a Flask Blueprint at `/api/v1/financials/<ticker>` that resolves the ticker to a CIK, fetches and parses financial statements, upserts the Company record, and returns structured JSON."*
6. *"Create a Flask Blueprint at `/api/v1/insider-trading/<ticker>/buys` that: fetches recent Form 4 filings from `https://efts.sec.gov/LATEST/search-index?q=%22{cik}%22&dateRange=custom&...`, downloads each Form 4 XML, parses `<nonDerivativeTransaction>` blocks for transaction code `P`, adds a 110 ms sleep between requests to respect the SEC rate limit, and returns a list of buy transactions."*

### Phase 2 — Frontend Scaffold
7. *"Create a React + Vite project called `my-sec-frontend`. Install MUI v7, `@mui/x-data-grid`, `axios`, and `react-router-dom` v7."*
8. *"Create a `Navbar` component and three pages: `HomePage` (welcome screen with links), `FinancialsPage` (search bar + MUI DataGrid showing income/balance/cashflow tabs), and `InsiderTradingPage` (search bar + DataGrid showing insider buys)."*
9. *"Create `services/api.js` with Axios functions: `fetchFinancials(ticker, years)` and `fetchInsiderBuys(ticker, limit)` pointing to `http://localhost:5000`."*
10. *"Add an `ErrorBoundary` component and wire up React Router with routes for `/`, `/financials`, and `/insider-trading`."*

### Phase 3 — Polish
11. *"Add a proxy in `vite.config.js` so `/api` requests in dev are forwarded to `http://localhost:5000`."*
12. *"Add loading spinners, error states, and empty-state messages to both data pages."*

---

## Environment Variables Reference

| Variable | Required | Example | Description |
|---|---|---|---|
| `SEC_USER_AGENT` | **Yes** | `Jane Smith jane@example.com` | Sent as HTTP `User-Agent` to SEC APIs |
| `DATABASE_URL` | No | `sqlite:///../instance/app.db` | SQLAlchemy connection string |
| `SECRET_KEY` | No | `some-random-string` | Flask session secret |
| `FLASK_DEBUG` | No | `1` | Enables Flask debug mode |

---

## Known Limitations

- **XBRL tag coverage** — Not all companies use the same GAAP tags. Some metrics may be missing for certain tickers.
- **No caching of parsed statements** — Financial data is re-fetched from SEC on every request. Add Redis or a caching layer for production use.
- **Insider trading rate limiting** — Processing 50 Form 4 filings takes ~6 seconds due to the mandatory 110 ms delay per SEC request.
- **SQLite for development only** — Switch `DATABASE_URL` to PostgreSQL for any production deployment.
