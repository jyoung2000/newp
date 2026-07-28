// Formatting helpers shared across routes.

export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(' ')
}

export function fmtDate(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' })
}

export function fmtDateTime(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  return d.toLocaleString(undefined, {
    year: 'numeric',
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function fmtRelative(value: string | null | undefined): string {
  if (!value) return '—'
  const d = new Date(value)
  if (Number.isNaN(d.getTime())) return '—'
  const diff = d.getTime() - Date.now()
  const abs = Math.abs(diff)
  const rtf = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' })
  const units: Array<[Intl.RelativeTimeFormatUnit, number]> = [
    ['year', 1000 * 60 * 60 * 24 * 365],
    ['month', 1000 * 60 * 60 * 24 * 30],
    ['day', 1000 * 60 * 60 * 24],
    ['hour', 1000 * 60 * 60],
    ['minute', 1000 * 60],
  ]
  for (const [unit, ms] of units) {
    if (abs >= ms) return rtf.format(Math.round(diff / ms), unit)
  }
  return rtf.format(Math.round(diff / 1000), 'second')
}

export function fmtSalary(
  min: number | null | undefined,
  max: number | null | undefined,
  currency: string | null | undefined,
  period: string | null | undefined,
  raw?: string | null,
): string {
  if (min == null && max == null) return raw || '—'
  const cur = currency || 'USD'
  const nf = new Intl.NumberFormat(undefined, {
    style: 'currency',
    currency: cur,
    maximumFractionDigits: 0,
  })
  const per = period ? `/${period === 'year' ? 'yr' : period === 'month' ? 'mo' : period}` : ''
  let money: string
  try {
    if (min != null && max != null && min !== max) money = `${nf.format(min)}–${nf.format(max)}`
    else money = nf.format((min ?? max) as number)
  } catch {
    money = `${min ?? ''}${max != null && max !== min ? `–${max}` : ''} ${cur}`
  }
  return `${money}${per}`
}

export function initials(first?: string | null, last?: string | null, email?: string | null): string {
  const a = (first || '').trim()
  const b = (last || '').trim()
  if (a || b) return `${a.charAt(0)}${b.charAt(0)}`.toUpperCase() || '?'
  if (email) return email.charAt(0).toUpperCase()
  return '?'
}

export function titleCase(s: string): string {
  return s
    .replace(/[_-]+/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .trim()
}

export function humanKind(kind: string): string {
  switch (kind) {
    case 'unknown_field':
      return 'Unknown field'
    case 'draft_approval':
      return 'Draft approval'
    case 'challenge':
      return 'Human challenge'
    case 'review':
      return 'Review before submit'
    case 'error':
      return 'Error'
    default:
      return titleCase(kind)
  }
}

// Colored buckets for a 0–100 match score.
export function scoreTone(score: number | null | undefined): 'high' | 'mid' | 'low' | 'none' {
  if (score == null) return 'none'
  if (score >= 75) return 'high'
  if (score >= 50) return 'mid'
  return 'low'
}
