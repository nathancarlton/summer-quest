// Font choices: applied as data-font on <html>, remembered per device.
export const FONTS = [
  { key: 'fredoka', label: 'Playful', family: "'Fredoka', system-ui, sans-serif" },
  { key: 'nunito', label: 'Friendly', family: "'Nunito', system-ui, sans-serif" },
  { key: 'inter', label: 'Clean', family: "'Inter', system-ui, sans-serif" },
]

const STORED_FONT = 'sq_font'

export function savedFont() {
  const f = localStorage.getItem(STORED_FONT)
  return FONTS.some((x) => x.key === f) ? f : 'fredoka'
}

export function applyFont(key) {
  document.documentElement.dataset.font = key
  localStorage.setItem(STORED_FONT, key)
}
