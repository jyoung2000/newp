import { cx } from '../lib/format'

export type BadgeTone = 'neutral' | 'accent' | 'success' | 'warning' | 'error' | 'purple'

const TONES: Record<BadgeTone, string> = {
  neutral:
    'bg-neutral-100 text-neutral-700 ring-neutral-200 dark:bg-neutral-800 dark:text-neutral-300 dark:ring-neutral-700',
  accent:
    'bg-accent-50 text-accent-700 ring-accent-200 dark:bg-accent-500/15 dark:text-accent-300 dark:ring-accent-500/30',
  success:
    'bg-emerald-50 text-emerald-700 ring-emerald-200 dark:bg-emerald-500/15 dark:text-emerald-300 dark:ring-emerald-500/30',
  warning:
    'bg-amber-50 text-amber-700 ring-amber-200 dark:bg-amber-500/15 dark:text-amber-300 dark:ring-amber-500/30',
  error:
    'bg-red-50 text-red-700 ring-red-200 dark:bg-red-500/15 dark:text-red-300 dark:ring-red-500/30',
  purple:
    'bg-violet-50 text-violet-700 ring-violet-200 dark:bg-violet-500/15 dark:text-violet-300 dark:ring-violet-500/30',
}

interface BadgeProps {
  tone?: BadgeTone
  children: React.ReactNode
  className?: string
  dot?: boolean
}

export function Badge({ tone = 'neutral', children, className, dot }: BadgeProps) {
  return (
    <span
      className={cx(
        'inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ring-1 ring-inset',
        TONES[tone],
        className,
      )}
    >
      {dot ? <span className="h-1.5 w-1.5 rounded-full bg-current opacity-80" /> : null}
      {children}
    </span>
  )
}
