import { useEffect, useMemo, useState } from 'react'
import { fetchUnusualMeta, fetchUnusualOptions, scanUnusualOptions } from '../services/api'
import { currencyForMarket, formatDate, formatMoney, formatNumber } from '../utils/format'

const EMPTY = {
  underlying: '',
  sentiment: '',
  universe: '',
  min_score: '',
}

export default function OptionsPage({ market }) {
  const currency = currencyForMarket(market)
  const [filters, setFilters] = useState(EMPTY)
  const [applied, setApplied] = useState(EMPTY)
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ items: [], total: 0, page_size: 50 })
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState('')
  const [scanNote, setScanNote] = useState('')

  const pageCount = useMemo(
    () => Math.max(1, Math.ceil((data.total || 0) / (data.page_size || 50))),
    [data.total, data.page_size],
  )

  useEffect(() => {
    setFilters(EMPTY)
    setApplied(EMPTY)
    setPage(1)
    setError('')
    setScanNote('')
  }, [market])

  useEffect(() => {
    let cancelled = false
    async function loadMeta() {
      try {
        const next = await fetchUnusualMeta(market)
        if (!cancelled) setMeta(next)
      } catch {
        if (!cancelled) setMeta(null)
      }
    }
    loadMeta()
    return () => {
      cancelled = true
    }
  }, [market, scanning])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const next = await fetchUnusualOptions({
          market,
          page,
          page_size: 50,
          underlying: applied.underlying || undefined,
          sentiment: applied.sentiment || undefined,
          universe: applied.universe || undefined,
          min_score: applied.min_score || undefined,
        })
        if (!cancelled) setData(next)
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load unusual options')
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

  async function handleScan() {
    setScanning(true)
    setScanNote('')
    setError('')
    try {
      const result = await scanUnusualOptions({
        market,
        include_watchlist: true,
        include_liquid: true,
        max_tickers: market === 'IN' ? 8 : 12,
      })
      setScanNote(
        `Scan ${result.status}: ${result.tickers_scanned || 0} tickers · ${result.alerts_upserted || 0} new alerts · ${result.notifications_created || 0} notifications`,
      )
      setPage(1)
      setApplied({ ...applied })
    } catch (err) {
      setError(err.message || 'Scan failed')
    } finally {
      setScanning(false)
    }
  }

  const heroCopy =
    market === 'IN'
      ? 'NSE F&O option-chain scanner for watchlist + liquid India names (indices and equities). Direction blends call/put bias with bid/ask aggressiveness. Alerts stay in-app only.'
      : 'Delayed Yahoo chain scanner for watchlist + liquid US names. Direction blends call/put bias with bid/ask aggressiveness. Alerts stay in-app only.'

  return (
    <>
      <section className="hero-strip">
        <h1>Unusual options</h1>
        <p>{heroCopy}</p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Activity feed · {market === 'IN' ? 'India F&O' : 'US'}</h2>
            <p>
              Source: {meta?.source || (market === 'IN' ? 'NSE option-chain-v3' : 'Yahoo Finance (delayed)')}
              {data.scan_date ? ` · scan day ${data.scan_date}` : ''}
              {data.latest_scan?.status
                ? ` · last run ${data.latest_scan.trigger} (${data.latest_scan.status})`
                : ''}
            </p>
          </div>
          <div className="stats">
            <div className="stat">
              <strong>{formatNumber(data.total || 0)}</strong>
              <span>alerts</span>
            </div>
            <div className="stat">
              <strong>{meta?.timing?.near_realtime_minutes || '—'}m</strong>
              <span>poll</span>
            </div>
            <div className="stat">
              <strong>{meta?.timing?.eod_hour_utc ?? '—'}h</strong>
              <span>EOD UTC</span>
            </div>
          </div>
        </div>

        <div className="filters">
          <div className="field">
            <label htmlFor="uoa-ticker">Ticker</label>
            <input
              id="uoa-ticker"
              value={filters.underlying}
              onChange={(e) => setFilters({ ...filters, underlying: e.target.value.toUpperCase() })}
              placeholder={market === 'IN' ? 'NIFTY / RELIANCE' : 'NVDA'}
            />
          </div>
          <div className="field">
            <label htmlFor="uoa-sentiment">Sentiment</label>
            <select
              id="uoa-sentiment"
              value={filters.sentiment}
              onChange={(e) => setFilters({ ...filters, sentiment: e.target.value })}
            >
              <option value="">All</option>
              {(meta?.sentiments || ['bullish', 'bearish', 'mixed', 'unclear']).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div className="field">
            <label htmlFor="uoa-universe">Universe</label>
            <select
              id="uoa-universe"
              value={filters.universe}
              onChange={(e) => setFilters({ ...filters, universe: e.target.value })}
            >
              <option value="">All</option>
              <option value="watchlist">Watchlist</option>
              <option value="liquid100">Liquid set</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="uoa-score">Min score</label>
            <input
              id="uoa-score"
              type="number"
              value={filters.min_score}
              onChange={(e) => setFilters({ ...filters, min_score: e.target.value })}
              placeholder="35"
            />
          </div>
          <div className="actions">
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                setPage(1)
                setApplied({ ...filters })
              }}
            >
              Apply
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              onClick={() => {
                setFilters(EMPTY)
                setApplied(EMPTY)
                setPage(1)
              }}
            >
              Reset
            </button>
            <button type="button" className="btn btn-primary" disabled={scanning} onClick={handleScan}>
              {scanning ? 'Scanning…' : market === 'IN' ? 'Scan sample (8)' : 'Scan sample (12)'}
            </button>
          </div>
        </div>

        {scanNote ? <p className="inline-note">{scanNote}</p> : null}
        {error ? <div className="error">{error}</div> : null}
        {loading ? <div className="empty muted">Loading unusual options…</div> : null}

        {!loading && !error && (data.items || []).length === 0 ? (
          <div className="empty muted">
            No alerts yet. Run a sample scan, or wait for the scheduled poll / EOD job.
          </div>
        ) : null}

        {!loading && (data.items || []).length > 0 ? (
          <>
            <div className="table-wrap">
              <ul className="feed-cards">
                {data.items.map((row) => (
                  <li key={`card-${row.id}-${row.contract_symbol}`} className="feed-card">
                    <div className="feed-card-top">
                      <div>
                        <strong className="mono">{row.underlying}</strong>
                        <span className="muted feed-card-sub mono">{row.contract_symbol}</span>
                      </div>
                      <span className={`side-pill ${row.option_type === 'call' ? 'buy' : 'sell'}`}>
                        {row.option_type}
                      </span>
                    </div>
                    <div className="feed-card-metrics">
                      <div>
                        <span className="muted">Score</span>
                        <strong className="mono">{formatNumber(row.score)}</strong>
                      </div>
                      <div>
                        <span className="muted">Premium</span>
                        <strong className="mono">{formatMoney(row.premium, 'USD')}</strong>
                      </div>
                      <div>
                        <span className="muted">Strike</span>
                        <strong className="mono">{formatNumber(row.strike)}</strong>
                      </div>
                      <div>
                        <span className="muted">Exp</span>
                        <strong className="mono">
                          {formatDate(row.expiration)} · {row.dte}d
                        </strong>
                      </div>
                    </div>
                    <div className="feed-card-body">
                      <span
                        className={`side-pill ${
                          row.sentiment === 'bullish' ? 'buy' : row.sentiment === 'bearish' ? 'sell' : ''
                        }`}
                      >
                        {row.sentiment || '—'}
                      </span>
                      <span className="muted">
                        Vol/OI {formatNumber(row.vol_oi)} · {row.aggressiveness || 'unknown'}
                        {row.reason ? ` · ${row.reason}` : ''}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
              <table className="desktop-table">
                <thead>
                  <tr>
                    <th>Underlying</th>
                    <th>Type</th>
                    <th>Strike / Exp</th>
                    <th>Vol / OI</th>
                    <th>Premium</th>
                    <th>Score</th>
                    <th>Direction</th>
                    <th>Universe</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row) => (
                    <tr key={`${row.id}-${row.contract_symbol}`}>
                      <td>
                        <strong>{row.underlying}</strong>
                        <div className="muted mono" style={{ fontSize: '0.78rem' }}>
                          {row.contract_symbol}
                        </div>
                      </td>
                      <td>
                        <span className={`side-pill ${row.option_type === 'call' ? 'buy' : 'sell'}`}>
                          {row.option_type}
                        </span>
                      </td>
                      <td className="mono">
                        {formatNumber(row.strike)}
                        <div className="muted">
                          {formatDate(row.expiration)} · {row.dte}d
                        </div>
                      </td>
                      <td className="mono">
                        {formatNumber(row.volume)} / {formatNumber(row.open_interest)}
                        <div className="muted">Vol/OI {formatNumber(row.vol_oi)}</div>
                      </td>
                      <td className="mono">{formatMoney(row.premium, currency)}</td>
                      <td className="mono">
                        <strong>{formatNumber(row.score)}</strong>
                      </td>
                      <td>
                        <span
                          className={`side-pill ${
                            row.sentiment === 'bullish' ? 'buy' : row.sentiment === 'bearish' ? 'sell' : ''
                          }`}
                        >
                          {row.sentiment || '—'}
                        </span>
                        <div className="muted" style={{ fontSize: '0.78rem', marginTop: '0.25rem' }}>
                          {row.aggressiveness || 'unknown'}
                          {row.reason ? ` · ${row.reason}` : ''}
                        </div>
                      </td>
                      <td>{row.universe || '—'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pager">
              <span className="muted">
                Page {page} of {pageCount}
              </span>
              <div className="actions">
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="btn btn-ghost"
                  disabled={page >= pageCount}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        ) : null}
      </section>
    </>
  )
}
