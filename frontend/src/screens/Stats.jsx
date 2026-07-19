import { CATEGORY_LABELS, TOPIC_META } from '../constants.js'
import { Hud } from './Home.jsx'

// ui.show_stats: the report card — per-category accuracy + badge collection.
export default function Stats({ player, onBack }) {
  const rows = Object.entries(player.categories)
    .filter(([, s]) => s.answered > 0)
    .map(([cat, s]) => ({
      cat,
      label: CATEGORY_LABELS[cat] || cat,
      correct: s.correct,
      answered: s.answered,
      acc: s.correct / s.answered,
    }))

  const color = (acc) => (acc >= 0.8 ? 'good' : acc >= 0.6 ? 'ok' : 'bad')

  return (
    <div className="shell center">
      <h1 className="logo">📊 My Stats</h1>
      <div className="card">
        <Hud player={player} />
        <p className="muted">
          Challenge level: {'⭐'.repeat(player.difficulty || 2)} ({player.difficulty || 2}/5)
        </p>
        {rows.length ? (
          <table className="stats-table">
            <thead>
              <tr>
                <th>Category</th>
                <th>Correct</th>
                <th>Accuracy</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.cat}>
                  <td>{r.label}</td>
                  <td>
                    {r.correct}/{r.answered}
                  </td>
                  <td className={color(r.acc)}>{Math.round(r.acc * 100)}%</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <p className="muted">Complete a quest to see your report card!</p>
        )}
        {Object.keys(player.stickers || {}).length > 0 && (
          <div className="badge-box">
            <div className="label">
              Sticker Book · ⚡ {player.sparks || 0} Sparks
            </div>
            <div className="sticker-shelf">
              {Object.entries(player.stickers).map(([key, count]) => (
                <span
                  key={key}
                  className="sticker-chip"
                  title={TOPIC_META[key]?.name || key}
                >
                  {TOPIC_META[key]?.emoji || '🎖️'} ×{count}
                </span>
              ))}
            </div>
          </div>
        )}
        {player.badge_details.length > 0 && (
          <div className="badge-box">
            <div className="label">Badge Collection</div>
            {player.badge_details.map((b) => (
              <div key={b.key} className="badge-row" title={b.desc}>
                {b.label}
              </div>
            ))}
          </div>
        )}
        <button className="btn primary" onClick={onBack}>
          Back
        </button>
      </div>
    </div>
  )
}
