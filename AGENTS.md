# AGENTS.md

## Cursor Cloud specific instructions

FilingDesk: Flask backend (`backend/`) + Vite/React frontend (`frontend/`). Pulls live data from SEC EDGAR / NSE / Yahoo; egress is open in this environment.

### Environment
- Backend Python deps live in `backend/.venv` (created by the startup update script). `pytest` is installed there by the update script (not in `requirements.txt`).
- Frontend deps are a normal `npm install` under `frontend/`.

### Run (dev)
- Backend: `cd backend && ./.venv/bin/python run.py` → binds `http://127.0.0.1:5000` (Flask debug reloader on). Health: `GET /api/health`.
- Frontend: `cd frontend && npm run dev` → `http://localhost:5173` (Vite). It talks to the backend on port 5000.
- Populate data by POSTing to `/api/v1/insider/sync` with `{"market":"US"}` (or `IN`); then read `/api/v1/insider/transactions?market=US`.

### Test / lint
- Backend tests: `cd backend && ./.venv/bin/python -m pytest -q`.
- Frontend lint: `cd frontend && npm run lint` (oxlint; currently emits warnings only).

The PowerShell/Cloudflare tunnel scripts are Windows-only and not needed here.
