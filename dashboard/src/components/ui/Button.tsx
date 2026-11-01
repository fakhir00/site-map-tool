import React from "react"
import { cn } from "../../lib/utils"

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'glow' | 'secondary' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg'
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant = 'primary', size = 'md', ...props }, ref) => {
    return (
      <button
        ref={ref}
        className={cn(
          "inline-flex items-center justify-center gap-2 rounded-xl font-semibold transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-glow-amber/40 disabled:pointer-events-none disabled:opacity-50 cursor-pointer active:scale-[0.97]",
          {
            'bg-glow-amber text-abyss hover:bg-[#ffb63d]': variant === 'primary',
            'glow-cta': variant === 'glow',
            'border border-line bg-raised text-ink hover:bg-surface hover:border-white/15': variant === 'secondary',
            'text-muted hover:bg-white/5 hover:text-ink': variant === 'ghost',
            'bg-warm-red text-abyss hover:brightness-110': variant === 'danger',
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
