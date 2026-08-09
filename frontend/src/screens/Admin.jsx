import { useEffect, useState } from 'react'
import { admin } from '../api.js'

// ─── Activity view ───────────────────────────────────────────────────────
// Timestamps are stored UTC and rendered in the parent's local time.

const time = (ts) =>
  new Date(ts).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })

const dayLabel = (ts) => {
  const d = new Date(ts)
  const today = new Date()
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  if (d.toDateString() === today.toDateString()) return 'Today'
  if (d.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return d.toLocaleDateString([], { weekday: 'long', month: 'short', day: 'numeric' })
}

const sinceLabel = (ts) => {
  if (!ts) return 'never'
  const mins = Math.round((Date.now() - new Date(ts).getTime()) / 60000)
  if (mins < 2) return 'just now'
  if (mins < 60) return `${mins} min ago`
  if (mins < 60 * 24) return `${Math.round(mins / 60)} hr ago`
  return `${Math.round(mins / 1440)} d ago`
}

// One line per thing they did, in plain language a parent can skim.
function describe(e) {
  const d = e.detail || {}
  switch (e.kind) {
    case 'joined':
      return ['🎉', 'Created their profile']
    case 'quest_start':
      return ['⚔️', `Started a quest (${d.questions} questions)`]
    case 'quest_done':
      return ['🏁', `Finished the quest — ${d.score}/${d.total} right, +${d.xp} XP`]
    case 'expedition_start':
      return ['🧭', `Started a ${d.topic} expedition`]
    case 'expedition_done':
      return ['🎖️', `Finished the expedition — ${d.score}/${d.total} right, +${d.sparks} Sparks`]
    case 'reading':
      return ['📖', `Read ${d.book}, chapter ${d.chapter}${d.chapter_title ? ` — ${d.chapter_title}` : ''}`]
    case 'reading_quiz_start':
      return ['📝', `Started the quiz for ${d.book} ch. ${d.chapter}`]
    case 'reading_quiz_done':
      return ['✅', `Finished the ${d.book} quiz — ${d.score}/${d.total} right, +${d.xp} XP`]
    case 'challenge':
      return ['⚖️', d.overturned
        ? 'Challenged a ruling — and won the appeal'
        : 'Challenged a ruling — it was upheld']
    case 'reported_question':
      return ['📮', 'Reported a question to the developers']
    case 'favorites':
      return ['✏️', `Updated favorites${d.changed?.length ? ` (${d.changed.join(', ')})` : ''}`]
    case 'renamed':
      return ['🪪', `Changed their name from ${d.from} to ${d.to}`]
    case 'secret_created':
      return ['🔐', 'Created their secret password']
    case 'secret_changed':
      return ['🔐', 'Changed their secret password']
    case 'logout':
      return ['👋', 'Signed out']
    default:
      return ['•', e.kind]
  }
}

function Session({ s }) {
  return (
    <div className="session">
      <div className="rep-head">
        <span className="rep-type">👤 {s.player_name}</span>
        <span className="rep-when">
          {time(s.start) === time(s.end)
            ? time(s.start)
            : `${time(s.start)} – ${time(s.end)}`}
          {s.minutes > 0 && ` · ${s.minutes} min`}
          {!s.signed_out && ' · still open'}
        </span>
      </div>
      {s.events.length === 0 ? (
        <p className="rep-detail muted">Signed in, then nothing else.</p>
      ) : (
        <ul className="act-list">
          {s.events.map((e, i) => {
            const [emoji, text] = describe(e)
            return (
              <li key={i}>
                <span className="act-time">{time(e.ts)}</span>
                <span>{emoji} {text}</span>
              </li>
            )
          })}
        </ul>
      )}
    </div>
  )
}

function Activity({ adminKey }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [days, setDays] = useState(14)

  useEffect(() => {
    let live = true
    setData(null)
    admin
      .activity(adminKey, days)
      .then((d) => live && setData(d))
      .catch((e) => live && setError(e.message))
    return () => { live = false }
  }, [adminKey, days])

  if (error) return <p className="error">{error}</p>
  if (!data) return <div className="card"><p className="muted">Loading activity…</p></div>

  // Sessions arrive newest-first; group them under day headings.
  const groups = []
  for (const s of data.sessions) {
    const label = dayLabel(s.start)
    if (!groups.length || groups[groups.length - 1].label !== label)
      groups.push({ label, sessions: [] })
    groups[groups.length - 1].sessions.push(s)
  }

  return (
    <div className="stack">
      <div className="card">
        <div className="row act-range">
          {[7, 14, 30].map((d) => (
            <button
              key={d}
              className={`btn grow ${d === days ? 'primary' : ''}`}
              onClick={() => setDays(d)}
            >
              {d} days
            </button>
          ))}
        </div>
        <table className="stats-table act-table">
          <thead>
            <tr>
              <th>Player</th>
              <th>Seen</th>
              <th>Visits</th>
              <th>Time</th>
            </tr>
          </thead>
          <tbody>
            {data.players.map((p) => (
              <tr key={p.id}>
                <td>
                  {p.name}
                  {p.failed_logins > 0 && (
                    <span className="act-warn" title="wrong password attempts">
                      {' '}⚠️ {p.failed_logins}
                    </span>
                  )}
                </td>
                <td>{sinceLabel(p.last_seen)}</td>
                <td>{p.sessions}</td>
                <td>{p.minutes} min</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {groups.length === 0 && (
        <div className="card">
          <p className="muted">Nobody has signed in during this window.</p>
        </div>
      )}
      {groups.map((g) => (
        <div key={g.label} className="stack">
          <div className="act-day">{g.label}</div>
          {g.sessions.map((s, i) => <Session key={i} s={s} />)}
        </div>
      ))}
      {data.failed_logins.length > 0 && (
        <div className="card">
          <div className="label">⚠️ Wrong password attempts</div>
          <ul className="act-list">
            {data.failed_logins.slice(0, 20).map((f, i) => (
              <li key={i}>
                <span className="act-time">{time(f.ts)}</span>
                <span>{f.player_name} — {dayLabel(f.ts).toLowerCase()}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}

const TYPE_META = {
  locked_out: { emoji: '🔑', label: 'Locked out', cls: 'rep-locked' },
  challenge_won: { emoji: '⚖️', label: 'AI ruling overturned', cls: 'rep-won' },
  manual: { emoji: '📮', label: 'Reported question', cls: 'rep-manual' },
}

// Reported/overturned questions are auto-blocked for everyone; this puts
// one back after the parent decides it was fine after all.
function RestoreButton({ qid, adminKey }) {
  const [state, setState] = useState('idle')
  const restore = async () => {
    setState('busy')
    try {
      await admin.unblock(qid, adminKey)
      setState('done')
    } catch (e) {
      setState('idle')
      alert(`Restore failed: ${e.message}`)
    }
  }
  if (state === 'done')
    return <p className="bonus-done">✅ Question restored to the rotation.</p>
  return (
    <button className="btn" onClick={restore} disabled={state === 'busy'}>
      {state === 'busy' ? 'Restoring…' : '♻️ This question was fine — restore it'}
    </button>
  )
}

function Report({ r, adminKey, onReset }) {
  const meta = TYPE_META[r.type] || { emoji: '📄', label: r.type, cls: '' }
  const [resetState, setResetState] = useState('idle') // idle -> confirm -> done
  const q = r.question

  const reset = async () => {
    if (resetState === 'idle') {
      setResetState('confirm')
      return
    }
    try {
      await admin.resetSecret(r.player_id, adminKey)
      setResetState('done')
      onReset?.()
    } catch (e) {
      setResetState('idle')
      alert(`Reset failed: ${e.message}`)
    }
  }

  return (
    <div className={`report ${meta.cls}`}>
      <div className="rep-head">
        <span className="rep-type">{meta.emoji} {meta.label}</span>
        <span className="rep-when">
          {r.player_name} · {(r.timestamp || '').slice(0, 16).replace('T', ' ')} UTC
        </span>
      </div>
      {q && (
        <>
          <p className="rep-q">{q.question}</p>
          {q.passage && <p className="rep-detail">📜 {q.passage}</p>}
          {q.options && <p className="rep-detail">{q.options.join(' · ')}</p>}
          <p className="rep-detail">
            Official answer: <strong>{q.answer}</strong>
            {r.student_answer && <> · kid answered: <strong>{r.student_answer}</strong></>}
          </p>
          {r.feedback_shown && <p className="rep-detail">Feedback shown: {r.feedback_shown}</p>}
        </>
      )}
      {r.note && <p className="rep-detail">{r.note}</p>}
      {q?.id && (r.type === 'manual' || r.type === 'challenge_won') && (
        <RestoreButton qid={q.id} adminKey={adminKey} />
      )}
      {r.type === 'locked_out' && resetState !== 'done' && (
        <button className={`btn ${resetState === 'confirm' ? 'boss-btn' : ''}`} onClick={reset}>
          {resetState === 'confirm'
            ? '⚠️ Click again to confirm the reset'
            : `Reset ${r.player_name}'s password`}
        </button>
      )}
      {resetState === 'done' && (
        <p className="bonus-done">
          ✅ Password cleared — {r.player_name} creates a new one at next login.
        </p>
      )}
    </div>
  )
}

// The Parent Zone: enter the admin key (the SYNC_TOKEN set on the backend)
// to read developer reports and reset locked-out kids' passwords.
export default function Admin({ onBack }) {
  const [key, setKey] = useState(localStorage.getItem('sq_admin') || '')
  const [authed, setAuthed] = useState(false)
  const [tab, setTab] = useState('activity')
  const [reports, setReports] = useState([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [confirmClear, setConfirmClear] = useState(false)

  const load = async (k = key) => {
    setBusy(true)
    setError('')
    try {
      const list = await admin.reports(k)
      setReports([...list].reverse()) // newest first
      setAuthed(true)
      localStorage.setItem('sq_admin', k)
    } catch (e) {
      setError(
        e.status === 401
          ? "That key doesn't match the server's SYNC_TOKEN."
          : e.message,
      )
    }
    setBusy(false)
  }

  const clearAll = async () => {
    if (!confirmClear) {
      setConfirmClear(true)
      return
    }
    setConfirmClear(false)
    try {
      await admin.clear(key)
      setReports([])
    } catch (e) {
      setError(e.message)
    }
  }

  if (!authed) {
    return (
      <div className="shell center">
        <h1 className="logo">🔧 Parent Zone</h1>
        <form
          className="card"
          onSubmit={(e) => {
            e.preventDefault()
            load()
          }}
        >
          <p className="muted">
            Enter your admin key — the <code>SYNC_TOKEN</code> you set on the
            backend. (If you haven't set one yet, leave this blank; reports
            and activity are open until you do.)
          </p>
          <label>
            Admin key
            <input
              type="password"
              value={key}
              onChange={(e) => setKey(e.target.value)}
              maxLength={128}
            />
          </label>
          {error && <p className="error">{error}</p>}
          <button className="btn primary big" disabled={busy}>
            {busy ? 'Checking…' : 'Open the Parent Zone'}
          </button>
          <button type="button" className="btn ghost" onClick={onBack}>
            Back
          </button>
        </form>
      </div>
    )
  }

  return (
    <div className="shell">
      <div className="quest-top">
        <span className="q-count">🔧 Parent Zone</span>
        {tab === 'reports' && (
          <button className="link" onClick={() => load()}>↻ Refresh</button>
        )}
      </div>
      <div className="row tab-row">
        <button
          className={`btn grow ${tab === 'activity' ? 'primary' : ''}`}
          onClick={() => setTab('activity')}
        >
          🕒 Activity
        </button>
        <button
          className={`btn grow ${tab === 'reports' ? 'primary' : ''}`}
          onClick={() => setTab('reports')}
        >
          📮 Reports ({reports.length})
        </button>
      </div>
      {error && <p className="error">{error}</p>}
      {tab === 'activity' && <Activity adminKey={key} />}
      {tab === 'reports' && (reports.length === 0 ? (
        <div className="card">
          <p className="muted">
            No reports — the question pipeline is quiet and nobody's locked out. 🎉
          </p>
        </div>
      ) : (
        <div className="stack">
          {reports.map((r, i) => (
            <Report key={i} r={r} adminKey={key} onReset={() => {}} />
          ))}
        </div>
      ))}
      <div className="row">
        {tab === 'reports' && reports.length > 0 && (
          <button className={`btn grow ${confirmClear ? 'boss-btn' : ''}`} onClick={clearAll}>
            {confirmClear ? '⚠️ Click again to clear ALL' : '🗑 Clear all reports'}
          </button>
        )}
        <button
          className="btn grow"
          onClick={() => {
            localStorage.removeItem('sq_admin')
            onBack()
          }}
        >
          Exit Parent Zone
        </button>
      </div>
    </div>
  )
}
