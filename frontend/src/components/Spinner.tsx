import { cx } from '../lib/format'

export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      className={cx('animate-spin text-current', className || 'h-5 w-5')}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path
        className="opacity-90"
        fill="currentColor"
        d="M4 12a8 8 0 0 1 8-8V0C5.4 0 0 5.4 0 12h4z"
      />
    </svg>
  )
}
