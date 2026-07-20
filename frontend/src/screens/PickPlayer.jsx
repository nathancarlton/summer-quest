import FontPicker from '../FontPicker.jsx'
import ThemePicker from '../ThemePicker.jsx'

export default function PickPlayer({ roster, onPick, onNew, onAdmin }) {
  return (
    <div className="shell center">
      <h1 className="logo">🗺️ Summer Quest</h1>
      <div className="card">
        <h2>Who's playing today?</h2>
        <div className="stack">
          {roster.map((p) => (
            <button key={p.id} className="btn player-row" onClick={() => onPick(p)}>
              <span className="player-name">{p.name}</span>
              <span className="player-meta">{p.has_secret ? '🔐' : '✨ set up'}</span>
            </button>
          ))}
          <button className="btn ghost" onClick={onNew}>
            ✨ New adventurer
          </button>
        </div>
      </div>
      <div className="foot-row">
        <ThemePicker />
        <FontPicker />
      </div>
      <button className="link" onClick={onAdmin}>
        🔧 Parent zone
      </button>
    </div>
  )
}
