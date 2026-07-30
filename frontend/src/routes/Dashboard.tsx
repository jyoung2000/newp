import { useState } from 'react'
import { Link, Navigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { qk } from '../lib/queryKeys'
import { useUserSettings } from '../lib/hooks'
import type { Dashboard as DashboardData, RunOut } from '../lib/types'
import { PageHeader } from '../components/PageHeader'
import { StatCard } from '../components/StatCard'
import { Card, CardHeader } from '../components/Card'
import { Skeleton, SkeletonCards } from '../components/Skeleton'
import { AreaChart } from '../components/charts/AreaChart'
import { BarBreakdown } from '../components/charts/BarBreakdown'
import { Funnel } from '../components/charts/Funnel'
import { Button } from '../components/Button'
import { StatusBadge } from '../components/StatusBadge'
import { Icon } from '../components/Icon'
import { EmptyState } from '../components/EmptyState'
import { pickActiveRun, runDone, runInFlight } from '../lib/runs'

const RANGES = [
  { label: '7d', days: 7 },
  { label: '30d', days: 30 },
  { label: '90d', days: 90 },
]

function RangeSelect({ days, onChange }: { days: number; onChange: (d: number) => void }) {
  return (
    <div className="inline-flex rounded-xl border border-neutral-200 bg-white p-0.5 dark:border-neutral-800 dark:bg-neutral-900">
      {RANGES.map((r) => (
        <button
          key={r.days}
          onClick={() => onChange(r.days)}
          className={
            'rounded-lg px-3 py-1.5 text-sm font-medium transition-colors ' +
            (days === r.days
              ? 'bg-accent-600 text-white shadow-sm'
              : 'text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800')
          }
        >
          {r.label}
        </button>
      ))}
    </div>
  )
}

function RunStatusCard() {
  const { data } = useQuery({
    queryKey: qk.runs,
    queryFn: () => api.get<RunOut[]>('/api/runs'),
    refetchInterval: 8000,
  })
  const run = pickActiveRun(data)
  if (!run) {
    return (
      <Card>
        <CardHeader title="Current run" icon={<Icon name="queue" />} />
        <EmptyState
          compact
          icon="queue"
          title="No active run"
          description="Pick listings and start applying to see live progress here."
          action={
            <Link to="/listings">
              <Button variant="primary" size="sm" icon="sparkles">
                Browse listings
              </Button>
            </Link>
          }
        />
      </Card>
    )
  }
  const inFlight = runInFlight(run)
  const done = runDone(run)
  const pct = run.total > 0 ? Math.round((done / run.total) * 100) : 0
  return (
    <Card>
      <CardHeader
        title={`Run #${run.id}`}
        subtitle={`${run.mode} mode · ${run.executor ?? 'auto'} executor`}
        icon={<Icon name="queue" />}
        action={<StatusBadge status={run.status} />}
      />
      <div className="mb-3 h-2 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
        <div className="h-full rounded-full bg-accent-600 transition-[width] duration-500" style={{ width: `${pct}%` }} />
      </div>
      <div className="grid grid-cols-3 gap-2 text-center sm:grid-cols-6">
        {[
          ['Queued', run.queued],
          ['Filling', run.filling],
          ['Needs you', run.needs_human],
          ['Submitted', run.submitted],
          ['Drafted', run.drafted],
          ['Failed', run.failed],
        ].map(([label, val]) => (
          <div key={label} className="rounded-xl bg-neutral-50 py-2 dark:bg-neutral-800/50">
            <div className="text-lg font-semibold tabular-nums text-neutral-900 dark:text-neutral-100">{val}</div>
            <div className="text-[11px] text-neutral-500 dark:text-neutral-400">{label}</div>
          </div>
        ))}
      </div>
      <div className="mt-4 flex items-center justify-between">
        <span className="text-sm text-neutral-500">{inFlight} in flight · {done} done</span>
        <Link to="/queue">
          <Button variant="secondary" size="sm" iconRight="arrowRight">
            Open queue
          </Button>
        </Link>
      </div>
    </Card>
  )
}

export function Dashboard() {
  // A brand-new account lands in setup rather than an empty dashboard. Only
  // from here: a deep link the user asked for is never hijacked, and both
  // "finish" and "I'll do this later" set the flags that stop this firing.
  const onboardingState = useUserSettings()
  const settings = onboardingState.data
  if (settings && !settings.onboarding_completed && !settings.onboarding_dismissed) {
    return <Navigate to="/onboarding" replace />
  }

  const [days, setDays] = useState(30)
  const { data, isLoading } = useQuery({
    queryKey: qk.analytics(days),
    queryFn: () => api.get<DashboardData>(`/api/analytics?days=${days}`),
  })

  const cards = data?.cards

  return (
    <div>
      <PageHeader
        title="Dashboard"
        subtitle="Your job search at a glance"
        actions={<RangeSelect days={days} onChange={setDays} />}
      />

      {isLoading || !cards ? (
        <SkeletonCards count={6} className="grid-cols-2 md:grid-cols-3 lg:grid-cols-6" />
      ) : (
        <div className="grid grid-cols-2 gap-4 md:grid-cols-3 lg:grid-cols-6">
          <StatCard label="Found today" value={cards.found_today} icon="sparkles" tone="accent" to="/listings" />
          <StatCard label="Applied this week" value={cards.applied_this_week} icon="applications" tone="success" to="/applications" />
          <StatCard label="Responses" value={cards.responses} icon="mail" tone="accent" />
          <StatCard label="Interviews" value={cards.interviews} icon="star" tone="purple" />
          <StatCard label="Offers" value={cards.offers} icon="checkCircle" tone="success" />
          <StatCard label="Pending" value={cards.pending_interventions} icon="inbox" tone="warning" to="/interventions" hint="Interventions" />
        </div>
      )}

      <div className="mt-6 grid gap-6 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader title="Applications over time" subtitle={`Found vs applied · last ${days} days`} />
          {isLoading || !data ? (
            <Skeleton className="h-52 w-full rounded-xl" />
          ) : (
            <AreaChart data={data.over_time} />
          )}
        </Card>
        <RunStatusCard />
      </div>

      <div className="mt-6 grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader title="By source" subtitle="Listings found & applied per source" />
          {isLoading || !data ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <BarBreakdown
              rows={data.by_source.map((b) => ({
                label: b.key,
                value: b.total,
                max: Math.max(1, ...data.by_source.map((x) => x.total)),
                caption: `${b.applied}/${b.total} applied`,
              }))}
            />
          )}
        </Card>
        <Card>
          <CardHeader title="Response rate by source" subtitle="Replies per application" />
          {isLoading || !data ? (
            <Skeleton className="h-40 w-full" />
          ) : (
            <BarBreakdown
              rows={data.response_rate_by_source.map((b) => {
                const rate = b.applied > 0 ? Math.round((b.responses / b.applied) * 100) : 0
                return {
                  label: b.key,
                  value: rate,
                  max: 100,
                  caption: `${rate}% · ${b.responses}/${b.applied}`,
                  tone: '#10b981',
                }
              })}
              emptyLabel="No responses tracked yet"
            />
          )}
        </Card>
      </div>

      <Card className="mt-6">
        <CardHeader title="Pipeline funnel" subtitle="From found to offer" />
        {isLoading || !data ? <Skeleton className="h-48 w-full" /> : <Funnel stages={data.funnel} />}
      </Card>
    </div>
  )
}
