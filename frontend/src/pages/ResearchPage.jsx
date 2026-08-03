import { useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { fetchFinancials, fetchMarketOverview } from '../services/api'
import { currencyForMarket, formatCompact, formatMoney, formatNumber } from '../utils/format'

const STATEMENT_TABS = [
  { id: 'income_statement', label: 'Income' },
  { id: 'balance_sheet', label: 'Balance sheet' },
  { id: 'cash_flow', label: 'Cash flow' },
  { id: 'summary', label: 'Summary' },
]

/** Fallback when API has no metric_order (keeps P&L top-down). */
const FALLBACK_METRIC_ORDER = {
  income_statement: [
    'Revenue',
    'CostOfRevenue',
    'GrossProfit',
    'ResearchAndDevelopment',
    'SellingGeneralAndAdministrative',
    'OperatingIncome',
    'InterestExpense',
    'IncomeBeforeTax',
    'IncomeTaxExpense',
    'NetIncome',
    'EBITDA',
    'EPSBasic',
    'EPSDiluted',
    'SharesOutstandingBasic',
    'SharesOutstandingDiluted',
  ],
  balance_sheet: [
    'Assets',
    'CurrentAssets',
    'Cash',
    'ShortTermInvestments',
    'AccountsReceivable',
    'Inventory',
    'Liabilities',
    'CurrentLiabilities',
    'AccountsPayable',
    'LongTermDebt',
    'StockholdersEquity',
    'RetainedEarnings',
  ],
  cash_flow: [
    'OperatingCashFlow',
    'InvestingCashFlow',
    'FinancingCashFlow',
    'Capex',
    'DividendsPaid',
    'ShareRepurchases',
    'FreeCashFlowProxy',
  ],
}

const YAHOO_EXCHANGE_TO_TV = {
  NMS: 'NASDAQ',
  NGM: 'NASDAQ',
  NAS: 'NASDAQ',
  NCM: 'NASDAQ',
  NYQ: 'NYSE',
  NYSE: 'NYSE',
  PCX: 'AMEX',
  ASE: 'AMEX',
  AMEX: 'AMEX',
  ARCA: 'AMEX',
  BATS: 'BATS',
  OTC: 'OTC',
}

function tradingViewSymbol(ticker, market, exchange) {
  const sym = (ticker || '').toUpperCase().replace(/\.(NS|BO)$/i, '')
  if (!sym) return ''
  if (market === 'IN') {
    const isBse = String(exchange || '').toUpperCase().includes('BSE')
    return `${isBse ? 'BSE' : 'NSE'}:${sym}`
  }
  const mapped = YAHOO_EXCHANGE_TO_TV[String(exchange || '').toUpperCase()]
  return mapped ? `${mapped}:${sym}` : sym
}

function orderedMetricKeys(tab, rows, metricOrderFromApi) {
  const present = new Set()
  rows.forEach((row) => {
    Object.keys(row).forEach((key) => {
      if (key !== 'year' && key !== 'filed_date') present.add(key)
    })
  })
  const preferred = metricOrderFromApi?.[tab] || FALLBACK_METRIC_ORDER[tab] || []
  const ordered = preferred.filter((key) => present.has(key))
  const rest = [...present].filter((key) => !ordered.includes(key)).sort()
  return [...ordered, ...rest]
}

let tvScriptPromise = null

function loadTradingViewScript() {
  if (window.TradingView) return Promise.resolve()
  if (tvScriptPromise) return tvScriptPromise
  tvScriptPromise = new Promise((resolve, reject) => {
    const existing = document.querySelector('script[data-tradingview]')
    if (existing) {
      existing.addEventListener('load', () => resolve())
      existing.addEventListener('error', () => reject(new Error('TradingView failed to load')))
      if (window.TradingView) resolve()
      return
    }
    const script = document.createElement('script')
    script.src = 'https://s3.tradingview.com/tv.js'
    script.async = true
    script.dataset.tradingview = '1'
    script.onload = () => resolve()
    script.onerror = () => reject(new Error('TradingView failed to load'))
    document.body.appendChild(script)
  })
  return tvScriptPromise
}

function TradingViewChart({ symbol }) {
  const hostRef = useRef(null)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!symbol || !hostRef.current) return undefined

    let cancelled = false
    const containerId = `tv_${symbol.replace(/[^a-zA-Z0-9]/g, '_')}_${Date.now()}`
    hostRef.current.innerHTML = ''
    const mount = document.createElement('div')
    mount.id = containerId
    mount.style.height = '440px'
    mount.style.width = '100%'
    hostRef.current.appendChild(mount)

    loadTradingViewScript()
      .then(() => {
        if (cancelled || !window.TradingView) return
        // TradingView attaches into container_id; keep a fresh node each symbol change.
        // eslint-disable-next-line no-new
        new window.TradingView.widget({
          autosize: true,
          symbol,
          interval: 'D',
          timezone: 'Etc/UTC',
          theme: 'light',
          style: '1',
          locale: 'en',
          toolbar_bg: '#f7fbf9',
          enable_publishing: false,
          allow_symbol_change: false,
          hide_side_toolbar: false,
          withdateranges: true,
          save_image: false,
          container_id: containerId,
        })
      })
      .catch((err) => {
        if (!cancelled) setError(err.message || 'Chart unavailable')
      })

    return () => {
      cancelled = true
      if (hostRef.current) hostRef.current.innerHTML = ''
    }
  }, [symbol])

  if (error) {
    return <div className="empty muted">{error}</div>
  }
  if (!symbol) {
    return <div className="empty muted">No symbol for chart.</div>
  }

  return <div className="tv-chart-wrap" ref={hostRef} />
}

