import { Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { qk } from '../lib/queryKeys'
import type { RunOut } from '../lib/types'
import { pickActiveRun, isRunActive, runDone } from '../lib/runs'
import { Icon } from '../components/Icon'
import { ThemeToggle } from './ThemeToggle'
import { StatusBadge } from './StatusBadge'
import { useRealtime } from '../lib/ws'
import { cx } from '../lib/format'

function RunStatusPill() {
  const { data } = useQuery({
    queryKey: qk.runs,
    queryFn: () => api.get<RunOut[]>('/api/runs'),
    refetchInterval: 8000,
  })
  const run = pickActiveRun(data)
  if (!run) return null
  const active = isRunActive(run)
  const done = runDone(run)
  return (
    <Link
      to="/queue"
      className="inline-flex items-center gap-2 rounded-full border border-neutral-200 bg-white/60 py-1 pl-2 pr-3 text-sm shadow-sm transition-colors hover:bg-neutral-50 dark:border-neutral-800 dark:bg-neutral-900/60 dark:hover:bg-neutral-800"
    >
      {active ? (
        <span className="relative flex h-2 w-2">
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-500 opacity-75" />
          <span className="relative inline-flex h-2 w-2 rounded-full bg-accent-600" />
        </span>
      ) : (
        <Icon name="check" className="h-4 w-4 text-emerald-500" />
      )}
      <span className="hidden font-medium text-neutral-700 sm:inline dark:text-neutral-200">
        Run #{run.id}
      </span>
      <StatusBadge status={run.status} dot={false} />
      <span className="hidden text-xs tabular-nums text-neutral-500 md:inline dark:text-neutral-400">
        {done}/{run.total}
      </span>
    </Link>
  )
}

function ConnectionDot() {
  const { connected } = useRealtime()
  return (
    <span
      className={cx(
        'inline-flex h-9 w-9 items-center justify-center rounded-xl',
        connected ? 'text-emerald-500' : 'text-neutral-400',
      )}
      title={connected ? 'Live updates connected' : 'Reconnecting…'}
    >
      <Icon name={connected ? 'wifi' : 'wifiOff'} className="h-[18px] w-[18px]" />
    </span>
  )
}

export function TopBar({ title }: { title?: string }) {
  return (
    <header className="sticky top-0 z-30 flex h-16 items-center gap-3 border-b border-neutral-200/70 bg-white/70 px-4 backdrop-blur-xl sm:px-6 dark:border-neutral-800/70 dark:bg-neutral-950/70">
      <div className="flex items-center gap-2 lg:hidden">
        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-600 text-white">
          <Icon name="onboarding" className="h-4 w-4" />
        </div>
        <span className="text-base font-semibold tracking-tightheading">JobPilot</span>
      </div>
      {title ? (
        <h1 className="hidden text-lg font-semibold tracking-tightheading text-neutral-900 lg:block dark:text-neutral-100">
          {title}
        </h1>
      ) : null}
      <div className="ml-auto flex items-center gap-2">
        <RunStatusPill />
        <ConnectionDot />
        <ThemeToggle />
      </div>
    </header>
  )
}
