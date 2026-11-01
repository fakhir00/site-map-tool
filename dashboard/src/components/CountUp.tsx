import { useCountUp } from '../lib/useCountUp'

type Props = {
  value: number
  duration?: number
  className?: string
}

/** Animated number that counts up from 0 (respects prefers-reduced-motion). */
export function CountUp({ value, duration, className }: Props) {
  const display = useCountUp(value, duration)
  return <span className={className}>{display.toLocaleString()}</span>
}
