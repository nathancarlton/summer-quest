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

// Post-quest compare-and-contrast: where you sit on the family board and the
// real XP gaps to the players just ahead and behind.
function Standings({ standings }) {
  if (!standings || standings.of < 2) return null
  const { rank, of, me, ahead, behind, leader } = standings
  return (
    <div className="standings">
      <div className="badge-title">🏆 FAMILY STANDINGS</div>
      <p>
        You're <strong>#{rank} of {of}</strong> with {me.xp} XP
        (Level {me.level_num} — {me.level_title}).
      </p>
      {ahead && (
        <p>
          {ahead.name} is <strong>{ahead.xp - me.xp} XP ahead</strong> of you
          at Level {ahead.level_num}. Every quest closes the gap!
        </p>
      )}
      {leader && leader.name !== (ahead && ahead.name) && (
        <p>
          {leader.name} leads the board at {leader.xp} XP
          (Level {leader.level_num} — {leader.level_title}).
        </p>
      )}
      {behind && (
        <p>
          You're {me.xp - behind.xp} XP ahead of {behind.name} — keep your
          streak alive to stay there.
        </p>
      )}
      {rank === 1 && <p>You lead the whole board — defend that crown! 👑</p>}
    </div>
  )
}

// A parent-queued offer to fold an old profile into this one. Everything
// shown is true: the old profile's XP, the reunion bonus, and the level the
// combined profile lands on. Rendered BELOW the standings on purpose.
function MergeOffer({ playerId, offer }) {
  const [state, setState] = useState('ask') // ask -> merging -> done | dismissed
  const [result, setResult] = useState(null)
  const [error, setError] = useState('')

  if (!offer || state === 'dismissed') return null
  if (state === 'done' && result)
    return (
      <div className="merge-offer">
        <div className="badge-title">🎉 PROFILES COMBINED!</div>
        <p>
          +{result.restored_xp} XP restored, +{result.bonus_xp} reunion bonus —
          you're now <strong>Level {result.player.level.num} —{' '}
          {result.player.level.title}</strong> with {result.player.xp} XP!
        </p>
      </div>
    )

  const combine = async () => {
    setState('merging')
    setError('')
    try {
      setResult(await api.mergeProfiles(playerId))
      setState('done')
    } catch (err) {
      setError(err.message)
      setState('ask')
    }
  }

  return (
    <div className="merge-offer">
      <div className="badge-title">👀 WAIT A SECOND…</div>
      <p>{offer.message}</p>
      <p>
        "{offer.source_name}" has <strong>{offer.source_xp} XP</strong> saved up
        (Level {offer.source_level} — {offer.source_level_title}). Combine, and
        all of it comes home — <strong>plus a +{offer.bonus_xp} XP reunion
        bonus</strong>. You'd jump to{' '}
        <strong>
          Level {offer.merged_level} — {offer.merged_level_title}
        </strong>{' '}
        with {offer.merged_xp} XP!
      </p>
      {error && <p className="error">{error}</p>}
      <div className="row">
        <button type="button" className="btn ghost" onClick={() => setState('dismissed')}>
          Not now
        </button>
        <button
          type="button"
          className="btn primary grow"
          onClick={combine}
          disabled={state === 'merging'}
        >
          {state === 'merging' ? 'Combining…' : 'Combine them! ⚡'}
        </button>
      </div>
    </div>
  )
}

// ui.session_summary: score, XP, streak bonus, newly unlocked badges.
export default function Summary({ summary, onHome }) {
  if (summary.kind === 'reading') {
    return (
      <div className="shell center">
        <div className="card">
          <h2>
            {summary.book.emoji} Chapter {summary.book.chapter + 1} Quiz Complete!
          </h2>
          <p className="muted">{summary.book.title}</p>
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
            </tbody>
          </table>
          <button className="btn primary big" onClick={onHome}>
            Back to camp 🏕️
          </button>
        </div>
      </div>
    )
  }
  if (summary.kind === 'expedition') {
    const s = summary.sticker
    return (
      <div className="shell center">
        <div className="card">
          <h2>🧭 Expedition Complete!</h2>
          <table className="summary-table">
            <tbody>
              <tr>
                <td>Score</td>
                <td>
                  {summary.score}/{summary.total}
                </td>
              </tr>
              <tr>
                <td>Sparks earned</td>
                <td>+{summary.sparks_earned} ⚡</td>
              </tr>
            </tbody>
          </table>
          <div className="sticker-award">
            <div className="sticker-emoji">{s.emoji}</div>
            <div>
              <div className="badge-title">NEW STICKER!</div>
              {s.name} — you've collected {s.count}
            </div>
          </div>
          <button className="btn primary big" onClick={onHome}>
            Back to camp 🏕️
          </button>
        </div>
      </div>
    )
  }
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
        <Standings standings={summary.standings} />
        <MergeOffer playerId={summary.player.id} offer={summary.merge_offer} />
        <button className="btn primary big" onClick={onHome}>
          Back to camp 🏕️
        </button>
      </div>
    </div>
  )
}
