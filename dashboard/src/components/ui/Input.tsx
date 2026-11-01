import React from "react"
import { cn } from "../../lib/utils"

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-10 w-full rounded-xl border border-line bg-raised px-3 py-2 text-sm text-ink file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted/70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-glow-amber/40 focus-visible:border-glow-amber/60 disabled:cursor-not-allowed disabled:opacity-50 transition-colors",
          className
        )}
        ref={ref}
        {...props}
      />
    )
  }
)
Input.displayName = "Input"
