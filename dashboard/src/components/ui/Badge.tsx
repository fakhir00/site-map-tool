import React from "react"
import { cn } from "../../lib/utils"

export interface BadgeProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: 'teal' | 'indigo' | 'slate' | 'red' | 'green' | 'amber' | 'cyan'
}

export function Badge({ className, variant = 'slate', ...props }: BadgeProps) {
  return (
    <div
      className={cn(
        "inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
        {
          'border-cyan-200 bg-cyan-50 text-cyan-800 dark:border-cyan-800/50 dark:bg-cyan-900/30 dark:text-cyan-300': variant === 'teal',
          'border-indigo-200 bg-indigo-50 text-indigo-700 dark:border-indigo-800/50 dark:bg-indigo-900/30 dark:text-indigo-300': variant === 'indigo',
          'border-slate-200 bg-slate-100 text-slate-700 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300': variant === 'slate',
          'border-rose-200 bg-rose-50 text-rose-700 dark:border-rose-800/50 dark:bg-rose-900/30 dark:text-rose-300': variant === 'red',
          'border-emerald-200 bg-emerald-50 text-emerald-700 dark:border-emerald-800/50 dark:bg-emerald-900/30 dark:text-emerald-300': variant === 'green',
          'border-amber-200 bg-amber-50 text-amber-700 dark:border-amber-800/50 dark:bg-amber-900/30 dark:text-amber-300': variant === 'amber',
          'border-sky-200 bg-sky-50 text-sky-700 dark:border-sky-800/50 dark:bg-sky-900/30 dark:text-sky-300': variant === 'cyan',
        },
        className
      )}
      {...props}
    />
  )
}
