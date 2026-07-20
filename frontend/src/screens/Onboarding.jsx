import { useState } from 'react'
import { WORLDS } from '../constants.js'
import { SecretFields, secretProblems } from './CreateSecret.jsx'

// The CLI's one-time favorites interview (ui.ask_preferences), as a form —
// plus choosing a secret password + hint, required for every new player.
export default function Onboarding({ onCreate, onBack }) {
  const [name, setName] = useState('')
  const [animal, setAnimal] = useState('')
  const [food, setFood] = useState('')
  const [world, setWorld] = useState('mystery')
  const [secret, setSecret] = useState('')
  const [confirm, setConfirm] = useState('')
  const [hint, setHint] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (e) => {
    e.preventDefault()
    if (!name.trim() || busy) return
    const problem = secretProblems(secret, confirm, hint)
    if (problem) {
      setError(problem)
      return
    }
    setBusy(true)
    setError('')
    try {
      await onCreate(
        name.trim(),
        {
          animal: animal.trim() || 'cat',
          food: food.trim() || 'pizza',
          theme: world,
        },
        secret,
        hint.trim(),
      )
    } catch (err) {
      setError(err.message)
      setBusy(false)
    }
  }

  return (
    <div className="shell center">
      <h1 className="logo">🗺️ Summer Quest</h1>
      <form className="card" onSubmit={submit}>
        <h2>Let's make your quest YOURS!</h2>
        <p className="muted">Your adventures will star the things you love.</p>
        <label>
          What's your name, adventurer?
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            maxLength={40}
            autoFocus
            required
          />
        </label>
        <label>
          What's your favorite animal?
          <input value={animal} onChange={(e) => setAnimal(e.target.value)} placeholder="cat" maxLength={60} />
        </label>
        <label>
          What's a food you love?
          <input value={food} onChange={(e) => setFood(e.target.value)} placeholder="pizza" maxLength={60} />
        </label>
        <div className="label">Pick an adventure world</div>
        <div className="chips">
          {WORLDS.map((w) => (
            <button
              key={w}
              type="button"
              className={`chip ${w === world ? 'chip-on' : ''}`}
              onClick={() => setWorld(w)}
            >
              {w}
            </button>
          ))}
        </div>
        <SecretFields
          secret={secret} setSecret={setSecret}
          confirm={confirm} setConfirm={setConfirm}
          hint={hint} setHint={setHint}
        />
        {error && <p className="error">{error}</p>}
        <div className="row">
          {onBack && (
            <button type="button" className="btn ghost" onClick={onBack}>
              Back
            </button>
          )}
          <button className="btn primary grow" disabled={!name.trim() || busy}>
            {busy ? 'Creating…' : 'Begin my quest! 🚀'}
          </button>
        </div>
      </form>
    </div>
  )
}
