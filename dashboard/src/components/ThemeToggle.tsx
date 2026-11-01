import { Moon, Sun } from 'lucide-react'
import { useTheme } from './themeContext'
import { Button } from './ui/Button'

interface ThemeToggleProps {
  /** Icon-only plate for topbars; full label row for drawer footers. */
  compact?: boolean
}

export function ThemeToggle({ compact = false }: ThemeToggleProps) {
  const { theme, setTheme } = useTheme()
  const next = theme === 'light' ? 'dark' : 'light'

  if (compact) {
    return (
      <Button
        aria-label={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
        className="h-9 w-9 p-0 border border-line bg-panel text-amber hover:border-amber/60 hover:bg-raised"
        onClick={() => setTheme(next)}
        size="sm"
        title={theme === 'light' ? 'Switch to dark mode' : 'Switch to light mode'}
        variant="ghost"
      >
        {theme === 'light' ? (
          <Moon className="h-4 w-4" />
        ) : (
          <Sun className="h-4 w-4" />
        )}
      </Button>
    )
  }

  return (
    <Button
      variant="ghost"
      size="sm"
      className="w-full justify-between border border-line bg-panel text-muted hover:border-amber/60 hover:text-text"
      onClick={() => setTheme(next)}
    >
      <span className="flex items-center">
        {theme === 'light' ? (
          <Moon className="mr-3 h-4 w-4 text-amber" />
        ) : (
          <Sun className="h-4 w-4 mr-3 text-amber" />
        )}
        <span className="font-mono text-[11px] uppercase tracking-[0.18em]">
          {theme === 'light' ? 'Dark mode' : 'Light mode'}
        </span>
      </span>
      <span className="font-mono text-[10px] uppercase tracking-[0.18em] opacity-60">Theme</span>
    </Button>
  )
}
