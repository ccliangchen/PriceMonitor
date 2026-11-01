import type { JSX } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Activity,
  LayoutDashboard,
  Plus,
  ScrollText,
  Settings as SettingsIcon,
  UserRound
} from 'lucide-react'
import { Navigate, NavLink, Route, Routes } from 'react-router-dom'

import { StatusDot } from '@/components/StatusDot'
import { apiRequest, getAppInfo } from '@/lib/api'
import { formatUptime } from '@/lib/format'
import type { Health } from '@/lib/types'
import Accounts from '@/pages/Accounts'
import AddProduct from '@/pages/AddProduct'
import Dashboard from '@/pages/Dashboard'
import Logs from '@/pages/Logs'
import ProductDetail from '@/pages/ProductDetail'
import SettingsPage from '@/pages/Settings'

const NAV_ITEMS = [
  { to: '/', label: '仪表盘', icon: LayoutDashboard, end: true },
  { to: '/add', label: '添加商品', icon: Plus, end: false },
  { to: '/accounts', label: '账号管理', icon: UserRound, end: false },
  { to: '/settings', label: '设置', icon: SettingsIcon, end: false },
  { to: '/logs', label: '日志', icon: ScrollText, end: false }
]

function HealthPill(): JSX.Element {
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => apiRequest<Health>('GET', '/api/v1/health'),
    refetchInterval: 5000,
    retry: 1
  })

  if (health.isPending) {
    return (
      <span className="flex items-center gap-2 text-xs text-slate-400">
        <StatusDot tone="idle" />
        连接后端…
      </span>
    )
  }

  if (health.isError) {
    return (
      <span className="flex items-center gap-2 text-xs text-rose-600">
        <StatusDot tone="error" />
        后端未连接
      </span>
    )
  }

  return (
    <span className="flex items-center gap-2 text-xs text-slate-500">
      <StatusDot tone={health.data.database === 'ok' ? 'ok' : 'warn'} />
      后端正常 · 已运行 {formatUptime(health.data.uptime_seconds)}
    </span>
  )
}

export default function App(): JSX.Element {
  const appInfo = useQuery({
    queryKey: ['app-info'],
    queryFn: getAppInfo,
    staleTime: Infinity,
    retry: false
  })

  return (
    <div className="flex h-screen overflow-hidden bg-slate-50 text-slate-900">
      <aside className="flex w-60 shrink-0 flex-col border-r border-slate-200 bg-white">
        <div className="px-5 pb-5 pt-6">
          <div className="flex items-center gap-2.5">
            <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-slate-900 text-base font-bold text-white">
              ¥
            </div>
            <div>
              <div className="text-sm font-semibold tracking-tight">PriceMonitor</div>
              <div className="text-[11px] text-slate-500">全平台史低监测</div>
            </div>
          </div>
        </div>

        <nav className="flex-1 space-y-1 px-3">
          {NAV_ITEMS.map(({ to, label, icon: Icon, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors ${
                  isActive
                    ? 'bg-slate-900 font-medium text-white'
                    : 'text-slate-600 hover:bg-slate-100 hover:text-slate-900'
                }`
              }
            >
              <Icon className="h-4 w-4" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-slate-100 px-5 py-4 text-[11px] text-slate-400">
          <div>v{appInfo.data?.version ?? '0.1.0'} · M2 开发中</div>
          <div className="mt-1 truncate" title={appInfo.data?.dataDir}>
            {appInfo.data?.dataDir ?? '本地数据目录'}
          </div>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-slate-200 bg-white/90 px-6">
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <Activity className="h-4 w-4" />
            <span>本地运行 · 数据不上传</span>
          </div>
          <HealthPill />
        </header>

        <main className="min-h-0 flex-1 overflow-auto p-6">
          <Routes>
            <Route path="/" element={<Dashboard />} />
            <Route path="/add" element={<AddProduct />} />
            <Route path="/products/:productId" element={<ProductDetail />} />
            <Route path="/accounts" element={<Accounts />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/logs" element={<Logs />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  )
}
