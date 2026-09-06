import { createContext, useContext } from 'react'

export type Theme = 'dark' | 'light'
export const ThemeProviderContext = createContext<{ theme: Theme; setTheme: (theme: Theme) => void } | undefined>(undefined)

export function useTheme() {
  const context = useContext(ThemeProviderContext)
  if (!context) throw new Error('useTheme must be used within a ThemeProvider')
  return context
}
