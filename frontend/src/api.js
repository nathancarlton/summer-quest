// Thin fetch wrapper around the Summer Quest API, with bearer-token auth.
const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

let TOKEN = localStorage.getItem('sq_token') || ''

export function setToken(t) {
  TOKEN = t || ''
  if (t) localStorage.setItem('sq_token', t)
  else localStorage.removeItem('sq_token')
}

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    ...opts,
    headers: {
      'Content-Type': 'application/json',
      ...(TOKEN ? { 'X-Player-Token': TOKEN } : {}),
      ...(opts.headers || {}),
    },
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail || ''
    } catch { /* non-JSON error body */ }
    const err = new Error(detail || `Request failed (${res.status})`)
    err.status = res.status
    throw err
  }
  return res.json()
}

// The kid's local calendar date — streaks follow their clock, not the server's.
const localDate = () => new Date().toLocaleDateString('en-CA')

export const api = {
  aiStatus: (probe) => req(`/api/v1/ai/status${probe ? '?probe=true' : ''}`),
  leaderboard: () => req('/api/v1/leaderboard'),
  listPlayers: () => req('/api/v1/players'),
  createPlayer: (name, prefs, secret, hint) =>
    req('/api/v1/players', {
      method: 'POST',
      body: JSON.stringify({ name, prefs, secret, hint }),
    }),
  login: (id, secret) =>
    req(`/api/v1/players/${id}/login`, {
      method: 'POST',
      body: JSON.stringify({ secret }),
    }),
  getHint: (id) => req(`/api/v1/players/${id}/hint`),
  setSecret: (id, secret, hint) =>
    req(`/api/v1/players/${id}/secret`, {
      method: 'POST',
      body: JSON.stringify({ secret, hint }),
    }),
  lockout: (id) => req(`/api/v1/players/${id}/lockout`, { method: 'POST' }),
  getPlayer: (id) => req(`/api/v1/players/${id}`),
  startQuest: (id) =>
    req(`/api/v1/players/${id}/quest`, {
      method: 'POST',
      body: JSON.stringify({ local_date: localDate() }),
    }),
  startExpedition: (id, topic) =>
    req(`/api/v1/players/${id}/expedition`, {
      method: 'POST',
      body: JSON.stringify({ topic }),
    }),
  answer: (questId, answer, timedOut = false) =>
    req(`/api/v1/quests/${questId}/answer`, {
      method: 'POST',
      body: JSON.stringify({ answer, timed_out: timedOut }),
    }),
  active: (id) => req(`/api/v1/players/${id}/active`),
  complete: (questId) => req(`/api/v1/quests/${questId}/complete`, { method: 'POST' }),
  challenge: (questId, index) =>
    req(`/api/v1/quests/${questId}/challenge`, {
      method: 'POST',
      body: JSON.stringify({ index }),
    }),
  report: (questId, index) =>
    req(`/api/v1/quests/${questId}/report`, {
      method: 'POST',
      body: JSON.stringify({ index }),
    }),
  updatePrefs: (id, prefs) =>
    req(`/api/v1/players/${id}/prefs`, { method: 'POST', body: JSON.stringify({ prefs }) }),
}

// Parent Zone: authenticated with the backend's SYNC_TOKEN as the admin key.
const adminHeaders = (key) => (key ? { Authorization: `Bearer ${key}` } : {})

export const admin = {
  reports: (key) => req('/api/v1/reports', { headers: adminHeaders(key) }),
  clear: (key) => req('/api/v1/reports', { method: 'DELETE', headers: adminHeaders(key) }),
  resetSecret: (pid, key) =>
    req(`/api/v1/players/${pid}/secret/reset`, {
      method: 'POST',
      headers: adminHeaders(key),
    }),
  unblock: (qid, key) =>
    req('/api/v1/questions/unblock', {
      method: 'POST',
      headers: adminHeaders(key),
      body: JSON.stringify({ id: qid }),
    }),
}
