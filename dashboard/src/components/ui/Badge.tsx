import React from "react"
import { cn } from "../../lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'teal' | 'indigo' | 'slate' | 'red' | 'green' | 'amber' | 'cyan'
}

export function Badge({ className, variant = 'slate', ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 font-mono text-[0.6875rem] font-medium uppercase tracking-[0.12em] transition-colors focus:outline-none focus:ring-2 focus:ring-amber focus:ring-offset-2 focus:ring-offset-ink",
        {
          // existing / your data — sky
          'border-sky/40 bg-sky/10 text-sky dark:border-sky/40 dark:bg-sky/10 dark:text-sky': variant === 'teal' || variant === 'cyan',
          // neutral label — muted
          'border-line bg-raised text-muted dark:border-line dark:bg-raised dark:text-muted': variant === 'indigo' || variant === 'slate',
          // error — red
          'border-red/50 bg-red/10 text-red dark:border-red/50 dark:bg-red/10 dark:text-red': variant === 'red',
          // done — green
          'border-green/50 bg-green/10 text-green dark:border-green/50 dark:bg-green/10 dark:text-green': variant === 'green',
          // missing / attention — amber outline
          'border-amber/60 bg-amber/10 text-amber dark:border-amber/60 dark:bg-amber/10 dark:text-amber': variant === 'amber',
        },
        className
      )}
      {...props}
    />
  )
}
