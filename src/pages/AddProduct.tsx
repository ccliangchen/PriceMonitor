import type { FormEvent, JSX } from 'react'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle2,
  Link2,
  Loader2,
  ShieldCheck
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import ModelSearch from '@/components/ModelSearch'
import { PageHeader } from '@/components/PageHeader'
import {
  bindListing,
  createProduct,
  fetchAccounts,
  fetchProducts,
  resolveListing
} from '@/lib/api'
import { shopTypeLabel } from '@/lib/format'
import type { ListingPayload, ListingResolve, ProductCreatePayload } from '@/lib/types'

const inputClass =
  'mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200'
const labelClass = 'text-sm font-medium text-slate-700'

const EVIDENCE_LABELS: Record<string, string> = {
  self_operated: '官方自营标识',
  official_badge: '官方旗舰店标识',
  badge_text: '官方标识文本',
  brand_match: '品牌一致',
  shop_brand: '店铺品牌'
}

function detectPlatform(url: string): 'jd' | 'taobao' | null {
  const value = url.trim().toLowerCase()
  if (!value) {
    return null
  }
  if (
    value.includes('jd.com') ||
    value.includes('3.cn')
  ) {
    return 'jd'
  }
  if (
    value.includes('taobao.com') ||
    value.includes('tmall.com') ||
    value.includes('tb.cn')
  ) {
    return 'taobao'
  }
  return null
}

