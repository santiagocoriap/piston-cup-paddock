// The color theme: "noche" (dark, the default) or "dia" (light). Each browser keeps its choice.
export type Theme = 'noche' | 'dia'

const THEME_KEY = 'paddock.theme'

export function readTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === 'dia' ? 'dia' : 'noche'
  } catch {
    return 'noche'
  }
}

export function applyTheme(theme: Theme): void {
  document.documentElement.dataset.theme = theme
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {
    // Private windows can refuse storage. The theme then lasts for this page only.
  }
}
