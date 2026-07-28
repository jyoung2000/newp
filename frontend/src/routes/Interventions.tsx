import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../lib/api'
import { qk } from '../lib/queryKeys'
import type { AnswerRequest, InterventionFieldMeta, InterventionOut } from '../lib/types'
import { PageHeader } from '../components/PageHeader'
import { Card } from '../components/Card'
import { Button } from '../components/Button'
import { Badge } from '../components/Badge'
import { StatusBadge } from '../components/StatusBadge'
import { Toggle } from '../components/Toggle'
import { Icon } from '../components/Icon'
import { EmptyState } from '../components/EmptyState'
import { AuthImage } from '../components/AuthImage'
import { SkeletonRows } from '../components/Skeleton'
import { SpringCheck } from '../components/SpringCheck'
import { useToast } from '../lib/toast'
import { cx, fmtRelative, humanKind } from '../lib/format'

function slugify(s: string): string {
  return s
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '_')
    .replace(/^_+|_+$/g, '')
    .slice(0, 60)
}

function useAnswerMutation(iv: InterventionOut) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  return useMutation({
    mutationFn: (body: AnswerRequest) => api.post<InterventionOut>(`/api/interventions/${iv.id}/answer`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['interventions'] })
      queryClient.invalidateQueries({ queryKey: qk.application(iv.application_id) })
    },
    onError: (e) => push({ title: 'Could not save', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })
}

