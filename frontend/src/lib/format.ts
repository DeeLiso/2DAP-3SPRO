export function formatNumber(value: number) {
  return new Intl.NumberFormat('en-US', { maximumFractionDigits: 0 }).format(Number.isFinite(value) ? value : 0)
}

export function formatMoney(value: number) {
  return `${formatNumber(value)} Ks`
}

export function formatDate(value: string) {
  const trimmed = (value ?? '').trim()
  return trimmed || '—'
}

export function getDeviceSummary(userAgent: string) {
  if (!userAgent) return 'Device not recorded'
  const browser = userAgent.includes('Edg/')
    ? 'Edge'
    : userAgent.includes('OPR/') || userAgent.includes('Opera')
      ? 'Opera'
      : userAgent.includes('Firefox')
        ? 'Firefox'
        : userAgent.includes('Chrome')
          ? 'Chrome'
          : userAgent.includes('Safari')
            ? 'Safari'
            : 'Browser'
  const platform = userAgent.includes('Android')
    ? 'Android'
    : /iPhone|iPad/.test(userAgent)
      ? 'iOS'
      : userAgent.includes('Windows')
        ? 'Windows'
        : userAgent.includes('Mac OS')
          ? 'Mac'
          : userAgent.includes('Linux')
            ? 'Linux'
            : ''
  return platform ? `${browser} · ${platform}` : browser
}

export function hotLimitsToInput(value: Record<string, number>) {
  return Object.entries(value ?? {})
    .filter(([number, amount]) => /^\d{1,2}$/.test(number) && Number.isInteger(amount) && amount >= 0)
    .sort(([a], [b]) => Number(a) - Number(b))
    .map(([number, amount]) => `${String(Number(number)).padStart(2, '0')}:${amount}`)
    .join(', ')
}

export function parseHotLimits(value: string) {
  const result: Record<string, number> = {}
  const entries = value.split(',').map((entry) => entry.trim()).filter(Boolean)
  for (const entry of entries) {
    const [rawNumber, rawAmount, ...rest] = entry.split(':').map((part) => part.trim())
    const numericNumber = Number(rawNumber)
    const numericAmount = Number(rawAmount)
    if (rest.length || !rawNumber || !rawAmount || !/^\d{1,2}$/.test(rawNumber) || numericNumber < 0 || numericNumber > 99 || !Number.isInteger(numericAmount) || numericAmount < 0) {
      throw new Error('Hot limits must use 00–99:amount pairs')
    }
    const key = String(numericNumber).padStart(2, '0')
    // "5:100, 05:200" would otherwise silently keep only the last amount.
    if (key in result) {
      throw new Error(`Hot limit ${key} is listed twice.`)
    }
    result[key] = numericAmount
  }
  return result
}
