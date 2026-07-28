import { Icon, type IconName } from './Icon'

interface EmptyStateProps {
  icon?: IconName
  title: string
  description?: string
  action?: React.ReactNode
  compact?: boolean
}

export function EmptyState({ icon = 'sparkles', title, description, action, compact }: EmptyStateProps) {
  return (
    <div
      className={
        'flex flex-col items-center justify-center rounded-2xl border border-dashed border-neutral-300 text-center dark:border-neutral-700 ' +
        (compact ? 'px-6 py-8' : 'px-6 py-14')
      }
    >
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-50 text-accent-600 dark:bg-accent-500/15 dark:text-accent-400">
        <Icon name={icon} className="h-6 w-6" />
      </div>
      <h3 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">{title}</h3>
      {description ? (
        <p className="mt-1 max-w-sm text-sm text-neutral-500 dark:text-neutral-400">{description}</p>
      ) : null}
      {action ? <div className="mt-4">{action}</div> : null}
    </div>
  )
}