function UrlAddProduct(): JSX.Element {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
    refetchInterval: 3000
  })
  const products = useQuery({
    queryKey: ['products'],
    queryFn: fetchProducts
  })

  const [url, setUrl] = useState('')
  const requiredPlatform = detectPlatform(url)
  const platformAccount = accounts.data?.find(
    (account) => account.platform === requiredPlatform
  )
  const loggedIn =
    requiredPlatform === null
      ? Boolean(url.trim())
      : platformAccount?.status === 'logged_in'
  const loginLabel = requiredPlatform === 'taobao' ? '淘宝' : '京东'
  const [resolved, setResolved] = useState<ListingResolve | null>(null)
  const [name, setName] = useState('')
  const [brand, setBrand] = useState('')
  const [model, setModel] = useState('')
  const [variant, setVariant] = useState('')
  const [ram, setRam] = useState('')
  const [storage, setStorage] = useState('')
  const [color, setColor] = useState('')
  const [notes, setNotes] = useState('')
  const [targetProductId, setTargetProductId] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const resolveMutation = useMutation({
    mutationFn: resolveListing,
    onSuccess: (data) => {
      setResolved(data)
      setName(data.title)
      setBrand(data.detected_specs.brand ?? '')
      setModel(data.detected_specs.model ?? '')
      setVariant(data.detected_specs.variant ?? '')
      setRam(data.detected_specs.ram_gb ?? '')
      setStorage(data.detected_specs.storage_gb ?? '')
      setColor('')
      setNotes('')
      setTargetProductId('')
      setFormError(null)
    }
  })

  const createMutation = useMutation({
    mutationFn: createProduct,
    onSuccess: (product) => {
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      navigate(`/products/${product.id}`)
    }
  })

  const bindMutation = useMutation({
    mutationFn: (payload: { productId: number; listing: ListingPayload }) =>
      bindListing(payload.productId, payload.listing),
    onSuccess: (product) => {
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      void queryClient.invalidateQueries({ queryKey: ['product', product.id] })
      navigate(`/products/${product.id}`)
    }
  })

  function handleResolve(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    if (!url.trim() || !loggedIn) {
      return
    }
    resolveMutation.mutate(url.trim())
  }

  function handleCreate(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    if (!resolved) {
      return
    }
    const ramNumber = Number(ram)
    const storageNumber = Number(storage)
    if (resolved.decision !== 'allowed') {
      setFormError('该链接未通过官方店铺校验，不能添加')
      return
    }

    const listing: ListingPayload = {
      platform: resolved.platform as 'jd' | 'taobao',
      url: resolved.url,
      title: resolved.title,
      shop_name: resolved.shop_name,
      shop_type: resolved.shop_type,
      platform_item_id: resolved.platform_item_id,
      platform_sku_id: resolved.platform_sku_id,
      shop_evidence: resolved.evidence,
      detected_specs: resolved.detected_specs
    }

    if (targetProductId) {
      setFormError(null)
      bindMutation.mutate({ productId: Number(targetProductId), listing })
      return
    }

    if (!name.trim() || !brand.trim() || !model.trim()) {
      setFormError('请填写商品名、品牌和型号')
      return
    }
    if (!ramNumber || !storageNumber || ramNumber <= 0 || storageNumber <= 0) {
      setFormError('请填写内存和存储容量（例如 12 和 512）')
      return
    }

    const payload: ProductCreatePayload = {
      name: name.trim(),
      brand: brand.trim(),
      model: model.trim(),
      variant: variant.trim(),
      ram_gb: ramNumber,
      storage_gb: storageNumber,
      color: color.trim() || null,
      notes: notes.trim() || null,
      listing
    }
    setFormError(null)
    createMutation.mutate(payload)
  }

  const canCreate = resolved?.decision === 'allowed'
  const decisionStyle =
    resolved?.decision === 'allowed'
      ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
      : resolved?.decision === 'rejected'
        ? 'border-rose-200 bg-rose-50 text-rose-700'
        : 'border-amber-200 bg-amber-50 text-amber-700'

  return (
    <div>
      {requiredPlatform && !loggedIn ? (
        <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            需要先登录{loginLabel}账号才能解析该商品链接。
            <Link to="/accounts" className="ml-2 font-medium underline">
              去账号管理登录
            </Link>
          </div>
        </div>
      ) : null}

      <form onSubmit={handleResolve} className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Link2 className="h-4 w-4" />
          京东 / 淘宝商品链接
        </div>
        <div className="mt-3 flex gap-2">
          <input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://item.jd.com/100012043978.html 或 https://detail.tmall.com/item.htm?id=..."
            className={inputClass}
          />
          <button
            type="submit"
            disabled={!loggedIn || !url.trim() || resolveMutation.isPending}
            className="mt-1.5 inline-flex shrink-0 items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
          >
            {resolveMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <ShieldCheck className="h-4 w-4" />
            )}
            解析链接
          </button>
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-500">
          支持京东（item.jd.com、u.jd.com、3.cn）和淘宝/天猫（item.taobao.com、detail.tmall.com、m.tb.cn）。
          桌面京东页会自动改用移动版抓取；淘宝需要先登录账号。
        </p>
        {resolveMutation.isError ? (
          <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            {resolveMutation.error instanceof Error
              ? resolveMutation.error.message
              : '解析失败'}
          </div>
        ) : null}
      </form>

      {resolved ? (
        <div className="mt-4 grid gap-4 lg:grid-cols-[1fr_1.25fr]">
          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="text-xs font-medium uppercase tracking-wider text-slate-400">
              店铺校验
            </div>
            <h2 className="mt-2 text-base font-semibold text-slate-900">{resolved.title}</h2>
            <div className="mt-2 text-sm text-slate-500">{resolved.shop_name}</div>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              <span className="rounded-full bg-slate-100 px-2.5 py-1 text-xs text-slate-600">
                {shopTypeLabel(resolved.shop_type)}
              </span>
              <span className={`rounded-full border px-2.5 py-1 text-xs ${decisionStyle}`}>
                {resolved.decision === 'allowed'
                  ? '官方店铺通过'
                  : resolved.decision === 'rejected'
                    ? '拒绝添加'
                    : '需要确认'}
              </span>
            </div>
            <p className="mt-3 text-xs leading-5 text-slate-500">{resolved.decision_reason}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {Object.entries(resolved.evidence).map(([key, value]) => (
                <span
                  key={key}
                  className="rounded-lg bg-slate-50 px-2 py-1 text-[11px] text-slate-500"
                >
                  {EVIDENCE_LABELS[key] ?? key}: {value}
                </span>
              ))}
            </div>
            {resolved.decision !== 'allowed' ? (
              <div className="mt-4 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-xs leading-5 text-amber-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                只有天猫官方旗舰店、京东官方旗舰店和京东官方自营可以通过。请换一个官方店铺的商品链接。
              </div>
            ) : null}
          </section>

          <form
            onSubmit={handleCreate}
            className="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div className="text-sm font-semibold text-slate-900">绑定商品</div>
            <label className={`${labelClass} mt-4 block`}>
              目标商品
              <select
                value={targetProductId}
                onChange={(event) => setTargetProductId(event.target.value)}
                className={inputClass}
              >
                <option value="">新建商品</option>
                {products.data?.map((product) => (
                  <option key={product.id} value={product.id}>
                    {product.name}（{product.ram_gb}GB+{product.storage_gb}GB）
                  </option>
                ))}
              </select>
            </label>
            <p className="mt-2 text-xs leading-5 text-slate-500">
              如果这是已有商品在另一个平台的链接，选择已有商品即可合并到同一个商品，价格取全平台最低。
            </p>

            {targetProductId ? (
              <div className="mt-5 rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm leading-6 text-slate-600">
                将把该链接绑定到已有商品，不需要重复填写品牌和规格。
              </div>
            ) : (
              <>
            <div className="mt-5 text-sm font-semibold text-slate-900">SKU 规格</div>
            <div className="mt-4 space-y-4">
              <label className={labelClass}>
                商品名
                <input
                  value={name}
                  onChange={(event) => setName(event.target.value)}
                  className={inputClass}
                />
              </label>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className={labelClass}>
                  品牌
                  <input
                    value={brand}
                    onChange={(event) => setBrand(event.target.value)}
                    placeholder="如 iQOO"
                    className={inputClass}
                  />
                </label>
                <label className={labelClass}>
                  型号
                  <input
                    value={model}
                    onChange={(event) => setModel(event.target.value)}
                    placeholder="如 Neo11"
                    className={inputClass}
                  />
                </label>
                <label className={labelClass}>
                  版本
                  <input
                    value={variant}
                    onChange={(event) => setVariant(event.target.value)}
                    placeholder="如 至尊版"
                    className={inputClass}
                  />
                </label>
              </div>
              <div className="grid gap-3 sm:grid-cols-3">
                <label className={labelClass}>
                  内存（GB）
                  <input
                    type="number"
                    min={1}
                    value={ram}
                    onChange={(event) => setRam(event.target.value)}
                    placeholder="12"
                    className={inputClass}
                  />
                </label>
                <label className={labelClass}>
                  存储（GB）
                  <input
                    type="number"
                    min={1}
                    value={storage}
                    onChange={(event) => setStorage(event.target.value)}
                    placeholder="512"
                    className={inputClass}
                  />
                </label>
                <label className={labelClass}>
                  颜色（可选）
                  <input
                    value={color}
                    onChange={(event) => setColor(event.target.value)}
                    placeholder="不填则视为不区分"
                    className={inputClass}
                  />
                </label>
              </div>
              <label className={labelClass}>
                备注（可选）
                <input
                  value={notes}
                  onChange={(event) => setNotes(event.target.value)}
                  className={inputClass}
                />
              </label>
            </div>
              </>
            )}

            {formError ? (
              <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                {formError}
              </div>
            ) : null}
            {createMutation.isError || bindMutation.isError ? (
              <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                {createMutation.error instanceof Error
                  ? createMutation.error.message
                  : bindMutation.error instanceof Error
                    ? bindMutation.error.message
                    : '添加失败'}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={!canCreate || createMutation.isPending || bindMutation.isPending}
              className="mt-5 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
            >
              {createMutation.isPending || bindMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle2 className="h-4 w-4" />
              )}
              {targetProductId ? '绑定并开始监控' : '添加并开始监控'}
            </button>
            <p className="mt-2 text-xs text-slate-400">
              添加后不会立即下单，只读取页面预估价和可见券；首次抓取只建立史低基线。
              品牌、型号、版本和规格与已有商品一致时，会自动合并为同一个商品并跨平台比价。
            </p>
          </form>
        </div>
      ) : null}
    </div>
  )
}

export default function AddProduct(): JSX.Element {
  const [mode, setMode] = useState<'model' | 'url'>('model')

  return (
    <div>
      <PageHeader
        title="添加商品"
        description="输入型号和规格自动匹配京东或淘宝/天猫官方店；也可以直接粘贴商品链接。"
      />

      <div className="mb-5 inline-flex rounded-lg bg-slate-100 p-1">
        <button
          type="button"
          onClick={() => setMode('model')}
          className={`rounded-md px-3 py-1.5 text-sm transition ${
            mode === 'model'
              ? 'bg-white font-medium text-slate-900 shadow-sm'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          按型号搜索
        </button>
        <button
          type="button"
          onClick={() => setMode('url')}
          className={`rounded-md px-3 py-1.5 text-sm transition ${
            mode === 'url'
              ? 'bg-white font-medium text-slate-900 shadow-sm'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          粘贴链接
        </button>
      </div>

      {mode === 'model' ? <ModelSearch /> : <UrlAddProduct />}
    </div>
  )
}
