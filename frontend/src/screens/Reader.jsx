import { useEffect, useRef, useState } from 'react'
import { api } from '../api.js'

// Chapter reader. Opening a chapter starts its quiz brewing in the
// background; by the time the kid reaches the bottom, the quiz is
// usually ready.
export default function Reader({ player, book, chapter, onQuiz, onNavigate, onBack }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [quizState, setQuizState] = useState('idle') // idle|starting|brewing
  const topRef = useRef(null)

  useEffect(() => {
    setData(null)
    setError('')
    setQuizState('idle')
    api.chapter(player.id, book, chapter).then((d) => {
      setData(d)
      topRef.current?.scrollIntoView()
    }).catch((e) => setError(e.message))
  }, [player.id, book, chapter])

  const takeQuiz = async () => {
    setQuizState('starting')
    try {
      await api.finishChapter(player.id, book, chapter)
      const resp = await api.startReadingQuiz(player.id, book, chapter)
      onQuiz(resp)
    } catch (e) {
      if (e.status === 425) setQuizState('brewing')
      else {
        setError(e.message)
        setQuizState('idle')
      }
    }
  }

  const markDoneAndNext = async () => {
    try {
      await api.finishChapter(player.id, book, chapter)
    } catch { /* progress marking is best-effort */ }
    onNavigate(chapter + 1)
  }

  if (error)
    return (
      <div className="shell center">
        <div className="card">
          <p className="error">{error}</p>
          <button className="btn primary" onClick={onBack}>Back to the library</button>
        </div>
      </div>
    )
  if (!data)
    return (
      <div className="shell center">
        <div className="spinner" />
        <p className="muted">Turning to your page…</p>
      </div>
    )

  return (
    <div className="shell">
      <div className="quest-top" ref={topRef}>
        <button className="link" onClick={onBack}>← Library</button>
        <span className="q-cat">
          Chapter {data.index + 1}/{data.chapters}
          {data.quizzed && ' · 📝 quizzed'}
        </span>
      </div>
      <div className="card reader-card">
        <h2>{data.chapter_title}</h2>
        <div className="reader-text">{data.text}</div>
        <div className="stack">
          {!data.quizzed && (
            <button
              className="btn primary big"
              onClick={takeQuiz}
              disabled={quizState === 'starting'}
            >
              {quizState === 'starting'
                ? 'Getting your quiz…'
                : '📝 Quiz this chapter (+XP)'}
            </button>
          )}
          {quizState === 'brewing' && (
            <p className="muted center-text">
              ✍️ The quiz for this chapter is still being written — read on and
              come back, or try again in a minute!
            </p>
          )}
          <div className="row">
            {data.index > 0 && (
              <button className="btn grow" onClick={() => onNavigate(chapter - 1)}>
                ← Previous
              </button>
            )}
            {data.index + 1 < data.chapters && (
              <button className="btn grow" onClick={markDoneAndNext}>
                Next chapter →
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
