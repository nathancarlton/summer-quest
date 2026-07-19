import { useEffect, useState } from 'react'
import { api } from './api.js'

// Tiny parent-facing indicator: is MiniMax alive behind the scenes?
// Green = last AI call worked · red = last call failed · gray = no key ·
// amber = no AI call yet since the server booted. Click = live re-test
// (fires a real one-word chat request on the backend).
const LABELS = {
  ok: 'AI online — fresh questions & real grading',
  error: 'AI ERROR — running on the offline question pack',
  no_key: 'No AI key configured — offline question pack only',
  unknown: 'AI idle since server start — click to test',
}

export default function AiDot() {
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)

  useEffect(() => {
    api.aiStatus().then(setStatus).catch(() =>
      setStatus({ state: 'error', detail: 'backend unreachable' }),
    )
  }, [])

  const probe = async () => {
    if (busy) return
    setBusy(true)
    try {
      setStatus(await api.aiStatus(true))
    } catch {
      setStatus({ state: 'error', detail: 'backend unreachable' })
    }
    setBusy(false)
  }

  const state = status?.state || 'unknown'
  const title = busy
    ? 'Testing the AI connection…'
    : `${LABELS[state] || 'AI status unknown'}${status?.detail ? ` (${status.detail})` : ''} — click to re-test`
  return (
    <button
      type="button"
      className={`ai-dot ai-${busy ? 'busy' : state}`}
      onClick={probe}
      title={title}
      aria-label={title}
    />
  )
}
