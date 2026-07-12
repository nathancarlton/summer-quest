import { useEffect, useState } from 'react'
import { api } from './api.js'
import PickPlayer from './screens/PickPlayer.jsx'
import Onboarding from './screens/Onboarding.jsx'
import Home from './screens/Home.jsx'
import Quest from './screens/Quest.jsx'
import Summary from './screens/Summary.jsx'
import Stats from './screens/Stats.jsx'

const STORED_ID = 'sq_player_id'

// Screens: loading -> pick | onboard -> home -> quest -> summary -> home
//                                      home -> stats -> home
export default function App() {
  const [screen, setScreen] = useState('loading')
  const [player, setPlayer] = useState(null)
  const [roster, setRoster] = useState([])
  const [quest, setQuest] = useState(null)
  const [summary, setSummary] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    const boot = async () => {
      const savedId = localStorage.getItem(STORED_ID)
      if (savedId) {
        try {
          setPlayer(await api.getPlayer(savedId))
          setScreen('home')
          return
        } catch {
          localStorage.removeItem(STORED_ID) // profile gone — re-pick
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

  const choosePlayer = async (id) => {
    setScreen('loading')
    try {
      const p = await api.getPlayer(id)
      localStorage.setItem(STORED_ID, p.id)
      setPlayer(p)
      setScreen('home')
    } catch (e) {
      setError(e.message)
      setScreen('error')
    }
  }

  const createPlayer = async (name, prefs) => {
    const p = await api.createPlayer(name, prefs)
    localStorage.setItem(STORED_ID, p.id)
    setPlayer(p)
    setScreen('home')
  }

  const startQuest = async () => {
    setScreen('loading')
    try {
      setQuest(await api.startQuest(player.id))
      setScreen('quest')
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
    setScreen('summary')
  }

  const goHome = async () => {
    try {
      setPlayer(await api.getPlayer(player.id)) // refresh XP/badges
    } catch { /* keep the copy we have */ }
    setScreen('home')
  }

  const switchPlayer = () => {
    localStorage.removeItem(STORED_ID)
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
  if (screen === 'quest')
    return <Quest quest={quest} onFinish={finishQuest} />
  if (screen === 'summary')
    return <Summary summary={summary} onHome={goHome} />
  if (screen === 'stats')
    return <Stats player={player} onBack={() => setScreen('home')} />
  return (
    <Home
      player={player}
      onStart={startQuest}
      onStats={() => setScreen('stats')}
      onSwitch={switchPlayer}
    />
  )
}
