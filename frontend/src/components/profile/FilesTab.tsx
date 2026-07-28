import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import { useFiles } from '../../lib/hooks'
import type { ConfirmParseRequest, FileOut, ParsedResume } from '../../lib/types'
import { Card } from '../Card'
import { Button } from '../Button'
import { Badge } from '../Badge'
import { Select } from '../Field'
import { Toggle } from '../Toggle'
import { Modal } from '../Modal'
import { Icon } from '../Icon'
import { EmptyState } from '../EmptyState'
import { SkeletonRows } from '../Skeleton'
import { useToast } from '../../lib/toast'
import { fmtDate } from '../../lib/format'

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(0)} KB`
  return `${(n / 1024 / 1024).toFixed(1)} MB`
}

function ParseReview({ fileId, parsed, onClose }: { fileId: number; parsed: ParsedResume; onClose: () => void }) {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const [replaceWork, setReplaceWork] = useState(false)
  const [replaceEdu, setReplaceEdu] = useState(false)

  const confirm = useMutation({
    mutationFn: () => {
      const body: ConfirmParseRequest = { parsed, replace_work_history: replaceWork, replace_education: replaceEdu }
      return api.post<FileOut>(`/api/files/${fileId}/confirm-parse`, body)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.files })
      queryClient.invalidateQueries({ queryKey: qk.profile })
      push({ title: 'Resume applied to profile', tone: 'success' })
      onClose()
    },
    onError: (e) => push({ title: 'Could not apply', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const c = parsed.contact
  const work = parsed.work_experiences ?? []
  const edu = parsed.educations ?? []
  const skills = parsed.skills ?? []
  return (
    <Modal
      open
      onClose={onClose}
      size="lg"
      title="Review parsed resume"
      description="Check what we extracted before it updates your profile."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" icon="check" loading={confirm.isPending} onClick={() => confirm.mutate()}>
            Apply to profile
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <section>
          <h4 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">Contact</h4>
          <div className="grid grid-cols-2 gap-2 text-sm">
            {[
              ['Name', [c.first_name, c.last_name].filter(Boolean).join(' ')],
              ['Email', c.email],
              ['Phone', c.phone],
              ['Location', [c.city, c.state, c.country].filter(Boolean).join(', ')],
              ['LinkedIn', c.linkedin_url],
              ['GitHub', c.github_url],
            ].map(([label, val]) => (
              <div key={label} className="rounded-lg border border-neutral-200 px-3 py-2 dark:border-neutral-800">
                <div className="text-xs text-neutral-400">{label}</div>
                <div className="truncate text-neutral-800 dark:text-neutral-200">{val || '—'}</div>
              </div>
            ))}
          </div>
        </section>

        {parsed.summary ? (
          <section>
            <h4 className="mb-1 text-sm font-semibold text-neutral-900 dark:text-neutral-100">Summary</h4>
            <p className="text-sm text-neutral-600 dark:text-neutral-300">{parsed.summary}</p>
          </section>
        ) : null}

        <section className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
            <div className="mb-2 flex items-center justify-between">
              <h4 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Experience ({work.length})</h4>
            </div>
            <ul className="space-y-1.5 text-sm text-neutral-600 dark:text-neutral-300">
              {work.slice(0, 6).map((w, i) => (
                <li key={i} className="truncate">
                  <span className="font-medium text-neutral-800 dark:text-neutral-200">{w.title}</span> · {w.company}
                </li>
              ))}
              {work.length === 0 ? <li className="text-neutral-400">None found</li> : null}
            </ul>
            <div className="mt-3 border-t border-neutral-100 pt-3 dark:border-neutral-800">
              <Toggle checked={replaceWork} onChange={setReplaceWork} label="Replace existing work history" description="Otherwise these are added alongside." />
            </div>
          </div>

          <div className="rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
            <h4 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">Education ({edu.length})</h4>
            <ul className="space-y-1.5 text-sm text-neutral-600 dark:text-neutral-300">
              {edu.slice(0, 6).map((e, i) => (
                <li key={i} className="truncate">
                  <span className="font-medium text-neutral-800 dark:text-neutral-200">{e.school}</span>
                  {e.degree ? ` · ${e.degree}` : ''}
                </li>
              ))}
              {edu.length === 0 ? <li className="text-neutral-400">None found</li> : null}
            </ul>
            <div className="mt-3 border-t border-neutral-100 pt-3 dark:border-neutral-800">
              <Toggle checked={replaceEdu} onChange={setReplaceEdu} label="Replace existing education" />
            </div>
          </div>
        </section>

        {skills.length > 0 ? (
          <section>
            <h4 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">Skills</h4>
            <div className="flex flex-wrap gap-1.5">
              {skills.slice(0, 24).map((s, i) => (
                <Badge key={i} tone="neutral">
                  {s.name}
                  {s.years != null ? ` · ${s.years}y` : ''}
                </Badge>
              ))}
            </div>
          </section>
        ) : null}
      </div>
    </Modal>
  )
}

export function FilesTab() {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const files = useFiles()
  const inputRef = useRef<HTMLInputElement>(null)
  const [kind, setKind] = useState('resume')
  const [review, setReview] = useState<{ fileId: number; parsed: ParsedResume } | null>(null)

  const invalidate = () => queryClient.invalidateQueries({ queryKey: qk.files })

  const upload = useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      form.append('kind', kind)
      return api.upload<FileOut>('/api/files', form)
    },
    onSuccess: () => {
      invalidate()
      push({ title: 'Uploaded', tone: 'success' })
    },
    onError: (e) => push({ title: 'Upload failed', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const setDefault = useMutation({
    mutationFn: (id: number) => api.post(`/api/files/${id}/default-resume`),
    onSuccess: invalidate,
  })
  const remove = useMutation({
    mutationFn: (id: number) => api.del(`/api/files/${id}`),
    onSuccess: invalidate,
  })
  const parse = useMutation({
    mutationFn: (id: number) => api.post<ParsedResume>(`/api/files/${id}/parse`),
    onSuccess: (parsed, id) => setReview({ fileId: id, parsed }),
    onError: (e) => push({ title: 'Could not parse', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <div className="space-y-5">
      <Card>
        <div className="flex flex-col gap-3 sm:flex-row sm:items-end">
          <Select label="File type" value={kind} onChange={(e) => setKind(e.target.value)} className="sm:w-48">
            <option value="resume">Resume</option>
            <option value="cover_letter">Cover letter</option>
            <option value="transcript">Transcript</option>
            <option value="other">Other</option>
          </Select>
          <input
            ref={inputRef}
            type="file"
            className="hidden"
            accept=".pdf,.doc,.docx,.txt,.rtf"
            onChange={(e) => {
              const f = e.target.files?.[0]
              if (f) upload.mutate(f)
              e.target.value = ''
            }}
          />
          <Button variant="primary" icon="upload" loading={upload.isPending} onClick={() => inputRef.current?.click()}>
            Upload file
          </Button>
          <p className="text-xs text-neutral-400 sm:ml-auto">PDF, DOCX or TXT · stored on your server.</p>
        </div>
      </Card>

      {files.isLoading ? (
        <Card>
          <SkeletonRows rows={3} />
        </Card>
      ) : !files.data || files.data.length === 0 ? (
        <EmptyState icon="upload" title="No files yet" description="Upload a resume to parse it into your profile." />
      ) : (
        <ul className="space-y-2">
          {files.data.map((f) => (
            <li key={f.id}>
              <Card padded={false} className="flex items-center gap-3 p-3.5">
                <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-neutral-100 text-neutral-500 dark:bg-neutral-800 dark:text-neutral-300">
                  <Icon name="applications" className="h-5 w-5" />
                </div>
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate font-medium text-neutral-900 dark:text-neutral-100">{f.filename}</span>
                    {f.is_default_resume ? <Badge tone="accent" dot>Default resume</Badge> : null}
                    {f.parse_confirmed ? <Badge tone="success">Parsed</Badge> : null}
                  </div>
                  <p className="text-xs text-neutral-400">
                    {f.kind} · {fmtBytes(f.size_bytes)} · {fmtDate(f.created_at)}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-1">
                  {f.kind === 'resume' && !f.is_default_resume ? (
                    <Button size="sm" variant="ghost" icon="star" onClick={() => setDefault.mutate(f.id)}>
                      Default
                    </Button>
                  ) : null}
                  {f.kind === 'resume' ? (
                    <Button size="sm" variant="secondary" icon="sparkles" loading={parse.isPending && parse.variables === f.id} onClick={() => parse.mutate(f.id)}>
                      {f.parse_confirmed ? 'Re-parse' : 'Parse'}
                    </Button>
                  ) : null}
                  <a href={`/api/files/${f.id}/download`} className="rounded-lg p-2 text-neutral-400 hover:bg-neutral-100 hover:text-neutral-700 dark:hover:bg-neutral-800" aria-label="Download">
                    <Icon name="download" className="h-4 w-4" />
                  </a>
                  <button onClick={() => remove.mutate(f.id)} className="rounded-lg p-2 text-neutral-400 hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-500/10" aria-label="Delete">
                    <Icon name="trash" className="h-4 w-4" />
                  </button>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}

      {review ? <ParseReview fileId={review.fileId} parsed={review.parsed} onClose={() => setReview(null)} /> : null}
    </div>
  )
}
