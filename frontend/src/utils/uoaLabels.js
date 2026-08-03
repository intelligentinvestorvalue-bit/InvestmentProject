/** Shared human-readable labels for unusual options alerts. */

export const AGGRESSIVENESS_LABELS = {
  buy_ask: 'Aggressive buy (near ask)',
  sell_bid: 'Aggressive sell (near bid)',
  mid: 'Mid-spread print',
  unknown: 'Bid/ask unavailable',
}

export const SENTIMENT_LABELS = {
  bullish: 'Bullish',
  bearish: 'Bearish',
  mixed: 'Mixed',
  unclear: 'Unclear',
}

export const UNIVERSE_LABELS = {
  watchlist: 'Watchlist',
  liquid100: 'Liquid universe',
}

export function aggressivenessLabel(code) {
  if (!code) return '—'
  return AGGRESSIVENESS_LABELS[code] || code
}

export function sentimentLabel(code) {
  if (!code) return '—'
  return SENTIMENT_LABELS[code] || code
}

export function universeLabel(code) {
  if (!code) return '—'
  return UNIVERSE_LABELS[code] || code
}

/** Friendly contract line, e.g. "NVDA $120 CALL · Aug 15 (25d)". */
export function formatOptionContract(row, { currency = 'USD' } = {}) {
  if (!row) return '—'
  const sym = row.underlying || row.ticker || ''
  const type = (row.option_type || '').toUpperCase()
  const money =
    row.strike == null
      ? ''
      : currency === 'INR'
        ? `₹${Number(row.strike).toLocaleString('en-IN', { maximumFractionDigits: 2 })}`
        : `$${Number(row.strike).toLocaleString('en-US', { maximumFractionDigits: 2 })}`
  const parts = [sym, money, type].filter(Boolean)
  let line = parts.join(' ')
  if (row.expiration) {
    const exp = String(row.expiration).slice(0, 10)
    line += ` · ${exp}`
  }
  if (row.dte != null && row.dte !== '') {
    line += ` (${row.dte}d)`
  }
  return line
}

export function formatIv(iv) {
  if (iv == null || Number.isNaN(Number(iv))) return '—'
  const n = Number(iv)
  // Yahoo often returns IV as 0–1; NSE may already be percent-like.
  const pct = n <= 2 ? n * 100 : n
  return `${pct.toFixed(1)}%`
}

export function parseNotificationPayload(note) {
  if (!note?.payload_json) return null
  try {
    return JSON.parse(note.payload_json)
  } catch {
    return null
  }
}
