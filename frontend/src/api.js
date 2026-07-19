// Thin fetch wrapper around the Summer Quest API.
const BASE = (import.meta.env.VITE_API_URL || 'http://localhost:8000').replace(/\/$/, '')

async function req(path, opts = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...opts,
  })
  if (!res.ok) {
    let detail = ''
    try {
      detail = (await res.json()).detail || ''
    } catch { /* non-JSON error body */ }
    throw new Error(detail || `Request failed (${res.status})`)
  }
  return res.json()
}

// The kid's local calendar date — streaks follow their clock, not the server's.
const localDate = () => new Date().toLocaleDateString('en-CA')

export const api = {
  aiStatus: (probe) => req(`/api/v1/ai/status${probe ? '?probe=true' : ''}`),
  leaderboard: () => req('/api/v1/leaderboard'),
  listPlayers: () => req('/api/v1/players'),
  createPlayer: (name, prefs) =>
    req('/api/v1/players', { method: 'POST', body: JSON.stringify({ name, prefs }) }),
  getPlayer: (id) => req(`/api/v1/players/${id}`),
  startExpedition: (id, topic) =>
    req(`/api/v1/players/${id}/expedition`, {
      method: 'POST',
      body: JSON.stringify({ topic }),
    }),
  startQuest: (id) =>
    req(`/api/v1/players/${id}/quest`, {
      method: 'POST',
      body: JSON.stringify({ local_date: localDate() }),
    }),
  answer: (questId, answer) =>
    req(`/api/v1/quests/${questId}/answer`, {
      method: 'POST',
      body: JSON.stringify({ answer }),
    }),
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
