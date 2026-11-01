import React from "react"
import { cn } from "../../lib/utils"

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-lg border border-line bg-ink px-3 py-2 text-sm text-text font-mono file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:font-sans placeholder:text-muted/60 focus-visible:outline-none focus-visible:border-amber/70 focus-visible:ring-2 focus-visible:ring-amber/40 disabled:cursor-not-allowed disabled:opacity-50 transition-colors dark:border-line dark:bg-ink dark:text-text dark:placeholder:text-muted/60",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"
