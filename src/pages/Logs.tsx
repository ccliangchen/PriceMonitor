import type { JSX } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, FolderOpen, ScrollText } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { getAppInfo } from '@/lib/api'

export default function Logs(): JSX.Element {
  const appInfo = useQuery({
    queryKey: ['app-info'],
    queryFn: getAppInfo,
    staleTime: Infinity,
    retry: false
  })

  const dataDir = appInfo.data?.dataDir ?? '—'

  return (
    <div>
      <PageHeader
        title="日志"
        description="M0 先展示日志位置；M1 会接入任务记录、失败原因和日志尾部查看。"
      />

      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <FolderOpen className="h-4 w-4" />
            日志目录
          </div>
          <div className="mt-3 break-all font-mono text-xs leading-5 text-slate-500">
            {dataDir}
            {'\\logs\\'}
          </div>
          <ul className="mt-4 space-y-2 text-sm text-slate-600">
            <li className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-slate-400" />
              main.log — Electron 主进程
            </li>
            <li className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-slate-400" />
              backend.log — Python sidecar
            </li>
            <li className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-slate-400" />
              backend-stdout.log / backend-stderr.log — 子进程输出
            </li>
          </ul>
        </section>

        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <ScrollText className="h-4 w-4" />
            任务记录
          </div>
          <div className="mt-6 rounded-xl border border-dashed border-slate-200 bg-slate-50 p-6 text-center text-sm text-slate-400">
            M1 接入采集任务后，这里会显示最近任务、失败原因和平台暂停状态。
          </div>
        </section>
      </div>
    </div>
  )
}
