import { useEffect, useState } from 'react'
import { api } from '../api.js'

const MEDALS = ['🥇', '🥈', '🥉']

export default function Leaderboard({ player, onBack }) {
  const [rows, setRows] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.leaderboard().then(setRows).catch((e) => setError(e.message))
  }, [])

  return (
    <div className="shell center">
      <h1 className="logo">🏆 Leaderboard</h1>
      <div className="card">
        {error && <p className="error">{error}</p>}
        {!rows && !error && <p className="muted">Gathering the champions…</p>}
        {rows && rows.length === 0 && (
          <p className="muted">No adventurers yet — be the first!</p>
        )}
        {rows && rows.length > 0 && (
          <div className="stack">
            {rows.map((r, i) => (
              <div
                key={r.id}
                className={`lb-row ${r.id === player?.id ? 'lb-you' : ''}`}
              >
                <span className="lb-rank">{MEDALS[i] || `${i + 1}.`}</span>
                <span className="lb-who">
                  <span className="lb-name">
                    {r.name}
                    {r.id === player?.id && <span className="lb-tag"> (you)</span>}
                  </span>
                  <span className="lb-level">
                    Lv {r.level_num} · {r.level_title}
                  </span>
                </span>
                <span className="lb-stats">
                  <span className="lb-xp">⭐ {r.xp}</span>
                  <span className="lb-small">
                    🔥 {r.streak} · 🏅 {r.badges} · ⚡ {r.sparks || 0}
                  </span>
                </span>
              </div>
            ))}
          </div>
        )}
        <button className="btn primary" onClick={onBack}>
          Back
        </button>
      </div>
    </div>
  )
}
