import { useState } from 'react'
import { api } from '../api.js'
import { CATEGORY_LABELS, TOPIC_META } from '../constants.js'
import { Hud } from './Home.jsx'

// Changing the name shown on the home screen, leaderboard and badges.
// Collisions are rejected by the server (the login roster shows names only,
// so two identical names would be impossible to tell apart).
function RenameBox({ player, onRenamed, onCancel }) {
  const [name, setName] = useState(player.name)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const trimmed = name.trim()

  const save = async (e) => {
    e.preventDefault()
    if (!trimmed || trimmed === player.name) {
      onCancel()
      return
    }
    setBusy(true)
    setError('')
    try {
      onRenamed(await api.rename(player.id, trimmed))
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <form className="rename-box" onSubmit={save}>
      <label>
        What should we call you?
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={40}
          autoFocus
        />
      </label>
      {error && <p className="error">{error}</p>}
      <p className="muted">
        Your XP, badges, streak and books all stay exactly where they are.
      </p>
      <div className="row">
        <button className="btn primary grow" disabled={busy}>
          {busy ? 'Saving…' : 'Save my new name'}
        </button>
        <button type="button" className="btn grow" onClick={onCancel}>
          Cancel
        </button>
      </div>
    </form>
  )
}

// ui.show_stats: the report card — per-category accuracy + badge collection.
export default function Stats({ player, onEditFavorites, onRenamed, onBack }) {
  const [renaming, setRenaming] = useState(false)
  const rows = Object.entries(player.categories)
    .filter(([, s]) => s.answered > 0)
    .map(([cat, s]) => ({
      cat,
      label: CATEGORY_LABELS[cat] || cat,
      correct: s.correct,
      answered: s.answered,
      acc: s.correct / s.answered,
    }))

  const color = (acc) => (acc >= 0.8 ? 'good' : acc >= 0.6 ? 'ok' : 'bad')

  return (
    <div className="shell center">
      <h1 className="logo">📊 My Stats</h1>
      <div className="card">
        <h2 className="stats-name">{player.name}</h2>
        <Hud player={player} />
        <p className="muted">
          Challenge level: {'⭐'.repeat(player.difficulty || 2)} ({player.difficulty || 2}/5)
        </p>
        {rows.length ? (
          <table className="stats-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Correct</th>
                <th>Accuracy</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.cat}>
                  <td>{r.label}</td>
                  <td>
                    {r.correct}/{r.answered}
                  </td>
                  <td className={color(r.acc)}>{Math.round(r.acc * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">Complete a quest to see your report card!</p>
        )}
        {Object.keys(player.stickers || {}).length > 0 && (
          <div className="badge-box">
            <div className="label">
              Sticker Book · ⚡ {player.sparks || 0} Sparks
            </div>
            <div className="sticker-shelf">
              {Object.entries(player.stickers).map(([key, count]) => (
                <span
                  key={key}
                  className="sticker-chip"
                  title={TOPIC_META[key]?.name || key}
                >
                  {TOPIC_META[key]?.emoji || '🎖️'} ×{count}
                </span>
              ))}
            </div>
          </div>
        )}
        {player.badge_details.length > 0 && (
          <div className="badge-box">
            <div className="label">Badge Collection</div>
            {player.badge_details.map((b) => (
              <div key={b.key} className="badge-row" title={b.desc}>
                {b.label}
              </div>
            ))}
          </div>
        )}
        {renaming ? (
          <RenameBox
            player={player}
            onRenamed={(p) => {
              setRenaming(false)
              onRenamed(p)
            }}
            onCancel={() => setRenaming(false)}
          />
        ) : (
          <div className="row">
            <button className="btn grow" onClick={onEditFavorites}>
              ✏️ My favorites
            </button>
            <button className="btn grow" onClick={() => setRenaming(true)}>
              🪪 Change my name
            </button>
          </div>
        )}
        <div className="row">
          <button className="btn primary grow" onClick={onBack}>
            Back
          </button>
        </div>
      </div>
    </div>
  )
}
