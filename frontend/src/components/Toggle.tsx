import { cx } from '../lib/format'

interface ToggleProps {
  checked: boolean
  onChange: (v: boolean) => void
  label?: string
  description?: string
  disabled?: boolean
  id?: string
}

export function Toggle({ checked, onChange, label, description, disabled, id }: ToggleProps) {
  const button = (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      aria-label={label}
      disabled={disabled}
      onClick={() => onChange(!checked)}
      className={cx(
        'relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-neutral-950',
        checked ? 'bg-accent-600' : 'bg-neutral-300 dark:bg-neutral-700',
        disabled && 'cursor-not-allowed opacity-50',
      )}
    >
      <span
        className={cx(
          'inline-block h-5 w-5 transform rounded-full bg-white shadow transition-transform duration-150',
          checked ? 'translate-x-5' : 'translate-x-0.5',
        )}
      />
    </button>
  )

  if (!label && !description) return button

  return (
    <label className="flex cursor-pointer items-center justify-between gap-4">
      <span className="min-w-0">
        {label ? (
          <span className="block text-sm font-medium text-neutral-800 dark:text-neutral-200">
            {label}
          </span>
        ) : null}
        {description ? (
          <span className="mt-0.5 block text-xs text-neutral-500 dark:text-neutral-400">
            {description}
          </span>
        ) : null}
      </span>
      {button}
    </label>
  )
}
