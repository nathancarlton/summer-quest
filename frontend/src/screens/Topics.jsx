import { TOPIC_META } from '../constants.js'

// Expedition topic picker. Quests train MCA skills; expeditions are trivia
// adventures — Sparks and stickers, a totally separate economy from XP.
export default function Topics({ onPick, onBack }) {
  return (
    <div className="shell center">
      <h1 className="logo">🧭 Expedition</h1>
      <p className="tagline">Trivia adventures — earn ⚡ Sparks and collect stickers!</p>
      <div className="card">
        <h2>Where are we exploring today?</h2>
        <div className="topic-grid">
          {Object.entries(TOPIC_META).map(([key, t]) => (
            <button key={key} className="btn topic-btn" onClick={() => onPick(key)}>
              <span className="topic-emoji">{t.emoji}</span>
              {t.name}
            </button>
          ))}
        </div>
        <button className="btn primary big" onClick={() => onPick(null)}>
          🎲 Surprise me!
        </button>
        <button className="btn ghost" onClick={onBack}>
          Back
        </button>
      </div>
    </div>
  )
}
