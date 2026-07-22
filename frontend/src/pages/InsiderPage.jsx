import { useEffect, useMemo, useState } from 'react'
import {
  fetchDisclosures,
  fetchHealth,
  fetchInsiderMeta,
  fetchInsiderTransactions,
  syncInsider,
} from '../services/api'
import { currencyForMarket, formatDate, formatMoney, formatNumber } from '../utils/format'

const EMPTY_FILTERS = {
  q: '',
  side: '',
  role: '',
  ticker: '',
  insider_name: '',
  relationship: '',
  officer_title: '',
  ownership_form: '',
  exchange: '',
  transaction_date_from: '',
  transaction_date_to: '',
  filing_date_from: '',
  filing_date_to: '',
  min_shares: '',
  max_shares: '',
  min_price: '',
  max_price: '',
  min_value: '',
  max_value: '',
  sort: 'filing_date_desc',
}

export default function InsiderPage({ market }) {
  const currency = currencyForMarket(market)
  const [view, setView] = useState('open_market')
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [applied, setApplied] = useState(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ items: [], total: 0, page_size: 50 })
  const [meta, setMeta] = useState(null)
  const [scheduler, setScheduler] = useState(null)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [backfilling, setBackfilling] = useState(false)
  const [error, setError] = useState('')
  const [syncNote, setSyncNote] = useState('')

  const pageCount = useMemo(
    () => Math.max(1, Math.ceil((data.total || 0) / (data.page_size || 50))),
    [data.total, data.page_size],
  )
  const busy = syncing || backfilling

  useEffect(() => {
    setFilters(EMPTY_FILTERS)
    setApplied(EMPTY_FILTERS)
    setPage(1)
    setView('open_market')
    setError('')
    setSyncNote('')
  }, [market])

  useEffect(() => {
    let cancelled = false
    async function loadMeta() {
      try {
        const [next, health] = await Promise.all([fetchInsiderMeta(market), fetchHealth()])
        if (!cancelled) {
          setMeta(next)
          setScheduler(health.scheduler || null)
        }
      } catch {
        if (!cancelled) setMeta(null)
      }
    }
    loadMeta()
    return () => {
      cancelled = true
    }
  }, [market, syncing, backfilling])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        let next
        if (market === 'IN' && (view === 'pledge' || view === 'sast')) {
          next = await fetchDisclosures({
            market: 'IN',
            kind: view,
            ticker: applied.ticker || undefined,
            page,
            page_size: 50,
          })
        } else {
          next = await fetchInsiderTransactions({
            market,
            page,
            page_size: 50,
            ...applied,
          })
        }
        if (!cancelled) setData(next)
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load insider data')
          setData({ items: [], total: 0, page_size: 50 })
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [market, applied, page, view])

  function updateFilter(key, value) {
    setFilters((prev) => ({ ...prev, [key]: value }))
  }

  function applyFilters(event) {
    event.preventDefault()
    setPage(1)
    setApplied({ ...filters })
  }

  function resetFilters() {
    setFilters(EMPTY_FILTERS)
    setApplied(EMPTY_FILTERS)
    setPage(1)
  }

  async function handleSync() {
    setSyncing(true)
    setError('')
    setSyncNote('')
    try {
      const payload =
        market === 'US'
          ? { mode: 'recent', days: 7, max_filings: 25 }
          : { days: 120, include_extra: true }
      const result = await syncInsider(market, payload)
      setSyncNote(
        market === 'US'
          ? `Recent sync: ${result.transactions_upserted || 0} new open-market rows from ${result.filings_seen || 0} filings.`
          : `Synced ${result.transactions_upserted || 0} rows.`,
      )
      setPage(1)
      setApplied((prev) => ({ ...prev }))
    } catch (err) {
      setError(err.message || 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  async function handleBackfill() {
    setBackfilling(true)
    setError('')
    setSyncNote('')
    try {
      const days = meta?.backfill_days_default || 30
      const maxFilings = meta?.backfill_max_filings_default || 300
      const result = await syncInsider('US', {
        mode: 'backfill',
        days,
        max_filings: maxFilings,
      })
      setSyncNote(
        `Backfill complete (${result.days || days}d): ${result.transactions_upserted || 0} new rows from ${result.filings_seen || 0} filings. Use filters on the local DB going forward.`,
      )
      setPage(1)
      setApplied((prev) => ({ ...prev }))
    } catch (err) {
      setError(err.message || 'Backfill failed')
    } finally {
      setBackfilling(false)
    }
  }

  const stats = meta?.stats
  const syncLabel = market === 'US' ? 'Sync recent Form 4s' : 'Sync PIT + pledge/SAST'
  const showOpenMarket = view === 'open_market'
  const coverageHint =
    market === 'US' && stats?.filing_date_min && stats?.filing_date_max
      ? `Local coverage: ${formatDate(stats.filing_date_min)} → ${formatDate(stats.filing_date_max)}`
      : null

  return (
    <div>
      <div className="hero-strip">
        <h1>{market === 'US' ? 'US open-market insider feed' : 'India insider & disclosures'}</h1>
        <p>
          {market === 'US'
            ? 'Track Form 4 open-market buys (P) and sells (S) across US filers. Backfill once to seed ~30 days locally, then filter the DB; scheduled sync keeps it current.'
            : 'Open-market PIT plus separate pledge and SAST Reg.29 views (NSE/BSE reported).'}{' '}
          Scheduled sync keeps feeds fresh in the background.
        </p>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>{market === 'US' ? 'US insider transactions' : 'India disclosures'}</h2>
            <p>
              {meta?.latest_sync
                ? `Last sync: ${meta.latest_sync.status}${meta.latest_sync.trigger ? ` (${meta.latest_sync.trigger})` : ''} · ${meta.latest_sync.transactions_upserted || 0} open-market rows`
                : 'No sync yet — pull recent filings or run a one-time backfill.'}
              {scheduler?.running
                ? ` · Scheduler on (${(scheduler.jobs || []).length} jobs)`
                : ' · Scheduler off'}
              {coverageHint ? ` · ${coverageHint}` : ''}
            </p>
            {syncNote ? <p className="muted">{syncNote}</p> : null}
          </div>
          <div className="stats">
            <div className="stat">
              <strong className="mono">{formatNumber(stats?.total_transactions)}</strong>
              <span>Open-market</span>
            </div>
            <div className="stat">
              <strong className="mono">{formatNumber(stats?.buy_count)}</strong>
              <span>Buys</span>
            </div>
            <div className="stat">
              <strong className="mono">{formatNumber(stats?.sell_count)}</strong>
              <span>Sells</span>
            </div>
            <div className="actions">
              <button className="btn btn-primary" type="button" onClick={handleSync} disabled={busy}>
                {syncing ? 'Syncing…' : syncLabel}
              </button>
              {market === 'US' ? (
                <button className="btn btn-ghost" type="button" onClick={handleBackfill} disabled={busy}>
                  {backfilling ? 'Backfilling…' : 'Backfill last 30 days'}
                </button>
              ) : null}
            </div>
          </div>
        </div>

        {market === 'IN' ? (
          <div className="tab-row">
            {[
              { id: 'open_market', label: 'Open market' },
              { id: 'pledge', label: 'Pledge' },
              { id: 'sast', label: 'SAST Reg.29' },
            ].map((item) => (
              <button
                key={item.id}
                type="button"
                className={view === item.id ? 'active' : ''}
                onClick={() => {
                  setView(item.id)
                  setPage(1)
                }}
              >
                {item.label}
              </button>
            ))}
          </div>
        ) : null}

        <form className="filters" onSubmit={applyFilters}>
          {showOpenMarket ? (
            <>
              <div className="field">
                <label htmlFor="q">Search</label>
                <input
                  id="q"
                  value={filters.q}
                  onChange={(e) => updateFilter('q', e.target.value)}
                  placeholder="Ticker, company, insider"
                />
              </div>
              <div className="field">
                <label htmlFor="side">Side</label>
                <select id="side" value={filters.side} onChange={(e) => updateFilter('side', e.target.value)}>
                  <option value="">All</option>
                  <option value="buy">Buy</option>
                  <option value="sell">Sell</option>
                </select>
              </div>
              <div className="field">
                <label htmlFor="role">Role</label>
                <select id="role" value={filters.role} onChange={(e) => updateFilter('role', e.target.value)}>
                  <option value="">All</option>
                  <option value="director">Director</option>
                  <option value="officer">Officer / KMP</option>
                  <option value="ten_percent">{market === 'IN' ? 'Promoter' : '10% owner'}</option>
                  <option value="other">Other</option>
                </select>
              </div>
            </>
          ) : null}
          <div className="field">
            <label htmlFor="ticker">Ticker</label>
            <input
              id="ticker"
              list="ticker-options"
              value={filters.ticker}
              onChange={(e) => updateFilter('ticker', e.target.value.toUpperCase())}
              placeholder={market === 'US' ? 'AAPL' : 'RELIANCE'}
            />
            <datalist id="ticker-options">
              {(meta?.tickers || []).map((t) => (
                <option key={t} value={t} />
              ))}
            </datalist>
          </div>
          {showOpenMarket ? (
            <>
              <div className="field">
                <label htmlFor="filing_date_from">Filing from</label>
                <input
                  id="filing_date_from"
                  type="date"
                  value={filters.filing_date_from}
                  onChange={(e) => updateFilter('filing_date_from', e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="filing_date_to">Filing to</label>
                <input
                  id="filing_date_to"
                  type="date"
                  value={filters.filing_date_to}
                  onChange={(e) => updateFilter('filing_date_to', e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="min_value">Min value</label>
                <input
                  id="min_value"
                  type="number"
                  min="0"
                  value={filters.min_value}
                  onChange={(e) => updateFilter('min_value', e.target.value)}
                  placeholder={market === 'US' ? '100000' : ''}
                />
              </div>
              <div className="field">
                <label htmlFor="max_value">Max value</label>
                <input
                  id="max_value"
                  type="number"
                  min="0"
                  value={filters.max_value}
                  onChange={(e) => updateFilter('max_value', e.target.value)}
                />
              </div>
              <div className="field">
                <label htmlFor="sort">Sort</label>
                <select id="sort" value={filters.sort} onChange={(e) => updateFilter('sort', e.target.value)}>
                  <option value="filing_date_desc">Filing date ↓</option>
                  <option value="transaction_date_desc">Tx date ↓</option>
                  <option value="value_desc">Value ↓</option>
                  <option value="shares_desc">Shares ↓</option>
                </select>
              </div>
            </>
          ) : null}
          <div className="actions">
            <button className="btn btn-primary" type="submit">
              Apply filters
            </button>
            <button className="btn btn-ghost" type="button" onClick={resetFilters}>
              Reset
            </button>
          </div>
        </form>

        {error ? <div className="error">{error}</div> : null}

        <div className="table-wrap">
          {loading ? (
            <div className="empty muted">Loading…</div>
          ) : data.items?.length ? (
            showOpenMarket ? (
              <table>
                <thead>
                  <tr>
                    <th>Side</th>
                    <th>Ticker</th>
                    <th>Company</th>
                    <th>Insider</th>
                    <th>Role</th>
                    {market === 'IN' ? <th>Exch</th> : null}
                    <th>Tx date</th>
                    <th>Filing</th>
                    <th>Shares</th>
                    <th>Price</th>
                    <th>Value</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row) => (
                    <tr key={row.id}>
                      <td>
                        <span className={`side-pill ${row.transaction_side}`}>{row.transaction_side}</span>
                      </td>
                      <td className="mono">{row.ticker || '—'}</td>
                      <td>{row.company_name || '—'}</td>
                      <td>
                        {row.source_url ? (
                          <a href={row.source_url} target="_blank" rel="noreferrer">
                            {row.insider_name}
                          </a>
                        ) : (
                          row.insider_name
                        )}
                      </td>
                      <td>{row.relationship || '—'}</td>
                      {market === 'IN' ? <td className="mono">{row.exchange || '—'}</td> : null}
                      <td className="mono">{formatDate(row.transaction_date)}</td>
                      <td className="mono">{formatDate(row.filing_date)}</td>
                      <td className="mono">{formatNumber(row.shares, 2)}</td>
                      <td className="mono">{formatMoney(row.price_per_share, currency)}</td>
                      <td className="mono">{formatMoney(row.total_value, currency)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <table>
                <thead>
                  <tr>
                    <th>Kind</th>
                    <th>Ticker</th>
                    <th>Company</th>
                    <th>Party</th>
                    <th>Side</th>
                    <th>Event</th>
                    <th>Filing</th>
                    <th>Shares</th>
                    <th>%</th>
                    <th>Details</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row) => (
                    <tr key={row.id}>
                      <td className="mono">{row.kind}</td>
                      <td className="mono">{row.ticker || '—'}</td>
                      <td>{row.company_name || '—'}</td>
                      <td>
                        {row.source_url ? (
                          <a href={row.source_url} target="_blank" rel="noreferrer">
                            {row.party_name || '—'}
                          </a>
                        ) : (
                          row.party_name || '—'
                        )}
                      </td>
                      <td>{row.side || '—'}</td>
                      <td className="mono">{formatDate(row.event_date)}</td>
                      <td className="mono">{formatDate(row.filing_date)}</td>
                      <td className="mono">{formatNumber(row.shares, 2)}</td>
                      <td className="mono">{formatNumber(row.percent, 2)}</td>
                      <td>{row.details || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )
          ) : (
            <div className="empty muted">
              No rows yet. Click <strong>{syncLabel}</strong>
              {market === 'US' ? (
                <>
                  {' '}
                  or <strong>Backfill last 30 days</strong>
                </>
              ) : null}{' '}
              to load data.
            </div>
          )}
        </div>

        <div className="pager">
          <span className="muted">
            {formatNumber(data.total)} matches · page {page} / {pageCount}
          </span>
          <div className="actions">
            <button
              className="btn btn-ghost"
              type="button"
              disabled={page <= 1 || loading}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Previous
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              disabled={page >= pageCount || loading}
              onClick={() => setPage((p) => p + 1)}
            >
              Next
            </button>
          </div>
        </div>
      </section>
    </div>
  )
}
