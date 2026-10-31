export function formatUptime(seconds: number): string {
  if (seconds < 60) {
    return `${seconds} 秒`
  }
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) {
    return `${minutes} 分钟`
  }
  const hours = Math.floor(minutes / 60)
  const remainingMinutes = minutes % 60
  return `${hours} 小时 ${remainingMinutes} 分钟`
}

export function formatPrice(cents: number): string {
  return `¥${(cents / 100).toLocaleString('zh-CN', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2
  })}`
}

export function formatDateTime(value: string | null | undefined): string {
  if (!value) {
    return '—'
  }
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) {
    return '—'
  }
  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit'
  }).format(date)
}

export function platformLabel(platform: string | null | undefined): string {
  if (platform === 'jd') {
    return '京东'
  }
  if (platform === 'taobao') {
    return '淘宝'
  }
  return '—'
}

export function shopTypeLabel(shopType: string): string {
  if (shopType === 'jd_official_self') {
    return '京东官方自营'
  }
  if (shopType === 'official_flagship') {
    return '官方旗舰店'
  }
  if (shopType === 'other') {
    return '非官方店铺'
  }
  return '店铺待确认'
}

export function sourceLabel(source: string | null | undefined): string {
  if (source === 'checkout') {
    return '结算实付'
  }
  if (source === 'page') {
    return '页面预估'
  }
  return '—'
}

export function statusLabel(status: string): string {
  const labels: Record<string, string> = {
    active: '监控中',
    paused: '已暂停',
    needs_review: '待确认',
    error: '异常',
    ok: '正常',
    failed: '失败',
    running: '进行中',
    verifying: '验证中',
    logged_in: '已登录',
    logging_in: '登录中',
    needs_login: '未登录',
    sent: '已发送',
    pending: '待发送'
  }
  return labels[status] ?? status
}
