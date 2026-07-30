import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import type { RecommendationIn, RecommendationOut } from '../../lib/types'
import { Card } from '../Card'
import { Button } from '../Button'
import { Badge } from '../Badge'
import { Input, Select, Textarea } from '../Field'
import { Modal } from '../Modal'
import { Icon } from '../Icon'
import { EmptyState } from '../EmptyState'
import { useToast } from '../../lib/toast'

// Most application forms that ask for references ask for three.
const TYPICAL_REFERENCE_COUNT = 3

const EMPTY: RecommendationIn = {
  name: '',
  title: null,
  relationship_to_user: null,
  contact: null,
  text: null,
  file_id: null,
  company: null,
  email: null,
  phone: null,
  years_known: null,
  reference_type: 'professional',
  may_contact: null,
}

function Group({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
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

function RecModal({
  open,
  initial,
  editId,
  onClose,
}: {
  open: boolean
  initial: RecommendationIn
  editId: number | null
  onClose: () => void
}) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [form, setForm] = useState<RecommendationIn>(initial)
  const set = <K extends keyof RecommendationIn>(key: K, value: RecommendationIn[K]) =>
    setForm((f) => ({ ...f, [key]: value }))

  const save = useMutation({
    mutationFn: () =>
      editId
        ? api.put<RecommendationOut>(`/api/profile/recommendations/${editId}`, form)
        : api.post<RecommendationOut>('/api/profile/recommendations', form),
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
      title={editId ? 'Edit reference' : 'Add a reference'}
      description="Reference sections ask for each person separately. Fill these in once and JobPilot answers them instead of stopping to ask."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()} disabled={!form.name}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <Group title="Who they are">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Name" required value={form.name} onChange={(e) => set('name', e.target.value)} />
            <Select
              label="Kind"
              hint="Forms often ask for a set number of each."
              value={form.reference_type ?? 'professional'}
              onChange={(e) => set('reference_type', e.target.value as 'professional' | 'personal')}
            >
              <option value="professional">Professional</option>
              <option value="personal">Personal</option>
            </Select>
            <Input
              label="Relationship to you"
              value={form.relationship_to_user ?? ''}
              onChange={(e) => set('relationship_to_user', e.target.value || null)}
              placeholder="e.g. Former manager"
            />
            <Input
              label="Years known"
              type="number"
              min={0}
              max={99}
              value={form.years_known ?? ''}
              onChange={(e) => set('years_known', e.target.value === '' ? null : Number(e.target.value))}
            />
            <Input label="Their job title" value={form.title ?? ''} onChange={(e) => set('title', e.target.value || null)} />
            <Input label="Where they work" value={form.company ?? ''} onChange={(e) => set('company', e.target.value || null)} />
          </div>
        </Group>

        <Group title="How to reach them" hint="Forms ask for both, in separate boxes.">
          <div className="grid gap-4 sm:grid-cols-2">
            <Input label="Email" type="email" value={form.email ?? ''} onChange={(e) => set('email', e.target.value || null)} />
            <Input label="Phone" value={form.phone ?? ''} onChange={(e) => set('phone', e.target.value || null)} />
            <div className="sm:col-span-2">
              <Select
                label="May an employer contact them?"
                hint="Left unanswered, JobPilot asks you when a form wants it."
                value={form.may_contact === true ? 'yes' : form.may_contact === false ? 'no' : ''}
                onChange={(e) =>
                  set('may_contact', e.target.value === 'yes' ? true : e.target.value === 'no' ? false : null)
                }
              >
                <option value="">Don’t answer — ask me</option>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </Select>
            </div>
          </div>
        </Group>

        <Group title="Notes" hint="For you — a written recommendation, or context. Not sent to forms.">
          <Textarea
            label="Notes"
            rows={3}
            value={form.text ?? ''}
            onChange={(e) => set('text', e.target.value || null)}
          />
        </Group>
      </div>
    </Modal>
  )
}

function missingFields(r: RecommendationOut): string[] {
  const missing: string[] = []
  const legacyEmail = Boolean(r.contact && r.contact.includes('@'))
  const legacyPhone = Boolean(r.contact && !r.contact.includes('@'))
  if (!r.email && !legacyEmail) missing.push('email')
  if (!r.phone && !legacyPhone) missing.push('phone')
  if (!r.relationship_to_user) missing.push('relationship')
  if (!r.company) missing.push('where they work')
  return missing
}

function toForm(r: RecommendationOut): RecommendationIn {
  return {
    name: r.name,
    title: r.title ?? null,
    relationship_to_user: r.relationship_to_user ?? null,
    contact: r.contact ?? null,
    text: r.text ?? null,
    file_id: r.file_id ?? null,
    company: r.company ?? null,
    email: r.email ?? null,
    phone: r.phone ?? null,
    years_known: r.years_known ?? null,
    reference_type: r.reference_type ?? 'professional',
    may_contact: r.may_contact ?? null,
  }
}

export function RecommendationsTab({ items }: { items: RecommendationOut[] }) {
  const queryClient = useQueryClient()
  const [modal, setModal] = useState<{ open: boolean; initial: RecommendationIn; editId: number | null }>({
    open: false,
    initial: EMPTY,
    editId: null,
  })

  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/profile/recommendations/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.profile }),
  })

  const shortBy = TYPICAL_REFERENCE_COUNT - items.length

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-neutral-500 dark:text-neutral-400">
          Order matters: the top entry is a form’s “Reference 1”.
          {shortBy > 0 && items.length > 0
            ? ` Most forms ask for ${TYPICAL_REFERENCE_COUNT} — you have ${items.length}.`
            : ''}
        </p>
        <Button variant="primary" size="sm" icon="plus" onClick={() => setModal({ open: true, initial: EMPTY, editId: null })}>
          Add reference
        </Button>
      </div>
      {items.length === 0 ? (
        <EmptyState
          icon="user"
          title="No references yet"
          description={`Add the people who can vouch for you — with how to reach them and how you know them. Most application forms ask for ${TYPICAL_REFERENCE_COUNT}.`}
        />
      ) : (
        <ul className="space-y-3">
          {items.map((r, i) => {
            const missing = missingFields(r)
            const email = r.email || (r.contact?.includes('@') ? r.contact : null)
            const phone = r.phone || (r.contact && !r.contact.includes('@') ? r.contact : null)
            return (
              <li key={r.id}>
                <Card padded={false} className="flex items-start gap-3 p-4">
                  <span
                    className="pt-0.5 text-[11px] font-semibold tabular-nums text-neutral-400"
                    title="Reference number on a form"
                  >
                    {i + 1}
                  </span>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="font-semibold text-neutral-900 dark:text-neutral-100">{r.name}</h4>
                      <Badge tone={r.reference_type === 'personal' ? 'purple' : 'accent'}>
                        {r.reference_type === 'personal' ? 'Personal' : 'Professional'}
                      </Badge>
                      {r.may_contact === false ? <Badge tone="warning">Do not contact</Badge> : null}
                    </div>
                    <p className="text-sm text-neutral-600 dark:text-neutral-300">
                      {[r.title, r.company, r.relationship_to_user].filter(Boolean).join(' · ') || '—'}
                    </p>
                    <p className="mt-0.5 text-xs text-neutral-400">
                      {[email, phone].filter(Boolean).join(' · ') || 'No contact details'}
                      {r.years_known != null ? ` · known ${r.years_known} year${r.years_known === 1 ? '' : 's'}` : ''}
                    </p>
                    {r.text ? <p className="mt-2 text-sm text-neutral-600 dark:text-neutral-300">“{r.text}”</p> : null}
                    {missing.length > 0 ? (
                      <button
                        onClick={() => setModal({ open: true, editId: r.id, initial: toForm(r) })}
                        className="mt-2 inline-flex items-center gap-1.5 rounded-lg bg-amber-50 px-2 py-1 text-xs text-amber-700 hover:bg-amber-100 dark:bg-amber-500/10 dark:text-amber-300"
                      >
                        <Icon name="alert" className="h-3.5 w-3.5" />
                        Forms will ask you for: {missing.join(', ')}
                      </button>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button
                      onClick={() => setModal({ open: true, editId: r.id, initial: toForm(r) })}
                      className="rounded-lg p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800"
                      aria-label="Edit"
                    >
                      <Icon name="edit" className="h-4 w-4" />
                    </button>
                    <button onClick={() => remove.mutate(r.id)} className="rounded-lg p-2 text-neutral-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" aria-label="Delete">
                      <Icon name="trash" className="h-4 w-4" />
                    </button>
                  </div>
                </Card>
              </li>
            )
          })}
        </ul>
      )}
      <RecModal key={`${modal.editId}-${modal.open}`} open={modal.open} initial={modal.initial} editId={modal.editId} onClose={() => setModal((m) => ({ ...m, open: false }))} />
    </div>
  )
}
