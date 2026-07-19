import { useState } from 'react'
import AiDot from '../AiDot.jsx'
import { api } from '../api.js'
import { CATEGORY_LABELS, CHEERS, ENCOURAGE, pick } from '../constants.js'

// Anticipation interstitial before the final question of a daily quest:
// size up the run so far, then unleash the boss.
function BossIntro({ correctSoFar, total, onReady }) {
  const answered = total - 1
  const pct = answered ? correctSoFar / answered : 0
  let hype
  if (correctSoFar === answered)
    hype = `PERFECT RUN — ${correctSoFar}/${answered} so far! One more and you're FLAWLESS.`
  else if (pct >= 0.7)
    hype = "You've been ON FIRE today. Time to finish the job."
  else if (pct >= 0.5)
    hype = 'A hard-fought quest… and heroes finish STRONG.'
  else
    hype = 'This quest has been BRUTAL. But one mighty swing changes everything!'
  return (
    <div className="card boss-card">
      <div className="boss-skull">👹</div>
      <h2 className="boss-title">THE BOSS APPROACHES…</h2>
      <p className="boss-hype">{hype}</p>
      <p className="boss-stats">
        {correctSoFar}/{answered} correct this quest · the boss is worth{' '}
        <strong>DOUBLE XP</strong>
      </p>
      <button className="btn boss-btn big" onClick={onReady}>
        ⚔️ FACE THE BOSS
      </button>
    </div>
  )
}

// The game loop from session.py: ask -> grade -> reveal -> next. Daily quests
// end in a double-XP boss battle; expeditions are 5 trivia questions paying
// Sparks (⚡) instead of XP.
export default function Quest({ quest, onFinish }) {
  const [index, setIndex] = useState(0)
  const [written, setWritten] = useState('')
  const [result, setResult] = useState(null) // grading reveal for current q
  const [cheer, setCheer] = useState('')
  const [correctSoFar, setCorrectSoFar] = useState(0)
  const [bossFaced, setBossFaced] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  // Appeals: null | 'busy' | {overturned, message, xp_awarded} — reset per question
  const [challenge, setChallenge] = useState(null)
  const [reported, setReported] = useState(false)

  const questions = quest.questions
  const q = questions[index]
  const isExpedition = quest.kind === 'expedition'
  const isBoss = !isExpedition && index === questions.length - 1
  const isLastReveal = result && index === questions.length - 1
  const pointsLabel = isExpedition ? '⚡' : 'XP'

  const submit = async (answer) => {
    if (busy || result) return
    setBusy(true)
    setError('')
    try {
      const r = await api.answer(quest.quest_id, answer)
      setCheer(pick(r.correct ? CHEERS : ENCOURAGE))
      if (r.correct) setCorrectSoFar((c) => c + 1)
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
    setChallenge(null)
    setReported(false)
    setIndex(index + 1)
  }

  const challengeRuling = async () => {
    if (challenge) return
    setChallenge('busy')
    try {
      const c = await api.challenge(quest.quest_id, index)
      setChallenge(c)
      if (c.overturned) setCorrectSoFar((n) => n + 1)
    } catch (e) {
      setChallenge({ overturned: false, message: e.message })
    }
  }

  const reportIssue = async () => {
    if (reported) return
    setReported(true)
    try {
      await api.report(quest.quest_id, index)
    } catch {
      /* fire-and-forget: don't interrupt the kid's flow */
    }
  }

  const header = isExpedition
    ? `${quest.topic.emoji} ${quest.topic.name}`
    : CATEGORY_LABELS[q.category] || q.category

  const showBossIntro = isBoss && !bossFaced && !result

  return (
    <div className="shell">
      <div className="quest-top">
        <span className="q-count">
          Question {index + 1}/{questions.length}
        </span>
        <span className="q-cat">
          {header} <AiDot />
        </span>
      </div>
      <div className="progress slim">
        <div
          className="progress-fill"
          style={{ width: `${((index + (result ? 1 : 0)) / questions.length) * 100}%` }}
        />
      </div>

      {showBossIntro ? (
        <BossIntro
          correctSoFar={correctSoFar}
          total={questions.length}
          onReady={() => setBossFaced(true)}
        />
      ) : (
        <>
          {isBoss && <div className="boss-banner">👹 BOSS BATTLE — double XP!</div>}

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

            {busy && q.type === 'mc' && !result && (
              <p className="muted center-text">Checking…</p>
            )}

            {result && (
              <div className={`result ${result.correct ? 'win' : 'lose'}`}>
                <div className="result-head">
                  {result.correct ? '🎉 ✨ ⭐' : '💪 💪 💪'}
                </div>
                <div className="result-cheer">{cheer}</div>
                {result.correct ? (
                  <div className="result-xp">
                    CORRECT! +{result.xp_gained} {pointsLabel}
                  </div>
                ) : (
                  <div className="result-answer">
                    {q.type === 'mc' ? `The answer was ${result.answer}.` : ''}
                  </div>
                )}
                {result.feedback && <p className="result-feedback">{result.feedback}</p>}

                {!result.correct && (
                  <div className="appeal-zone">
                    {challenge === null && (
                      <button className="btn appeal-btn" onClick={challengeRuling}>
                        ⚖️ Wait — I think I'm right! Challenge it
                      </button>
                    )}
                    {challenge === 'busy' && (
                      <p className="muted center-text">
                        ⚖️ The appeals judge is reviewing your answer…
                      </p>
                    )}
                    {challenge && challenge !== 'busy' && (
                      <div className={`verdict ${challenge.overturned ? 'verdict-win' : ''}`}>
                        {challenge.overturned && (
                          <div className="result-xp">
                            ⚖️ OVERRULED — you were right! +{challenge.xp_awarded}{' '}
                            {pointsLabel}
                          </div>
                        )}
                        <p className="result-feedback">{challenge.message}</p>
                      </div>
                    )}
                    <button
                      className="link"
                      onClick={reportIssue}
                      disabled={reported}
                    >
                      {reported
                        ? '📮 Sent to the game developers ✅'
                        : '📮 Report this question to the game developers'}
                    </button>
                  </div>
                )}

                <button className="btn primary big" onClick={next} disabled={busy || challenge === 'busy'}>
                  {busy
                    ? 'Finishing…'
                    : isLastReveal
                      ? '🏁 Finish'
                      : 'Next question ➜'}
                </button>
              </div>
            )}

            {error && <p className="error">{error}</p>}
          </div>
        </>
      )}
    </div>
  )
}
