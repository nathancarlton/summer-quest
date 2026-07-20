import { useState } from 'react'
import { admin } from '../api.js'

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
            are open until you do.)
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
            {busy ? 'Checking…' : 'Open reports'}
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
        <span className="q-count">🔧 Developer reports ({reports.length})</span>
        <button className="link" onClick={() => load()}>↻ Refresh</button>
      </div>
      {error && <p className="error">{error}</p>}
      {reports.length === 0 ? (
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
      )}
      <div className="row">
        {reports.length > 0 && (
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
