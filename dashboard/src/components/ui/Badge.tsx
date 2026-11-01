import React from "react"
import { cn } from "../../lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'teal' | 'indigo' | 'slate' | 'red' | 'green' | 'amber' | 'cyan'
}

export function Badge({ className, variant = 'slate', ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus-visible:ring-2 focus-visible:ring-site-sky",
        {
          // Existing / yours data — Site Sky
          'border-sky-200 bg-sky-50 text-sky-800 dark:border-site-sky/30 dark:bg-site-sky/10 dark:text-site-sky': variant === 'teal',
          'border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-line dark:bg-site-sky/10 dark:text-site-sky': variant === 'indigo',
          // Neutral
          'border-slate-200 bg-slate-100 text-slate-700 dark:border-line dark:bg-raised dark:text-muted': variant === 'slate',
          // Errors only — Signal Red
          'border-rose-200 bg-rose-50 text-rose-700 dark:border-signal-red/30 dark:bg-signal-red/10 dark:text-signal-red': variant === 'red',
          // Success — Built Green
          'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-built-green/30 dark:bg-built-green/10 dark:text-built-green': variant === 'green',
          // Missing things — Signal Amber
          'border-amber-200 bg-amber-50 text-amber-800 dark:border-signal-amber/30 dark:bg-signal-amber/10 dark:text-signal-amber': variant === 'amber',
          // Existing / yours data — Site Sky
          'border-cyan-200 bg-cyan-50 text-cyan-800 dark:border-site-sky/30 dark:bg-site-sky/10 dark:text-site-sky': variant === 'cyan',
        },
        className
      )}
      {...props}
    />
  )
}
