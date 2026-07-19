import { useMemo, useState } from 'react'
import { api } from '../api.js'
import { PREF_QUESTIONS, pick } from '../constants.js'

// Earning a badge unlocks a bonus: add (or refresh) one favorite that gets
// woven into future AI adventures. Questions rotate and stay impersonal —
// things, places, weather — never names of people.
function BadgeBonus({ player }) {
  const question = useMemo(() => {
    const prefs = player.prefs || {}
    const unset = PREF_QUESTIONS.filter((p) => !prefs[p.key])
    return pick(unset.length ? unset : PREF_QUESTIONS)
  }, [player])
  const [value, setValue] = useState('')
  const [state, setState] = useState('ask') // ask -> saving -> done | skipped
  const [error, setError] = useState('')

  if (state === 'done')
    return <p className="bonus-done">✨ Saved! Watch for it in your next adventures.</p>
  if (state === 'skipped') return null

  const save = async (e) => {
    e.preventDefault()
    if (!value.trim()) return
    setState('saving')
    setError('')
    try {
      await api.updatePrefs(player.id, { [question.key]: value.trim() })
      setState('done')
    } catch (err) {
      setError(err.message)
      setState('ask')
    }
  }

  return (
    <form className="badge-bonus" onSubmit={save}>
      <div className="badge-title">🎁 BADGE BONUS</div>
      <label>
        {question.q}
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder={question.ph}
          maxLength={60}
        />
      </label>
      <p className="bonus-note">
        It'll sneak into your future quests! (Things only — please no names of people.)
      </p>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button type="button" className="btn ghost" onClick={() => setState('skipped')}>
          Skip
        </button>
        <button className="btn primary grow" disabled={!value.trim() || state === 'saving'}>
          {state === 'saving' ? 'Saving…' : 'Add it! ✨'}
        </button>
      </div>
    </form>
  )
}

// ui.session_summary: score, XP, streak bonus, newly unlocked badges.
export default function Summary({ summary, onHome }) {
  return (
    <div className="shell center">
      <div className="card">
        <h2>🏁 Quest Complete, {summary.player.name}!</h2>
        <table className="summary-table">
          <tbody>
            <tr>
              <td>Score</td>
              <td>
                {summary.score}/{summary.total}
              </td>
            </tr>
            <tr>
              <td>XP earned</td>
              <td>+{summary.xp_gained}</td>
            </tr>
            {summary.streak_bonus > 0 && (
              <tr>
                <td>Streak bonus</td>
                <td>+{summary.streak_bonus}</td>
              </tr>
            )}
          </tbody>
        </table>
        {summary.difficulty_delta > 0 && (
          <p className="diff-up">
            ⬆️ You're crushing it — the next quests level up to challenge{' '}
            {summary.difficulty}/5!
          </p>
        )}
        {summary.difficulty_delta < 0 && (
          <p className="diff-down">
            ⬇️ We'll ease things up a little — challenge {summary.difficulty}/5.
          </p>
        )}
        {summary.new_badges.map((b) => (
          <div key={b.key} className="badge-unlock">
            <div className="badge-title">NEW BADGE UNLOCKED!</div>
            <div>
              {b.label} — {b.desc}
            </div>
          </div>
        ))}
        {summary.new_badges.length > 0 && <BadgeBonus player={summary.player} />}
        <button className="btn primary big" onClick={onHome}>
          Back to camp 🏕️
        </button>
      </div>
    </div>
  )
}
