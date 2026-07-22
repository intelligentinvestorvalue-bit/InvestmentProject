const API_BASE = ''

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(options.headers || {}),
    },
    ...options,
  })

  const data = await response.json().catch(() => ({}))
  if (!response.ok) {
    const message = data.error || data.message || `Request failed (${response.status})`
    throw new Error(message)
  }
  return data
}

export function fetchMarkets() {
  return request('/api/v1/markets')
}

export function fetchInsiderMeta(market) {
  return request(`/api/v1/insider/meta?market=${encodeURIComponent(market)}`)
}

export function fetchInsiderTransactions(params) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      qs.set(key, value)
    }
  })
  return request(`/api/v1/insider/transactions?${qs.toString()}`)
}

export function syncInsider(market, payload = {}) {
  return request(`/api/v1/insider/sync?market=${encodeURIComponent(market)}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchDisclosures(params) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      qs.set(key, value)
    }
  })
  return request(`/api/v1/insider/disclosures?${qs.toString()}`)
}

export function fetchFinancials(ticker, market, params = {}) {
  const qs = new URLSearchParams({ market, ...params })
  return request(`/api/v1/financials/${encodeURIComponent(ticker)}?${qs.toString()}`)
}

export function fetchSectors(market) {
  return request(`/api/v1/explore/sectors?market=${encodeURIComponent(market)}`)
}

export function fetchIndustries(market, sector) {
  const qs = new URLSearchParams({ market })
  if (sector) qs.set('sector', sector)
  return request(`/api/v1/explore/industries?${qs.toString()}`)
}

export function fetchExploreCompanies(params) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      qs.set(key, value)
    }
  })
  return request(`/api/v1/explore/companies?${qs.toString()}`)
}

export function syncExplore(market, payload = {}) {
  return request(`/api/v1/explore/sync?market=${encodeURIComponent(market)}`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchWatchlists(market) {
  const qs = market ? `?market=${encodeURIComponent(market)}` : ''
  return request(`/api/v1/watchlists${qs}`)
}

export function createWatchlist(payload) {
  return request('/api/v1/watchlists', { method: 'POST', body: JSON.stringify(payload) })
}

export function fetchWatchlist(id) {
  return request(`/api/v1/watchlists/${id}`)
}

export function renameWatchlist(id, name) {
  return request(`/api/v1/watchlists/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  })
}

export function deleteWatchlist(id) {
  return request(`/api/v1/watchlists/${id}`, { method: 'DELETE' })
}

export function addWatchlistItem(id, payload) {
  return request(`/api/v1/watchlists/${id}/items`, {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function removeWatchlistItem(id, itemId) {
  return request(`/api/v1/watchlists/${id}/items/${itemId}`, { method: 'DELETE' })
}

export function fetchHealth() {
  return request('/api/health')
}

export function fetchUnusualOptions(params = {}) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      qs.set(key, value)
    }
  })
  return request(`/api/v1/options/unusual?${qs.toString()}`)
}

export function fetchUnusualMeta() {
  return request('/api/v1/options/unusual/meta')
}

export function scanUnusualOptions(payload = {}) {
  return request('/api/v1/options/unusual/scan', {
    method: 'POST',
    body: JSON.stringify(payload),
  })
}

export function fetchNotifications(params = {}) {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== '') {
      qs.set(key, value)
    }
  })
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  return request(`/api/v1/notifications${suffix}`)
}

export function markNotificationRead(id) {
  return request(`/api/v1/notifications/${id}/read`, { method: 'POST' })
}

export function markAllNotificationsRead() {
  return request('/api/v1/notifications/read-all', { method: 'POST' })
}
