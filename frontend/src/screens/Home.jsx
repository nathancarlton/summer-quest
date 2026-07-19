import AiDot from '../AiDot.jsx'
import ThemePicker from '../ThemePicker.jsx'

// The HUD from ui.py: XP, level, streak, badges, progress to next level.
export function Hud({ player }) {
  const { level } = player
  const pct = level.next ? Math.min(100, (player.xp / level.next.threshold) * 100) : 100
  return (
    <div className="hud card">
      <div className="hud-row">
        <span>⭐ {player.xp} XP</span>
        <span>
          Lv {level.num} · {level.title}
        </span>
        <span>🔥 {player.streak}</span>
        <span>🏅 {player.badges.length}</span>
        <span>⚡ {player.sparks || 0}</span>
      </div>
      {level.next && (
        <div className="progress-wrap">
          <div className="progress-label">
            Next: {level.next.title} — {player.xp}/{level.next.threshold} XP
          </div>
          <div className="progress">
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
        </div>
      )}
    </div>
  )
}

export default function Home({ player, onStart, onExpedition, onStats, onBoard, onSwitch }) {
  return (
    <div className="shell center">
      <h1 className="logo">🗺️ Summer Quest</h1>
      <p className="tagline">Level up your brain. 15 minutes a day.</p>
      <div className="card welcome">
        <h2>Welcome back, {player.name}! 👋</h2>
        <Hud player={player} />
        <div className="stack">
          <button className="btn primary big" onClick={onStart}>
            ⚔️ Start today's quest
          </button>
          <button className="btn big" onClick={onExpedition}>
            🧭 Expedition <span className="muted">— trivia for ⚡ & stickers</span>
          </button>
          <div className="row">
            <button className="btn grow" onClick={onStats}>
              📊 My stats
            </button>
            <button className="btn grow" onClick={onBoard}>
              🏆 Leaderboard
            </button>
          </div>
        </div>
      </div>
      <button className="link" onClick={onSwitch}>
        Not {player.name}? Switch player
      </button>
      <div className="foot-row">
        <ThemePicker />
        <AiDot />
      </div>
    </div>
  )
}
