import React from "react"
import { cn } from "../../lib/utils"

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-slate-200 bg-white p-5 text-slate-950 shadow-sm dark:border-line dark:bg-panel dark:text-text",
        className
      )}
      {...props}
    />
  )
}
