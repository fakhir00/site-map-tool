import React from "react"
import { cn } from "../../lib/utils"

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        // Drafting-table paper: panel bg, hairline border, top inner highlight
        "rounded-2xl border border-line bg-panel p-5 text-text shadow-[inset_0_1px_0_rgba(255,255,255,0.07),0_12px_32px_-16px_rgba(0,0,0,0.6)] dark:border-line dark:bg-panel dark:text-text",
        className
      )}
      {...props}
    />
  )
}