// --- Challenge: never an answer box. The human solves it themselves. --------
function ChallengePanel({ iv }: { iv: InterventionOut }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const meta = (iv.field_meta ?? {}) as InterventionFieldMeta
  const done = useMutation({
    mutationFn: () => api.post<InterventionOut>(`/api/interventions/${iv.id}/challenge-done`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['interventions'] })
      queryClient.invalidateQueries({ queryKey: qk.application(iv.application_id) })
      push({ title: 'Resuming', tone: 'success', message: 'JobPilot will re-check the challenge before continuing.' })
    },
    onError: (e) => push({ title: 'Could not resume', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <div className="space-y-4">
      <div className="rounded-2xl border border-amber-200 bg-amber-50 p-4 dark:border-amber-500/30 dark:bg-amber-500/10">
        <div className="flex items-start gap-3">
          <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-amber-100 text-amber-600 dark:bg-amber-500/20 dark:text-amber-300">
            <Icon name="shield" className="h-5 w-5" />
          </div>
          <div>
            <h4 className="font-semibold text-amber-900 dark:text-amber-200">This challenge is yours to solve</h4>
            <p className="mt-1 text-sm leading-relaxed text-amber-800/90 dark:text-amber-200/80">
              JobPilot never solves CAPTCHAs or human-verification challenges for you — that’s the rule. Solve it yourself in
              the live page, then press resume. Nothing is submitted until you do.
            </p>
          </div>
        </div>
      </div>

      {meta.novnc ? (
        <div>
          <p className="mb-2 flex items-center gap-1.5 text-sm font-medium text-neutral-700 dark:text-neutral-300">
            <Icon name="monitor" className="h-4 w-4" />
            Live browser
          </p>
          <div className="overflow-hidden rounded-xl border border-neutral-200 dark:border-neutral-800">
            <iframe
              title="Live browser (noVNC)"
              src={meta.novnc}
              className="h-[420px] w-full bg-neutral-900"
              allow="clipboard-read; clipboard-write"
            />
          </div>
          <p className="mt-1.5 text-xs text-neutral-400">Interact with the page above to complete the challenge.</p>
        </div>
      ) : (
        <div className="flex items-start gap-2 rounded-xl border border-neutral-200 p-3 text-sm text-neutral-600 dark:border-neutral-800 dark:text-neutral-300">
          <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0 text-accent-500" />
          <span>Switch to the browser tab running this application, solve the challenge there, then come back and press resume.</span>
        </div>
      )}

      <Button variant="primary" icon="checkCircle" onClick={() => done.mutate()} loading={done.isPending} block>
        I solved it — Resume
      </Button>
    </div>
  )
}

// --- Review: approve a filled application for submission. --------------------
function ReviewPanel({ iv }: { iv: InterventionOut }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['interventions'] })
    queryClient.invalidateQueries({ queryKey: qk.application(iv.application_id) })
  }
  const approve = useMutation({
    mutationFn: () => api.post(`/api/interventions/${iv.id}/approve-review`),
    onSuccess: () => {
      invalidate()
      push({ title: 'Approved for submission', tone: 'success' })
    },
    onError: (e) => push({ title: 'Could not approve', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })
  const cancel = useMutation({
    mutationFn: () => api.post(`/api/interventions/${iv.id}/cancel`),
    onSuccess: invalidate,
    onError: (e) => push({ title: 'Could not cancel', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })
  return (
    <div className="space-y-3">
      <div className="flex items-start gap-2 rounded-xl bg-accent-50 p-3 text-sm text-accent-800 dark:bg-accent-500/10 dark:text-accent-300">
        <Icon name="eye" className="mt-0.5 h-4 w-4 shrink-0" />
        <span>The application is filled and waiting for your OK. Review the screenshot, then approve to submit.</span>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" icon="check" onClick={() => approve.mutate()} loading={approve.isPending}>
          Approve & submit
        </Button>
        <Link to={`/applications?focus=${iv.application_id}`}>
          <Button variant="secondary" icon="applications">
            View filled fields
          </Button>
        </Link>
        <Button variant="ghost" icon="close" onClick={() => cancel.mutate()} loading={cancel.isPending}>
          Cancel
        </Button>
      </div>
    </div>
  )
}

// --- Field answer form (unknown_field / draft_approval / error). ------------
function AnswerForm({ iv }: { iv: InterventionOut }) {
  const meta = (iv.field_meta ?? {}) as InterventionFieldMeta
  const options = Array.isArray(meta.options) ? meta.options : []
  const fieldType = (meta.field_type ?? (options.length > 0 ? 'select' : 'text')).toLowerCase()
  const isDraft = iv.kind === 'draft_approval'

  const [value, setValue] = useState<string>(isDraft && meta.draft != null ? String(meta.draft) : '')
  const [saveKb, setSaveKb] = useState(true)
  const [keyEdit, setKeyEdit] = useState(false)
  const [questionKey, setQuestionKey] = useState(slugify(meta.label || iv.question || ''))
  const mut = useAnswerMutation(iv)

  const submit = (skip: boolean) => {
    const body: AnswerRequest = skip
      ? { skip: true, save_to_kb: false }
      : {
          answer: fieldType === 'boolean' ? value === 'yes' : value,
          save_to_kb: saveKb,
          question_key: questionKey || null,
          skip: false,
        }
    mut.mutate(body)
  }

  const renderInput = () => {
    if (fieldType === 'boolean') {
      return (
        <div className="flex gap-2">
          {['yes', 'no'].map((v) => (
            <button
              key={v}
              type="button"
              onClick={() => setValue(v)}
              className={cx(
                'flex-1 rounded-xl border px-4 py-2.5 text-sm font-medium capitalize transition-colors',
                value === v
                  ? 'border-accent-400 bg-accent-50 text-accent-700 dark:border-accent-500/40 dark:bg-accent-500/10 dark:text-accent-300'
                  : 'border-neutral-200 hover:border-neutral-300 dark:border-neutral-800',
              )}
            >
              {v}
            </button>
          ))}
        </div>
      )
    }
    if (options.length > 0) {
      return (
        <div className="space-y-1.5">
          {options.map((opt) => (
            <button
              key={opt}
              type="button"
              onClick={() => setValue(opt)}
              className={cx(
                'flex w-full items-center gap-2.5 rounded-xl border px-3 py-2.5 text-left text-sm transition-colors',
                value === opt
                  ? 'border-accent-400 bg-accent-50 dark:border-accent-500/40 dark:bg-accent-500/10'
                  : 'border-neutral-200 hover:border-neutral-300 dark:border-neutral-800',
              )}
            >
              <span
                className={cx(
                  'flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2',
                  value === opt ? 'border-accent-600' : 'border-neutral-300 dark:border-neutral-600',
                )}
              >
                {value === opt ? <span className="h-2 w-2 rounded-full bg-accent-600" /> : null}
              </span>
              <span className="text-neutral-800 dark:text-neutral-200">{opt}</span>
            </button>
          ))}
        </div>
      )
    }
    if (fieldType === 'textarea') {
      return <textarea className="input min-h-[90px]" value={value} onChange={(e) => setValue(e.target.value)} placeholder="Your answer…" />
    }
    return (
      <input
        className="input"
        type={fieldType === 'number' ? 'number' : fieldType === 'date' ? 'date' : 'text'}
        value={value}
        onChange={(e) => setValue(e.target.value)}
        placeholder="Your answer…"
      />
    )
  }

  return (
    <div className="space-y-3">
      {isDraft ? (
        <div className="flex items-start gap-2 rounded-xl bg-violet-50 p-3 text-sm text-violet-800 dark:bg-violet-500/10 dark:text-violet-300">
          <Icon name="sparkles" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>JobPilot drafted an answer. Confirm or edit it before it’s used.</span>
        </div>
      ) : null}

      {meta.is_knockout ? (
        <div className="flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
          <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>This looks like a knockout question — JobPilot never guesses these. Please answer it yourself.</span>
        </div>
      ) : null}
      {meta.is_eeo ? (
        <div className="flex items-start gap-2 rounded-xl bg-neutral-50 p-3 text-xs text-neutral-600 dark:bg-neutral-800/60 dark:text-neutral-300">
          <Icon name="shield" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>EEO question — the default is “decline to self-identify”. Only answer if you want to.</span>
        </div>
      ) : null}

      {renderInput()}

      <div className="rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
        <Toggle
          checked={saveKb}
          onChange={setSaveKb}
          label="Save for future applications"
          description="Reuse this answer automatically when the same question comes up."
        />
        {saveKb ? (
          <div className="mt-3 border-t border-neutral-100 pt-3 dark:border-neutral-800">
            {keyEdit ? (
              <input
                className="input text-sm"
                value={questionKey}
                onChange={(e) => setQuestionKey(slugify(e.target.value))}
                placeholder="normalized_question_key"
              />
            ) : (
              <button
                onClick={() => setKeyEdit(true)}
                className="flex items-center gap-1.5 text-xs text-neutral-500 hover:text-neutral-700 dark:hover:text-neutral-300"
              >
                <Icon name="edit" className="h-3.5 w-3.5" />
                Key: <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono dark:bg-neutral-800">{questionKey || '—'}</code>
              </button>
            )}
          </div>
        ) : null}
      </div>

      <div className="flex gap-2">
        <Button
          variant="primary"
          icon={isDraft ? 'check' : undefined}
          onClick={() => submit(false)}
          loading={mut.isPending && !mut.variables?.skip}
          disabled={value === '' && !options.length}
        >
          {isDraft ? 'Confirm answer' : 'Submit answer'}
        </Button>
        <Button variant="ghost" icon="skip" onClick={() => submit(true)} loading={mut.isPending && Boolean(mut.variables?.skip)}>
          Skip this field
        </Button>
      </div>
    </div>
  )
}

function InterventionCard({ iv, focused }: { iv: InterventionOut; focused: boolean }) {
  const meta = (iv.field_meta ?? {}) as InterventionFieldMeta
  const isChallenge = iv.kind === 'challenge'
  const isReview = iv.kind === 'review'
  const resolved = iv.status !== 'open'
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (focused) ref.current?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, [focused])

  return (
    <div
      ref={ref}
      className={cx(
        'card overflow-hidden p-0',
        focused && 'ring-2 ring-accent-500 ring-offset-2 ring-offset-white dark:ring-offset-neutral-950',
      )}
    >
      <div className="flex flex-wrap items-center gap-2 border-b border-neutral-100 px-4 py-3 dark:border-neutral-800">
        <Badge tone={isChallenge ? 'warning' : isReview ? 'accent' : iv.kind === 'draft_approval' ? 'purple' : 'neutral'} dot>
          {humanKind(iv.kind)}
        </Badge>
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-neutral-900 dark:text-neutral-100">
            {iv.listing_title ?? `Application #${iv.application_id}`}
          </p>
          {iv.listing_company ? (
            <p className="truncate text-xs text-neutral-500 dark:text-neutral-400">{iv.listing_company}</p>
          ) : null}
        </div>
        <div className="ml-auto flex items-center gap-2">
          {iv.application_status ? <StatusBadge status={iv.application_status} dot={false} /> : null}
          <span className="hidden text-xs text-neutral-400 sm:inline">{fmtRelative(iv.created_at)}</span>
        </div>
      </div>

      <div className="grid gap-5 p-4 md:grid-cols-2">
        <div>
          {iv.question ? (
            <p className="mb-3 text-[15px] font-medium leading-snug text-neutral-900 dark:text-neutral-100">
              {iv.question}
            </p>
          ) : null}
          {meta.detail && isChallenge ? (
            <p className="mb-3 text-sm text-neutral-500">{meta.detail}</p>
          ) : null}

          {resolved ? (
            <div className="flex items-center gap-2 rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300">
              <SpringCheck size="h-6 w-6" />
              <span>
                Resolved{iv.resolved_by ? ` by ${iv.resolved_by}` : ''} · {fmtRelative(iv.resolved_at)}
                {iv.answer != null && typeof iv.answer !== 'object' ? ` — “${String(iv.answer)}”` : ''}
              </span>
            </div>
          ) : isChallenge ? (
            <ChallengePanel iv={iv} />
          ) : isReview ? (
            <ReviewPanel iv={iv} />
          ) : (
            <AnswerForm iv={iv} />
          )}
        </div>

        <div className="order-first md:order-last">
          <AuthImage src={iv.screenshot_url} alt="Application screenshot" cropHeight="max-h-64" />
        </div>
      </div>
    </div>
  )
}

export function Interventions() {
  const [params] = useSearchParams()
  const focusId = params.get('focus')
  const [filter, setFilter] = useState<'open' | 'all'>('open')

  const { data, isLoading } = useQuery({
    queryKey: qk.interventions(filter),
    queryFn: () => api.get<InterventionOut[]>(`/api/interventions?status=${filter}`),
    refetchInterval: 15000,
  })

  const items = useMemo(() => {
    const list = data ?? []
    if (!focusId) return list
    const id = Number(focusId)
    return [...list].sort((a, b) => (a.id === id ? -1 : b.id === id ? 1 : 0))
  }, [data, focusId])

  const openCount = (data ?? []).filter((i) => i.status === 'open').length

  return (
    <div>
      <PageHeader
        title="Interventions"
        subtitle="Questions and checks that need a human — you"
        actions={
          <div className="inline-flex rounded-xl border border-neutral-200 bg-white p-0.5 dark:border-neutral-800 dark:bg-neutral-900">
            {(['open', 'all'] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cx(
                  'rounded-lg px-3 py-1.5 text-sm font-medium capitalize transition-colors',
                  filter === f
                    ? 'bg-accent-600 text-white shadow-sm'
                    : 'text-neutral-600 hover:bg-neutral-100 dark:text-neutral-400 dark:hover:bg-neutral-800',
                )}
              >
                {f}
                {f === 'open' && openCount > 0 ? ` (${openCount})` : ''}
              </button>
            ))}
          </div>
        }
      />

      <div className="mb-4 flex items-start gap-2 rounded-xl border border-neutral-200 bg-white/60 p-3 text-sm text-neutral-600 dark:border-neutral-800 dark:bg-neutral-900/60 dark:text-neutral-300">
        <Icon name="shield" className="mt-0.5 h-4 w-4 shrink-0 text-accent-500" />
        <span>
          You decide every CAPTCHA and every knockout question. This inbox works on your phone too — solve challenges wherever
          you are.
        </span>
      </div>

      {isLoading ? (
        <Card>
          <SkeletonRows rows={3} />
        </Card>
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon="checkCircle"
            title={filter === 'open' ? 'Nothing needs you right now' : 'No interventions yet'}
            description={
              filter === 'open'
                ? 'When an application hits a question or a challenge, it will show up here.'
                : 'Answered and resolved interventions will appear here.'
            }
            action={
              <Link to="/listings">
                <Button variant="secondary" icon="listings">
                  Go to listings
                </Button>
              </Link>
            }
          />
        </Card>
      ) : (
        <div className="mx-auto max-w-3xl space-y-3">
          {items.map((iv) => (
            <InterventionCard key={iv.id} iv={iv} focused={focusId != null && Number(focusId) === iv.id} />
          ))}
        </div>
      )}
    </div>
  )
}
