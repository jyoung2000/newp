import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api, qs } from '../lib/api'
import { qk } from '../lib/queryKeys'
import { useDebouncedValue } from '../lib/useDebounce'
import type { ApplicationOut } from '../lib/types'
import { PageHeader } from '../components/PageHeader'
import { Card } from '../components/Card'
import { Badge } from '../components/Badge'
import { StatusBadge } from '../components/StatusBadge'
import { Select } from '../components/Field'
import { Icon } from '../components/Icon'
import { EmptyState } from '../components/EmptyState'
import { SkeletonRows } from '../components/Skeleton'
import { ApplicationDrawer } from '../components/ApplicationDrawer'
import { fmtDateTime, titleCase } from '../lib/format'

const STATUS_OPTIONS = [
  { value: '', label: 'All statuses' },
  { value: 'queued', label: 'Queued' },
  { value: 'filling', label: 'Filling' },
  { value: 'needs_human', label: 'Needs you' },
  { value: 'submitted', label: 'Submitted' },
  { value: 'drafted', label: 'Drafted' },
  { value: 'failed', label: 'Failed' },
  { value: 'skipped', label: 'Skipped' },
  { value: 'stopped', label: 'Stopped' },
]

const OUTCOME_TONE: Record<string, 'neutral' | 'accent' | 'success' | 'purple' | 'error'> = {
  none: 'neutral',
  no_response: 'neutral',
  rejected: 'error',
  recruiter_reply: 'accent',
  interview: 'purple',
  offer: 'success',
}

function hostOf(url: string | null | undefined): string {
  if (!url) return '—'
  try {
    return new URL(url).hostname.replace(/^www\./, '')
  } catch {
    return '—'
  }
}

export function Applications() {
  const [params, setParams] = useSearchParams()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')
  const [drawerId, setDrawerId] = useState<number | null>(null)
  const debouncedQ = useDebouncedValue(q, 350)

  // Open a specific application when arriving via ?focus=.
  useEffect(() => {
    const focus = params.get('focus')
    if (focus) {
      setDrawerId(Number(focus))
      params.delete('focus')
      setParams(params, { replace: true })
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const query = { status, q: debouncedQ, limit: 200 }
  const { data, isLoading } = useQuery({
    queryKey: qk.applications(query),
    queryFn: () => api.get<ApplicationOut[]>(`/api/applications${qs(query)}`),
    refetchInterval: 15000,
  })

  const rows = data ?? []

  return (
    <div>
      <PageHeader
        title="Applications"
        subtitle="Every application, with a full timeline"
        actions={
          <a href="/api/transfer/applications.csv">
            <span className="inline-flex h-10 items-center gap-2 rounded-xl border border-neutral-300 bg-white px-4 text-sm font-medium text-neutral-800 shadow-sm hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100 dark:hover:bg-neutral-800">
              <Icon name="download" className="h-4 w-4" />
              Export CSV
            </span>
          </a>
        }
      />

      <Card padded={false} className="p-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
          <div className="relative flex-1">
            <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search role or company…"
              className="input pl-9"
              aria-label="Search applications"
            />
          </div>
          <Select value={status} onChange={(e) => setStatus(e.target.value)} aria-label="Status filter" className="sm:w-48">
            {STATUS_OPTIONS.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      <Card padded={false} className="mt-3 overflow-hidden">
        {isLoading ? (
          <div className="p-4">
            <SkeletonRows rows={6} />
          </div>
        ) : rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon="applications"
              title="No applications yet"
              description="Applications you start from listings will be logged here."
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[760px] text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500 dark:border-neutral-800">
                  <th className="px-4 py-2.5 font-medium">When</th>
                  <th className="px-4 py-2.5 font-medium">Role</th>
                  <th className="hidden px-4 py-2.5 font-medium lg:table-cell">Source</th>
                  <th className="hidden px-4 py-2.5 font-medium md:table-cell">Executor</th>
                  <th className="hidden px-4 py-2.5 font-medium sm:table-cell">Mode</th>
                  <th className="px-4 py-2.5 font-medium">Status</th>
                  <th className="px-4 py-2.5 font-medium">Outcome</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <tr
                    key={a.id}
                    onClick={() => setDrawerId(a.id)}
                    className="cursor-pointer border-b border-neutral-100 transition-colors hover:bg-neutral-50 dark:border-neutral-800/60 dark:hover:bg-neutral-800/40"
                  >
                    <td className="whitespace-nowrap px-4 py-3 text-neutral-500 dark:text-neutral-400">
                      {fmtDateTime(a.submitted_at ?? a.created_at)}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2 font-medium text-neutral-900 dark:text-neutral-100">
                        <span className="line-clamp-1">{a.title ?? `Listing #${a.listing_id}`}</span>
                        {a.open_interventions > 0 ? (
                          <Badge tone="warning" dot>
                            {a.open_interventions}
                          </Badge>
                        ) : null}
                      </div>
                      <div className="mt-0.5 line-clamp-1 text-xs text-neutral-500 dark:text-neutral-400">{a.company ?? '—'}</div>
                    </td>
                    <td className="hidden px-4 py-3 text-neutral-500 lg:table-cell dark:text-neutral-400">{hostOf(a.listing_url)}</td>
                    <td className="hidden px-4 py-3 text-neutral-500 md:table-cell dark:text-neutral-400">
                      {a.executor ? titleCase(a.executor) : '—'}
                    </td>
                    <td className="hidden px-4 py-3 sm:table-cell">
                      <Badge tone="neutral">{titleCase(a.mode)}</Badge>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={a.status} />
                    </td>
                    <td className="px-4 py-3">
                      {a.outcome && a.outcome !== 'none' ? (
                        <Badge tone={OUTCOME_TONE[a.outcome] ?? 'neutral'}>{titleCase(a.outcome)}</Badge>
                      ) : (
                        <span className="text-xs text-neutral-400">—</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <ApplicationDrawer appId={drawerId} onClose={() => setDrawerId(null)} />
    </div>
  )
}
