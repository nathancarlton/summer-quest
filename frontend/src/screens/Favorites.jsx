import { useState } from 'react'
import { api } from '../api.js'
import { PREF_QUESTIONS } from '../constants.js'

// Edit (or retire) any favorite directly — no need to wait for a badge
// bonus. Clearing a field removes that favorite from future questions.
export default function Favorites({ player, onSaved, onBack }) {
  const [values, setValues] = useState(() => {
    const v = {}
    for (const q of PREF_QUESTIONS) v[q.key] = player.prefs?.[q.key] || ''
    return v
  })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const save = async (e) => {
    e.preventDefault()
    setBusy(true)
    setError('')
    try {
      const p = await api.updatePrefs(player.id, values)
      onSaved(p)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="shell center">
      <h1 className="logo">✏️ My Favorites</h1>
      <form className="card" onSubmit={save}>
        <p className="muted">
          These sneak into your quests as an occasional surprise. Change any
          of them whenever you want — or erase one to retire it completely.
        </p>
        {PREF_QUESTIONS.map((q) => (
          <label key={q.key}>
            {q.q}
            <input
              value={values[q.key]}
              onChange={(e) => setValues({ ...values, [q.key]: e.target.value })}
              placeholder={q.ph}
              maxLength={60}
            />
          </label>
        ))}
        <p className="bonus-note">
          Things only — please no names of people.
        </p>
        {error && <p className="error">{error}</p>}
        <button className="btn primary big" disabled={busy}>
          {busy ? 'Saving…' : 'Save my favorites ✨'}
        </button>
        <button type="button" className="btn ghost" onClick={onBack}>
          Back
        </button>
      </form>
    </div>
  )
}
