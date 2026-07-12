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

export const pick = (arr) => arr[Math.floor(Math.random() * arr.length)]
