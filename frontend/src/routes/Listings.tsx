import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError, qs } from '../lib/api'
import { qk } from '../lib/queryKeys'
import { useSources } from '../lib/hooks'
import { useDebouncedValue } from '../lib/useDebounce'
import type { ListingOut, ManualAddRequest, RunMode } from '../lib/types'
import { PageHeader } from '../components/PageHeader'
import { Card } from '../components/Card'
import { Button } from '../components/Button'
import { Badge } from '../components/Badge'
import { Input, Select } from '../components/Field'
import { MatchMeter } from '../components/MatchMeter'
import { Icon } from '../components/Icon'
import { EmptyState } from '../components/EmptyState'
import { SkeletonRows } from '../components/Skeleton'
import { Modal } from '../components/Modal'
import { ListingDrawer } from '../components/ListingDrawer'
import { RunConfigModal } from '../components/RunConfigModal'
import { useToast } from '../lib/toast'
import { cx, fmtRelative, fmtSalary, titleCase } from '../lib/format'

const SORTS = [
  { value: 'score', label: 'Best match' },
  { value: 'posted', label: 'Newest posted' },
  { value: 'fetched', label: 'Recently found' },
  { value: 'salary', label: 'Highest salary' },
  { value: 'company', label: 'Company A–Z' },
]

function ManualAddModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [form, setForm] = useState<ManualAddRequest>({})

  const set = (k: keyof ManualAddRequest, v: string) => setForm((f) => ({ ...f, [k]: v || null }))

  const add = useMutation({
    mutationFn: () => api.post<ListingOut>('/api/listings/manual', form),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['listings'] })
      push({ title: 'Listing added', tone: 'success' })
      setForm({})
      onClose()
    },
    onError: (e) => push({ title: 'Could not add listing', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title="Add a listing manually"
      description="Paste a job URL, or fill in the details yourself."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" icon="plus" loading={add.isPending} onClick={() => add.mutate()}>
            Add listing
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <Input label="Job URL" value={form.url ?? ''} onChange={(e) => set('url', e.target.value)} placeholder="https://…" hint="If provided, JobPilot can fetch the details." />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Title" value={form.title ?? ''} onChange={(e) => set('title', e.target.value)} />
          <Input label="Company" value={form.company ?? ''} onChange={(e) => set('company', e.target.value)} />
          <Input label="Location" value={form.location ?? ''} onChange={(e) => set('location', e.target.value)} />
          <Input label="Salary" value={form.salary_raw ?? ''} onChange={(e) => set('salary_raw', e.target.value)} placeholder="e.g. $120k–$150k" />
        </div>
        <Input label="Apply URL" value={form.apply_url ?? ''} onChange={(e) => set('apply_url', e.target.value)} placeholder="Direct application link (optional)" />
        <div>
          <label className="label">Description</label>
          <textarea className="input min-h-[100px]" value={form.description ?? ''} onChange={(e) => set('description', e.target.value)} />
        </div>
      </div>
    </Modal>
  )
}

function ExportMenu() {
  return (
    <details className="group relative">
      <summary className="inline-flex h-10 cursor-pointer list-none items-center gap-2 rounded-xl border border-neutral-300 bg-white px-4 text-sm font-medium text-neutral-800 shadow-sm hover:bg-neutral-50 dark:border-neutral-700 dark:bg-neutral-900 dark:text-neutral-100 dark:hover:bg-neutral-800">
        <Icon name="download" className="h-4 w-4" />
        Export
        <Icon name="chevronDown" className="h-3.5 w-3.5" />
      </summary>
      <div className="absolute right-0 z-20 mt-1 w-44 overflow-hidden rounded-xl border border-neutral-200 bg-white py-1 shadow-lg dark:border-neutral-800 dark:bg-neutral-900">
        <a href="/api/transfer/listings.csv" className="flex items-center gap-2 px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-800">
          <Icon name="applications" className="h-4 w-4" /> Listings CSV
        </a>
        <a href="/api/transfer/listings.json" className="flex items-center gap-2 px-3 py-2 text-sm text-neutral-700 hover:bg-neutral-100 dark:text-neutral-200 dark:hover:bg-neutral-800">
          <Icon name="applications" className="h-4 w-4" /> Listings JSON
        </a>
      </div>
    </details>
  )
}

