import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchUnusualMeta, fetchUnusualOptions, scanUnusualOptions } from '../services/api'
import { currencyForMarket, formatMoney, formatNumber } from '../utils/format'
import {
  aggressivenessLabel,
  formatIv,
  formatOptionContract,
  sentimentLabel,
  universeLabel,
} from '../utils/uoaLabels'

function emptyFilters(defaults = {}) {
  return {
    underlying: '',
    sentiment: '',
    universe: '',
    option_type: '',
    aggressiveness: '',
    min_score: '',
    min_vol_oi: '',
    min_premium: '',
    ...defaults,
  }
}

function quoteBlock(row, currency) {
  const last = row.last_price != null ? formatMoney(row.last_price, currency) : '—'
  const bid = row.bid != null ? formatMoney(row.bid, currency) : '—'
  const ask = row.ask != null ? formatMoney(row.ask, currency) : '—'
  return (
    <>
      <div className="mono">Last {last}</div>
      <div className="muted mono" style={{ fontSize: '0.78rem' }}>
        {bid} / {ask}
      </div>
      <div className="muted" style={{ fontSize: '0.78rem' }}>
        IV {formatIv(row.implied_volatility)}
      </div>
    </>
  )
}

export default function OptionsPage({ market }) {
  const currency = currencyForMarket(market)
  const [searchParams, setSearchParams] = useSearchParams()
  const [filters, setFilters] = useState(() => emptyFilters())
  const [applied, setApplied] = useState(() => emptyFilters())
  const [defaultsReady, setDefaultsReady] = useState(false)
  const [page, setPage] = useState(1)
  const [data, setData] = useState({ items: [], total: 0, page_size: 50 })
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(false)
  const [scanning, setScanning] = useState(false)
  const [error, setError] = useState('')
  const [scanNote, setScanNote] = useState('')
  const [focusTicker, setFocusTicker] = useState('')
  const [showLegend, setShowLegend] = useState(false)

  const pageCount = useMemo(
    () => Math.max(1, Math.ceil((data.total || 0) / (data.page_size || 50))),
    [data.total, data.page_size],
  )

  const thresholds = meta?.thresholds || {}
  const directionModel = meta?.direction_model || []
  const fieldHelp = meta?.field_help || {}

  useEffect(() => {
    setError('')
    setScanNote('')
    setDefaultsReady(false)
    setPage(1)
  }, [market])

  useEffect(() => {
    let cancelled = false
    async function loadMeta() {
      try {
        const next = await fetchUnusualMeta(market)
        if (cancelled) return
        setMeta(next)

        const ticker = (searchParams.get('ticker') || searchParams.get('underlying') || '').toUpperCase()
        const sentiment = searchParams.get('sentiment') || ''
        const minScoreParam = searchParams.get('min_score')
        const notifyScore = next?.thresholds?.notify_min_score
        const nextFilters = emptyFilters({
          underlying: ticker,
          sentiment,
          min_score:
            minScoreParam != null && minScoreParam !== ''
              ? String(minScoreParam)
              : notifyScore != null
                ? String(notifyScore)
                : '80',
          min_vol_oi: searchParams.get('min_vol_oi') || String(next?.thresholds?.min_vol_oi ?? ''),
          option_type: searchParams.get('option_type') || '',
          aggressiveness: searchParams.get('aggressiveness') || '',
          universe: searchParams.get('universe') || '',
          min_premium: searchParams.get('min_premium') || '',
        })
        setFilters(nextFilters)
        setApplied(nextFilters)
        setFocusTicker(ticker)
        setDefaultsReady(true)
      } catch {
        if (!cancelled) {
          setMeta(null)
          setDefaultsReady(true)
        }
      }
    }
    loadMeta()
    return () => {
      cancelled = true
    }
  }, [market, searchParams])

  useEffect(() => {
    if (!defaultsReady) return
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
          option_type: applied.option_type || undefined,
          aggressiveness: applied.aggressiveness || undefined,
          min_score: applied.min_score || undefined,
          min_vol_oi: applied.min_vol_oi || undefined,
          min_premium: applied.min_premium || undefined,
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
  }, [market, applied, page, defaultsReady])

  function applyFilters(next = filters) {
    setPage(1)
    setApplied({ ...next })
    setFocusTicker(next.underlying || '')
    const params = {}
    if (next.underlying) params.ticker = next.underlying
    if (next.sentiment) params.sentiment = next.sentiment
    if (next.min_score) params.min_score = next.min_score
    if (next.min_vol_oi) params.min_vol_oi = next.min_vol_oi
    if (next.option_type) params.option_type = next.option_type
    if (next.aggressiveness) params.aggressiveness = next.aggressiveness
    if (next.universe) params.universe = next.universe
    if (next.min_premium) params.min_premium = next.min_premium
    setSearchParams(params)
  }

  function resetFilters() {
    const notifyScore = thresholds.notify_min_score
    const next = emptyFilters({
      min_score: notifyScore != null ? String(notifyScore) : '80',
      min_vol_oi: thresholds.min_vol_oi != null ? String(thresholds.min_vol_oi) : '',
    })
    setFilters(next)
    applyFilters(next)
  }

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
      setApplied((prev) => ({ ...prev }))
    } catch (err) {
      setError(err.message || 'Scan failed')
    } finally {
      setScanning(false)
    }
  }

  const heroCopy =
    market === 'IN'
      ? 'NSE F&O unusual-activity dashboard. Each row is a contract that cleared Vol/OI, premium, and score gates. In-app alerts only fire for clear bullish/bearish prints.'
      : 'US unusual-options dashboard. Each row is a contract that cleared Vol/OI, premium, and score gates. In-app alerts only fire for clear bullish/bearish prints.'

  return (
    <>
      <section className="hero-strip">
        <h1>Unusual options dashboard</h1>
        <p>{heroCopy}</p>
      </section>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>
              {focusTicker ? `${focusTicker} · filtered view` : `Activity · ${market === 'IN' ? 'India F&O' : 'US'}`}
            </h2>
            <p>
              Source: {meta?.source || (market === 'IN' ? 'NSE option-chain-v3' : 'Yahoo Finance (delayed)')}
              {data.scan_date ? ` · scan day ${data.scan_date}` : ''}
              {thresholds.require_vol_oi ? ' · Vol/OI required' : ''}
              {thresholds.notify_min_score != null ? ` · notify score ≥ ${thresholds.notify_min_score}` : ''}
            </p>
          </div>
          <div className="stats">
            <div className="stat">
              <strong className="mono">{formatNumber(data.total || 0)}</strong>
              <span>matches</span>
            </div>
            <div className="stat">
              <strong className="mono">{formatNumber(thresholds.min_vol_oi)}</strong>
              <span>min Vol/OI</span>
            </div>
            <div className="stat">
              <strong className="mono">{formatNumber(thresholds.notify_min_score)}</strong>
              <span>notify score</span>
            </div>
          </div>
        </div>

        <div className="uoa-legend-bar">
          <button type="button" className="btn btn-ghost" onClick={() => setShowLegend((v) => !v)}>
            {showLegend ? 'Hide how to read alerts' : 'How to read these alerts'}
          </button>
          {showLegend ? (
            <div className="uoa-legend">
              <ul>
                {(directionModel.length
                  ? directionModel
                  : [
                      'Calls lean bullish; puts lean bearish.',
                      'Last near ask ≈ aggressive buy; near bid ≈ possible sell/hedge (mixed).',
                      'Score blends Vol/OI, premium, volume, and DTE.',
                      'Premium is estimated notional, not your P&L.',
                    ]
                ).map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
              {fieldHelp.vol_oi || fieldHelp.premium ? (
                <dl className="uoa-field-help">
                  {fieldHelp.vol_oi ? (
                    <>
                      <dt>Vol/OI</dt>
                      <dd>{fieldHelp.vol_oi}</dd>
                    </>
                  ) : null}
                  {fieldHelp.premium ? (
                    <>
                      <dt>Premium</dt>
                      <dd>{fieldHelp.premium}</dd>
                    </>
                  ) : null}
                  {fieldHelp.aggressiveness ? (
                    <>
                      <dt>Flow</dt>
                      <dd>{fieldHelp.aggressiveness}</dd>
                    </>
                  ) : null}
                  {fieldHelp.sentiment ? (
                    <>
                      <dt>Sentiment</dt>
                      <dd>{fieldHelp.sentiment}</dd>
                    </>
                  ) : null}
                </dl>
              ) : null}
            </div>
          ) : null}
        </div>

        <form
          className="filters"
          onSubmit={(e) => {
            e.preventDefault()
            applyFilters()
          }}
        >
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
            <label htmlFor="uoa-type">Type</label>
            <select
              id="uoa-type"
              value={filters.option_type}
              onChange={(e) => setFilters({ ...filters, option_type: e.target.value })}
            >
              <option value="">All</option>
              <option value="call">Call</option>
              <option value="put">Put</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="uoa-sentiment">Sentiment</label>
            <select
              id="uoa-sentiment"
              value={filters.sentiment}
              onChange={(e) => setFilters({ ...filters, sentiment: e.target.value })}
            >
              <option value="">All</option>
              <option value="bullish">Bullish (likely long calls / short puts bias)</option>
              <option value="bearish">Bearish (likely long puts / short calls bias)</option>
              <option value="mixed">Mixed (possible sell/hedge)</option>
              <option value="unclear">Unclear</option>
            </select>
          </div>
          <div className="field">
            <label htmlFor="uoa-agg">Flow</label>
            <select
              id="uoa-agg"
              value={filters.aggressiveness}
              onChange={(e) => setFilters({ ...filters, aggressiveness: e.target.value })}
            >
              <option value="">All</option>
              <option value="buy_ask">Aggressive buy (near ask)</option>
              <option value="sell_bid">Aggressive sell (near bid)</option>
              <option value="mid">Mid-spread</option>
              <option value="unknown">Bid/ask unavailable</option>
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
            <label htmlFor="uoa-score" title={fieldHelp.score || ''}>
              Min score
            </label>
            <input
              id="uoa-score"
              type="number"
              value={filters.min_score}
              onChange={(e) => setFilters({ ...filters, min_score: e.target.value })}
              placeholder={String(thresholds.notify_min_score ?? 80)}
            />
          </div>
          <div className="field">
            <label htmlFor="uoa-voloi" title={fieldHelp.vol_oi || ''}>
              Min Vol/OI
            </label>
            <input
              id="uoa-voloi"
              type="number"
              step="0.1"
              value={filters.min_vol_oi}
              onChange={(e) => setFilters({ ...filters, min_vol_oi: e.target.value })}
              placeholder={String(thresholds.min_vol_oi ?? 3)}
            />
          </div>
          <div className="field">
            <label htmlFor="uoa-premium" title={fieldHelp.premium || ''}>
              Min premium (notional)
            </label>
            <input
              id="uoa-premium"
              type="number"
              value={filters.min_premium}
              onChange={(e) => setFilters({ ...filters, min_premium: e.target.value })}
              placeholder={String(thresholds.min_premium ?? '')}
            />
          </div>
          <div className="actions">
            <button type="submit" className="btn btn-primary">
              Apply filters
            </button>
            <button type="button" className="btn btn-ghost" onClick={resetFilters}>
              Reset
            </button>
            <button type="button" className="btn btn-primary" disabled={scanning} onClick={handleScan}>
              {scanning ? 'Scanning…' : market === 'IN' ? 'Scan sample (8)' : 'Scan sample (12)'}
            </button>
          </div>
        </form>

        {scanNote ? <p className="inline-note">{scanNote}</p> : null}
        {error ? <div className="error">{error}</div> : null}
        {loading ? <div className="empty muted">Loading unusual options…</div> : null}

        {!loading && !error && (data.items || []).length === 0 ? (
          <div className="empty muted">
            No unusual matches for these filters. Loosen min score / Vol/OI, or run a sample scan.
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
                        <strong className="mono">
                          {formatOptionContract(row, { currency })}
                        </strong>
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
                        <span className="muted">Notional premium</span>
                        <strong className="mono">{formatMoney(row.premium, currency)}</strong>
                      </div>
                      <div>
                        <span className="muted">Vol/OI</span>
                        <strong className="mono">{formatNumber(row.vol_oi)}×</strong>
                      </div>
                      <div>
                        <span className="muted">Volume / OI</span>
                        <strong className="mono">
                          {formatNumber(row.volume)} / {formatNumber(row.open_interest)}
                        </strong>
                      </div>
                    </div>
                    <div className="feed-card-quote">{quoteBlock(row, currency)}</div>
                    <div className="feed-card-body">
                      <span
                        className={`side-pill ${
                          row.sentiment === 'bullish' ? 'buy' : row.sentiment === 'bearish' ? 'sell' : ''
                        }`}
                      >
                        {sentimentLabel(row.sentiment)}
                      </span>
                      <span className="muted">
                        {aggressivenessLabel(row.aggressiveness)}
                        {row.reason ? ` · ${row.reason}` : ''}
                      </span>
                    </div>
                  </li>
                ))}
              </ul>
              <table className="desktop-table uoa-table">
                <thead>
                  <tr>
                    <th>Contract</th>
                    <th>Type</th>
                    <th title={fieldHelp.vol_oi || ''}>Volume / OI</th>
                    <th title={fieldHelp.vol_oi || ''}>Vol/OI</th>
                    <th title={fieldHelp.premium || ''}>Notional premium</th>
                    <th>Quote / IV</th>
                    <th title={fieldHelp.score || ''}>Score</th>
                    <th title={fieldHelp.sentiment || ''}>Sentiment</th>
                    <th title={fieldHelp.aggressiveness || ''}>Flow</th>
                    <th>Universe</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((row) => (
                    <tr
                      key={`${row.id}-${row.contract_symbol}`}
                      className={
                        focusTicker && row.underlying === focusTicker ? 'row-focus' : undefined
                      }
                    >
                      <td>
                        <strong>{formatOptionContract(row, { currency })}</strong>
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
                        {formatNumber(row.volume)} / {formatNumber(row.open_interest)}
                      </td>
                      <td className="mono">
                        <strong>{formatNumber(row.vol_oi)}×</strong>
                      </td>
                      <td className="mono">{formatMoney(row.premium, currency)}</td>
                      <td>{quoteBlock(row, currency)}</td>
                      <td className="mono">
                        <strong>{formatNumber(row.score)}</strong>
                      </td>
                      <td>
                        <span
                          className={`side-pill ${
                            row.sentiment === 'bullish' ? 'buy' : row.sentiment === 'bearish' ? 'sell' : ''
                          }`}
                        >
                          {sentimentLabel(row.sentiment)}
                        </span>
                      </td>
                      <td>
                        <div>{aggressivenessLabel(row.aggressiveness)}</div>
                        {row.reason ? (
                          <div className="muted" style={{ fontSize: '0.78rem', marginTop: '0.25rem' }}>
                            {row.reason}
                          </div>
                        ) : null}
                      </td>
                      <td>{universeLabel(row.universe)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="pager">
              <span className="muted">
                {formatNumber(data.total)} matches · page {page} / {pageCount}
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
