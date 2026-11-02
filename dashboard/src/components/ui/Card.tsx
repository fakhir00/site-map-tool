import React from "react"
import { cn } from "../../lib/utils"

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  lift?: boolean
}

export function Card({ className, lift = true, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-overlay/8 bg-surface p-5 text-ink shadow-card",
        lift && "card-lift",
        className
      )}
      {...props}
    />
  )
}
