import { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import { useDebouncedValue } from '../../lib/useDebounce'
import type { SavedAnswerIn, SavedAnswerOut } from '../../lib/types'
import { Card } from '../Card'
import { Button } from '../Button'
import { Badge } from '../Badge'
import { Input, Select } from '../Field'
import { Modal } from '../Modal'
import { Icon } from '../Icon'
import { EmptyState } from '../EmptyState'
import { SkeletonRows } from '../Skeleton'
import { useToast } from '../../lib/toast'
import { fmtRelative } from '../../lib/format'

const ANSWER_TYPES = ['text', 'boolean', 'number', 'select', 'date']

interface AnswerForm {
  question_text: string
  answer: string
  answer_type: string
  job_family: string
  question_key: string
  approved: boolean
}

const EMPTY: AnswerForm = { question_text: '', answer: '', answer_type: 'text', job_family: '', question_key: '', approved: true }

function AnswerModal({ open, initial, editId, onClose }: { open: boolean; initial: AnswerForm; editId: number | null; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [form, setForm] = useState<AnswerForm>(initial)

  const save = useMutation({
    mutationFn: () => {
      const body: SavedAnswerIn = {
        question_text: form.question_text,
        answer: form.answer_type === 'boolean' ? form.answer === 'true' : form.answer,
        answer_type: form.answer_type,
        job_family: form.job_family || null,
        question_key: form.question_key || null,
        approved: form.approved,
      }
      return editId ? api.put<SavedAnswerOut>(`/api/saved-answers/${editId}`, body) : api.post<SavedAnswerOut>('/api/saved-answers', body)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-answers'] })
      push({ title: editId ? 'Updated' : 'Added', tone: 'success' })
      onClose()
    },
    onError: (e) => push({ title: 'Could not save', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editId ? 'Edit saved answer' : 'Add saved answer'}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" loading={save.isPending} onClick={() => save.mutate()} disabled={!form.question_text}>
            Save
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        <div>
          <label className="label">Question</label>
          <textarea className="input min-h-[70px]" value={form.question_text} onChange={(e) => setForm((f) => ({ ...f, question_text: e.target.value }))} />
        </div>
        {form.answer_type === 'boolean' ? (
          <Select label="Answer" value={form.answer} onChange={(e) => setForm((f) => ({ ...f, answer: e.target.value }))}>
            <option value="true">Yes</option>
            <option value="false">No</option>
          </Select>
        ) : (
          <div>
            <label className="label">Answer</label>
            <textarea className="input min-h-[70px]" value={form.answer} onChange={(e) => setForm((f) => ({ ...f, answer: e.target.value }))} />
          </div>
        )}
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Answer type" value={form.answer_type} onChange={(e) => setForm((f) => ({ ...f, answer_type: e.target.value }))}>
            {ANSWER_TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </Select>
          <Input label="Job family (optional)" value={form.job_family} onChange={(e) => setForm((f) => ({ ...f, job_family: e.target.value }))} placeholder="e.g. engineering" />
        </div>
        <Input label="Normalized key (optional)" value={form.question_key} onChange={(e) => setForm((f) => ({ ...f, question_key: e.target.value }))} placeholder="auto-generated if blank" />
      </div>
    </Modal>
  )
}

export function SavedAnswersTab() {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [q, setQ] = useState('')
  const [modal, setModal] = useState<{ open: boolean; initial: AnswerForm; editId: number | null }>({ open: false, initial: EMPTY, editId: null })
  const debouncedQ = useDebouncedValue(q, 300)

  const { data, isLoading } = useQuery({
    queryKey: qk.savedAnswers(debouncedQ),
    queryFn: () => api.get<SavedAnswerOut[]>(`/api/saved-answers${debouncedQ ? `?q=${encodeURIComponent(debouncedQ)}` : ''}`),
  })

  const approve = useMutation({
    mutationFn: (id: number) => api.post(`/api/saved-answers/${id}/approve`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['saved-answers'] })
      push({ title: 'Approved', tone: 'success' })
    },
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/saved-answers/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['saved-answers'] }),
  })

  const renderAnswer = (a: unknown) => (a == null ? '—' : typeof a === 'boolean' ? (a ? 'Yes' : 'No') : String(a))

  return (
    <div>
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="relative flex-1">
          <Icon name="search" className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-neutral-400" />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search saved answers…" className="input pl-9" aria-label="Search saved answers" />
        </div>
        <Button variant="primary" icon="plus" onClick={() => setModal({ open: true, initial: EMPTY, editId: null })}>
          Add answer
        </Button>
      </div>

      {isLoading ? (
        <SkeletonRows rows={4} />
      ) : !data || data.length === 0 ? (
        <EmptyState icon="inbox" title="No saved answers" description="Answers you save while handling interventions build up here." />
      ) : (
        <ul className="space-y-2">
          {data.map((a) => (
            <li key={a.id}>
              <Card padded={false} className="p-4">
                <div className="flex items-start gap-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <p className="font-medium text-neutral-900 dark:text-neutral-100">{a.question_text}</p>
                      {a.approved ? <Badge tone="success" dot>Approved</Badge> : <Badge tone="warning" dot>Needs approval</Badge>}
                    </div>
                    <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-300">{renderAnswer(a.answer)}</p>
                    <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-neutral-400">
                      <span className="inline-flex items-center gap-1">
                        <Icon name="refresh" className="h-3.5 w-3.5" />
                        Used {a.times_used}×
                      </span>
                      {a.last_used_at ? <span>· last {fmtRelative(a.last_used_at)}</span> : null}
                      {a.job_family ? <Badge tone="neutral">{a.job_family}</Badge> : null}
                      <code className="rounded bg-neutral-100 px-1 py-0.5 font-mono dark:bg-neutral-800">{a.question_key}</code>
                    </div>
                  </div>
                  <div className="flex shrink-0 items-center gap-1">
                    {!a.approved ? (
                      <Button size="sm" variant="secondary" icon="check" onClick={() => approve.mutate(a.id)} loading={approve.isPending && approve.variables === a.id}>
                        Approve
                      </Button>
                    ) : null}
                    <button
                      onClick={() =>
                        setModal({
                          open: true,
                          editId: a.id,
                          initial: {
                            question_text: a.question_text,
                            answer: typeof a.answer === 'boolean' ? String(a.answer) : a.answer == null ? '' : String(a.answer),
                            answer_type: a.answer_type,
                            job_family: a.job_family ?? '',
                            question_key: a.question_key,
                            approved: a.approved,
                          },
                        })
                      }
                      className="rounded-lg p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800"
                      aria-label="Edit"
                    >
                      <Icon name="edit" className="h-4 w-4" />
                    </button>
                    <button onClick={() => remove.mutate(a.id)} className="rounded-lg p-2 text-neutral-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" aria-label="Delete">
                      <Icon name="trash" className="h-4 w-4" />
                    </button>
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}
      <AnswerModal key={`${modal.editId}-${modal.open}`} open={modal.open} initial={modal.initial} editId={modal.editId} onClose={() => setModal((m) => ({ ...m, open: false }))} />
    </div>
  )
}
