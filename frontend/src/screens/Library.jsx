import { useEffect, useState } from 'react'
import { api } from '../api.js'

// The Reading Room shelf: eight public-domain classics with per-kid
// progress. Chapter counts appear after a book's first open (that's when
// the backend fetches and caches it).
export default function Library({ player, onOpen, onBack }) {
  const [shelf, setShelf] = useState(null)
  const [error, setError] = useState('')

  useEffect(() => {
    api.books(player.id).then(setShelf).catch((e) => setError(e.message))
  }, [player.id])

  return (
    <div className="shell center">
      <h1 className="logo">📖 Reading Room</h1>
      <p className="tagline">Real classic adventures — quiz each chapter for XP!</p>
      <div className="card">
        {error && <p className="error">{error}</p>}
        {!shelf && !error && <p className="muted">Opening the library…</p>}
        {shelf && (
          <div className="stack">
            {shelf.map((b) => (
              <button
                key={b.key}
                className="btn book-row"
                onClick={() => onOpen(b.key, Math.min(b.finished_through, (b.chapters ?? 1) - 1))}
              >
                <span className="book-emoji">{b.emoji}</span>
                <span className="book-info">
                  <span className="book-title">{b.title}</span>
                  <span className="book-author">{b.author}</span>
                </span>
                <span className="book-progress">
                  {b.chapters
                    ? b.finished_through >= b.chapters
                      ? '✅ Finished!'
                      : `Ch ${b.finished_through + 1}/${b.chapters}`
                    : b.finished_through > 0
                      ? `Ch ${b.finished_through + 1}`
                      : 'New!'}
                  {b.quizzed_count > 0 && <span className="book-quizzed">📝 {b.quizzed_count}</span>}
                </span>
              </button>
            ))}
          </div>
        )}
        <p className="bonus-note">
          Public-domain texts via Project Gutenberg.
        </p>
        <button className="btn primary" onClick={onBack}>
          Back
        </button>
      </div>
    </div>
  )
}
