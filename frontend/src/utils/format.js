export function formatNumber(value, digits = 0) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString(undefined, {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  })
}

export function formatMoney(value, currency = 'USD') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  return Number(value).toLocaleString(undefined, {
    style: 'currency',
    currency,
    maximumFractionDigits: 2,
  })
}

export function formatCompact(value, currency = 'USD') {
  if (value === null || value === undefined || Number.isNaN(Number(value))) return '—'
  const abs = Math.abs(Number(value))
  const sign = Number(value) < 0 ? '-' : ''
  const symbol = currency === 'INR' ? '₹' : '$'
  if (abs >= 1e12) return `${sign}${symbol}${(abs / 1e12).toFixed(2)}T`
  if (abs >= 1e9) return `${sign}${symbol}${(abs / 1e9).toFixed(2)}B`
  if (abs >= 1e6) return `${sign}${symbol}${(abs / 1e6).toFixed(2)}M`
  return formatMoney(value, currency)
}

export function formatDate(value) {
  if (!value) return '—'
  return value
}

export function currencyForMarket(market) {
  return market === 'IN' ? 'INR' : 'USD'
}
