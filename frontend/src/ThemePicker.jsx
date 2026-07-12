import { useState } from 'react'
import { THEMES, applyTheme, savedTheme } from './theme.js'

export default function ThemePicker() {
  const [theme, setTheme] = useState(savedTheme())
  const choose = (key) => {
    applyTheme(key)
    setTheme(key)
  }
  return (
    <div className="theme-picker" role="group" aria-label="Color theme">
      {THEMES.map((t) => (
        <button
          key={t.key}
          type="button"
          title={t.label}
          aria-label={`${t.label} theme`}
          className={`theme-dot ${t.key === theme ? 'theme-dot-on' : ''}`}
          style={{ background: t.dot }}
          onClick={() => choose(t.key)}
        />
      ))}
    </div>
  )
}
