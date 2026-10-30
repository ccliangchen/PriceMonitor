import type { JSX } from 'react'
import { LogIn, ShieldCheck } from 'lucide-react'

import { PageHeader } from '@/components/PageHeader'

const PLATFORMS = [
  {
    key: 'jd',
    name: '京东',
    note: '仅允许官方自营店、官方旗舰店',
    milestone: 'M1'
  },
  {
    key: 'taobao',
    name: '淘宝 / 天猫',
    note: '仅允许官方旗舰店',
    milestone: 'M2'
  }
]

export default function Accounts(): JSX.Element {
  return (
    <div>
      <PageHeader
        title="账号管理"
        description="使用自己的账号扫码登录，应用不保存账号密码。"
      />

      <div className="grid gap-4 md:grid-cols-2">
        {PLATFORMS.map((platform) => (
          <section
            key={platform.key}
            className="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div className="flex items-start justify-between gap-3">
              <div>
                <h2 className="text-base font-semibold text-slate-900">{platform.name}</h2>
                <p className="mt-1 text-sm text-slate-500">{platform.note}</p>
              </div>
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs font-medium text-slate-500">
                {platform.milestone}
              </span>
            </div>

            <div className="mt-5 flex items-center gap-2 text-sm text-slate-400">
              <span className="h-2 w-2 rounded-full bg-slate-300" />
              未登录
            </div>

            <button
              type="button"
              disabled
              title={`${platform.milestone} 开放`}
              className="mt-4 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-3 py-2 text-sm font-medium text-white opacity-40"
            >
              <LogIn className="h-4 w-4" />
              扫码登录
            </button>
          </section>
        ))}
      </div>

      <div className="mt-6 flex items-start gap-3 rounded-2xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-800">
        <ShieldCheck className="mt-0.5 h-4 w-4 shrink-0" />
        <p>
          登录态只保存在本机浏览器配置目录；应用不保存账号密码，不绕过验证码。自动化访问可能触发平台风控，请自行评估账号风险。
        </p>
      </div>
    </div>
  )
}
