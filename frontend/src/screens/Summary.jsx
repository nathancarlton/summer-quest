// ui.session_summary: score, XP, streak bonus, newly unlocked badges.
export default function Summary({ summary, onHome }) {
  return (
    <div className="shell center">
      <div className="card">
        <h2>🏁 Quest Complete, {summary.player.name}!</h2>
        <table className="summary-table">
          <tbody>
            <tr>
              <td>Score</td>
              <td>
                {summary.score}/{summary.total}
              </td>
            </tr>
            <tr>
              <td>XP earned</td>
              <td>+{summary.xp_gained}</td>
            </tr>
            {summary.streak_bonus > 0 && (
              <tr>
                <td>Streak bonus</td>
                <td>+{summary.streak_bonus}</td>
              </tr>
            )}
          </tbody>
        </table>
        {summary.new_badges.map((b) => (
          <div key={b.key} className="badge-unlock">
            <div className="badge-title">NEW BADGE UNLOCKED!</div>
            <div>
              {b.label} — {b.desc}
            </div>
          </div>
        ))}
        <button className="btn primary big" onClick={onHome}>
          Back to camp 🏕️
        </button>
      </div>
    </div>
  )
}
