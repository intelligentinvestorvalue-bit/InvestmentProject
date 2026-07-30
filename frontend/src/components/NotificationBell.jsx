import { useEffect, useRef, useState } from 'react'
import { fetchNotifications, markAllNotificationsRead, markNotificationRead } from '../services/api'
import { formatDate } from '../utils/format'

export default function NotificationBell() {
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

  async function onRead(id) {
    try {
      await markNotificationRead(id)
      await refresh()
    } catch {
      /* ignore */
    }
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
              <li key={note.id} className={note.is_read ? 'read' : 'unread'}>
                <button type="button" onClick={() => onRead(note.id)}>
                  <strong>{note.title}</strong>
                  <span className="muted">{note.body}</span>
                  <span className="muted notify-meta">
                    {note.kind === 'deep_dive_push'
                      ? 'deep dive'
                      : note.kind === 'deep_dive_pushed'
                        ? 'deep dive started'
                        : note.kind === 'deep_dive_cancelled'
                          ? 'deep dive deferred'
                          : note.kind}
                    {note.ticker ? ` · ${note.ticker}` : ''}
                    {note.created_at ? ` · ${formatDate(note.created_at)}` : ''}
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
