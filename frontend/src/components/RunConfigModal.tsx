import { useEffect, useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { api, ApiError } from '../lib/api'
import { useFiles, useUserSettings } from '../lib/hooks'
import type { RunCreate, RunCreated, RunMode, Executor } from '../lib/types'
import { Modal } from './Modal'
import { Button } from './Button'
import { Toggle } from './Toggle'
import { Select } from './Field'
import { Icon } from './Icon'
import { useToast } from '../lib/toast'
import { cx } from '../lib/format'

const MODES: { value: RunMode; label: string; desc: string }[] = [
  { value: 'auto', label: 'Auto', desc: 'Fill and submit automatically (you still solve any challenge).' },
  { value: 'review', label: 'Review', desc: 'Fill everything, then pause for your approval before submitting.' },
  { value: 'draft', label: 'Draft', desc: 'Prepare the application without submitting anything.' },
]
const EXECUTORS: { value: Executor; label: string }[] = [
  { value: 'auto', label: 'Auto' },
  { value: 'extension', label: 'Browser extension' },
  { value: 'playwright', label: 'Server (Playwright)' },
]

export function RunConfigModal({
  open,
  onClose,
  listingIds,
  initialMode = 'review',
  title = 'Apply to selected',
}: {
  open: boolean
  onClose: () => void
  listingIds: number[]
  initialMode?: RunMode
  title?: string
}) {
  const navigate = useNavigate()
  const { push } = useToast()
  const settings = useUserSettings()
  const files = useFiles()
  const resumes = (files.data ?? []).filter((f) => f.kind === 'resume')

  const [mode, setMode] = useState<RunMode>(initialMode)
  const [executor, setExecutor] = useState<Executor>('auto')
  const [humanize, setHumanize] = useState(true)
  const [resumeId, setResumeId] = useState<string>('')

  // Seed executor/humanize defaults from the user's settings once loaded.
  useEffect(() => {
    if (settings.data) {
      setExecutor(settings.data.executor_default ?? 'auto')
      setHumanize(settings.data.humanize_default ?? true)
    }
  }, [settings.data])

  // Reflect the requested initial mode whenever the modal is reopened.
  useEffect(() => {
    if (open) setMode(initialMode)
  }, [open, initialMode])

  const create = useMutation({
    mutationFn: () => {
      const body: RunCreate = {
        listing_ids: listingIds,
        mode,
        executor,
        humanize,
        resume_file_id: resumeId ? Number(resumeId) : null,
      }
      return api.post<RunCreated>('/api/runs', body)
    },
    onSuccess: (res) => {
      const already = res.already_applied.length
      push({
        title: 'Run started',
        tone: 'success',
        message:
          `${res.created_applications} application${res.created_applications === 1 ? '' : 's'} queued` +
          (already > 0 ? ` · ${already} already applied` : '') +
          (res.pacing_note ? ` · ${res.pacing_note}` : ''),
      })
      onClose()
      navigate('/queue')
    },
    onError: (e) => push({ title: 'Could not start run', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={title}
      description={`${listingIds.length} listing${listingIds.length === 1 ? '' : 's'} selected`}
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="primary" icon="play" loading={create.isPending} onClick={() => create.mutate()} disabled={listingIds.length === 0}>
            Start run
          </Button>
        </>
      }
    >
      <div className="space-y-5">
        <div>
          <span className="label">Mode</span>
          <div className="space-y-2">
            {MODES.map((m) => (
              <button
                key={m.value}
                type="button"
                onClick={() => setMode(m.value)}
                className={cx(
                  'flex w-full items-start gap-3 rounded-xl border p-3 text-left transition-colors',
                  mode === m.value
                    ? 'border-accent-400 bg-accent-50 dark:border-accent-500/40 dark:bg-accent-500/10'
                    : 'border-neutral-200 hover:border-neutral-300 dark:border-neutral-800 dark:hover:border-neutral-700',
                )}
              >
                <span
                  className={cx(
                    'mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border-2',
                    mode === m.value ? 'border-accent-600' : 'border-neutral-300 dark:border-neutral-600',
                  )}
                >
                  {mode === m.value ? <span className="h-2 w-2 rounded-full bg-accent-600" /> : null}
                </span>
                <span>
                  <span className="block text-sm font-medium text-neutral-900 dark:text-neutral-100">{m.label}</span>
                  <span className="block text-xs text-neutral-500 dark:text-neutral-400">{m.desc}</span>
                </span>
              </button>
            ))}
          </div>
        </div>

        <Select label="Executor" value={executor} onChange={(e) => setExecutor(e.target.value as Executor)}>
          {EXECUTORS.map((x) => (
            <option key={x.value} value={x.value}>
              {x.label}
            </option>
          ))}
        </Select>

        <Select label="Resume" value={resumeId} onChange={(e) => setResumeId(e.target.value)} hint="Overrides your default resume for this run.">
          <option value="">Use default resume</option>
          {resumes.map((r) => (
            <option key={r.id} value={r.id}>
              {r.filename}
              {r.is_default_resume ? ' (default)' : ''}
            </option>
          ))}
        </Select>

        <div className="rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
          <Toggle checked={humanize} onChange={setHumanize} label="Humanize typing" description="Adds natural pauses and typing rhythm while filling." />
        </div>

        <div className="flex items-start gap-2 rounded-xl bg-accent-50 p-3 text-xs text-accent-700 ring-1 ring-inset ring-accent-200 dark:bg-accent-500/10 dark:text-accent-300 dark:ring-accent-500/25">
          <Icon name="shield" className="mt-0.5 h-4 w-4 shrink-0" />
          <span>You solve every CAPTCHA yourself, knockout questions are never guessed, and EEO fields default to “decline to self-identify”.</span>
        </div>
      </div>
    </Modal>
  )
}
