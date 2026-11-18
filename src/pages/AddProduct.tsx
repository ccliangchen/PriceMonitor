import type { FormEvent, JSX } from 'react'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { PageHeader } from '@/components/PageHeader'
import { PlatformBadge } from '@/components/PlatformBadge'
import { bindListing, createProduct, fetchAccounts, fetchEdgeStatus, fetchProducts, refreshProduct, resolveListing } from '@/lib/api'
import { shopTypeLabel } from '@/lib/format'
import type { ListingPayload, ListingResolve } from '@/lib/types'

const inputClass = 'mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none focus:border-slate-400 focus:ring-2 focus:ring-slate-200'

function platformForUrl(url: string): 'jd' | 'taobao' | null {
  try {
    const host = new URL(url.trim()).hostname.toLowerCase()
    if (host === 'jd.com' || host.endsWith('.jd.com') || host === '3.cn' || host.endsWith('.3.cn')) return 'jd'
    if (['taobao.com', 'tmall.com', 'tb.cn'].some((domain) => host === domain || host.endsWith(`.${domain}`))) return 'taobao'
  } catch {
    return null
  }
  return null
}

export default function AddProduct(): JSX.Element {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const queryClient = useQueryClient()
  const products = useQuery({ queryKey: ['products'], queryFn: fetchProducts })
  const accounts = useQuery({ queryKey: ['accounts'], queryFn: fetchAccounts })
  const edge = useQuery({ queryKey: ['edge-status'], queryFn: fetchEdgeStatus, refetchInterval: 5000 })
  const [name, setName] = useState('')
  const [notes, setNotes] = useState('')
  const [url, setUrl] = useState('')
  const [targetProductId, setTargetProductId] = useState(searchParams.get('productId') ?? '')
  const [resolved, setResolved] = useState<ListingResolve | null>(null)
  const platform = platformForUrl(url)
  const account = accounts.data?.find((item) => item.platform === platform)
  const extensionReady = platform != null && edge.data?.platforms.includes(platform)

  const create = useMutation({
    mutationFn: createProduct,
    onSuccess: (product) => {
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      navigate(`/products/${product.id}`)
    }
  })
  const resolve = useMutation({ mutationFn: resolveListing, onSuccess: setResolved })
  const bind = useMutation({
    mutationFn: (payload: { productId: number; listing: ListingPayload }) =>
      bindListing(payload.productId, payload.listing),
    onSuccess: (product) => {
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      void queryClient.invalidateQueries({ queryKey: ['product', product.id] })
      void refreshProduct(product.id).catch(() => undefined)
      navigate(`/products/${product.id}`)
    }
  })

  function handleCreate(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    if (name.trim()) create.mutate({ name: name.trim(), notes: notes.trim() || null })
  }
  function handleResolve(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    setResolved(null)
    if (url.trim()) resolve.mutate(url.trim())
  }
  function handleBind(): void {
    if (!resolved || !targetProductId) return
    bind.mutate({
      productId: Number(targetProductId),
      listing: {
        platform: resolved.platform as 'jd' | 'taobao',
        url: resolved.url, title: resolved.title, shop_name: resolved.shop_name,
        shop_type: resolved.shop_type, platform_item_id: resolved.platform_item_id,
        platform_sku_id: resolved.platform_sku_id, shop_evidence: resolved.evidence,
        detected_specs: resolved.detected_specs
      }
    })
  }

  return (
    <div>
      <PageHeader title="添加商品" description="自己建立商品，再把京东、淘宝或天猫的商品链接逐条添加进去。" />
      <div className="grid gap-5 xl:grid-cols-2">
        <form onSubmit={handleCreate} className="rounded-2xl border border-slate-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-slate-900">建立商品</h2>
          <p className="mt-2 text-sm text-slate-500">只需填写方便自己识别的名称。建立后可添加多个链接。</p>
          <label className="mt-5 block text-sm font-medium text-slate-700">商品名称
            <input value={name} onChange={(event) => setName(event.target.value)} className={inputClass} placeholder="例如：书桌台灯" required />
          </label>
          <label className="mt-4 block text-sm font-medium text-slate-700">备注（可选）
            <input value={notes} onChange={(event) => setNotes(event.target.value)} className={inputClass} />
          </label>
          <button type="submit" disabled={!name.trim() || create.isPending} className="mt-5 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">
            {create.isPending ? '建立中…' : '建立商品'}
          </button>
          {create.isError ? <p className="mt-3 text-sm text-rose-600">{create.error instanceof Error ? create.error.message : '建立失败'}</p> : null}
        </form>
        <section className="rounded-2xl border border-slate-200 bg-white p-5">
          <h2 className="text-sm font-semibold text-slate-900">添加商品链接</h2>
          <label className="mt-5 block text-sm font-medium text-slate-700">选择归属商品
            <select value={targetProductId} onChange={(event) => setTargetProductId(event.target.value)} className={inputClass}>
              <option value="">请选择已建立的商品</option>
              {products.data?.map((item) => <option key={item.id} value={item.id}>{item.name}</option>)}
            </select>
          </label>
          <form onSubmit={handleResolve} className="mt-4">
            <label className="block text-sm font-medium text-slate-700">京东、淘宝或天猫商品详情页链接
              <input value={url} onChange={(event) => { setUrl(event.target.value); setResolved(null) }} className={inputClass} placeholder="https://item.jd.com/... 或 https://detail.tmall.com/item.htm?id=..." />
            </label>
            <button type="submit" disabled={!url.trim() || resolve.isPending} className="mt-3 rounded-lg border border-slate-200 px-4 py-2 text-sm font-medium text-slate-700 disabled:opacity-40">
              {resolve.isPending ? '读取中…' : '读取链接信息'}
            </button>
          </form>
          {resolve.isPending && platform === 'taobao' ? <p className="mt-3 text-xs text-slate-500">淘宝直接读取失败时会自动启动所选浏览器，并等待扩展从独立窗口返回。</p> : null}
          {platform === 'jd' && !extensionReady ? <p className="mt-3 text-xs text-slate-500">读取京东链接时会自动启动所选浏览器；请确认扩展已安装并保持账号登录。<Link to="/accounts" className="underline">查看浏览器设置</Link></p> : null}
          {platform === 'taobao' && account?.status !== 'logged_in' && !extensionReady ? <p className="mt-3 text-xs text-slate-500">淘宝应用账号未登录时会自动启动所选浏览器并使用扩展读取。<Link to="/accounts" className="underline">前往账号管理</Link></p> : null}
          {resolve.isError ? <p className="mt-3 text-sm text-rose-600">{resolve.error instanceof Error ? resolve.error.message : '链接读取失败'}</p> : null}
          {resolved ? (
            <div className="mt-5 rounded-xl border border-slate-200 bg-slate-50 p-4">
              <div className="text-sm font-medium text-slate-900">{resolved.title}</div>
              <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-600">
                <PlatformBadge platform={resolved.platform} /><span>{resolved.shop_name || '店铺待读取'}</span><span>{shopTypeLabel(resolved.shop_type)}</span>
              </div>
              <p className="mt-2 text-xs text-slate-500">绑定后自动读取价格；店铺是否官方不影响监测。</p>
              <button type="button" onClick={handleBind} disabled={!targetProductId || bind.isPending} className="mt-4 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40">
                {bind.isPending ? '绑定中…' : '添加到所选商品'}
              </button>
              {bind.isError ? <p className="mt-3 text-sm text-rose-600">{bind.error instanceof Error ? bind.error.message : '绑定失败'}</p> : null}
            </div>
          ) : null}
        </section>
      </div>
    </div>
  )
}
