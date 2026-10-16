import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import App from './App.tsx'
import './i18n'
import { applyTheme, readTheme } from './lib/theme'
import './styles/tokens.css'
import './index.css'

// The saved theme goes on the page before the first paint.
applyTheme(readTheme())

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
