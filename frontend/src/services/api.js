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
