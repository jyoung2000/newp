import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../lib/api'
import { qk } from '../lib/queryKeys'
import { useSources } from '../lib/hooks'
import type {
  SearchRequest,
  SearchRunStatus,
  SearchStarted,
  SearchTargetOut,
  SourceInfo,
} from '../lib/types'
import { PageHeader } from '../components/PageHeader'
import { Card, CardHeader } from '../components/Card'
import { Input, Select } from '../components/Field'
import { ChipInput } from '../components/ChipInput'
import { Toggle } from '../components/Toggle'
import { Button } from '../components/Button'
import { Badge } from '../components/Badge'
import { SourceStatusBadge } from '../components/StatusBadge'
import { Icon } from '../components/Icon'
import { EmptyState } from '../components/EmptyState'
import { Skeleton } from '../components/Skeleton'
import { useToast } from '../lib/toast'
import { cx, fmtRelative, titleCase } from '../lib/format'

const EDUCATION_OPTIONS = [
  { value: '', label: 'Any education' },
  { value: 'high_school', label: 'High school' },
  { value: 'associate', label: 'Associate' },
  { value: 'bachelor', label: "Bachelor's" },
  { value: 'master', label: "Master's" },
  { value: 'doctorate', label: 'Doctorate' },
]
const POSTED_OPTIONS = [
  { value: '', label: 'Any time' },
  { value: '1', label: 'Past 24 hours' },
  { value: '3', label: 'Past 3 days' },
  { value: '7', label: 'Past week' },
  { value: '14', label: 'Past 2 weeks' },
  { value: '30', label: 'Past month' },
]

function sourceSelectable(s: SourceInfo): boolean {
  if (s.forbidden) return false
  if (s.status === 'forbidden' || s.status === 'disabled') return false
  if (s.requires_key && !s.configured) return false
  return true
}

function ProgressPanel({ runId, onClear }: { runId: string; onClear: () => void }) {
  const { data } = useQuery({
    queryKey: qk.searchRun(runId),
    queryFn: () => api.get<SearchRunStatus>(`/api/search/runs/${runId}`),
    refetchInterval: (q) => {
      const s = q.state.data?.status
      return s === 'done' || s === 'error' || s === 'completed' ? false : 1500
    },
  })
  const status = data?.status ?? 'running'
  const done = status === 'done' || status === 'completed' || status === 'error'
  const pct = data && data.total_sources > 0 ? Math.round((data.completed_sources / data.total_sources) * 100) : 0
  const perSource = (data?.per_source ?? {}) as Record<string, unknown>

  return (
    <Card className="mt-4 border-accent-200 dark:border-accent-500/30">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {done ? (
            <Icon name={status === 'error' ? 'alert' : 'checkCircle'} className={cx('h-5 w-5', status === 'error' ? 'text-red-500' : 'text-emerald-500')} />
          ) : (
            <span className="relative flex h-2.5 w-2.5">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-accent-500 opacity-75" />
              <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-accent-600" />
            </span>
          )}
          <span className="font-semibold text-neutral-900 dark:text-neutral-100">
            {status === 'error' ? 'Search failed' : done ? 'Search complete' : 'Searching…'}
          </span>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-sm tabular-nums text-neutral-500">
            {data?.completed_sources ?? 0}/{data?.total_sources ?? 0} sources
          </span>
          {done ? (
            <Button size="sm" variant="ghost" icon="close" onClick={onClear}>
              Dismiss
            </Button>
          ) : null}
        </div>
      </div>

      <div className="my-3 h-2 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
        <div className="h-full rounded-full bg-accent-600 transition-[width] duration-500" style={{ width: `${done ? 100 : pct}%` }} />
      </div>

      <div className="flex gap-6 text-sm">
        <div>
          <span className="text-2xl font-semibold tabular-nums text-neutral-900 dark:text-neutral-100">{data?.found ?? 0}</span>
          <span className="ml-1.5 text-neutral-500">found</span>
        </div>
        <div>
          <span className="text-2xl font-semibold tabular-nums text-emerald-600 dark:text-emerald-400">{data?.new ?? 0}</span>
          <span className="ml-1.5 text-neutral-500">new</span>
        </div>
      </div>

      {data?.error ? <p className="mt-2 text-sm text-red-600 dark:text-red-400">{data.error}</p> : null}

      {Object.keys(perSource).length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {Object.entries(perSource).map(([name, val]) => (
            <Badge key={name} tone="neutral">
              {titleCase(name)}: {typeof val === 'number' ? val : typeof val === 'object' && val ? JSON.stringify(val) : String(val)}
            </Badge>
          ))}
        </div>
      ) : null}

      {done && status !== 'error' ? (
        <div className="mt-4">
          <Button variant="primary" size="sm" iconRight="arrowRight" onClick={() => (window.location.href = '/listings')}>
            View {data?.new ?? 0} new listings
          </Button>
        </div>
      ) : null}
    </Card>
  )
}

