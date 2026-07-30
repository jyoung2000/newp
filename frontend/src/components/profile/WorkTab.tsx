import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import type { WorkExperienceIn, WorkExperienceOut } from '../../lib/types'
import { Card } from '../Card'
import { Button } from '../Button'
import { Badge } from '../Badge'
import { Input, Select, Textarea } from '../Field'
import { Toggle } from '../Toggle'
import { Modal } from '../Modal'
import { Icon } from '../Icon'
import { EmptyState } from '../EmptyState'
import { useToast } from '../../lib/toast'
import { fmtDate } from '../../lib/format'

const EMPTY: WorkExperienceIn = {
  title: '',
  company: '',
  location: null,
  start_date: null,
  end_date: null,
  is_current: false,
  bullets: [],
  manager_name: null,
  manager_title: null,
  manager_email: null,
  manager_phone: null,
  may_contact_employer: null,
  reason_for_leaving: null,
  summary: null,
}

/** Section heading inside the editor, with the reason the fields exist. */
function Group({
  title,
  hint,
  children,
}: {
  title: string
  hint?: string
  children: React.ReactNode
}) {
  return (
    <section>
      <h5 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
        {title}
      </h5>
      {hint ? <p className="mt-0.5 text-xs text-neutral-400">{hint}</p> : null}
      <div className="mt-2.5">{children}</div>
    </section>
  )
}

/**
 * Yes / No / not answered. A Toggle can't express the third state, and this
 * question must not have a default — "may we contact this employer" answered
 * wrongly can cost someone a job.
 */
function YesNoUnset({
  label,
  hint,
  value,
  onChange,
}: {
  label: string
  hint?: string
  value: boolean | null | undefined
  onChange: (v: boolean | null) => void
}) {
  return (
    <Select
      label={label}
      hint={hint}
      value={value === true ? 'yes' : value === false ? 'no' : ''}
      onChange={(e) => onChange(e.target.value === 'yes' ? true : e.target.value === 'no' ? false : null)}
    >
      <option value="">Don’t answer — ask me</option>
      <option value="yes">Yes</option>
      <option value="no">No</option>
    </Select>
  )
}

