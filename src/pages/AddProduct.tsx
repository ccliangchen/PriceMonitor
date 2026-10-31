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
import { createProduct, fetchAccounts, resolveListing } from '@/lib/api'
import { shopTypeLabel } from '@/lib/format'
import type { ListingResolve, ProductCreatePayload } from '@/lib/types'

const inputClass =
  'mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200'
const labelClass = 'text-sm font-medium text-slate-700'

const EVIDENCE_LABELS: Record<string, string> = {
  self_operated: '官方自营标识',
  official_badge: '官方旗舰店标识',
  brand_match: '品牌一致',
  shop_brand: '店铺品牌'
}

function UrlAddProduct(): JSX.Element {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
    refetchInterval: 3000
  })
  const jd = accounts.data?.find((account) => account.platform === 'jd')
  const loggedIn = jd?.status === 'logged_in'

  const [url, setUrl] = useState('')
  const [resolved, setResolved] = useState<ListingResolve | null>(null)
  const [name, setName] = useState('')
  const [brand, setBrand] = useState('')
  const [model, setModel] = useState('')
  const [variant, setVariant] = useState('')
  const [ram, setRam] = useState('')
  const [storage, setStorage] = useState('')
  const [color, setColor] = useState('')
  const [notes, setNotes] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const resolveMutation = useMutation({
    mutationFn: resolveListing,
    onSuccess: (data) => {
      setResolved(data)
      setName(data.title)
      setBrand('')
      setModel('')
      setVariant('')
      setRam(data.detected_specs.ram_gb ?? '')
      setStorage(data.detected_specs.storage_gb ?? '')
      setColor('')
      setNotes('')
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
    if (!name.trim() || !brand.trim() || !model.trim()) {
      setFormError('请填写商品名、品牌和型号')
      return
    }
    if (!ramNumber || !storageNumber || ramNumber <= 0 || storageNumber <= 0) {
      setFormError('请填写内存和存储容量（例如 12 和 512）')
      return
    }
    if (resolved.decision !== 'allowed') {
      setFormError('该链接未通过官方店铺校验，不能添加')
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
      listing: {
        platform: 'jd',
        url: resolved.url,
        title: resolved.title,
        shop_name: resolved.shop_name,
        shop_type: resolved.shop_type,
        platform_item_id: resolved.platform_item_id,
        platform_sku_id: resolved.platform_sku_id,
        shop_evidence: resolved.evidence,
        detected_specs: resolved.detected_specs
      }
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
      {!loggedIn ? (
        <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            需要先登录京东账号才能解析商品链接。
            <Link to="/accounts" className="ml-2 font-medium underline">
              去账号管理登录
            </Link>
          </div>
        </div>
      ) : null}

      <form onSubmit={handleResolve} className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Link2 className="h-4 w-4" />
          京东商品链接
        </div>
        <div className="mt-3 flex gap-2">
          <input
            value={url}
            onChange={(event) => setUrl(event.target.value)}
            placeholder="https://item.jd.com/100012043978.html"
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
          支持 item.jd.com、item.m.jd.com、u.jd.com、3.cn。桌面商品页会自动改用移动版抓取，避开 PC 频控。
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
                只有官方旗舰店和京东官方自营可以通过。请换一个官方店铺的商品链接。
              </div>
            ) : null}
          </section>

          <form
            onSubmit={handleCreate}
            className="rounded-2xl border border-slate-200 bg-white p-5"
          >
            <div className="text-sm font-semibold text-slate-900">SKU 规格</div>
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

            {formError ? (
              <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                {formError}
              </div>
            ) : null}
            {createMutation.isError ? (
              <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
                {createMutation.error instanceof Error
                  ? createMutation.error.message
                  : '添加失败'}
              </div>
            ) : null}

            <button
              type="submit"
              disabled={!canCreate || createMutation.isPending}
              className="mt-5 inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
            >
              {createMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle2 className="h-4 w-4" />
              )}
              添加并开始监控
            </button>
            <p className="mt-2 text-xs text-slate-400">
              添加后不会立即下单，只读取页面价格和可见券；首次抓取只建立史低基线。
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
        description="输入型号和规格自动匹配官方店；也可以粘贴商品链接。"
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
