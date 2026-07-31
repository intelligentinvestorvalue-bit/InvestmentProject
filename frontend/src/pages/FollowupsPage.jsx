import { useEffect, useState } from 'react'
import { fetchDeepDiveFollowups } from '../services/api'
import { formatDate, formatMoney } from '../utils/format'

export default function FollowupsPage({ market }) {
  const [data, setData] = useState({ items: [], total: 0, once_per_ticker: true })
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    let cancelled = false
    async function load() {
      if (market !== 'US') {
        setData({ items: [], total: 0, once_per_ticker: true })
        return
      }
      setLoading(true)
      setError('')
      try {
        const next = await fetchDeepDiveFollowups({ market: 'US', limit: 100 })
        if (!cancelled) setData(next)
      } catch (err) {
        if (!cancelled) {
          setError(err.message || 'Failed to load follow-ups')
          setData({ items: [], total: 0, once_per_ticker: true })
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => {
      cancelled = true
    }
  }, [market])

  return (
    <div>
      <div className="hero-strip">
        <h1>Deep-dive follow-ups</h1>
        <p>
          Officer buys ≥ $100k on tickers already sent to Equity Research. These are logged here for
          awareness — they are not re-queued for another deep dive.
        </p>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>Same-ticker alerts</h2>
            <p>
              {market === 'US'
                ? data.once_per_ticker
                  ? 'Once-per-ticker is on: first qualifying buy queues a deep dive; later buys appear below.'
                  : 'Timed cooldown mode is on; follow-ups still record while a ticker is blocked from re-queue.'
                : 'Follow-ups are US Form 4 only — switch market to US.'}
            </p>
          </div>
          <div className="stats">
            <div className="stat">
              <strong className="mono">{data.total || 0}</strong>
              <span>Follow-ups</span>
            </div>
          </div>
        </div>

        {error ? <div className="error">{error}</div> : null}

        <div className="table-wrap">
          {loading ? (
            <div className="empty muted">Loading…</div>
          ) : market !== 'US' ? (
            <div className="empty muted">Switch to US to see deep-dive follow-ups.</div>
          ) : data.items?.length ? (
            <table>
              <thead>
                <tr>
                  <th>Ticker</th>
                  <th>Company</th>
                  <th>Insider</th>
                  <th>Title</th>
                  <th>Value</th>
                  <th>Seen</th>
                  <th>Filing</th>
                </tr>
              </thead>
              <tbody>
                {data.items.map((row) => (
                  <tr key={row.id}>
                    <td className="mono">{row.ticker}</td>
                    <td>{row.company_name || '—'}</td>
                    <td>{row.insider_name || '—'}</td>
                    <td>{row.officer_title || '—'}</td>
                    <td className="mono">{formatMoney(row.total_value)}</td>
                    <td className="mono">{formatDate((row.created_at || '').slice(0, 10))}</td>
                    <td>
                      {row.source_url ? (
                        <a href={row.source_url} target="_blank" rel="noreferrer">
                          Form 4
                        </a>
                      ) : (
                        '—'
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="empty muted">
              No follow-ups yet. After a ticker is deep-dived once, later ≥$100k officer buys show up here.
            </div>
          )}
        </div>
      </section>
    </div>
  )
}
