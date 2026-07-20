import { useState } from 'react'
import { api } from '../api.js'

// Password gate for a player who has a secret set. Shows their hint on
// demand (and automatically after a miss), with a "forgot" escape hatch
// that notifies the game developers instead of leaving them stuck.
export default function Login({ player, onSuccess, onBack }) {
  const [secret, setSecret] = useState('')
  const [hint, setHint] = useState(null) // null = not fetched yet
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [notified, setNotified] = useState(false)

  const showHint = async () => {
    try {
      const h = await api.getHint(player.id)
      setHint(h.hint || '(no hint was saved)')
    } catch (e) {
      setHint(`(couldn't fetch your hint: ${e.message})`)
    }
  }

  const submit = async (e) => {
    e.preventDefault()
    if (!secret || busy) return
    setBusy(true)
    setError('')
    try {
      const r = await api.login(player.id, secret)
      onSuccess(r.token, r.player)
    } catch (err) {
      setError(
        err.status === 401
          ? "That's not it — check your hint and try again!"
          : err.message,
      )
      if (hint === null) showHint() // a miss earns the hint automatically
      setBusy(false)
    }
  }

  const forgot = async () => {
    if (notified) return
    setNotified(true)
    try {
      await api.lockout(player.id)
    } catch { /* the message below still tells them to find a grown-up */ }
  }

  return (
    <div className="shell center">
      <h1 className="logo">🗺️ Summer Quest</h1>
      <form className="card" onSubmit={submit}>
        <h2>Hi {player.name}! 🔐</h2>
        <p className="muted">Enter your secret password to continue.</p>
        <label>
          Secret password
          <input
            type="password"
            value={secret}
            onChange={(e) => setSecret(e.target.value)}
            maxLength={64}
            autoFocus
          />
        </label>
        {hint !== null ? (
          <p className="hint-box">💡 Your hint: {hint}</p>
        ) : (
          <button type="button" className="link" onClick={showHint}>
            💡 Show my hint
          </button>
        )}
        {error && <p className="error">{error}</p>}
        <button className="btn primary big" disabled={!secret || busy}>
          {busy ? 'Checking…' : 'Let me in! 🗝️'}
        </button>
        {notified ? (
          <p className="bonus-done">
            📮 The game developers have been notified — ask your grown-up to
            reset your password!
          </p>
        ) : (
          <button type="button" className="link" onClick={forgot}>
            I forgot my secret password — tell the game developers
          </button>
        )}
        <button type="button" className="btn ghost" onClick={onBack}>
          Back
        </button>
      </form>
    </div>
  )
}
