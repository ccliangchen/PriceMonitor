import type { FormEvent, JSX } from 'react'
import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  AlertTriangle,
  CheckCircle2,
  Loader2,
  Search,
  Trash2
} from 'lucide-react'
import { Link, useNavigate } from 'react-router-dom'

import { PlatformBadge } from '@/components/PlatformBadge'
import { createProduct, fetchAccounts, searchModel } from '@/lib/api'
import { shopTypeLabel } from '@/lib/format'
import type {
  ModelSearchCandidate,
  ModelSearchResponse,
  ParsedProductQuery,
  ProductCreatePayload,
  SearchPlatform,
  SkuVariantOption
} from '@/lib/types'

const inputClass =
  'mt-1.5 w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-800 outline-none transition focus:border-slate-400 focus:ring-2 focus:ring-slate-200'

interface SpecOption {
  ram: number
  storage: number
}

function specKey(ram: number, storage: number): string {
  return `${ram}-${storage}`
}

function specLabel(ram: number, storage: number): string {
  return `${ram}GB+${storage}GB`
}

function collectSpecs(candidates: ModelSearchCandidate[]): SpecOption[] {
  const map = new Map<string, SpecOption>()
  for (const candidate of candidates) {
    for (const variant of candidate.variants) {
      if (variant.ram_gb === null || variant.storage_gb === null) {
        continue
      }
      map.set(specKey(variant.ram_gb, variant.storage_gb), {
        ram: variant.ram_gb,
        storage: variant.storage_gb
      })
    }
  }
  return [...map.values()].sort(
    (left, right) => left.ram - right.ram || left.storage - right.storage
  )
}

function findVariant(
  candidate: ModelSearchCandidate,
  spec: SpecOption | undefined
): SkuVariantOption | undefined {
  if (!spec) {
    return undefined
  }
  return candidate.variants.find(
    (variant) =>
      variant.ram_gb === spec.ram && variant.storage_gb === spec.storage
  )
}

function pickDefaultSpec(
  specs: SpecOption[],
  query: ParsedProductQuery
): SpecOption | undefined {
  if (specs.length === 0) {
    return undefined
  }
  if (query.ram_gb !== null && query.storage_gb !== null) {
    const exact = specs.find(
      (spec) => spec.ram === query.ram_gb && spec.storage === query.storage_gb
    )
    if (exact) {
      return exact
    }
    const sameRam = specs
      .filter((spec) => spec.ram === query.ram_gb && spec.storage >= (query.storage_gb ?? 0))
      .sort((left, right) => left.storage - right.storage)[0]
    if (sameRam) {
      return sameRam
    }
    const larger = specs
      .filter((spec) => spec.storage >= (query.storage_gb ?? 0))
      .sort((left, right) => left.ram - right.ram || left.storage - right.storage)[0]
    if (larger) {
      return larger
    }
  }
  return specs[0]
}

