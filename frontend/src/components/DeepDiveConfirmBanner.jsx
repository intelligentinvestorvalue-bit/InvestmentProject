import { useEffect, useMemo, useState } from 'react'
import {
  cancelDeepDive,
  confirmDeepDive,
  fetchDeepDivePending,
} from '../services/api'
import { formatMoney } from '../utils/format'

function secondsLeft(deadlineIso, serverSkewMs) {
  if (!deadlineIso) return 0
  const deadline = new Date(deadlineIso).getTime()
  const now = Date.now() + serverSkewMs
  return Math.max(0, Math.ceil((deadline - now) / 1000))
}

export default function DeepDiveConfirmBanner() {
  const [pending, setPending] = useState([])
  const [enabled, setEnabled] = useState(true)
  const [serverSkewMs, setServerSkewMs] = useState(0)
  const [busyId, setBusyId] = useState(null)
  const [error, setError] = useState('')
  const [tick, setTick] = useState(0)

  async function refresh() {
    try {
      const data = await fetchDeepDivePending()
      setEnabled(Boolean(data.enabled))
      setPending(data.pending || [])
      if (data.server_time) {
        const skew = new Date(data.server_time).getTime() - Date.now()
        setServerSkewMs(Number.isFinite(skew) ? skew : 0)
      }
      setError('')
    } catch (err) {
      // Silent when backend is briefly unavailable.
      setError(err?.message || '')
    }
  }

  useEffect(() => {
    refresh()
    const poll = setInterval(refresh, 4000)
    const clock = setInterval(() => setTick((n) => n + 1), 1000)
    return () => {
      clearInterval(poll)
      clearInterval(clock)
    }
  }, [])

  const items = useMemo(() => pending, [pending, tick])

  if (!enabled || items.length === 0) return null

  async function onCancel(id) {
    setBusyId(id)
    try {
      await cancelDeepDive(id)
      await refresh()
    } catch (err) {
      setError(err.message || 'Cancel failed')
    } finally {
      setBusyId(null)
    }
  }

  async function onConfirm(id) {
    setBusyId(id)
    try {
      await confirmDeepDive(id)
      await refresh()
    } catch (err) {
      setError(err.message || 'Push failed')
    } finally {
      setBusyId(null)
    }
  }

  return (
    <div className="deep-dive-banner" role="status" aria-live="polite">
      {items.map((item) => {
        const left = secondsLeft(item.confirm_deadline_at, serverSkewMs)
        return (
          <div key={item.id} className="deep-dive-banner-item">
            <div className="deep-dive-banner-copy">
              <strong>
                Push {item.ticker} to Equity Research queue
                {left > 0 ? ` in ${left}s` : ''}
              </strong>
              <span>
                {(item.officer_title || 'Officer') +
                  (item.insider_name ? ` · ${item.insider_name}` : '')}
                {item.total_value != null ? ` · bought ${formatMoney(item.total_value)}` : ''}
                {item.company_name ? ` · ${item.company_name}` : ''}
              </span>
              <span className="muted">
                Parked on the Equity Research queue. Research does not start until you click Start overnight there.
              </span>
            </div>
            <div className="deep-dive-banner-actions">
              <button
                type="button"
                className="btn btn-ghost"
                disabled={busyId === item.id}
                onClick={() => onCancel(item.id)}
              >
                Cancel
              </button>
              <button
                type="button"
                className="btn"
                disabled={busyId === item.id}
                onClick={() => onConfirm(item.id)}
              >
                Push now
              </button>
            </div>
          </div>
        )
      })}
      {error ? <p className="deep-dive-banner-error">{error}</p> : null}
    </div>
  )
}
