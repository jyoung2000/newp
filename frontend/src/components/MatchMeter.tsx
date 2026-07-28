import { cx, scoreTone } from '../lib/format'

const TONE_BAR: Record<string, string> = {
  high: 'bg-emerald-500',
  mid: 'bg-amber-500',
  low: 'bg-neutral-400',
  none: 'bg-neutral-300 dark:bg-neutral-700',
}
const TONE_TEXT: Record<string, string> = {
  high: 'text-emerald-600 dark:text-emerald-400',
  mid: 'text-amber-600 dark:text-amber-400',
  low: 'text-neutral-500 dark:text-neutral-400',
  none: 'text-neutral-400',
}

export function MatchMeter({
  score,
  className,
  showValue = true,
  width = 'w-24',
}: {
  score: number | null | undefined
  className?: string
  showValue?: boolean
  width?: string
}) {
  const tone = scoreTone(score)
  const pct = Math.max(0, Math.min(100, score ?? 0))
  return (
    <div className={cx('flex items-center gap-2', className)}>
      <div
        className={cx('h-2 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800', width)}
        role="progressbar"
        aria-valuenow={score ?? 0}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label="Match score"
      >
        <div
          className={cx('h-full rounded-full transition-[width] duration-500', TONE_BAR[tone])}
          style={{ width: `${pct}%` }}
        />
      </div>
      {showValue ? (
        <span className={cx('w-8 text-right text-xs font-semibold tabular-nums', TONE_TEXT[tone])}>
          {score == null ? '—' : Math.round(score)}
        </span>
      ) : null}
    </div>
  )
}
