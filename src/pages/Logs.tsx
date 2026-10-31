import type { JSX } from 'react'
import { useQuery } from '@tanstack/react-query'
import { FileText, FolderOpen, Loader2, RefreshCw, ScrollText } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'
import { fetchJobs, getAppInfo } from '@/lib/api'
import { formatDateTime, platformLabel, statusLabel } from '@/lib/format'

function statusStyle(status: string): string {
  if (status === 'ok') {
    return 'bg-emerald-50 text-emerald-700'
  }
  if (status === 'failed') {
    return 'bg-rose-50 text-rose-700'
  }
  if (status === 'running') {
    return 'bg-amber-50 text-amber-700'
  }
  return 'bg-slate-100 text-slate-500'
}

function jobTypeLabel(jobType: string): string {
  if (jobType === 'page_price') {
    return '页面抓价'
  }
  if (jobType === 'checkout') {
    return '结算校准'
  }
  if (jobType === 'login_check') {
    return '登录检查'
  }
  return jobType
}

export default function Logs(): JSX.Element {
  const jobs = useQuery({
    queryKey: ['jobs'],
    queryFn: fetchJobs,
    refetchInterval: 5000
  })
  const appInfo = useQuery({
    queryKey: ['app-info'],
    queryFn: getAppInfo,
    staleTime: Infinity,
    retry: false
  })

  return (
    <div>
      <PageHeader
        title="日志"
        description="最近抓取任务、失败原因和平台状态。"
      >
        <button
          type="button"
          onClick={() => void jobs.refetch()}
          className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          <RefreshCw className="h-4 w-4" />
          刷新
        </button>
      </PageHeader>

      {jobs.isError ? (
        <div className="mb-4 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
          读取任务失败：
          {jobs.error instanceof Error ? jobs.error.message : '未知错误'}
        </div>
      ) : null}

      <section className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <div className="flex items-center justify-between border-b border-slate-100 px-5 py-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
            <ScrollText className="h-4 w-4" />
            最近任务
          </div>
          <div className="text-xs text-slate-400">{jobs.data?.length ?? 0} 条</div>
        </div>

        {jobs.isPending ? (
          <div className="flex h-40 items-center justify-center text-sm text-slate-400">
            <Loader2 className="mr-2 h-4 w-4 animate-spin" />
            加载任务…
          </div>
        ) : jobs.data && jobs.data.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-left text-sm">
              <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-400">
                <tr>
                  <th className="px-5 py-3 font-medium">开始时间</th>
                  <th className="px-5 py-3 font-medium">平台</th>
                  <th className="px-5 py-3 font-medium">任务</th>
                  <th className="px-5 py-3 font-medium">状态</th>
                  <th className="px-5 py-3 font-medium">错误</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {jobs.data.map((job) => (
                  <tr key={job.id} className="text-slate-600">
                    <td className="whitespace-nowrap px-5 py-3 text-xs text-slate-500">
                      {formatDateTime(job.started_at)}
                    </td>
                    <td className="px-5 py-3">{platformLabel(job.platform)}</td>
                    <td className="px-5 py-3">{jobTypeLabel(job.job_type)}</td>
                    <td className="px-5 py-3">
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${statusStyle(
                          job.status
                        )}`}
                      >
                        {statusLabel(job.status)}
                      </span>
                    </td>
                    <td
                      className="max-w-[360px] truncate px-5 py-3 text-xs text-rose-600"
                      title={job.error_message ?? ''}
                    >
                      {job.error_message ?? '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="flex h-40 flex-col items-center justify-center gap-2 text-sm text-slate-400">
            <ScrollText className="h-5 w-5" />
            还没有抓取任务。添加商品后点“立即刷新”或等待定时轮询。
          </div>
        )}
      </section>

      <section className="mt-4 rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <FolderOpen className="h-4 w-4" />
          日志目录
        </div>
        <div className="mt-3 break-all font-mono text-xs leading-5 text-slate-500">
          {appInfo.data?.dataDir ?? '—'}
          {'\\logs\\'}
        </div>
        <div className="mt-3 flex flex-wrap gap-4 text-xs text-slate-500">
          <span className="flex items-center gap-1">
            <FileText className="h-3.5 w-3.5" />
            main.log
          </span>
          <span className="flex items-center gap-1">
            <FileText className="h-3.5 w-3.5" />
            backend.log
          </span>
          <span className="flex items-center gap-1">
            <FileText className="h-3.5 w-3.5" />
            backend-stdout.log / backend-stderr.log
          </span>
        </div>
      </section>
    </div>
  )
}
