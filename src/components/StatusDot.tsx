import type { JSX } from 'react'

const TONES = {
  ok: 'bg-emerald-500',
  warn: 'bg-amber-500',
  error: 'bg-rose-500',
  idle: 'bg-slate-300'
} as const

export type StatusTone = keyof typeof TONES

export function StatusDot({ tone }: { tone: StatusTone }): JSX.Element {
  return <span className={`inline-block h-2 w-2 rounded-full ${TONES[tone]}`} />
}
