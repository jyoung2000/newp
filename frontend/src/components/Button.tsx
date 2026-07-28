import { forwardRef } from 'react'
import { cx } from '../lib/format'
import { Icon, type IconName } from './Icon'
import { Spinner } from './Spinner'

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger' | 'subtle'
type Size = 'sm' | 'md' | 'lg'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  icon?: IconName
  iconRight?: IconName
  block?: boolean
}

const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-accent-600 text-white hover:bg-accent-700 active:bg-accent-700 border border-transparent shadow-sm',
  secondary:
    'bg-white text-neutral-800 hover:bg-neutral-50 border border-neutral-300 shadow-sm dark:bg-neutral-900 dark:text-neutral-100 dark:border-neutral-700 dark:hover:bg-neutral-800',
  ghost:
    'bg-transparent text-neutral-700 hover:bg-neutral-100 border border-transparent dark:text-neutral-300 dark:hover:bg-neutral-800',
  danger:
    'bg-red-600 text-white hover:bg-red-700 border border-transparent shadow-sm',
  subtle:
    'bg-neutral-100 text-neutral-800 hover:bg-neutral-200 border border-transparent dark:bg-neutral-800 dark:text-neutral-100 dark:hover:bg-neutral-700',
}

const SIZES: Record<Size, string> = {
  sm: 'h-8 px-3 text-xs gap-1.5 rounded-lg',
  md: 'h-10 px-4 text-sm gap-2 rounded-xl',
  lg: 'h-11 px-5 text-sm gap-2 rounded-xl',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  { variant = 'secondary', size = 'md', loading, icon, iconRight, block, className, children, disabled, ...rest },
  ref,
) {
  return (
    <button
      ref={ref}
      className={cx(
        'inline-flex select-none items-center justify-center font-medium transition-colors duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-500 focus-visible:ring-offset-2 focus-visible:ring-offset-white dark:focus-visible:ring-offset-neutral-950',
        'disabled:cursor-not-allowed disabled:opacity-50',
        VARIANTS[variant],
        SIZES[size],
        block && 'w-full',
        className,
      )}
      disabled={disabled || loading}
      {...rest}
    >
      {loading ? <Spinner className="h-4 w-4" /> : icon ? <Icon name={icon} className="h-4 w-4" /> : null}
      {children}
      {iconRight && !loading ? <Icon name={iconRight} className="h-4 w-4" /> : null}
    </button>
  )
})
