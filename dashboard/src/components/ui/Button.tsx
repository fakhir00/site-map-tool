import React from "react"
import { cn } from "../../lib/utils"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost' | 'danger' | 'draft'
  size?: 'sm' | 'md' | 'lg'
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-lg font-display font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber focus-visible:ring-offset-2 focus-visible:ring-offset-ink active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50",
          {
            // Solid amber — the hero CTA
            'bg-amber text-ink shadow-[0_6px_20px_-8px_rgba(245,165,36,0.7)] hover:brightness-110 dark:bg-amber dark:text-ink': variant === 'primary',
            // Transparent with hairline border
            'border border-line bg-transparent text-text hover:border-amber/60 hover:bg-raised hover:text-text dark:border-line dark:bg-transparent dark:text-text': variant === 'secondary',
            'text-muted hover:bg-raised hover:text-text dark:text-muted dark:hover:bg-raised dark:hover:text-text': variant === 'ghost',
            // Danger keeps a drafting-red stamp feel
            'bg-red/90 text-ink hover:bg-red dark:bg-red/90 dark:hover:bg-red': variant === 'danger',
            // Drafting action — small mono uppercase markup button
            'font-mono text-xs uppercase tracking-[0.14em] border border-dashed border-amber/60 bg-transparent text-amber hover:border-amber hover:bg-amber/10': variant === 'draft',
            'h-8 px-3 text-sm': size === 'sm',
            'h-10 px-4 text-sm': size === 'md',
            'h-12 px-5 text-base': size === 'lg',
          },
          // draft variant forces a compact size
          variant === 'draft' && 'h-8 px-3',
          className
        )}
        {...props}
      />
    )
  }
)
Button.displayName = "Button"
