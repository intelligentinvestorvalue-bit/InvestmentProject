import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { fetchNotifications, markAllNotificationsRead, markNotificationRead } from '../services/api'
import { formatDate, formatMoney, formatNumber } from '../utils/format'
import {
  aggressivenessLabel,
  formatIv,
  formatOptionContract,
  parseNotificationPayload,
  sentimentLabel,
} from '../utils/uoaLabels'

function kindLabel(kind) {
  if (kind === 'deep_dive_push') return 'deep dive'
  if (kind === 'deep_dive_pushed') return 'deep dive started'
  if (kind === 'deep_dive_cancelled') return 'deep dive deferred'
  if (kind === 'deep_dive_followup') return 'follow-up buy'
  if (kind === 'uoa') return 'unusual options'
  return kind || 'alert'
}

function routeForNote(note) {
  if (note.kind === 'uoa') {
    const params = new URLSearchParams()
    if (note.ticker) params.set('ticker', note.ticker)
    try {
      const payload = note.payload_json ? JSON.parse(note.payload_json) : null
      if (payload?.sentiment) params.set('sentiment', payload.sentiment)
      if (payload?.option_type) params.set('option_type', payload.option_type)
      if (payload?.score != null) {
        params.set('min_score', String(Math.max(0, Math.floor(Number(payload.score) - 5))))
      }
    } catch {
      /* ignore bad payload */
    }
    const qs = params.toString()
    return qs ? `/options?${qs}` : '/options'
  }
  if (note.kind === 'deep_dive_followup') return '/followups'
  if (String(note.kind || '').startsWith('deep_dive')) return '/'
  return null
}

function marketForNote(note) {
  try {
    const payload = note.payload_json ? JSON.parse(note.payload_json) : null
    if (payload?.market === 'IN' || payload?.market === 'US') return payload.market
  } catch {
    /* ignore */
  }
  return null
}

function UoaNotificationContent({ note }) {
  const payload = parseNotificationPayload(note)
  if (!payload) {
    return (
      <>
        <strong>{note.title}</strong>
        <span className="muted notify-body-text">{note.body}</span>
      </>
    )
  }

  const currency = payload.market === 'IN' ? 'INR' : 'USD'
  const contract = formatOptionContract(payload, { currency })
  const sentiment = sentimentLabel(payload.sentiment)
  const flow = aggressivenessLabel(payload.aggressiveness)
  const severityClass =
    note.severity === 'bullish' || payload.sentiment === 'bullish'
      ? 'buy'
      : note.severity === 'bearish' || payload.sentiment === 'bearish'
        ? 'sell'
        : ''

  return (
    <>
      <strong>
        <span className={`side-pill ${severityClass}`}>{sentiment}</span>{' '}
        {contract}
      </strong>
      <span className="muted notify-body-text">
        {flow}
        {payload.reason ? ` · ${payload.reason}` : ''}
      </span>
      <span className="notify-chips">
        <span className="notify-chip mono">
          score {payload.score != null ? formatNumber(payload.score, 1) : '—'}
        </span>
        <span className="notify-chip mono">
          Vol/OI {payload.vol_oi != null ? `${formatNumber(payload.vol_oi, 2)}×` : '—'}
        </span>
        <span className="notify-chip mono">
          premium {formatMoney(payload.premium, currency)}
        </span>
        {payload.volume != null ? (
          <span className="notify-chip mono">
            vol {formatNumber(payload.volume)} / oi {formatNumber(payload.open_interest)}
          </span>
        ) : null}
        {payload.last_price != null || payload.bid != null ? (
          <span className="notify-chip mono">
            last {formatMoney(payload.last_price, currency)} · {formatMoney(payload.bid, currency)}/
            {formatMoney(payload.ask, currency)}
          </span>
        ) : null}
        {payload.implied_volatility != null ? (
          <span className="notify-chip mono">IV {formatIv(payload.implied_volatility)}</span>
        ) : null}
      </span>
    </>
  )
}

export default function NotificationBell({ onMarketChange }) {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [items, setItems] = useState([])
  const [unread, setUnread] = useState(0)
  const [loading, setLoading] = useState(false)
  const panelRef = useRef(null)

  async function refresh() {
    setLoading(true)
    try {
      const data = await fetchNotifications({ page_size: 20 })
      setItems(data.items || [])
      setUnread(data.unread || 0)
    } catch {
      // Keep last known state on transient failures.
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    refresh()
    const id = setInterval(refresh, 45000)
    return () => clearInterval(id)
  }, [])

  useEffect(() => {
    function onDocClick(event) {
      if (!panelRef.current) return
      if (!panelRef.current.contains(event.target)) setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  async function onOpen() {
    setOpen((v) => !v)
    if (!open) await refresh()
  }

  async function onSelect(note) {
    try {
      await markNotificationRead(note.id)
    } catch {
      /* ignore */
    }
    setOpen(false)
    const nextMarket = marketForNote(note)
    if (nextMarket && typeof onMarketChange === 'function') {
      onMarketChange(nextMarket)
    }
    const path = routeForNote(note)
    if (path) navigate(path)
    else await refresh()
  }

  async function onReadAll() {
    try {
      await markAllNotificationsRead()
      await refresh()
    } catch {
      /* ignore */
    }
  }

  return (
    <div className="notify-wrap" ref={panelRef}>
      <button type="button" className="notify-bell" aria-label="Notifications" onClick={onOpen}>
        <span className="notify-bell-icon" aria-hidden />
        {unread > 0 ? <em className="notify-badge">{unread > 99 ? '99+' : unread}</em> : null}
      </button>
      {open ? (
        <div className="notify-panel" role="dialog" aria-label="In-app notifications">
          <div className="notify-panel-head">
            <strong>In-app alerts</strong>
            <button type="button" className="btn btn-ghost" onClick={onReadAll} disabled={!unread}>
              Mark all read
            </button>
          </div>
          {loading && items.length === 0 ? <p className="muted notify-empty">Loading…</p> : null}
          {!loading && items.length === 0 ? <p className="muted notify-empty">No notifications yet</p> : null}
          <ul className="notify-list">
            {items.map((note) => (
              <li
                key={note.id}
                className={`${note.is_read ? 'read' : 'unread'}${
                  note.severity === 'bullish'
                    ? ' severity-bullish'
                    : note.severity === 'bearish'
                      ? ' severity-bearish'
                      : ''
                }`}
              >
                <button type="button" onClick={() => onSelect(note)}>
                  {note.kind === 'uoa' ? (
                    <UoaNotificationContent note={note} />
                  ) : (
                    <>
                      <strong>{note.title}</strong>
                      <span className="muted notify-body-text">{note.body}</span>
                    </>
                  )}
                  <span className="muted notify-meta">
                    {kindLabel(note.kind)}
                    {note.ticker ? ` · ${note.ticker}` : ''}
                    {note.created_at ? ` · ${formatDate(note.created_at)}` : ''}
                    {routeForNote(note) ? ' · open dashboard' : ''}
                  </span>
                </button>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </div>
  )
}
