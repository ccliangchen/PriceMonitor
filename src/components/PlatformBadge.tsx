import type { JSX } from 'react'

import { platformLabel } from '@/lib/format'

export function PlatformBadge({
  platform
}: {
  platform: string | null | undefined
}): JSX.Element {
  const style =
    platform === 'jd'
      ? 'bg-rose-50 text-rose-600'
      : platform === 'taobao'
        ? 'bg-orange-50 text-orange-600'
        : 'bg-slate-100 text-slate-500'
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium ${style}`}
    >
      {platformLabel(platform)}
    </span>
  )
}
