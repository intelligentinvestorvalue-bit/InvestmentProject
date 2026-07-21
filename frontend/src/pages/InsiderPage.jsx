import { useEffect, useMemo, useState } from 'react'
import { fetchInsiderMeta, fetchInsiderTransactions, syncInsider } from '../services/api'
import { formatDate, formatMoney, formatNumber } from '../utils/format'

const EMPTY_FILTERS = {
  q: '',
  side: '',
  role: '',
  ticker: '',
  insider_name: '',
  relationship: '',
  officer_title: '',
  ownership_form: '',
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
  const [filters, setFilters] = useState(EMPTY_FILTERS)
  const [applied, setApplied] = useState(EMPTY_FILTERS)
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ items: [], total: 0, page_size: 50 })
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')

  const pageCount = useMemo(
    () => Math.max(1, Math.ceil((data.total || 0) / (data.page_size || 50))),
    [data.total, data.page_size],
  )

  useEffect(() => {
    setFilters(EMPTY_FILTERS)
    setApplied(EMPTY_FILTERS)
    setPage(1)
    setError('')
  }, [market])

  useEffect(() => {
    let cancelled = false
    async function loadMeta() {
      try {
        const next = await fetchInsiderMeta(market)
        if (!cancelled) setMeta(next)
      } catch (err) {
        if (!cancelled) setMeta(null)
      }
    }
    loadMeta()
    return () => {
      cancelled = true
    }
  }, [market, syncing])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const next = await fetchInsiderTransactions({
          market,
          page,
          page_size: 50,
          ...applied,
        })
        if (!cancelled) setData(next)
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load insider transactions')
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
  }, [market, applied, page])

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
    try {
      await syncInsider(market, { days: 7, max_filings: 25 })
      setPage(1)
      setApplied((prev) => ({ ...prev }))
    } catch (err) {
      setError(err.message || 'Sync failed')
    } finally {
      setSyncing(false)
    }
  }

  if (market === 'IN') {
    return (
      <section className="panel planned">
        <h2>India insider feed — Phase 2</h2>
        <p className="muted">
          US is live first. India will use free NSE + BSE disclosures and SEBI/SAST filings,
          starting with open-market style insider buy/sell activity.
        </p>
        <ul>
          <li>1. Insider activity</li>
          <li>2. Financial statements</li>
          <li>3. Sector browse</li>
        </ul>
      </section>
    )
  }

  const stats = meta?.stats

  return (
    <div>
      <div className="hero-strip">
        <h1>Global open-market insider feed</h1>
        <p>
          Track Form 4 open-market buys (P) and sells (S) across US filers. Filter by role,
          ticker, dates, price, size, and more — then sync fresh filings from SEC EDGAR.
        </p>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>US insider transactions</h2>
            <p>
              {meta?.latest_sync
                ? `Last sync: ${meta.latest_sync.status} · ${meta.latest_sync.transactions_upserted || 0} rows upserted`
                : 'No sync yet — pull recent Form 4 filings to populate the feed.'}
            </p>
          </div>
          <div className="stats">
            <div className="stat">
              <strong className="mono">{formatNumber(stats?.total_transactions)}</strong>
              <span>Cached rows</span>
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
              <button className="btn btn-primary" type="button" onClick={handleSync} disabled={syncing}>
                {syncing ? 'Syncing from SEC…' : 'Sync recent Form 4s'}
              </button>
            </div>
          </div>
        </div>

        <form className="filters" onSubmit={applyFilters}>
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
              <option value="buy">Buy (P)</option>
              <option value="sell">Sell (S)</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="role">Role</label>
            <select id="role" value={filters.role} onChange={(e) => updateFilter('role', e.target.value)}>
              <option value="">All</option>
              <option value="director">Director</option>
              <option value="officer">Officer</option>
              <option value="ten_percent">10% owner</option>
              <option value="other">Other</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="ticker">Ticker</label>
            <input
              id="ticker"
              list="ticker-options"
              value={filters.ticker}
              onChange={(e) => updateFilter('ticker', e.target.value.toUpperCase())}
              placeholder="AAPL"
            />
            <datalist id="ticker-options">
              {(meta?.tickers || []).map((ticker) => (
                <option key={ticker} value={ticker} />
              ))}
            </datalist>
          </div>
          <div className="field">
            <label htmlFor="insider_name">Insider</label>
            <input
              id="insider_name"
              value={filters.insider_name}
              onChange={(e) => updateFilter('insider_name', e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="relationship">Relationship</label>
            <input
              id="relationship"
              list="relationship-options"
              value={filters.relationship}
              onChange={(e) => updateFilter('relationship', e.target.value)}
            />
            <datalist id="relationship-options">
              {(meta?.relationships || []).map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </div>
          <div className="field">
            <label htmlFor="officer_title">Officer title</label>
            <input
              id="officer_title"
              list="title-options"
              value={filters.officer_title}
              onChange={(e) => updateFilter('officer_title', e.target.value)}
            />
            <datalist id="title-options">
              {(meta?.officer_titles || []).map((item) => (
                <option key={item} value={item} />
              ))}
            </datalist>
          </div>
          <div className="field">
            <label htmlFor="ownership_form">Ownership</label>
            <select
              id="ownership_form"
              value={filters.ownership_form}
              onChange={(e) => updateFilter('ownership_form', e.target.value)}
            >
              <option value="">All</option>
              <option value="D">Direct (D)</option>
              <option value="I">Indirect (I)</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="transaction_date_from">Tx date from</label>
            <input
              id="transaction_date_from"
              type="date"
              value={filters.transaction_date_from}
              onChange={(e) => updateFilter('transaction_date_from', e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="transaction_date_to">Tx date to</label>
            <input
              id="transaction_date_to"
              type="date"
              value={filters.transaction_date_to}
              onChange={(e) => updateFilter('transaction_date_to', e.target.value)}
            />
          </div>
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
            <label htmlFor="min_shares">Min shares</label>
            <input
              id="min_shares"
              type="number"
              min="0"
              value={filters.min_shares}
              onChange={(e) => updateFilter('min_shares', e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="max_shares">Max shares</label>
            <input
              id="max_shares"
              type="number"
              min="0"
              value={filters.max_shares}
              onChange={(e) => updateFilter('max_shares', e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="min_price">Min price</label>
            <input
              id="min_price"
              type="number"
              min="0"
              step="0.01"
              value={filters.min_price}
              onChange={(e) => updateFilter('min_price', e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="max_price">Max price</label>
            <input
              id="max_price"
              type="number"
              min="0"
              step="0.01"
              value={filters.max_price}
              onChange={(e) => updateFilter('max_price', e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="min_value">Min value ($)</label>
            <input
              id="min_value"
              type="number"
              min="0"
              value={filters.min_value}
              onChange={(e) => updateFilter('min_value', e.target.value)}
            />
          </div>
          <div className="field">
            <label htmlFor="max_value">Max value ($)</label>
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
              <option value="filing_date_asc">Filing date ↑</option>
              <option value="transaction_date_desc">Tx date ↓</option>
              <option value="transaction_date_asc">Tx date ↑</option>
              <option value="value_desc">Value ↓</option>
              <option value="value_asc">Value ↑</option>
              <option value="shares_desc">Shares ↓</option>
              <option value="shares_asc">Shares ↑</option>
              <option value="price_desc">Price ↓</option>
              <option value="price_asc">Price ↑</option>
            </select>
          </div>
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
            <div className="empty muted">Loading transactions…</div>
          ) : data.items?.length ? (
            <table>
              <thead>
                <tr>
                  <th>Side</th>
                  <th>Ticker</th>
                  <th>Company</th>
                  <th>Insider</th>
                  <th>Role</th>
                  <th>Tx date</th>
                  <th>Filing</th>
                  <th>Shares</th>
                  <th>Price</th>
                  <th>Value</th>
                  <th>Owned after</th>
                  <th>Form</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.id}>
                    <td>
                      <span className={`side-pill ${row.transaction_side}`}>
                        {row.transaction_side}
                      </span>
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
                    <td className="mono">{formatDate(row.transaction_date)}</td>
                    <td className="mono">{formatDate(row.filing_date)}</td>
                    <td className="mono">{formatNumber(row.shares, 2)}</td>
                    <td className="mono">{formatMoney(row.price_per_share)}</td>
                    <td className="mono">{formatMoney(row.total_value)}</td>
                    <td className="mono">{formatNumber(row.shares_owned_after, 2)}</td>
                    <td className="mono">{row.ownership_form || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty muted">
              No transactions yet. Click <strong>Sync recent Form 4s</strong> to pull open-market
              buys and sells from SEC EDGAR.
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
