import { Link } from 'react-router-dom'
import { Icon, type IconName } from './Icon'
import { cx } from '../lib/format'

interface StatCardProps {
  label: string
  value: number | string
  icon: IconName
  tone?: 'accent' | 'success' | 'warning' | 'purple' | 'neutral'
  to?: string
  hint?: string
}

const TONE: Record<NonNullable<StatCardProps['tone']>, string> = {
  accent: 'bg-accent-50 text-accent-600 dark:bg-accent-500/15 dark:text-accent-400',
  success: 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400',
  warning: 'bg-amber-50 text-amber-600 dark:bg-amber-500/15 dark:text-amber-400',
  purple: 'bg-violet-50 text-violet-600 dark:bg-violet-500/15 dark:text-violet-400',
  neutral: 'bg-neutral-100 text-neutral-600 dark:bg-neutral-800 dark:text-neutral-300',
}

export function StatCard({ label, value, icon, tone = 'neutral', to, hint }: StatCardProps) {
  const inner = (
    <div className="card h-full p-4 transition-shadow hover:shadow-md sm:p-5">
      <div className="flex items-start justify-between">
        <span className="text-sm font-medium text-neutral-500 dark:text-neutral-400">{label}</span>
        <span className={cx('flex h-8 w-8 items-center justify-center rounded-lg', TONE[tone])}>
          <Icon name={icon} className="h-[18px] w-[18px]" />
        </span>
      </div>
      <div className="mt-2 text-3xl font-semibold tracking-tightheading text-neutral-900 tabular-nums dark:text-white">
        {value}
      </div>
      {hint ? <p className="mt-1 text-xs text-neutral-400">{hint}</p> : null}
    </div>
  )
  return to ? (
    <Link to={to} className="block focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 rounded-2xl">
      {inner}
    </Link>
  ) : (
    inner
  )
}