export function Listings() {
  const sources = useSources()
  const [q, setQ] = useState('')
  const [source, setSource] = useState('')
  const [minScore, setMinScore] = useState('')
  const [remote, setRemote] = useState('')
  const [sort, setSort] = useState('score')
  const [selected, setSelected] = useState<Set<number>>(new Set())
  const [drawerId, setDrawerId] = useState<number | null>(null)
  const [manualOpen, setManualOpen] = useState(false)
  const [runModal, setRunModal] = useState<{ open: boolean; mode: RunMode }>({ open: false, mode: 'review' })

  const debouncedQ = useDebouncedValue(q, 350)
  const params = {
    q: debouncedQ,
    source,
    min_score: minScore,
    remote,
    sort,
    limit: 200,
  }

  const { data, isLoading } = useQuery({
    queryKey: qk.listings(params),
    queryFn: () => api.get<ListingOut[]>(`/api/listings${qs(params)}`),
  })

  const rows = data ?? []
  const allSelected = rows.length > 0 && rows.every((r) => selected.has(r.id))
  const selectedIds = useMemo(() => Array.from(selected), [selected])

  const toggle = (id: number) =>
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  const toggleAll = () =>
    setSelected(() => (allSelected ? new Set() : new Set(rows.map((r) => r.id))))
  const clearSel = () => setSelected(new Set())

  return (
    <div>
      <PageHeader
        title="Listings"
        subtitle={`${rows.length} opening${rows.length === 1 ? '' : 's'} matched`}
        actions={
          <>
            <ExportMenu />
            <Button variant="secondary" icon="plus" onClick={() => setManualOpen(true)}>
              Add listing
            </Button>
          </>
        }
      />

      <Card padded={false} className="p-3">
        <div className="flex flex-col gap-2 sm:flex-row sm:flex-wrap sm:items-center">
          <div className="relative flex-1 sm:min-w-[220px]">
            <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
            <input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search title, company…"
              className="input pl-9"
              aria-label="Search listings"
            />
          </div>
          <Select value={source} onChange={(e) => setSource(e.target.value)} aria-label="Source" className="sm:w-40">
            <option value="">All sources</option>
            {(sources.data ?? []).map((s) => (
              <option key={s.name} value={s.name}>
                {s.label}
              </option>
            ))}
          </Select>
          <Select value={minScore} onChange={(e) => setMinScore(e.target.value)} aria-label="Minimum match" className="sm:w-36">
            <option value="">Any match</option>
            <option value="50">50+ match</option>
            <option value="75">75+ match</option>
            <option value="90">90+ match</option>
          </Select>
          <Select value={remote} onChange={(e) => setRemote(e.target.value)} aria-label="Remote" className="sm:w-32">
            <option value="">Any place</option>
            <option value="true">Remote</option>
            <option value="false">On-site</option>
          </Select>
          <Select value={sort} onChange={(e) => setSort(e.target.value)} aria-label="Sort" className="sm:w-40">
            {SORTS.map((s) => (
              <option key={s.value} value={s.value}>
                {s.label}
              </option>
            ))}
          </Select>
        </div>
      </Card>

      {selected.size > 0 ? (
        <div className="sticky top-16 z-20 mt-3 flex flex-wrap items-center gap-2 rounded-xl border border-accent-200 bg-accent-50/90 px-3 py-2 backdrop-blur dark:border-accent-500/30 dark:bg-accent-500/10">
          <span className="text-sm font-medium text-accent-800 dark:text-accent-200">{selected.size} selected</span>
          <button onClick={clearSel} className="text-sm text-accent-700 underline-offset-2 hover:underline dark:text-accent-300">
            Clear
          </button>
          <div className="ml-auto flex flex-wrap gap-2">
            <Button size="sm" variant="secondary" icon="queue" onClick={() => setRunModal({ open: true, mode: 'review' })}>
              Add to queue
            </Button>
            <Button size="sm" variant="primary" icon="sparkles" onClick={() => setRunModal({ open: true, mode: 'auto' })}>
              Auto apply
            </Button>
          </div>
        </div>
      ) : null}

      <Card padded={false} className="mt-3 overflow-hidden">
        {isLoading ? (
          <div className="p-4">
            <SkeletonRows rows={6} />
          </div>
        ) : rows.length === 0 ? (
          <div className="p-6">
            <EmptyState
              icon="search"
              title="No listings yet"
              description="Run a search to pull in real openings, or add one manually."
              action={
                <Button variant="primary" icon="search" onClick={() => (window.location.href = '/search')}>
                  Search jobs
                </Button>
              }
            />
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-sm">
              <thead>
                <tr className="border-b border-neutral-200 text-left text-xs uppercase tracking-wide text-neutral-500 dark:border-neutral-800">
                  <th className="w-10 px-3 py-2.5">
                    <input
                      type="checkbox"
                      checked={allSelected}
                      onChange={toggleAll}
                      className="h-4 w-4 rounded border-neutral-300 accent-accent-600 focus:ring-accent-500"
                      aria-label="Select all"
                    />
                  </th>
                  <th className="px-3 py-2.5 font-medium">Role</th>
                  <th className="px-3 py-2.5 font-medium">Salary</th>
                  <th className="hidden px-3 py-2.5 font-medium md:table-cell">Education</th>
                  <th className="hidden px-3 py-2.5 font-medium sm:table-cell">Posted</th>
                  <th className="px-3 py-2.5 font-medium">Match</th>
                  <th className="hidden px-3 py-2.5 font-medium lg:table-cell">Source</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.id}
                    className={cx(
                      'cursor-pointer border-b border-neutral-100 transition-colors hover:bg-neutral-50 dark:border-neutral-800/60 dark:hover:bg-neutral-800/40',
                      selected.has(r.id) && 'bg-accent-50/50 dark:bg-accent-500/5',
                    )}
                    onClick={() => setDrawerId(r.id)}
                  >
                    <td className="px-3 py-3" onClick={(e) => e.stopPropagation()}>
                      <input
                        type="checkbox"
                        checked={selected.has(r.id)}
                        onChange={() => toggle(r.id)}
                        className="h-4 w-4 rounded border-neutral-300 accent-accent-600 focus:ring-accent-500"
                        aria-label={`Select ${r.title}`}
                      />
                    </td>
                    <td className="px-3 py-3">
                      <div className="flex items-center gap-2 font-medium text-neutral-900 dark:text-neutral-100">
                        <span className="line-clamp-1">{r.title}</span>
                        {r.applied ? <Badge tone="success">Applied</Badge> : null}
                      </div>
                      <div className="mt-0.5 flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
                        <Icon name="building" className="h-3.5 w-3.5" />
                        <span className="line-clamp-1">{r.company}</span>
                        {r.remote ? <Badge tone="accent">Remote</Badge> : null}
                      </div>
                    </td>
                    <td className="whitespace-nowrap px-3 py-3 text-neutral-600 dark:text-neutral-300">
                      {fmtSalary(r.salary_min, r.salary_max, r.salary_currency, r.salary_period, r.salary_raw)}
                    </td>
                    <td className="hidden px-3 py-3 text-neutral-500 md:table-cell dark:text-neutral-400">
                      {r.education_level ? titleCase(r.education_level) : '—'}
                    </td>
                    <td className="hidden whitespace-nowrap px-3 py-3 text-neutral-500 sm:table-cell dark:text-neutral-400">
                      {fmtRelative(r.posted_at)}
                    </td>
                    <td className="px-3 py-3">
                      <MatchMeter score={r.match_score} width="w-16" />
                    </td>
                    <td className="hidden px-3 py-3 lg:table-cell">
                      <Badge tone="neutral">{titleCase(r.source)}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <ListingDrawer listingId={drawerId} onClose={() => setDrawerId(null)} />
      <ManualAddModal open={manualOpen} onClose={() => setManualOpen(false)} />
      <RunConfigModal
        open={runModal.open}
        onClose={() => setRunModal((s) => ({ ...s, open: false }))}
        listingIds={selectedIds}
        initialMode={runModal.mode}
        title={runModal.mode === 'auto' ? 'Auto apply to selected' : 'Add selected to queue'}
      />
    </div>
  )
}
