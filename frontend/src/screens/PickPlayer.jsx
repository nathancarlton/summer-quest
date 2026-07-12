import ThemePicker from '../ThemePicker.jsx'

export default function PickPlayer({ roster, onPick, onNew }) {
  return (
    <div className="shell center">
      <h1 className="logo">🗺️ Summer Quest</h1>
      <div className="card">
        <h2>Who's playing today?</h2>
        <div className="stack">
          {roster.map((p) => (
            <button key={p.id} className="btn player-row" onClick={() => onPick(p.id)}>
              <span className="player-name">{p.name}</span>
              <span className="player-meta">
                ⭐ {p.xp} XP &nbsp; 🔥 {p.streak}
              </span>
            </button>
          ))}
          <button className="btn ghost" onClick={onNew}>
            ✨ New adventurer
          </button>
        </div>
      </div>
      <ThemePicker />
    </div>
  )
}
