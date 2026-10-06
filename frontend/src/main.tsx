import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import '@fontsource/graduate'
import '@fontsource-variable/fraunces'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// Fade out the Handsome Dan splash once React has painted.
requestAnimationFrame(() => {
  const splash = document.getElementById('splash')
  if (!splash) return
  setTimeout(() => {
    splash.classList.add('done')
    setTimeout(() => splash.remove(), 600)
  }, 500)
})
