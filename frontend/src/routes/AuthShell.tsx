import { Icon } from '../components/Icon'
import { ThemeToggle } from '../components/ThemeToggle'

export function AuthShell({
  title,
  subtitle,
  children,
  footer,
}: {
  title: string
  subtitle?: string
  children: React.ReactNode
  footer?: React.ReactNode
}) {
  return (
    <div className="relative flex min-h-full items-center justify-center overflow-hidden px-4 py-12">
      <div className="pointer-events-none absolute inset-0 -z-10">
        <div className="absolute -top-24 left-1/2 h-72 w-[36rem] -translate-x-1/2 rounded-full bg-accent-500/15 blur-3xl" />
      </div>
      <div className="absolute right-4 top-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-sm">
        <div className="mb-6 flex flex-col items-center text-center">
          <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-accent-600 text-white shadow-lg shadow-accent-600/25">
            <Icon name="onboarding" className="h-7 w-7" />
          </div>
          <h1 className="text-xl font-semibold tracking-tightheading text-neutral-900 dark:text-white">
            {title}
          </h1>
          {subtitle ? (
            <p className="mt-1 text-sm text-neutral-500 dark:text-neutral-400">{subtitle}</p>
          ) : null}
        </div>
        <div className="card p-6">{children}</div>
        {footer ? <div className="mt-4 text-center text-sm text-neutral-500">{footer}</div> : null}
        <p className="mt-6 flex items-center justify-center gap-1.5 text-center text-xs text-neutral-400">
          <Icon name="lock" className="h-3.5 w-3.5" />
          Self-hosted · your data stays on your server
        </p>
      </div>
    </div>
  )
}
