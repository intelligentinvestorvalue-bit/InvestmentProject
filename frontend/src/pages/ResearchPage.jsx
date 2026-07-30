import { useEffect, useMemo, useState } from 'react'
import { fetchFinancials } from '../services/api'
import { currencyForMarket, formatCompact, formatNumber } from '../utils/format'

const STATEMENT_TABS = [
  { id: 'income_statement', label: 'Income' },
  { id: 'balance_sheet', label: 'Balance sheet' },
  { id: 'cash_flow', label: 'Cash flow' },
  { id: 'summary', label: 'Summary' },
]

export default function ResearchPage({ market }) {
  const currency = currencyForMarket(market)
  const [ticker, setTicker] = useState(() => sessionStorage.getItem('fd_ticker') || (market === 'US' ? 'AAPL' : 'RELIANCE'))
  const [tab, setTab] = useState('income_statement')
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const saved = sessionStorage.getItem('fd_ticker')
    setTicker(saved || (market === 'US' ? 'AAPL' : 'RELIANCE'))
    setTab('income_statement')
    setData(null)
    setError('')
  }, [market])

  const rows = data?.statements?.[tab] || []
  const metricKeys = useMemo(() => {
    const keys = new Set()
    rows.forEach((row) => {
      Object.keys(row).forEach((key) => {
        if (key !== 'year' && key !== 'filed_date') keys.add(key)
      })
    })
    return Array.from(keys)
  }, [rows])

  async function load(refresh = false) {
    const symbol = ticker.trim().toUpperCase()
    if (!symbol) return
    setLoading(true)
    setError('')
    try {
      const next = await fetchFinancials(symbol, market, {
        years: market === 'US' ? 10 : 5,
        refresh: refresh ? '1' : '0',
      })
      setData(next)
      sessionStorage.setItem('fd_ticker', symbol)
      if (!(next.statements?.[tab] || []).length) {
        const first = ['income_statement', 'balance_sheet', 'cash_flow', 'summary'].find(
          (key) => (next.statements?.[key] || []).length,
        )
        if (first) setTab(first)
      }
    } catch (err) {
      setData(null)
      setError(err.message || 'Failed to load financials')
    } finally {
      setLoading(false)
    }
  }

  function onSubmit(event) {
    event.preventDefault()
    load(false)
  }

  return (
    <div>
      <div className="hero-strip">
        <h1>Company research</h1>
        <p>
          {market === 'US'
            ? 'Multi-year financial statements from free SEC XBRL company facts.'
            : 'Multi-year financial statements from free Yahoo Finance (.NS / .BO), with NSE/BSE insider context.'}
        </p>
      </div>

      <section className="panel">
        <form className="filters" onSubmit={onSubmit}>
          <div className="field">
            <label htmlFor="research-ticker">Ticker</label>
            <input
              id="research-ticker"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              placeholder={market === 'US' ? 'AAPL' : 'INFY'}
            />
          </div>
          <div className="actions">
            <button className="btn btn-primary" type="submit" disabled={loading}>
              {loading ? 'Loading…' : 'Load financials'}
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              disabled={loading || !ticker.trim()}
              onClick={() => load(true)}
            >
              Refresh
            </button>
          </div>
        </form>

        {error ? <div className="error">{error}</div> : null}

        {data ? (
          <>
            <div className="panel-header">
              <div>
                <h2>
                  {data.company_name || data.ticker}{' '}
                  <span className="muted mono">({data.ticker})</span>
                </h2>
                <p>
                  {data.cached ? 'Served from cache' : 'Fresh fetch'}
                  {data.note ? ` · ${data.note}` : ''}
                  {data.sector ? ` · ${data.sector}` : ''}
                  {data.industry ? ` / ${data.industry}` : ''}
                </p>
              </div>
            </div>

            <div className="tab-row">
              {STATEMENT_TABS.filter((item) => item.id !== 'summary' || (data.statements?.summary || []).length > 0).map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className={tab === item.id ? 'active' : ''}
                  onClick={() => setTab(item.id)}
                >
                  {item.label}
                </button>
              ))}
            </div>

            <div className="table-wrap table-wrap-sticky">
              {rows.length ? (
                <table className="research-table">
                  <thead>
                    <tr>
                      <th>Metric</th>
                      {rows.map((row) => (
                        <th key={row.year} className="mono">
                          {row.year}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {metricKeys.map((metric) => (
                      <tr key={metric}>
                        <td>{metric}</td>
                        {rows.map((row) => (
                          <td key={`${metric}-${row.year}`} className="mono">
                            {typeof row[metric] === 'number'
                              ? Math.abs(row[metric]) >= 1000
                                ? formatCompact(row[metric], currency)
                                : formatNumber(row[metric], 2)
                              : '—'}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty muted">No rows for this statement yet.</div>
              )}
            </div>
          </>
        ) : (
          !loading && !error && (
            <div className="empty muted">Enter a ticker and load financials to begin.</div>
          )
        )}
      </section>
    </div>
  )
}
