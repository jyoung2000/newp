import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../lib/api'
import { qk } from '../lib/queryKeys'
import type { ApplicationOut, RunOut } from '../lib/types'
import { pickActiveRun, isRunActive, runDone } from '../lib/runs'
import { PageHeader } from '../components/PageHeader'
import { Card, CardHeader } from '../components/Card'
import { Button } from '../components/Button'
import { Badge } from '../components/Badge'
import { StatusBadge } from '../components/StatusBadge'
import { Icon } from '../components/Icon'
import { EmptyState } from '../components/EmptyState'
import { SkeletonRows } from '../components/Skeleton'
import { useToast } from '../lib/toast'
import { cx, titleCase } from '../lib/format'

const SHORTCUTS = [
  ['j / k', 'Move between cards'],
  ['a', 'Handle (open interventions)'],
  ['e', 'Open details'],
  ['s', 'Skip application'],
]

export function Queue() {
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const { push } = useToast()
  const [focus, setFocus] = useState(0)
  const cardRefs = useRef<(HTMLDivElement | null)[]>([])

  const runs = useQuery({
    queryKey: qk.runs,
    queryFn: () => api.get<RunOut[]>('/api/runs'),
    refetchInterval: 5000,
  })
  const run = pickActiveRun(runs.data)

  const apps = useQuery({
    queryKey: qk.applications({ scope: 'queue' }),
    queryFn: () => api.get<ApplicationOut[]>('/api/applications?limit=200'),
    refetchInterval: 5000,
  })

  const runApps = useMemo(
    () => (run ? (apps.data ?? []).filter((a) => a.run_batch_id === run.id) : []),
    [apps.data, run],
  )

  const control = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'pause' | 'resume' | 'stop' }) =>
      api.post(`/api/runs/${id}/${action}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.runs })
      queryClient.invalidateQueries({ queryKey: ['applications'] })
    },
    onError: (e) => push({ title: 'Action failed', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const skip = useMutation({
    mutationFn: (id: number) => api.post(`/api/applications/${id}/skip`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['applications'] })
      push({ title: 'Application skipped', tone: 'info' })
    },
    onError: (e) => push({ title: 'Could not skip', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  // Keyboard navigation / quick actions on the focused card.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return
      if (runApps.length === 0) return
      if (e.key === 'j') {
        setFocus((f) => Math.min(runApps.length - 1, f + 1))
      } else if (e.key === 'k') {
        setFocus((f) => Math.max(0, f - 1))
      } else if (e.key === 's') {
        const app = runApps[focus]
        if (app) skip.mutate(app.id)
      } else if (e.key === 'a') {
        const app = runApps[focus]
        if (app && app.open_interventions > 0) navigate('/interventions')
      } else if (e.key === 'e') {
        const app = runApps[focus]
        if (app) navigate(`/applications?focus=${app.id}`)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [runApps, focus, skip, navigate])

  useEffect(() => {
    cardRefs.current[focus]?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [focus])

  const active = run ? isRunActive(run) : false

  return (
    <div>
      <PageHeader
        title="Queue"
        subtitle="Live application run"
        actions={
          run && active ? (
            <div className="flex gap-2">
              {run.status === 'paused' ? (
                <Button variant="secondary" icon="play" onClick={() => control.mutate({ id: run.id, action: 'resume' })}>
                  Resume
                </Button>
              ) : (
                <Button variant="secondary" icon="pause" onClick={() => control.mutate({ id: run.id, action: 'pause' })}>
                  Pause
                </Button>
              )}
              <Button variant="danger" icon="stop" onClick={() => control.mutate({ id: run.id, action: 'stop' })}>
                Stop
              </Button>
            </div>
          ) : undefined
        }
      />

      {runs.isLoading ? (
        <Card>
          <SkeletonRows rows={4} />
        </Card>
      ) : !run ? (
        <Card>
          <EmptyState
            icon="queue"
            title="No runs yet"
            description="Select listings and start applying — the live run appears here."
            action={
              <Link to="/listings">
                <Button variant="primary" icon="sparkles">
                  Browse listings
                </Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <>
          <Card>
            <CardHeader
              title={`Run #${run.id}`}
              subtitle={`${titleCase(run.mode)} mode · ${titleCase(run.executor ?? 'auto')} executor`}
              action={<StatusBadge status={run.status} />}
            />
            <div className="grid grid-cols-3 gap-2 text-center sm:grid-cols-6">
              {(
                [
                  ['Queued', run.queued],
                  ['Filling', run.filling],
                  ['Needs you', run.needs_human],
                  ['Submitted', run.submitted],
                  ['Drafted', run.drafted],
                  ['Failed', run.failed],
                ] as const
              ).map(([label, val]) => (
                <div key={label} className="rounded-xl bg-neutral-50 py-2.5 dark:bg-neutral-800/50">
                  <div className="text-xl font-semibold tabular-nums text-neutral-900 dark:text-neutral-100">{val}</div>
                  <div className="text-[11px] text-neutral-500 dark:text-neutral-400">{label}</div>
                </div>
              ))}
            </div>
            <p className="mt-3 text-sm text-neutral-500">
              {runDone(run)} of {run.total} processed
            </p>
          </Card>

          <div className="mt-4 flex items-center justify-between">
            <h2 className="text-sm font-semibold text-neutral-700 dark:text-neutral-300">Applications</h2>
            <div className="hidden items-center gap-3 text-xs text-neutral-400 sm:flex">
              {SHORTCUTS.map(([k, d]) => (
                <span key={k} className="inline-flex items-center gap-1.5">
                  <kbd className="rounded border border-neutral-300 bg-neutral-100 px-1.5 py-0.5 font-mono text-[10px] text-neutral-600 dark:border-neutral-700 dark:bg-neutral-800 dark:text-neutral-300">
                    {k}
                  </kbd>
                  {d}
                </span>
              ))}
            </div>
          </div>

          {runApps.length === 0 ? (
            <Card className="mt-3">
              <EmptyState compact icon="check" title="Nothing in flight" description="Applications for this run will appear here as they process." />
            </Card>
          ) : (
            <div className="mt-3 space-y-2.5">
              {runApps.map((app, i) => (
                <div
                  key={app.id}
                  ref={(el) => (cardRefs.current[i] = el)}
                  tabIndex={0}
                  onClick={() => setFocus(i)}
                  onFocus={() => setFocus(i)}
                  className={cx(
                    'card p-4 outline-none transition-shadow',
                    i === focus && 'ring-2 ring-accent-500 ring-offset-2 ring-offset-white dark:ring-offset-neutral-950',
                  )}
                >
                  <div className="flex items-center gap-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <p className="truncate font-medium text-neutral-900 dark:text-neutral-100">
                          {app.title ?? `Listing #${app.listing_id}`}
                        </p>
                        <StatusBadge status={app.status} />
                        {app.open_interventions > 0 ? (
                          <Badge tone="warning" dot>
                            {app.open_interventions} to handle
                          </Badge>
                        ) : null}
                      </div>
                      <p className="mt-0.5 truncate text-sm text-neutral-500 dark:text-neutral-400">
                        {app.company ?? '—'}
                        {app.needs_human_reason ? ` · ${titleCase(app.needs_human_reason)}` : ''}
                      </p>
                    </div>
                    <div className="flex shrink-0 items-center gap-1.5">
                      {app.open_interventions > 0 ? (
                        <Link to="/interventions">
                          <Button size="sm" variant="primary" icon="inbox">
                            Handle
                          </Button>
                        </Link>
                      ) : null}
                      <Button size="sm" variant="ghost" icon="skip" onClick={() => skip.mutate(app.id)}>
                        Skip
                      </Button>
                      <button
                        onClick={() => navigate(`/applications?focus=${app.id}`)}
                        className="rounded-lg p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-600 dark:hover:bg-neutral-800"
                        aria-label="Open details"
                      >
                        <Icon name="chevronRight" className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </div>
  )
}
