// Color themes: applied as data-theme on <html>, remembered per device.
export const THEMES = [
  { key: 'sunset', label: 'Sunset', dot: 'linear-gradient(135deg, #fde68a, #f9a8d4)' },
  { key: 'ocean', label: 'Ocean', dot: 'linear-gradient(135deg, #7dd3fc, #818cf8)' },
  { key: 'forest', label: 'Forest', dot: 'linear-gradient(135deg, #86efac, #5eead4)' },
  { key: 'midnight', label: 'Midnight', dot: 'linear-gradient(135deg, #312e81, #4c1d95)' },
  { key: 'paperback', label: 'Paperback', dot: 'linear-gradient(135deg, #f3e5c8, #c9a878)' },
]

const STORED_THEME = 'sq_theme'

export function savedTheme() {
  const t = localStorage.getItem(STORED_THEME)
  return THEMES.some((x) => x.key === t) ? t : 'sunset'
}

export function applyTheme(key) {
  document.documentElement.dataset.theme = key
  localStorage.setItem(STORED_THEME, key)
}
