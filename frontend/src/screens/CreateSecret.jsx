import { useState } from 'react'
import { api } from '../api.js'

// Fields for choosing a secret password + hint. Used standalone for
// returning players who predate passwords, and embedded in Onboarding
// for brand-new adventurers.
export function SecretFields({ secret, setSecret, confirm, setConfirm, hint, setHint }) {
  return (
    <>
      <label>
        Make up a secret password (4+ letters)
        <input
          type="password"
          value={secret}
          onChange={(e) => setSecret(e.target.value)}
          minLength={4}
          maxLength={64}
          required
        />
      </label>
      <label>
        Type it again to be sure
        <input
          type="password"
          value={confirm}
          onChange={(e) => setConfirm(e.target.value)}
          maxLength={64}
          required
        />
      </label>
      <label>
        A hint only YOU would understand
        <input
          value={hint}
          onChange={(e) => setHint(e.target.value)}
          placeholder="e.g. my lucky number + the fluffy one"
          minLength={3}
          maxLength={100}
          required
        />
      </label>
      <p className="bonus-note">
        Pick a hint no one else can guess — it helps future-you remember,
        without giving the password away to anyone else.
      </p>
    </>
  )
}

export function secretProblems(secret, confirm, hint) {
  if (secret.length < 4) return 'Your secret password needs at least 4 characters.'
  if (secret !== confirm) return "The two passwords don't match — try again."
  if (hint.trim().length < 3) return 'Add a hint (at least 3 characters) so future-you can remember!'
  if (hint.trim().toLowerCase().includes(secret.toLowerCase()))
    return "Sneaky, but no — the hint can't contain the password itself!"
  return null
}

// Standalone screen for a returning player who doesn't have a secret yet.
export default function CreateSecret({ player, onSuccess, onBack }) {
  const [secret, setSecret] = useState('')
  const [confirm, setConfirm] = useState('')
  const [hint, setHint] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    const problem = secretProblems(secret, confirm, hint)
    if (problem) {
      setError(problem)
      return
    }
    setBusy(true)
    setError('')
    try {
      const r = await api.setSecret(player.id, secret, hint.trim())
      onSuccess(r.token, r.player)
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="shell center">
      <h1 className="logo">🗺️ Summer Quest</h1>
      <form className="card" onSubmit={submit}>
        <h2>One new thing, {player.name}! 🔐</h2>
        <p className="muted">
          Your quest now has a lock on it. Create a secret password so only
          YOU can play as {player.name}.
        </p>
        <SecretFields
          secret={secret} setSecret={setSecret}
          confirm={confirm} setConfirm={setConfirm}
          hint={hint} setHint={setHint}
        />
        {error && <p className="error">{error}</p>}
        <button className="btn primary big" disabled={busy}>
          {busy ? 'Locking it in…' : 'Lock it in! 🗝️'}
        </button>
        <button type="button" className="btn ghost" onClick={onBack}>
          Back
        </button>
      </form>
    </div>
  )
}
