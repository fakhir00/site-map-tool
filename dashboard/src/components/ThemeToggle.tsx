import { Moon, Sun } from 'lucide-react'
import { useTheme } from './themeContext'
import { Button } from './ui/Button'

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  return (
    <Button
      variant="ghost"
      size="sm"
      className="w-full justify-start text-muted hover:bg-raised/80 hover:text-ink"
      onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
    >
      {theme === 'light' ? (
        <Moon className="h-4 w-4 mr-3 text-glow-amber" />
      ) : (
        <Sun className="h-4 w-4 mr-3 text-glow-amber" />
      )}
      {theme === 'light' ? 'Dark mode' : 'Light mode'}
    </Button>
  )
}
