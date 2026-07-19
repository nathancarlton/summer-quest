// Mirrors quest/ui.py — the CLI's labels and rotating cheer lines.
export const CATEGORY_LABELS = {
  vocabulary: 'Vocabulary 📖',
  grammar: 'Grammar ✏️',
  reading: 'Reading 🔍',
  figurative_language: 'Figurative Language 🎭',
  writing_mechanics: 'Writing Mechanics 🛠️',
  math_challenge: 'Math Challenge 🧮',
}

export const CHEERS = [
  'BOOM! NAILED IT!', "YOU'RE ON FIRE!", 'ABSOLUTELY CRUSHED IT!',
  'GENIUS ALERT!', 'UNSTOPPABLE!', 'LEGENDARY!', 'JACKPOT!',
  'BRAIN POWER!', 'TOO EASY FOR YOU!', 'SUPERSTAR!',
]

export const ENCOURAGE = [
  "So close — you've totally got this!", 'Not quite, but great try!',
  'Keep going — mistakes help you level up!', 'Almost! Learn it and smash it next time!',
]

export const WORLDS = ['space', 'ocean', 'jungle', 'sports', 'mystery', 'video games']

// Badge-bonus favorite questions — deliberately impersonal (things, places,
// weather; never people), so profiles don't collect identifying details.
export const PREF_QUESTIONS = [
  { key: 'color', q: "What's your favorite color?", ph: 'e.g. teal' },
  { key: 'place', q: "What's a place you'd love to visit someday?", ph: 'e.g. the Grand Canyon' },
  { key: 'instrument', q: "What's a musical instrument you think is cool?", ph: 'e.g. drums' },
  { key: 'sport', q: "What's a sport or activity you enjoy?", ph: 'e.g. rock climbing' },
  { key: 'song', q: "What's a song you love right now?", ph: 'e.g. Bohemian Rhapsody' },
  { key: 'weather', q: "What's your favorite kind of weather?", ph: 'e.g. thunderstorms' },
  { key: 'animal', q: "What's your favorite animal these days?", ph: 'e.g. otter' },
  { key: 'food', q: "What's a food you love these days?", ph: 'e.g. tacos' },
]

// Mirrors quest/expeditions.py TOPICS (names + sticker emoji).
export const TOPIC_META = {
  science: { name: 'Science Lab', emoji: '🧪' },
  nature: { name: 'Wild World', emoji: '🐾' },
  body: { name: 'Body & Food', emoji: '🥦' },
  money: { name: 'Money Matters', emoji: '💰' },
  civics: { name: 'We the People', emoji: '🏛️' },
  geo: { name: 'Map Masters', emoji: '🗺️' },
}

export const pick = (arr) => arr[Math.floor(Math.random() * arr.length)]
