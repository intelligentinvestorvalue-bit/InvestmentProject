import { NavLink } from 'react-router-dom'
import NotificationBell from './NotificationBell'

export default function TopBar({ market, onMarketChange }) {
  return (
    <div className="chrome">
      <header className="topbar">
        <div className="brand">
          <div className="brand-mark" aria-hidden>
            Fd
          </div>
          <div className="brand-copy">
            <strong>FilingDesk</strong>
            <span className="brand-tagline">Cross-market insider research</span>
          </div>
        </div>

        <div className="topbar-actions">
          <NotificationBell />
          <div className="market-switch" role="tablist" aria-label="Market">
            <button
              type="button"
              role="tab"
              className={market === 'US' ? 'active' : ''}
              aria-selected={market === 'US'}
              onClick={() => onMarketChange('US')}
            >
              US
            </button>
            <button
              type="button"
              role="tab"
              className={market === 'IN' ? 'active' : ''}
              aria-selected={market === 'IN'}
              onClick={() => onMarketChange('IN')}
            >
              India
            </button>
          </div>
        </div>
      </header>

      <nav className="nav-row" aria-label="Primary">
        <NavLink to="/" end className={({ isActive }) => (isActive ? 'active' : undefined)}>
          Insider
        </NavLink>
        <NavLink to="/watchlists" className={({ isActive }) => (isActive ? 'active' : undefined)}>
          Watchlists
        </NavLink>
        <NavLink to="/options" className={({ isActive }) => (isActive ? 'active' : undefined)}>
          Options
        </NavLink>
        <NavLink to="/research" className={({ isActive }) => (isActive ? 'active' : undefined)}>
          Research
        </NavLink>
        <NavLink to="/explore" className={({ isActive }) => (isActive ? 'active' : undefined)}>
          Explore
        </NavLink>
      </nav>
    </div>
  )
}
