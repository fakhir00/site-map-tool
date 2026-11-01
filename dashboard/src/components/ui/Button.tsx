import React from "react"
import { cn } from "../../lib/utils"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-lg font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-site-sky focus-visible:ring-offset-2 focus-visible:ring-offset-transparent disabled:pointer-events-none disabled:opacity-50",
          {
            // Primary CTA — Signal Amber only, one per screen by design
            'bg-signal-amber text-blueprint-deep hover:bg-signal-amber/90 active:bg-signal-amber/80': variant === 'primary',
            // Secondary — ghost/outline on navy
            'border border-slate-300 bg-white text-slate-800 hover:bg-slate-50 dark:border-line dark:bg-transparent dark:text-text dark:hover:bg-raised': variant === 'secondary',
            // Ghost — subtle
            'text-slate-600 hover:bg-slate-100 hover:text-slate-950 dark:text-muted dark:hover:bg-raised dark:hover:text-text': variant === 'ghost',
            // Danger — Signal Red, errors only
            'bg-signal-red text-blueprint-deep hover:bg-signal-red/90 active:bg-signal-red/80': variant === 'danger',
            'h-8 px-3 text-sm': size === 'sm',
            'h-10 px-4 text-sm': size === 'md',
            'h-12 px-5 text-base': size === 'lg',
          },
          className
        )}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"
