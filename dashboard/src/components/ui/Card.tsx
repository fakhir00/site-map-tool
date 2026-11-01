import React from "react"
import { cn } from "../../lib/utils"

export interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  lift?: boolean
}

export function Card({ className, lift = true, ...props }: CardProps) {
  return (
    <div
      className={cn(
        "rounded-2xl border border-white/8 bg-surface p-5 text-ink shadow-[0_8px_24px_rgba(0,0,0,0.35)]",
        lift && "card-lift",
        className
      )}
      {...props}
    />
  )
}
