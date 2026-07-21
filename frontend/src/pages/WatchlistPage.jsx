import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  addWatchlistItem,
  createWatchlist,
  deleteWatchlist,
  fetchWatchlist,
  fetchWatchlists,
  removeWatchlistItem,
} from '../services/api'
import { formatDate, formatNumber } from '../utils/format'

export default function WatchlistPage({ market }) {
  const [lists, setLists] = useState([])
  const [activeId, setActiveId] = useState(null)
  const [detail, setDetail] = useState(null)
  const [name, setName] = useState('')
  const [ticker, setTicker] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function loadLists() {
    const data = await fetchWatchlists(market)
    setLists(data.items || [])
    if (!activeId && data.items?.length) {
      setActiveId(data.items[0].id)
    } else if (activeId && !(data.items || []).some((w) => w.id === activeId)) {
      setActiveId(data.items?.[0]?.id || null)
      setDetail(null)
    }
  }

  async function loadDetail(id) {
    if (!id) {
      setDetail(null)
      return
    }
    const data = await fetchWatchlist(id)
    setDetail(data)
  }

  useEffect(() => {
    setActiveId(null)
    setDetail(null)
    setError('')
    let cancelled = false
    async function boot() {
      setLoading(true)
      try {
        await loadLists()
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load watchlists')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    boot()
    return () => {
      cancelled = true
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market])

  useEffect(() => {
    if (!activeId) return
    let cancelled = false
    async function run() {
      try {
        await loadDetail(activeId)
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load watchlist')
      }
    }
    run()
    return () => {
      cancelled = true
    }
  }, [activeId])

  async function onCreate(event) {
    event.preventDefault()
    if (!name.trim()) return
    setError('')
    try {
      const wl = await createWatchlist({ name: name.trim(), market })
      setName('')
      await loadLists()
      setActiveId(wl.id)
    } catch (err) {
      setError(err.message || 'Create failed')
    }
  }

  async function onAddTicker(event) {
    event.preventDefault()
    if (!activeId || !ticker.trim()) return
    setError('')
    try {
      await addWatchlistItem(activeId, { ticker: ticker.trim().toUpperCase() })
      setTicker('')
      await loadLists()
      await loadDetail(activeId)
    } catch (err) {
      setError(err.message || 'Add ticker failed')
    }
  }

  async function onDeleteList() {
    if (!activeId) return
    if (!window.confirm('Delete this watchlist?')) return
    await deleteWatchlist(activeId)
    setActiveId(null)
    await loadLists()
  }

  async function onRemoveItem(itemId) {
    await removeWatchlistItem(activeId, itemId)
    await loadLists()
    await loadDetail(activeId)
  }

  return (
    <div>
      <div className="hero-strip">
        <h1>Watchlists</h1>
        <p>
          Save tickers for {market === 'US' ? 'US' : 'India'} and jump back into research or insider
          activity. Scheduled syncs keep the underlying feeds fresh.
        </p>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>{market} saved screens</h2>
            <p>{formatNumber(lists.length)} watchlists</p>
          </div>
        </div>

        <form className="filters" onSubmit={onCreate}>
          <div className="field">
            <label htmlFor="wl-name">New watchlist</label>
            <input
              id="wl-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={market === 'US' ? 'Mega-cap watch' : 'Nifty names'}
            />
          </div>
          <div className="actions">
            <button className="btn btn-primary" type="submit">
              Create
            </button>
          </div>
        </form>

        {error ? <div className="error">{error}</div> : null}

        <div className="explore-grid">
          <div className="explore-col">
            <h3>Lists</h3>
            <ul className="chip-list">
              {lists.length ? (
                lists.map((wl) => (
                  <li key={wl.id}>
                    <button
                      type="button"
                      className={activeId === wl.id ? 'active' : ''}
                      onClick={() => setActiveId(wl.id)}
                    >
                      {wl.name}
                      <span>{wl.item_count}</span>
                    </button>
                  </li>
                ))
              ) : (
                <li className="muted">{loading ? 'Loading…' : 'No watchlists yet.'}</li>
              )}
            </ul>
          </div>

          <div className="explore-col wide">
            {detail ? (
              <>
                <div className="panel-header" style={{ border: 0, padding: '0 0 0.75rem' }}>
                  <div>
                    <h2>{detail.name}</h2>
                    <p>{formatNumber(detail.items?.length)} tickers</p>
                  </div>
                  <div className="actions">
                    <button className="btn btn-ghost" type="button" onClick={onDeleteList}>
                      Delete list
                    </button>
                  </div>
                </div>

                <form className="filters" onSubmit={onAddTicker} style={{ border: 0, padding: '0 0 1rem' }}>
                  <div className="field">
                    <label htmlFor="wl-ticker">Add ticker</label>
                    <input
                      id="wl-ticker"
                      value={ticker}
                      onChange={(e) => setTicker(e.target.value.toUpperCase())}
                      placeholder={market === 'US' ? 'AAPL' : 'INFY'}
                    />
                  </div>
                  <div className="actions">
                    <button className="btn btn-primary" type="submit">
                      Add
                    </button>
                  </div>
                </form>

                <div className="table-wrap">
                  {detail.items?.length ? (
                    <table>
                      <thead>
                        <tr>
                          <th>Ticker</th>
                          <th>Name</th>
                          <th>Buys</th>
                          <th>Sells</th>
                          <th>Last tx</th>
                          <th />
                        </tr>
                      </thead>
                      <tbody>
                        {detail.items.map((item) => (
                          <tr key={item.id}>
                            <td className="mono">
                              <Link
                                to="/research"
                                onClick={() => sessionStorage.setItem('fd_ticker', item.ticker)}
                              >
                                {item.ticker}
                              </Link>
                            </td>
                            <td>{item.company_name || '—'}</td>
                            <td className="mono">{formatNumber(item.buy_count)}</td>
                            <td className="mono">{formatNumber(item.sell_count)}</td>
                            <td className="mono">{formatDate(item.last_tx_date)}</td>
                            <td>
                              <button
                                className="btn btn-ghost"
                                type="button"
                                onClick={() => onRemoveItem(item.id)}
                              >
                                Remove
                              </button>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  ) : (
                    <div className="empty muted">Add tickers to start monitoring this screen.</div>
                  )}
                </div>
              </>
            ) : (
              <div className="empty muted">Select or create a watchlist.</div>
            )}
          </div>
        </div>
      </section>
    </div>
  )
}
