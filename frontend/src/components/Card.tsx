import { cx } from '../lib/format'

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  padded?: boolean
}

export function Card({ padded = true, className, children, ...rest }: CardProps) {
  return (
    <div className={cx('card', padded && 'p-5', className)} {...rest}>
      {children}
    </div>
  )
}

export function CardHeader({
  title,
  subtitle,
  action,
  icon,
}: {
  title: React.ReactNode
  subtitle?: React.ReactNode
  action?: React.ReactNode
  icon?: React.ReactNode
}) {
  return (
    <div className="mb-4 flex items-start justify-between gap-3">
      <div className="flex items-start gap-3">
        {icon ? <div className="mt-0.5 text-accent-600 dark:text-accent-400">{icon}</div> : null}
        <div>
          <h3 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">{title}</h3>
          {subtitle ? (
            <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">{subtitle}</p>
          ) : null}
        </div>
      </div>
      {action}
    </div>
  )
}