function SavedSearches() {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const { data, isLoading } = useQuery({
    queryKey: qk.searchTargets,
    queryFn: () => api.get<SearchTargetOut[]>('/api/search/targets'),
  })

  const runNow = useMutation({
    mutationFn: (id: number) => api.post<SearchStarted>(`/api/search/targets/${id}/run`),
    onSuccess: () => push({ title: 'Search started', tone: 'success', message: 'Running in the background.' }),
    onError: (e) => push({ title: 'Could not start', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/search/targets/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.searchTargets }),
  })

  return (
    <Card>
      <CardHeader title="Saved searches" subtitle="Reusable searches, optionally on a schedule" icon={<Icon name="clock" />} />
      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-14 w-full rounded-xl" />
          <Skeleton className="h-14 w-full rounded-xl" />
        </div>
      ) : !data || data.length === 0 ? (
        <EmptyState compact icon="clock" title="No saved searches" description='Tick "Save this search" when you run one to reuse it later.' />
      ) : (
        <ul className="space-y-2">
          {data.map((t) => (
            <li key={t.id} className="flex items-center gap-3 rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <p className="truncate font-medium text-neutral-900 dark:text-neutral-100">{t.name}</p>
                  {t.schedule_minutes ? (
                    <Badge tone="accent" dot>
                      Every {t.schedule_minutes >= 60 ? `${Math.round(t.schedule_minutes / 60)}h` : `${t.schedule_minutes}m`}
                    </Badge>
                  ) : (
                    <Badge tone="neutral">Manual</Badge>
                  )}
                  {t.notify_new ? <Badge tone="purple">Notify</Badge> : null}
                </div>
                <p className="mt-0.5 truncate text-xs text-neutral-500 dark:text-neutral-400">
                  {t.title_terms.join(', ') || '—'}
                  {t.location ? ` · ${t.location}` : ''} · last run {fmtRelative(t.last_run_at)}
                </p>
              </div>
              <Button size="sm" variant="secondary" icon="play" onClick={() => runNow.mutate(t.id)} loading={runNow.isPending && runNow.variables === t.id}>
                Run
              </Button>
              <button
                onClick={() => remove.mutate(t.id)}
                className="rounded-lg p-2 text-neutral-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10"
                aria-label={`Delete ${t.name}`}
              >
                <Icon name="trash" className="h-4 w-4" />
              </button>
            </li>
          ))}
        </ul>
      )}
    </Card>
  )
}

