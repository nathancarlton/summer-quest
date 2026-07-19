import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App.jsx'
import { applyTheme, savedTheme } from './theme.js'
import { applyFont, savedFont } from './font.js'
import './styles.css'

applyTheme(savedTheme())
applyFont(savedFont())

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
)