export default function ResearchPage({ market }) {
  const currencyHint = currencyForMarket(market)
  const [searchParams, setSearchParams] = useSearchParams()
  const initialTicker =
    (searchParams.get('ticker') || sessionStorage.getItem('fd_ticker') || '').toUpperCase() ||
    (market === 'US' ? 'AAPL' : 'RELIANCE')

  const [ticker, setTicker] = useState(initialTicker)
  const [tab, setTab] = useState('income_statement')
  const [data, setData] = useState(null)
  const [marketData, setMarketData] = useState(null)
  const [loading, setLoading] = useState(false)
  const [marketLoading, setMarketLoading] = useState(false)
  const [error, setError] = useState('')
  const [marketError, setMarketError] = useState('')

  const currency = marketData?.currency === 'INR' ? 'INR' : currencyHint

  const rows = data?.statements?.[tab] || []
  const metricKeys = useMemo(
    () => orderedMetricKeys(tab, rows, data?.metric_order),
    [tab, rows, data?.metric_order],
  )

  const chartSymbol = useMemo(
    () =>
      tradingViewSymbol(
        marketData?.ticker || ticker,
        market,
        marketData?.exchange || data?.exchange,
      ),
    [marketData?.ticker, marketData?.exchange, data?.exchange, ticker, market],
  )

  async function loadMarket(symbol, { refresh = false } = {}) {
    setMarketLoading(true)
    setMarketError('')
    try {
      const next = await fetchMarketOverview(symbol, market, {
        range: '1y',
        ...(refresh ? { refresh: '1' } : {}),
      })
      setMarketData(next)
    } catch (err) {
      setMarketData(null)
      setMarketError(err.message || 'Failed to load market overview')
    } finally {
      setMarketLoading(false)
    }
  }

  async function load(refresh = false, symbolOverride = null) {
    const symbol = (symbolOverride || ticker).trim().toUpperCase()
    if (!symbol) return
    setTicker(symbol)
    setLoading(true)
    setError('')
    try {
      const [financials] = await Promise.all([
        fetchFinancials(symbol, market, {
          years: market === 'US' ? 10 : 5,
          refresh: refresh ? '1' : '0',
        }),
        loadMarket(symbol, { refresh }),
      ])
      setData(financials)
      sessionStorage.setItem('fd_ticker', symbol)
      setSearchParams({ ticker: symbol }, { replace: true })
      if (!(financials.statements?.[tab] || []).length) {
        const first = ['income_statement', 'balance_sheet', 'cash_flow', 'summary'].find(
          (key) => (financials.statements?.[key] || []).length,
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

  useEffect(() => {
    const fromUrl = (searchParams.get('ticker') || '').toUpperCase()
    const next = fromUrl || sessionStorage.getItem('fd_ticker') || (market === 'US' ? 'AAPL' : 'RELIANCE')
    setTicker(next)
    setTab('income_statement')
    setData(null)
    setMarketData(null)
    setError('')
    setMarketError('')
    load(false, next)
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload when market or URL ticker changes
  }, [market, searchParams.get('ticker')])

  function onSubmit(event) {
    event.preventDefault()
    load(false)
  }

  const price = marketData?.price || {}
  const changeClass =
    price.change_pct == null ? '' : price.change_pct >= 0 ? 'chg-up' : 'chg-down'

  const statementsNote =
    data?.cache_note ||
    (data?.cached
      ? 'Statements from local DB cache. Refresh to re-pull source data.'
      : data
        ? 'Statements freshly pulled and cached locally.'
        : '')

  return (
    <div>
      <div className="hero-strip">
        <h1>Company research</h1>
        <p>
          Overview metrics from Yahoo (15-minute cache), TradingView price chart, plus{' '}
          {market === 'US'
            ? 'multi-year financials from free SEC XBRL (DB-cached until Refresh).'
            : 'multi-year financials from free Yahoo Finance (.NS / .BO, DB-cached until Refresh).'}
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
            <button className="btn btn-primary" type="submit" disabled={loading || marketLoading}>
              {loading || marketLoading ? 'Loading…' : 'Load research'}
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              disabled={loading || marketLoading || !ticker.trim()}
              onClick={() => load(true)}
            >
              Refresh
            </button>
          </div>
        </form>

        {error ? <div className="error">{error}</div> : null}
        {marketError ? <div className="error">{marketError}</div> : null}

        {marketData || data ? (
          <>
            <div className="panel-header">
              <div>
                <h2>
                  {marketData?.company_name || data?.company_name || ticker}{' '}
                  <span className="muted mono">({marketData?.ticker || data?.ticker || ticker})</span>
                </h2>
                <p>
                  {[marketData?.exchange, marketData?.sector || data?.sector, marketData?.industry || data?.industry]
                    .filter(Boolean)
                    .join(' · ') || 'Company research'}
                  {statementsNote ? ` · ${statementsNote}` : ''}
                </p>
              </div>
              <div className="stats">
                <div className="stat">
                  <strong className="mono">{formatMoney(price.last, currency)}</strong>
                  <span className={changeClass}>
                    {price.change_pct == null
                      ? 'last'
                      : `${price.change_pct >= 0 ? '+' : ''}${formatNumber(price.change_pct, 2)}%`}
                  </span>
                </div>
                <div className="stat">
                  <strong className="mono">{formatCompact(price.market_cap, currency)}</strong>
                  <span>Market cap</span>
                </div>
                <div className="stat">
                  <strong className="mono">
                    {price.pe_trailing != null ? formatNumber(price.pe_trailing, 1) : '—'}
                  </strong>
                  <span>Trailing P/E</span>
                </div>
              </div>
            </div>

            <div className="research-overview">
              <div className="research-overview-metrics">
                <div>
                  <span className="muted">Open</span>
                  <strong className="mono">{formatMoney(price.open, currency)}</strong>
                </div>
                <div>
                  <span className="muted">Day range</span>
                  <strong className="mono">
                    {formatMoney(price.day_low, currency)} – {formatMoney(price.day_high, currency)}
                  </strong>
                </div>
                <div>
                  <span className="muted">52w range</span>
                  <strong className="mono">
                    {formatMoney(price.fifty_two_week_low, currency)} –{' '}
                    {formatMoney(price.fifty_two_week_high, currency)}
                  </strong>
                </div>
                <div>
                  <span className="muted">Volume</span>
                  <strong className="mono">{formatNumber(price.volume)}</strong>
                </div>
                <div>
                  <span className="muted">EPS (ttm)</span>
                  <strong className="mono">
                    {price.eps_trailing != null ? formatNumber(price.eps_trailing, 2) : '—'}
                  </strong>
                </div>
                <div>
                  <span className="muted">Beta</span>
                  <strong className="mono">{price.beta != null ? formatNumber(price.beta, 2) : '—'}</strong>
                </div>
              </div>

              <div className="research-chart-panel">
                {marketLoading && !marketData ? (
                  <div className="empty muted">Loading chart…</div>
                ) : (
                  <TradingViewChart symbol={chartSymbol} />
                )}
                <p className="muted chart-source">
                  Chart: TradingView · Overview: {marketData?.source || 'Yahoo (delayed)'}
                  {marketData?.cached ? ' · overview cached 15m' : ''}
                </p>
              </div>
            </div>

            {marketData?.summary ? <p className="research-summary">{marketData.summary}</p> : null}

            <div className="tab-row">
              {STATEMENT_TABS.filter(
                (item) => item.id !== 'summary' || (data?.statements?.summary || []).length > 0,
              ).map((item) => (
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
              {loading && !rows.length ? (
                <div className="empty muted">Loading financials…</div>
              ) : rows.length ? (
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
                <div className="empty muted">No statement rows yet for this ticker.</div>
              )}
            </div>
          </>
        ) : (
          !loading &&
          !marketLoading &&
          !error &&
          !marketError && <div className="empty muted">Enter a ticker and load research to begin.</div>
        )}
      </section>
    </div>
  )
}
