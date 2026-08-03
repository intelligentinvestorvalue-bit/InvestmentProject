import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  fetchExploreCompanies,
  fetchIndustries,
  fetchSectors,
  syncExplore,
} from '../services/api'
import { formatNumber } from '../utils/format'

export default function ExplorePage({ market }) {
  const [sectors, setSectors] = useState([])
  const [industries, setIndustries] = useState([])
  const [companies, setCompanies] = useState([])
  const [sector, setSector] = useState('')
  const [industry, setIndustry] = useState('')
  const [q, setQ] = useState('')
  const [loading, setLoading] = useState(false)
  const [syncing, setSyncing] = useState(false)
  const [error, setError] = useState('')
  const [meta, setMeta] = useState({ total_companies: 0 })

  async function loadSectors() {
    const data = await fetchSectors(market)
    setSectors(data.sectors || [])
    setMeta({ total_companies: data.total_companies || 0 })
  }

  async function loadIndustries(nextSector) {
    const data = await fetchIndustries(market, nextSector || undefined)
    setIndustries(data.industries || [])
  }

  async function loadCompanies(next = {}) {
    const data = await fetchExploreCompanies({
      market,
      sector: next.sector ?? sector,
      industry: next.industry ?? industry,
      q: next.q ?? q,
      page_size: 100,
    })
    setCompanies(data.items || [])
  }

  useEffect(() => {
    setSector('')
    setIndustry('')
    setQ('')
    setError('')
    let cancelled = false
    async function boot() {
      setLoading(true)
      try {
        await loadSectors()
        if (!cancelled) {
          await loadIndustries('')
          await loadCompanies({ sector: '', industry: '', q: '' })
        }
      } catch (err) {
        if (!cancelled) setError(err.message || 'Failed to load explore data')
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

  async function handleSync() {
    setSyncing(true)
    setError('')
    try {
      await syncExplore(market, { limit: 30 })
      await loadSectors()
      await loadIndustries(sector)
      await loadCompanies()
    } catch (err) {
      setError(err.message || 'Explore sync failed')
    } finally {
      setSyncing(false)
    }
  }

  async function onSelectSector(nextSector) {
    setSector(nextSector)
    setIndustry('')
    setLoading(true)
    try {
      await loadIndustries(nextSector)
      await loadCompanies({ sector: nextSector, industry: '' })
    } catch (err) {
      setError(err.message || 'Failed to filter sector')
    } finally {
      setLoading(false)
    }
  }

  async function onSelectIndustry(nextIndustry) {
    setIndustry(nextIndustry)
    setLoading(true)
    try {
      await loadCompanies({ industry: nextIndustry })
    } catch (err) {
      setError(err.message || 'Failed to filter industry')
    } finally {
      setLoading(false)
    }
  }

  async function onSearch(event) {
    event.preventDefault()
    setLoading(true)
    try {
      await loadCompanies({ q })
    } catch (err) {
      setError(err.message || 'Search failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="hero-strip">
        <h1>Sector explore</h1>
        <p>
          Browse companies by sector/industry using metadata enriched from free{' '}
          {market === 'US' ? 'SEC submissions (SIC)' : 'NSE quote industry fields'}. Sync after
          loading insider data for best coverage.
        </p>
      </div>

      <section className="panel">
        <div className="panel-header">
          <div>
            <h2>{market === 'US' ? 'US' : 'India'} sectors</h2>
            <p>{formatNumber(meta.total_companies)} companies indexed</p>
          </div>
          <div className="actions">
            <button className="btn btn-primary" type="button" onClick={handleSync} disabled={syncing}>
              {syncing ? 'Enriching…' : 'Enrich sector metadata'}
            </button>
          </div>
        </div>

        <form className="filters" onSubmit={onSearch}>
          <div className="field">
            <label htmlFor="explore-q">Search companies</label>
            <input
              id="explore-q"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Ticker or name"
            />
          </div>
          <div className="actions">
            <button className="btn btn-primary" type="submit" disabled={loading}>
              Search
            </button>
            <button
              className="btn btn-ghost"
              type="button"
              onClick={() => onSelectSector('')}
              disabled={loading}
            >
              Clear filters
            </button>
          </div>
        </form>

        {error ? <div className="error">{error}</div> : null}

        <div className="explore-grid">
          <div className="explore-col">
            <h3>Sectors</h3>
            <ul className="chip-list">
              {sectors.length ? (
                sectors.map((item) => (
                  <li key={item.sector}>
                    <button
                      type="button"
                      className={sector === item.sector ? 'active' : ''}
                      onClick={() => onSelectSector(item.sector)}
                    >
                      {item.sector}
                      <span>{item.company_count}</span>
                    </button>
                  </li>
                ))
              ) : (
                <li className="muted">No sectors yet — sync insider data, then enrich.</li>
              )}
            </ul>
          </div>

          <div className="explore-col">
            <h3>Industries {sector ? `· ${sector}` : ''}</h3>
            <ul className="chip-list">
              {industries.length ? (
                industries.map((item) => (
                  <li key={item.industry}>
                    <button
                      type="button"
                      className={industry === item.industry ? 'active' : ''}
                      onClick={() => onSelectIndustry(item.industry)}
                    >
                      {item.industry}
                      <span>{item.company_count}</span>
                    </button>
                  </li>
                ))
              ) : (
                <li className="muted">Pick a sector or enrich metadata first.</li>
              )}
            </ul>
          </div>

          <div className="explore-col wide">
            <h3>Companies</h3>
            <div className="table-wrap">
              {loading ? (
                <div className="empty muted">Loading…</div>
              ) : companies.length ? (
                <table>
                  <thead>
                    <tr>
                      <th>Ticker</th>
                      <th>Name</th>
                      <th>Sector</th>
                      <th>Industry</th>
                    </tr>
                  </thead>
                  <tbody>
                    {companies.map((row) => (
                      <tr key={`${row.market}-${row.ticker}`}>
                        <td className="mono">
                          <Link
                            to={`/research?ticker=${encodeURIComponent(row.ticker)}`}
                            onClick={() => sessionStorage.setItem('fd_ticker', row.ticker)}
                            className="ticker-link"
                          >
                            {row.ticker}
                          </Link>
                        </td>
                        <td>{row.name || '—'}</td>
                        <td>{row.sector || '—'}</td>
                        <td>{row.industry || '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="empty muted">No companies match these filters yet.</div>
              )}
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