export function Search() {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const sources = useSources()

  const [terms, setTerms] = useState<string[]>([])
  const [location, setLocation] = useState('')
  const [remote, setRemote] = useState(false)
  const [salaryFloor, setSalaryFloor] = useState('')
  const [education, setEducation] = useState('')
  const [postedWithin, setPostedWithin] = useState('')
  const [selectedSources, setSelectedSources] = useState<string[]>([])
  const [saveAs, setSaveAs] = useState('')
  const [runId, setRunId] = useState<string | null>(null)

  const toggleSource = (name: string) =>
    setSelectedSources((prev) => (prev.includes(name) ? prev.filter((s) => s !== name) : [...prev, name]))

  const run = useMutation({
    mutationFn: () => {
      const body: SearchRequest = {
        terms,
        location: location || null,
        remote: remote ? true : null,
        salary_floor: salaryFloor ? Number(salaryFloor) : null,
        education_level: education || null,
        posted_within_days: postedWithin ? Number(postedWithin) : null,
        sources: selectedSources,
        save_as: saveAs || null,
      }
      return api.post<SearchStarted>('/api/search/run', body)
    },
    onSuccess: (res) => {
      setRunId(res.run_id)
      if (saveAs) {
        queryClient.invalidateQueries({ queryKey: qk.searchTargets })
        setSaveAs('')
      }
      push({ title: 'Search started', tone: 'success' })
    },
    onError: (e) => push({ title: 'Search failed to start', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const canRun = terms.length > 0 && selectedSources.length > 0 && !run.isPending

  return (
    <div>
      <PageHeader title="Search jobs" subtitle="Find real openings across the sources you’re allowed to use" />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <Card>
            <div className="space-y-4">
              <ChipInput
                label="Job titles / keywords"
                value={terms}
                onChange={setTerms}
                placeholder="e.g. Product Manager, Frontend Engineer"
                hint="Press Enter or comma to add each term."
              />
              <div className="grid gap-4 sm:grid-cols-2">
                <Input label="Location" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="City, state or country" />
                <Input
                  label="Minimum salary"
                  type="number"
                  inputMode="numeric"
                  value={salaryFloor}
                  onChange={(e) => setSalaryFloor(e.target.value)}
                  placeholder="e.g. 120000"
                />
                <Select label="Education level" value={education} onChange={(e) => setEducation(e.target.value)}>
                  {EDUCATION_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
                <Select label="Posted within" value={postedWithin} onChange={(e) => setPostedWithin(e.target.value)}>
                  {POSTED_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
                <Toggle checked={remote} onChange={setRemote} label="Remote only" description="Restrict to roles marked remote." />
              </div>
            </div>
          </Card>

          <Card className="mt-4">
            <CardHeader
              title="Sources"
              subtitle="Each source lists its permission basis and current status"
              icon={<Icon name="shield" />}
              action={
                sources.data && sources.data.length > 0 ? (
                  <button
                    className="text-sm font-medium text-accent-600 hover:underline dark:text-accent-400"
                    onClick={() =>
                      setSelectedSources(sources.data!.filter(sourceSelectable).map((s) => s.name))
                    }
                  >
                    Select all available
                  </button>
                ) : null
              }
            />
            {sources.isLoading ? (
              <div className="space-y-2">
                {[0, 1, 2].map((i) => (
                  <Skeleton key={i} className="h-16 w-full rounded-xl" />
                ))}
              </div>
            ) : (
              <div className="grid gap-2 sm:grid-cols-2">
                {(sources.data ?? []).map((s) => {
                  const selectable = sourceSelectable(s)
                  const checked = selectedSources.includes(s.name)
                  return (
                    <button
                      key={s.name}
                      type="button"
                      disabled={!selectable}
                      onClick={() => toggleSource(s.name)}
                      className={cx(
                        'flex items-start gap-3 rounded-xl border p-3 text-left transition-colors',
                        checked
                          ? 'border-accent-400 bg-accent-50 dark:border-accent-500/40 dark:bg-accent-500/10'
                          : 'border-neutral-200 hover:border-neutral-300 dark:border-neutral-800 dark:hover:border-neutral-700',
                        !selectable && 'cursor-not-allowed opacity-60',
                      )}
                    >
                      <span
                        className={cx(
                          'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md border',
                          checked ? 'border-accent-600 bg-accent-600 text-white' : 'border-neutral-300 dark:border-neutral-600',
                        )}
                      >
                        {checked ? <Icon name="check" className="h-3.5 w-3.5" strokeWidth={3} /> : null}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex items-center justify-between gap-2">
                          <span className="truncate font-medium text-neutral-900 dark:text-neutral-100">{s.label}</span>
                          <SourceStatusBadge status={s.status} />
                        </span>
                        <span className="mt-0.5 block text-xs text-neutral-500 dark:text-neutral-400">
                          {titleCase(s.permission_basis)}
                          {s.detail ? ` · ${s.detail}` : ''}
                        </span>
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </Card>

          <Card className="mt-4">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
              <Input
                label="Save this search as (optional)"
                value={saveAs}
                onChange={(e) => setSaveAs(e.target.value)}
                placeholder="e.g. Remote PM roles"
                className="sm:flex-1"
              />
              <Button variant="primary" icon="search" onClick={() => run.mutate()} disabled={!canRun} loading={run.isPending}>
                Run search
              </Button>
            </div>
            {terms.length === 0 || selectedSources.length === 0 ? (
              <p className="mt-2 text-xs text-neutral-400">Add at least one keyword and select a source to run.</p>
            ) : null}
          </Card>

          {runId ? <ProgressPanel runId={runId} onClear={() => setRunId(null)} /> : null}
        </div>

        <div>
          <SavedSearches />
        </div>
      </div>
    </div>
  )
}
