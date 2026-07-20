import { useEffect, useState } from 'react'
import { api, setToken } from './api.js'
import PickPlayer from './screens/PickPlayer.jsx'
import Onboarding from './screens/Onboarding.jsx'
import Login from './screens/Login.jsx'
import CreateSecret from './screens/CreateSecret.jsx'
import Home from './screens/Home.jsx'
import Quest from './screens/Quest.jsx'
import Summary from './screens/Summary.jsx'
import Stats from './screens/Stats.jsx'
import Leaderboard from './screens/Leaderboard.jsx'
import Topics from './screens/Topics.jsx'

const STORED_ID = 'sq_player_id'

// Screens: loading -> pick -> login|createSecret -> home -> quest -> summary
//          pick -> onboard (new player, includes secret creation) -> home
export default function App() {
  const [screen, setScreen] = useState('loading')
  const [player, setPlayer] = useState(null)
  const [pending, setPending] = useState(null) // roster entry awaiting login
  const [roster, setRoster] = useState([])
  const [quest, setQuest] = useState(null)
  const [summary, setSummary] = useState(null)
  const [active, setActive] = useState(null) // unfinished session info
  const [error, setError] = useState('')

  const refreshActive = (p) => {
    // active_info rides along in the player payload — set synchronously so
    // the home screen shows the right button on its very first render. The
    // fetch fallback only covers an older backend without the field.
    if (p.active_info) {
      setActive(p.active_info)
      return
    }
    setActive(null)
    api.active(p.id).then(setActive).catch(() => setActive({ active: false }))
  }

  useEffect(() => {
    const boot = async () => {
      const savedId = localStorage.getItem(STORED_ID)
      if (savedId) {
        try {
          const p = await api.getPlayer(savedId) // sends the stored token
          setPlayer(p)
          refreshActive(p)
          setScreen('home')
          return
        } catch {
          // profile gone, or token expired/reset — back through the picker
          localStorage.removeItem(STORED_ID)
          setToken(null)
        }
      }
      await showPicker()
    }
    boot().catch((e) => {
      setError(e.message)
      setScreen('error')
    })
  }, [])

  const showPicker = async () => {
    const players = await api.listPlayers()
    setRoster(players)
    setScreen(players.length ? 'pick' : 'onboard')
  }

  const choosePlayer = (entry) => {
    // Roster entries carry has_secret: password gate for players who have
    // one, forced secret creation for those who don't.
    setPending(entry)
    setScreen(entry.has_secret ? 'login' : 'createSecret')
  }

  const onAuthed = (token, p) => {
    setToken(token)
    localStorage.setItem(STORED_ID, p.id)
    setPlayer(p)
    refreshActive(p)
    setPending(null)
    setScreen('home')
  }

  const createPlayer = async (name, prefs, secret, hint) => {
    const r = await api.createPlayer(name, prefs, secret, hint)
    onAuthed(r.token, r.player)
  }

  const enterSession = async (resp) => {
    // A resumed session where everything was already answered just needs
    // its finale — go straight to the summary.
    if (resp.resumed && resp.answered >= resp.questions.length) {
      const s = await api.complete(resp.quest_id)
      setSummary(s)
      setPlayer(s.player)
      setActive(null)
      setScreen('summary')
      return
    }
    setQuest(resp)
    setScreen('quest')
  }

  const startQuest = async () => {
    setScreen('loading')
    try {
      await enterSession(await api.startQuest(player.id))
    } catch (e) {
      setError(e.message)
      setScreen('error')
    }
  }

  const startExpedition = async (topic) => {
    setScreen('loading')
    try {
      await enterSession(await api.startExpedition(player.id, topic))
    } catch (e) {
      setError(e.message)
      setScreen('error')
    }
  }

  const finishQuest = async () => {
    const s = await api.complete(quest.quest_id)
    setSummary(s)
    setPlayer(s.player)
    setQuest(null)
    setActive(null)
    setScreen('summary')
  }

  const goHome = async () => {
    try {
      const p = await api.getPlayer(player.id) // refresh XP/badges
      setPlayer(p)
      refreshActive(p)
    } catch { /* keep the copy we have */ }
    setScreen('home')
  }

  const switchPlayer = () => {
    localStorage.removeItem(STORED_ID)
    setToken(null)
    setPlayer(null)
    setScreen('loading')
    showPicker().catch((e) => {
      setError(e.message)
      setScreen('error')
    })
  }

  if (screen === 'loading') {
    return (
      <div className="shell center">
        <div className="spinner" />
        <p className="muted">Summoning your quest…</p>
      </div>
    )
  }
  if (screen === 'error') {
    return (
      <div className="shell center">
        <div className="card">
          <h2>😴 The quest world is napping</h2>
          <p className="muted">{error || "Couldn't reach the server."}</p>
          <button className="btn primary" onClick={() => window.location.reload()}>
            Try again
          </button>
        </div>
      </div>
    )
  }
  if (screen === 'pick')
    return <PickPlayer roster={roster} onPick={choosePlayer} onNew={() => setScreen('onboard')} />
  if (screen === 'onboard')
    return <Onboarding onCreate={createPlayer} onBack={roster.length ? () => setScreen('pick') : null} />
  if (screen === 'login')
    return <Login player={pending} onSuccess={onAuthed} onBack={switchPlayer} />
  if (screen === 'createSecret')
    return <CreateSecret player={pending} onSuccess={onAuthed} onBack={switchPlayer} />
  if (screen === 'quest')
    return <Quest quest={quest} onFinish={finishQuest} />
  if (screen === 'summary')
    return <Summary summary={summary} onHome={goHome} />
  if (screen === 'stats')
    return <Stats player={player} onBack={() => setScreen('home')} />
  if (screen === 'board')
    return <Leaderboard player={player} onBack={() => setScreen('home')} />
  if (screen === 'topics')
    return <Topics onPick={startExpedition} onBack={() => setScreen('home')} />
  return (
    <Home
      player={player}
      active={active}
      onStart={startQuest}
      onExpedition={() => setScreen('topics')}
      onStats={() => setScreen('stats')}
      onBoard={() => setScreen('board')}
      onSwitch={switchPlayer}
    />
  )
}
