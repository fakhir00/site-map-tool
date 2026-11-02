import React from "react"
import { cn } from "../../lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'teal' | 'indigo' | 'slate' | 'red' | 'green' | 'amber' | 'cyan'
}

export function Badge({ className, variant = 'slate', ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border border-overlay/8 px-2.5 py-0.5 text-xs font-semibold transition-colors",
        {
          'bg-alive-green/10 text-alive-green border-alive-green/20': variant === 'teal',
          'bg-soft-violet/15 text-soft-violet border-soft-violet/20': variant === 'indigo',
          'bg-overlay/5 text-muted': variant === 'slate',
          'bg-warm-red/15 text-warm-red': variant === 'red',
          'bg-alive-green/15 text-alive-green': variant === 'green',
          'bg-glow-amber/15 text-glow-amber': variant === 'amber',
          'bg-soft-violet/15 text-soft-violet': variant === 'cyan',
        },
        className
      )}
      {...props}
    />
  )
}
