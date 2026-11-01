import React from "react"
import { cn } from "../../lib/utils"

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm text-slate-950 file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-slate-400 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-site-sky disabled:cursor-not-allowed disabled:bg-slate-100 disabled:text-slate-500 dark:border-line dark:bg-raised dark:text-text dark:placeholder:text-muted/60 dark:focus-visible:border-site-sky/60 dark:disabled:bg-panel dark:disabled:text-muted",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"
