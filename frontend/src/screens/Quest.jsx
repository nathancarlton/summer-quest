import { useState } from 'react'
import AiDot from '../AiDot.jsx'
import { api } from '../api.js'
import { CATEGORY_LABELS, CHEERS, ENCOURAGE, pick } from '../constants.js'

// The game loop from session.py: ask -> grade -> reveal -> next; last one is
// the double-XP boss battle.
export default function Quest({ quest, onFinish }) {
  const [index, setIndex] = useState(0)
  const [written, setWritten] = useState('')
  const [result, setResult] = useState(null) // grading reveal for current q
  const [cheer, setCheer] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const questions = quest.questions
  const q = questions[index]
  const isBoss = index === questions.length - 1
  const isLastReveal = result && index === questions.length - 1

  const submit = async (answer) => {
    if (busy || result) return
    setBusy(true)
    setError('')
    try {
      const r = await api.answer(quest.quest_id, answer)
      setCheer(pick(r.correct ? CHEERS : ENCOURAGE))
      setResult(r)
    } catch (e) {
      setError(e.message)
    } finally {
      setBusy(false)
    }
  }

  const next = async () => {
    if (isLastReveal) {
      setBusy(true)
      try {
        await onFinish()
      } catch (e) {
        setError(e.message)
        setBusy(false)
      }
      return
    }
    setResult(null)
    setWritten('')
    setIndex(index + 1)
  }

  return (
    <div className="shell">
      <div className="quest-top">
        <span className="q-count">
          Question {index + 1}/{questions.length}
        </span>
        <span className="q-cat">
          {CATEGORY_LABELS[q.category] || q.category} <AiDot />
        </span>
      </div>
      <div className="progress slim">
        <div
          className="progress-fill"
          style={{ width: `${((index + (result ? 1 : 0)) / questions.length) * 100}%` }}
        />
      </div>

      {isBoss && (
        <div className="boss-banner">👹 BOSS BATTLE — double XP!</div>
      )}

      <div className="card">
        {q.passage && (
          <div className="passage">
            <div className="passage-title">📜 Read this</div>
            {q.passage}
          </div>
        )}
        <h2 className="question">{q.question}</h2>

        {!result && q.type === 'mc' && (
          <div className="stack">
            {q.options.map((opt, i) => (
              <button
                key={i}
                className="btn option"
                disabled={busy}
                onClick={() => submit('ABCD'[i])}
              >
                {opt}
              </button>
            ))}
          </div>
        )}

        {!result && q.type === 'short' && (
          <form
            className="stack"
            onSubmit={(e) => {
              e.preventDefault()
              if (written.trim()) submit(written.trim())
            }}
          >
            <textarea
              value={written}
              onChange={(e) => setWritten(e.target.value)}
              placeholder="Type your answer…"
              rows={3}
              maxLength={2000}
              disabled={busy}
            />
            <button className="btn primary" disabled={busy || !written.trim()}>
              {busy ? '🤔 Evaluating your answer…' : 'Submit answer'}
            </button>
          </form>
        )}

        {busy && q.type === 'mc' && !result && <p className="muted center-text">Checking…</p>}

        {result && (
          <div className={`result ${result.correct ? 'win' : 'lose'}`}>
            <div className="result-head">
              {result.correct ? '🎉 ✨ ⭐' : '💪 💪 💪'}
            </div>
            <div className="result-cheer">{cheer}</div>
            {result.correct ? (
              <div className="result-xp">CORRECT! +{result.xp_gained} XP</div>
            ) : (
              <div className="result-answer">
                {q.type === 'mc' ? `The answer was ${result.answer}.` : ''}
              </div>
            )}
            {result.feedback && <p className="result-feedback">{result.feedback}</p>}
            <button className="btn primary big" onClick={next} disabled={busy}>
              {busy
                ? 'Finishing…'
                : isLastReveal
                  ? '🏁 Finish quest'
                  : 'Next question ➜'}
            </button>
          </div>
        )}

        {error && <p className="error">{error}</p>}
      </div>
    </div>
  )
}