function WorkModal({
  open,
  initial,
  editId,
  onClose,
}: {
  open: boolean
  initial: WorkExperienceIn
  editId: number | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [form, setForm] = useState<WorkExperienceIn>(initial)
  const [bullets, setBullets] = useState((initial.bullets ?? []).join('\n'))
  const set = <K extends keyof WorkExperienceIn>(key: K, value: WorkExperienceIn[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const save = useMutation({
    mutationFn: () => {
      const body: WorkExperienceIn = {
        ...form,
        bullets: bullets.split('\n').map((b) => b.trim()).filter(Boolean),
      }
      return editId
        ? api.put<WorkExperienceOut>(`/api/profile/work-experiences/${editId}`, body)
        : api.post<WorkExperienceOut>('/api/profile/work-experiences', body)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.profile })
      push({ title: editId ? 'Updated' : 'Added', tone: 'success' })
      onClose()
    },
    onError: (e) => push({ title: 'Could not save', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={editId ? 'Edit role' : 'Add a role'}
      description="Application forms ask for more than a résumé does. Everything you fill in here, JobPilot can answer for you instead of stopping to ask."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()} disabled={!form.title || !form.company}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <Group title="The role">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Job title" required value={form.title} onChange={(e) => set('title', e.target.value)} />
            <Input label="Company" required value={form.company} onChange={(e) => set('company', e.target.value)} />
            <Input label="Location" value={form.location ?? ''} onChange={(e) => set('location', e.target.value || null)} placeholder="City, State" />
            <div className="flex items-end pb-1">
              <Toggle
                checked={Boolean(form.is_current)}
                onChange={(v) => setForm((f) => ({ ...f, is_current: v, end_date: v ? null : f.end_date }))}
                label="I currently work here"
              />
            </div>
            <Input label="Start date" type="date" value={form.start_date ?? ''} onChange={(e) => set('start_date', e.target.value || null)} />
            <Input
              label="End date"
              type="date"
              value={form.end_date ?? ''}
              disabled={Boolean(form.is_current)}
              hint={form.is_current ? 'Forms get “Present” for a current role.' : undefined}
              onChange={(e) => set('end_date', e.target.value || null)}
            />
          </div>
        </Group>

        <Group
          title="Your manager"
          hint="Employment-history sections ask who you reported to and how to reach them."
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Manager name" value={form.manager_name ?? ''} onChange={(e) => set('manager_name', e.target.value || null)} />
            <Input label="Their title" value={form.manager_title ?? ''} onChange={(e) => set('manager_title', e.target.value || null)} placeholder="e.g. Director of Engineering" />
            <Input label="Their email" type="email" value={form.manager_email ?? ''} onChange={(e) => set('manager_email', e.target.value || null)} />
            <Input label="Their phone" value={form.manager_phone ?? ''} onChange={(e) => set('manager_phone', e.target.value || null)} />
            <div className="sm:col-span-2">
              <YesNoUnset
                label="May an employer contact them?"
                hint="Left unanswered, JobPilot asks you when a form wants it."
                value={form.may_contact_employer}
                onChange={(v) => set('may_contact_employer', v)}
              />
            </div>
          </div>
        </Group>

        <Group title="Leaving" hint={form.is_current ? 'Not asked for a role you still hold.' : undefined}>
          <Input
            label="Reason for leaving"
            value={form.reason_for_leaving ?? ''}
            disabled={Boolean(form.is_current)}
            onChange={(e) => set('reason_for_leaving', e.target.value || null)}
            placeholder="e.g. Took a role with more scope"
            hint="A short, factual phrase — it goes into the form as written."
          />
        </Group>

        <Group title="What you did" hint="The summary fills a description box; highlights fill a résumé.">
          <div className="grid gap-4">
            <Textarea
              label="Summary"
              rows={3}
              value={form.summary ?? ''}
              onChange={(e) => set('summary', e.target.value || null)}
              placeholder="A paragraph describing the role and your responsibilities."
            />
            <Textarea
              label="Highlights (one per line)"
              rows={4}
              value={bullets}
              onChange={(e) => setBullets(e.target.value)}
              placeholder={'Led a team of 5…\nShipped X that improved Y…'}
              hint="Used when a form has no summary box."
            />
          </div>
        </Group>
      </div>
    </Modal>
  )
}

/** Which form-facing fields are still empty, so the user can see the gap. */
function missingFields(w: WorkExperienceOut): string[] {
  const missing: string[] = []
  if (!w.manager_name) missing.push('manager')
  if (!w.reason_for_leaving && !w.is_current) missing.push('reason for leaving')
  if (!w.summary && (w.bullets ?? []).length === 0) missing.push('summary')
  if (!w.start_date) missing.push('start date')
  return missing
}

function toForm(w: WorkExperienceOut): WorkExperienceIn {
  return {
    title: w.title,
    company: w.company,
    location: w.location ?? null,
    start_date: w.start_date ?? null,
    end_date: w.end_date ?? null,
    is_current: w.is_current,
    bullets: w.bullets ?? [],
    manager_name: w.manager_name ?? null,
    manager_title: w.manager_title ?? null,
    manager_email: w.manager_email ?? null,
    manager_phone: w.manager_phone ?? null,
    may_contact_employer: w.may_contact_employer ?? null,
    reason_for_leaving: w.reason_for_leaving ?? null,
    summary: w.summary ?? null,
  }
}

export function WorkTab({ items }: { items: WorkExperienceOut[] }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [modal, setModal] = useState<{ open: boolean; initial: WorkExperienceIn; editId: number | null }>({
    open: false,
    initial: EMPTY,
    editId: null,
  })

  const sorted = [...items].sort((a, b) => a.order_index - b.order_index)

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/profile/work-experiences/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.profile }),
  })
  const reorder = useMutation({
    mutationFn: (ids: number[]) => api.post('/api/profile/work-experiences/reorder', { ids }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.profile }),
    onError: (e) => push({ title: 'Could not reorder', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const move = (index: number, dir: -1 | 1) => {
    const next = [...sorted]
    const target = index + dir
    if (target < 0 || target >= next.length) return
    ;[next[index], next[target]] = [next[target], next[index]]
    reorder.mutate(next.map((w) => w.id))
  }

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Order matters: the top entry is your most recent role, and it’s the one a form’s
          “Employer 1” gets.
        </p>
        <Button variant="primary" size="sm" icon="plus" onClick={() => setModal({ open: true, initial: EMPTY, editId: null })}>
          Add role
        </Button>
      </div>

      {sorted.length === 0 ? (
        <EmptyState
          icon="applications"
          title="No work history yet"
          description="Add your roles — with the manager, dates and reason for leaving that application forms ask for — and JobPilot can fill an employment-history section without stopping."
        />
      ) : (
        <ul className="space-y-3">
          {sorted.map((w, i) => {
            const missing = missingFields(w)
            return (
              <li key={w.id}>
                <Card padded={false} className="p-4">
                  <div className="flex gap-3">
                    <div className="flex flex-col items-center gap-1 pt-0.5">
                      <span className="text-[11px] font-semibold tabular-nums text-neutral-400" title="Employer number on a form">
                        {i + 1}
                      </span>
                      <button onClick={() => move(i, -1)} disabled={i === 0} className="rounded p-0.5 text-neutral-400 hover:text-neutral-700 disabled:opacity-30 dark:hover:text-neutral-200" aria-label="Move up">
                        <Icon name="chevronDown" className="h-4 w-4 rotate-180" />
                      </button>
                      <button onClick={() => move(i, 1)} disabled={i === sorted.length - 1} className="rounded p-0.5 text-neutral-400 hover:text-neutral-700 disabled:opacity-30 dark:hover:text-neutral-200" aria-label="Move down">
                        <Icon name="chevronDown" className="h-4 w-4" />
                      </button>
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex flex-wrap items-center gap-2">
                        <h4 className="font-semibold text-neutral-900 dark:text-neutral-100">{w.title}</h4>
                        {w.is_current ? <Badge tone="success">Current</Badge> : null}
                      </div>
                      <p className="text-sm text-neutral-600 dark:text-neutral-300">
                        {w.company}
                        {w.location ? ` · ${w.location}` : ''}
                      </p>
                      <p className="mt-0.5 text-xs text-neutral-400">
                        {fmtDate(w.start_date)} – {w.is_current ? 'Present' : fmtDate(w.end_date)}
                      </p>

                      <dl className="mt-2 grid gap-x-6 gap-y-1 text-xs sm:grid-cols-2">
                        {w.manager_name ? (
                          <div className="flex gap-1.5">
                            <dt className="text-neutral-400">Manager</dt>
                            <dd className="min-w-0 truncate text-neutral-600 dark:text-neutral-300">
                              {w.manager_name}
                              {w.manager_title ? `, ${w.manager_title}` : ''}
                              {w.may_contact_employer === false ? ' (do not contact)' : ''}
                            </dd>
                          </div>
                        ) : null}
                        {w.reason_for_leaving ? (
                          <div className="flex gap-1.5">
                            <dt className="text-neutral-400">Left because</dt>
                            <dd className="min-w-0 truncate text-neutral-600 dark:text-neutral-300">{w.reason_for_leaving}</dd>
                          </div>
                        ) : null}
                      </dl>

                      {w.summary ? (
                        <p className="mt-2 line-clamp-3 text-sm text-neutral-600 dark:text-neutral-300">{w.summary}</p>
                      ) : null}
                      {w.bullets && w.bullets.length > 0 ? (
                        <ul className="mt-2 list-disc space-y-0.5 pl-5 text-sm text-neutral-600 dark:text-neutral-300">
                          {w.bullets.map((b, bi) => (
                            <li key={bi}>{b}</li>
                          ))}
                        </ul>
                      ) : null}

                      {missing.length > 0 ? (
                        <button
                          onClick={() => setModal({ open: true, editId: w.id, initial: toForm(w) })}
                          className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-amber-50 px-2 py-1 text-xs text-amber-700 hover:bg-amber-100 dark:bg-amber-500/10 dark:text-amber-300"
                        >
                          <Icon name="alert" className="h-3.5 w-3.5" />
                          Forms will ask you for: {missing.join(', ')}
                        </button>
                      ) : null}
                    </div>
                    <div className="flex shrink-0 gap-1">
                      <button
                        onClick={() => setModal({ open: true, editId: w.id, initial: toForm(w) })}
                        className="rounded-lg p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800"
                        aria-label="Edit"
                      >
                        <Icon name="edit" className="h-4 w-4" />
                      </button>
                      <button
                        onClick={() => remove.mutate(w.id)}
                        className="rounded-lg p-2 text-neutral-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10"
                        aria-label="Delete"
                      >
                        <Icon name="trash" className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                </Card>
              </li>
            )
          })}
        </ul>
      )}

      <WorkModal
        key={`${modal.editId}-${modal.open}`}
        open={modal.open}
        initial={modal.initial}
        editId={modal.editId}
        onClose={() => setModal((m) => ({ ...m, open: false }))}
      />
    </div>
  )
}