export default function ModelSearch(): JSX.Element {
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const accounts = useQuery({
    queryKey: ['accounts'],
    queryFn: fetchAccounts,
    refetchInterval: 5000
  })
  const [platform, setPlatform] = useState<SearchPlatform>('jd')
  const account = accounts.data?.find((item) => item.platform === platform)
  const loggedIn = account?.status === 'logged_in'
  const platformText = platform === 'jd' ? '京东' : '淘宝/天猫'

  const [input, setInput] = useState('')
  const [result, setResult] = useState<ModelSearchResponse | null>(null)
  const [selectedSpec, setSelectedSpec] = useState('')

  const searchMutation = useMutation({
    mutationFn: (variables: { query: string; platform: SearchPlatform }) =>
      searchModel(variables.query, variables.platform),
    onSuccess: (data) => {
      setResult(data)
      const specs = collectSpecs(data.candidates)
      const chosen = pickDefaultSpec(specs, data.query)
      setSelectedSpec(chosen ? specKey(chosen.ram, chosen.storage) : '')
    }
  })

  const addMutation = useMutation({
    mutationFn: async () => {
      if (!result || !selectedSpec) {
        throw new Error('请选择可用规格')
      }
      const specs = collectSpecs(result.candidates)
      const spec = specs.find(
        (item) => specKey(item.ram, item.storage) === selectedSpec
      )
      if (!spec) {
        throw new Error('请选择可用规格')
      }
      const targets = result.candidates
        .map((candidate) => ({
          candidate,
          variant: findVariant(candidate, spec)
        }))
        .filter(
          (item): item is { candidate: ModelSearchCandidate; variant: SkuVariantOption } =>
            item.variant !== undefined
        )
      if (targets.length === 0) {
        throw new Error('没有可添加的官方店商品')
      }

      const sizeLabel = specLabel(spec.ram, spec.storage)
      const name = [
        result.query.brand,
        result.query.model,
        result.query.variant,
        sizeLabel
      ]
        .filter(Boolean)
        .join(' ')

      let productId: number | null = null
      for (const { candidate, variant } of targets) {
        const storeType = candidate.store_type as 'official_flagship' | 'jd_official_self'
        const itemId =
          candidate.platform === 'taobao'
            ? (candidate.platform_item_id ?? variant.sku_id)
            : variant.sku_id
        const fallbackEvidence: Record<string, string> =
          candidate.platform === 'taobao'
            ? {
                official_badge: 'true',
                badge_text: '官方旗舰店',
                brand_match: 'true',
                shop_brand: result.query.brand
              }
            : storeType === 'jd_official_self'
              ? {
                  self_operated: 'true',
                  brand_match: 'true',
                  shop_brand: result.query.brand
                }
              : {
                  official_badge: 'true',
                  badge_text: '官方旗舰店',
                  brand_match: 'true',
                  shop_brand: result.query.brand
                }
        const payload: ProductCreatePayload = {
          name,
          brand: result.query.brand,
          model: result.query.model,
          variant: result.query.variant,
          ram_gb: spec.ram,
          storage_gb: spec.storage,
          color: null,
          notes: null,
          listing: {
            platform: candidate.platform,
            url: variant.url,
            title: candidate.title ?? name,
            shop_name: candidate.store_name,
            shop_type: storeType,
            platform_item_id: itemId,
            platform_sku_id: variant.sku_id,
            shop_evidence:
              Object.keys(candidate.shop_evidence ?? {}).length > 0
                ? candidate.shop_evidence
                : fallbackEvidence,
            detected_specs: {
              ram_gb: String(spec.ram),
              storage_gb: String(spec.storage)
            }
          }
        }
        const product = await createProduct(payload)
        productId = product.id
      }
      return productId
    },
    onSuccess: (productId) => {
      void queryClient.invalidateQueries({ queryKey: ['products'] })
      if (productId) {
        navigate(`/products/${productId}`)
      }
    }
  })

  function handleSearch(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault()
    if (!input.trim() || !loggedIn) {
      return
    }
    setResult(null)
    setSelectedSpec('')
    searchMutation.mutate({ query: input.trim(), platform })
  }

  function handlePlatformChange(next: SearchPlatform): void {
    if (next === platform) {
      return
    }
    setPlatform(next)
    setResult(null)
    setSelectedSpec('')
    searchMutation.reset()
    addMutation.reset()
  }

  function handleAbandon(): void {
    setInput('')
    setResult(null)
    setSelectedSpec('')
    searchMutation.reset()
    addMutation.reset()
  }

  const specs = result ? collectSpecs(result.candidates) : []
  const selected = specs.find(
    (spec) => specKey(spec.ram, spec.storage) === selectedSpec
  )
  const query = result?.query
  const requestedRam = query?.ram_gb ?? null
  const requestedStorage = query?.storage_gb ?? null
  const requestedSpec =
    requestedRam !== null && requestedStorage !== null
      ? specLabel(requestedRam, requestedStorage)
      : null
  const requestedAvailable =
    result !== null &&
    requestedRam !== null &&
    requestedStorage !== null &&
    result.candidates.some((candidate) =>
      candidate.variants.some(
        (variant) =>
          variant.ram_gb === requestedRam &&
          variant.storage_gb === requestedStorage
      )
    )
  const matchingTargets = result
    ? result.candidates.filter((candidate) => findVariant(candidate, selected))
    : []

  return (
    <div>
      {!loggedIn ? (
        <div className="mb-4 flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm leading-6 text-amber-800">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <div>
            需要先登录{platformText}账号才能搜索官方店商品。
            <Link to="/accounts" className="ml-2 font-medium underline">
              去账号管理登录
            </Link>
          </div>
        </div>
      ) : null}

      <div className="mb-4 inline-flex rounded-lg bg-slate-100 p-1">
        <button
          type="button"
          onClick={() => handlePlatformChange('jd')}
          className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition ${
            platform === 'jd'
              ? 'bg-white font-medium text-slate-900 shadow-sm'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          京东官方店
        </button>
        <button
          type="button"
          onClick={() => handlePlatformChange('taobao')}
          className={`inline-flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm transition ${
            platform === 'taobao'
              ? 'bg-white font-medium text-slate-900 shadow-sm'
              : 'text-slate-500 hover:text-slate-800'
          }`}
        >
          淘宝/天猫官方店
        </button>
      </div>

      <form onSubmit={handleSearch} className="rounded-2xl border border-slate-200 bg-white p-5">
        <div className="flex items-center gap-2 text-sm font-semibold text-slate-900">
          <Search className="h-4 w-4" />
          手机型号和规格
        </div>
        <div className="mt-3 flex gap-2">
          <input
            value={input}
            onChange={(event) => setInput(event.target.value)}
            placeholder="例如：iQOO Neo11 至尊版 12G+512G"
            className={inputClass}
          />
          <button
            type="submit"
            disabled={!loggedIn || !input.trim() || searchMutation.isPending}
            className="mt-1.5 inline-flex shrink-0 items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
          >
            {searchMutation.isPending ? (
              <Loader2 className="h-4 w-4 animate-spin" />
            ) : (
              <Search className="h-4 w-4" />
            )}
            搜索{platformText}官方店
          </button>
        </div>
        <p className="mt-2 text-xs leading-5 text-slate-500">
          {platform === 'jd'
            ? '按型号搜索覆盖 iQOO 京东自营旗舰店和 iQOO 官方旗舰店；规格不存在时会展示可用规格。首次搜索会打开官方店商品页，可能触发一次京东验证。'
            : '会先搜索品牌的天猫官方旗舰店，再在店内按型号搜索；规格不存在时会展示可用规格。淘宝风控比京东严格，触发滑块或登录失效时请稍后重试、完成验证，或改用“粘贴链接”。'}
        </p>
        {searchMutation.isError ? (
          <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
            {searchMutation.error instanceof Error
              ? searchMutation.error.message
              : '搜索失败'}
          </div>
        ) : null}
      </form>

      {searchMutation.isPending ? (
        <div className="mt-4 flex items-center gap-3 rounded-2xl border border-slate-200 bg-white p-5 text-sm text-slate-500">
          <Loader2 className="h-4 w-4 animate-spin" />
          {platform === 'jd'
            ? '正在打开两家官方店商品页并读取 SKU 列表，大约 30–60 秒（两家店之间自动间隔，避免频控）…'
            : '正在搜索天猫官方旗舰店并读取商品 SKU，大约 20–60 秒；触发风控时会提示稍后重试…'}
        </div>
      ) : null}

      {result ? (
        <div className="mt-4 space-y-4">
          <section className="rounded-2xl border border-slate-200 bg-white p-5">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="font-semibold text-slate-900">
                {result.query.brand} {result.query.model} {result.query.variant}
              </span>
              <span className="text-slate-400">/</span>
              <span className="text-slate-600">你输入的规格：{requestedSpec ?? '未填写'}</span>
            </div>

            {!requestedAvailable ? (
              <div className="mt-3 flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 p-3 text-sm leading-6 text-amber-800">
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                <div>
                  {requestedSpec
                    ? `${requestedSpec} 在该型号不可用。下面是可选的官方规格，请选择后再添加。`
                    : '请输入内存和存储规格，例如 12G+512G。'}
                </div>
              </div>
            ) : null}

            <div className="mt-4">
              <div className="text-xs font-medium text-slate-500">可选规格</div>
              <div className="mt-2 flex flex-wrap gap-2">
                {specs.map((spec) => {
                  const key = specKey(spec.ram, spec.storage)
                  const active = key === selectedSpec
                  return (
                    <button
                      key={key}
                      type="button"
                      onClick={() => setSelectedSpec(key)}
                      className={`rounded-lg border px-3 py-2 text-sm transition ${
                        active
                          ? 'border-slate-900 bg-slate-900 font-medium text-white'
                          : 'border-slate-200 bg-white text-slate-600 hover:border-slate-300'
                      }`}
                    >
                      {specLabel(spec.ram, spec.storage)}
                    </button>
                  )
                })}
                {specs.length === 0 ? (
                  <span className="text-sm text-slate-400">没有读到可用规格</span>
                ) : null}
              </div>
            </div>
          </section>

          <div className="grid gap-4 md:grid-cols-2">
            {result.candidates.map((candidate) => {
              const variant = findVariant(candidate, selected)
              return (
                <section
                  key={`${candidate.platform}-${candidate.store_type}-${candidate.store_name}`}
                  className="rounded-2xl border border-slate-200 bg-white p-5"
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-sm font-semibold text-slate-900">
                      {candidate.store_name}
                    </h2>
                    <PlatformBadge platform={candidate.platform} />
                    <span className="rounded-full bg-slate-100 px-2.5 py-1 text-[11px] text-slate-500">
                      {shopTypeLabel(candidate.store_type)}
                    </span>
                  </div>
                  <p className="mt-1 line-clamp-2 text-xs text-slate-500">
                    {candidate.title ?? '—'}
                  </p>

                  {candidate.error ? (
                    <div className="mt-3 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-700">
                      {candidate.error}
                      {candidate.error.includes('登录') ? (
                        <Link to="/accounts" className="ml-2 font-medium underline">
                          去账号管理
                        </Link>
                      ) : null}
                    </div>
                  ) : variant ? (
                    <div className="mt-3 rounded-lg bg-slate-50 p-3 text-xs text-slate-600">
                      <div>
                        已匹配：{specLabel(variant.ram_gb ?? 0, variant.storage_gb ?? 0)}
                        {variant.color ? ` · ${variant.color}` : ''}
                        {variant.spec ? ` · ${variant.spec}` : ''}
                      </div>
                      <div className="mt-1 text-slate-400">
                        SKU {variant.sku_id} · 添加后抓取价格
                      </div>
                    </div>
                  ) : (
                    <div className="mt-3 rounded-lg border border-dashed border-slate-200 bg-slate-50 p-3 text-xs text-slate-400">
                      该店没有所选规格
                    </div>
                  )}

                  {candidate.variants.length > 0 ? (
                    <div className="mt-3 text-[11px] text-slate-400">
                      该店可用：
                      {candidate.variants
                        .map((item) =>
                          item.ram_gb !== null && item.storage_gb !== null
                            ? specLabel(item.ram_gb, item.storage_gb)
                            : ''
                        )
                        .filter(Boolean)
                        .join('、')}
                    </div>
                  ) : null}
                </section>
              )
            })}
          </div>

          {addMutation.isError ? (
            <div className="rounded-xl border border-rose-200 bg-rose-50 p-3 text-sm text-rose-700">
              {addMutation.error instanceof Error
                ? addMutation.error.message
                : '添加失败'}
            </div>
          ) : null}

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="button"
              onClick={() => addMutation.mutate()}
              disabled={matchingTargets.length === 0 || addMutation.isPending}
              className="inline-flex items-center gap-2 rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-40"
            >
              {addMutation.isPending ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <CheckCircle2 className="h-4 w-4" />
              )}
              添加并开始监控（{matchingTargets.length} 个官方链接）
            </button>
            <button
              type="button"
              onClick={handleAbandon}
              className="inline-flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-600 hover:bg-slate-50"
            >
              <Trash2 className="h-4 w-4" />
              放弃监测该商品
            </button>
            <span className="text-xs text-slate-400">
              会把所选规格的所有官方店绑到同一个商品，价格取最低；首次抓取只建基线。
            </span>
          </div>
        </div>
      ) : null}
    </div>
  )
}
