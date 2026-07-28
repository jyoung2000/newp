import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../lib/api'
import { qk } from '../lib/queryKeys'
import type { ApplicationDetail, ApplicationOutcome, EventOut } from '../lib/types'
import { Drawer } from './Drawer'
import { Button } from './Button'
import { Badge } from './Badge'
import { StatusBadge } from './StatusBadge'
import { Icon } from './Icon'
import { AuthImage } from './AuthImage'
import { SkeletonText } from './Skeleton'
import { Select } from './Field'
import { useToast } from '../lib/toast'
import { fmtDateTime, titleCase } from '../lib/format'

const OUTCOMES: { value: ApplicationOutcome; label: string }[] = [
  { value: 'none', label: 'No outcome yet' },
  { value: 'no_response', label: 'No response' },
  { value: 'rejected', label: 'Rejected' },
  { value: 'recruiter_reply', label: 'Recruiter reply' },
  { value: 'interview', label: 'Interview' },
  { value: 'offer', label: 'Offer' },
]

function eventDetail(ev: EventOut): string | null {
  const p = ev.payload as Record<string, unknown>
  if (!p) return null
  const bits: string[] = []
  for (const key of ['reason', 'detail', 'status', 'field', 'message']) {
    const v = p[key]
    if (typeof v === 'string' && v) bits.push(titleCase(key) + ': ' + v)
  }
  return bits.length > 0 ? bits.join(' · ') : null
}

function Timeline({ events }: { events: EventOut[] }) {
  if (events.length === 0) {
    return <p className="text-sm text-neutral-400">No events recorded yet.</p>
  }
  const sorted = [...events].sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
  return (
    <ol className="relative ml-1.5 space-y-4 border-l border-neutral-200 pl-5 dark:border-neutral-800">
      {sorted.map((ev) => {
        const detail = eventDetail(ev)
        return (
          <li key={ev.id} className="relative">
            <span className="absolute -left-[27px] top-0.5 flex h-4 w-4 items-center justify-center rounded-full bg-accent-100 ring-2 ring-white dark:bg-accent-500/25 dark:ring-neutral-900">
              <span className="h-1.5 w-1.5 rounded-full bg-accent-600" />
            </span>
            <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">{titleCase(ev.type)}</p>
            <p className="text-xs text-neutral-400">{fmtDateTime(ev.created_at)}</p>
            {detail ? <p className="mt-0.5 text-xs text-neutral-500 dark:text-neutral-400">{detail}</p> : null}
          </li>
        )
      })}
    </ol>
  )
}

function FieldSnapshot({ snapshot }: { snapshot: Record<string, unknown> }) {
  const entries = Object.entries(snapshot)
  if (entries.length === 0) return <p className="text-sm text-neutral-400">No fields captured.</p>
  return (
    <dl className="divide-y divide-neutral-100 rounded-xl border border-neutral-200 dark:divide-neutral-800 dark:border-neutral-800">
      {entries.map(([k, v]) => (
        <div key={k} className="flex gap-3 px-3 py-2 text-sm">
          <dt className="w-1/3 shrink-0 font-medium text-neutral-500 dark:text-neutral-400">{titleCase(k)}</dt>
          <dd className="min-w-0 flex-1 break-words text-neutral-800 dark:text-neutral-200">
            {v == null ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v)}
          </dd>
        </div>
      ))}
    </dl>
  )
}

export function ApplicationDrawer({ appId, onClose }: { appId: number | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { push } = useToast()

  const { data, isLoading } = useQuery({
    queryKey: qk.application(appId ?? 0),
    queryFn: () => api.get<ApplicationDetail>(`/api/applications/${appId}`),
    enabled: appId != null,
  })

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['applications'] })
    if (appId) queryClient.invalidateQueries({ queryKey: qk.application(appId) })
  }

  const setOutcome = useMutation({
    mutationFn: (outcome: ApplicationOutcome) => api.post(`/api/applications/${appId}/outcome`, { outcome }),
    onSuccess: () => {
      invalidate()
      push({ title: 'Outcome updated', tone: 'success' })
    },
    onError: (e) => push({ title: 'Update failed', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })
  const requeue = useMutation({
    mutationFn: () => api.post(`/api/applications/${appId}/requeue`),
    onSuccess: () => {
      invalidate()
      push({ title: 'Re-queued', tone: 'success' })
    },
    onError: (e) => push({ title: 'Could not requeue', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })
  const skip = useMutation({
    mutationFn: () => api.post(`/api/applications/${appId}/skip`),
    onSuccess: () => {
      invalidate()
      push({ title: 'Skipped', tone: 'info' })
    },
    onError: (e) => push({ title: 'Could not skip', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const shot = data?.confirmation_screenshot_url ?? (appId ? `/api/applications/${appId}/screenshot` : null)
  const snapshot = (data?.field_snapshot ?? null) as Record<string, unknown> | null

  return (
    <Drawer
      open={appId != null}
      onClose={onClose}
      title={data?.title ?? 'Application'}
      subtitle={data?.company ?? undefined}
    >
      {isLoading || !data ? (
        <SkeletonText lines={8} />
      ) : (
        <div className="space-y-6">
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge status={data.status} />
            <Badge tone="neutral">{titleCase(data.mode)} mode</Badge>
            {data.executor ? <Badge tone="neutral">{titleCase(data.executor)}</Badge> : null}
            {data.humanize ? <Badge tone="accent">Humanized</Badge> : null}
          </div>

          {data.error ? (
            <div className="flex items-start gap-2 rounded-xl bg-red-50 p-3 text-sm text-red-700 dark:bg-red-500/10 dark:text-red-300">
              <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
              {data.error}
            </div>
          ) : null}

          <section>
            <label className="label">Outcome</label>
            <Select value={data.outcome} onChange={(e) => setOutcome.mutate(e.target.value as ApplicationOutcome)}>
              {OUTCOMES.map((o) => (
                <option key={o.value} value={o.value}>
                  {o.label}
                </option>
              ))}
            </Select>
          </section>

          <section>
            <h4 className="mb-3 text-sm font-semibold text-neutral-900 dark:text-neutral-100">Timeline</h4>
            <Timeline events={data.events} />
          </section>

          {snapshot ? (
            <section>
              <h4 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">Filled fields</h4>
              <FieldSnapshot snapshot={snapshot} />
            </section>
          ) : null}

          <section>
            <h4 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">Confirmation</h4>
            <AuthImage src={shot} alt="Confirmation screenshot" cropHeight="max-h-80" />
          </section>

          <div className="flex flex-wrap gap-2 border-t border-neutral-200 pt-4 dark:border-neutral-800">
            <Button variant="secondary" icon="refresh" onClick={() => requeue.mutate()} loading={requeue.isPending}>
              Re-queue
            </Button>
            <Button variant="ghost" icon="skip" onClick={() => skip.mutate()} loading={skip.isPending}>
              Skip
            </Button>
            {data.listing_url ? (
              <a href={data.listing_url} target="_blank" rel="noreferrer" className="ml-auto">
                <Button variant="ghost" iconRight="external">
                  Listing
                </Button>
              </a>
            ) : null}
          </div>
        </div>
      )}
    </Drawer>
  )
}
