import { cx } from '../lib/format'

// Spring checkmark used on successful submits.
export function SpringCheck({ className, size = 'h-6 w-6' }: { className?: string; size?: string }) {
  return (
    <span
      className={cx(
        'inline-flex animate-check-pop items-center justify-center rounded-full bg-emerald-500 text-white',
        size,
        className,
      )}
    >
      <svg viewBox="0 0 24 24" fill="none" className="h-3/5 w-3/5" aria-hidden="true">
        <path
          d="M20 6 9 17l-5-5"
          stroke="currentColor"
          strokeWidth="3"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    </span>
  )
}
