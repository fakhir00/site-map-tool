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
          'border-cyan-200 bg-cyan-50 text-cyan-800': variant === 'teal',
          'border-indigo-200 bg-indigo-50 text-indigo-700': variant === 'indigo',
          'border-slate-200 bg-slate-100 text-slate-700': variant === 'slate',
          'border-rose-200 bg-rose-50 text-rose-700': variant === 'red',
          'border-emerald-200 bg-emerald-50 text-emerald-700': variant === 'green',
          'border-amber-200 bg-amber-50 text-amber-700': variant === 'amber',
          'border-sky-200 bg-sky-50 text-sky-700': variant === 'cyan',
        },
        className
      )}
      {...props}
    />
  )
}
