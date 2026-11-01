import { Moon, Sun } from 'lucide-react'
import { useTheme } from './themeContext'
import { Button } from './ui/Button'

export function ThemeToggle() {
  const { theme, setTheme } = useTheme()

  return (
    <Button
      variant="ghost"
      size="sm"
      className="w-full justify-start text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-muted dark:hover:bg-raised dark:hover:text-slate-50"
      onClick={() => setTheme(theme === 'light' ? 'dark' : 'light')}
    >
      {theme === 'light' ? (
        <Moon className="h-4 w-4 mr-3" />
      ) : (
        <Sun className="h-4 w-4 mr-3" />
      )}
      {theme === 'light' ? 'Dark mode' : 'Light mode'}
    </Button>
  )
}
