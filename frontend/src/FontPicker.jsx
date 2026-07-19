import { useState } from 'react'
import { FONTS, applyFont, savedFont } from './font.js'

// "Aa" chips, each rendered in its own typeface so the choice previews itself.
export default function FontPicker() {
  const [font, setFont] = useState(savedFont())
  const choose = (key) => {
    applyFont(key)
    setFont(key)
  }
  return (
    <div className="font-picker" role="group" aria-label="Font">
      {FONTS.map((f) => (
        <button
          key={f.key}
          type="button"
          title={`${f.label} font`}
          aria-label={`${f.label} font`}
          className={`font-btn ${f.key === font ? 'font-btn-on' : ''}`}
          style={{ fontFamily: f.family }}
          onClick={() => choose(f.key)}
        >
          Aa
        </button>
      ))}
    </div>
  )
}
