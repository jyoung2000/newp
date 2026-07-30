import { useRef, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import type {
  BackupContents,
  ImportListingsResult,
  ImportPreview,
  ImportResult,
  RestoreResult,
} from '../../lib/types'
import { Card, CardHeader } from '../Card'
import { Button } from '../Button'
import { Badge } from '../Badge'
import { Toggle } from '../Toggle'
import { Icon, type IconName } from '../Icon'
import { useToast } from '../../lib/toast'
import { titleCase } from '../../lib/format'

const EXPORTS: { href: string; label: string; desc: string; icon: IconName }[] = [
  { href: '/api/transfer/everything.zip', label: 'Everything (.zip)', desc: 'Full backup — restorable below', icon: 'download' },
  { href: '/api/transfer/profile.json', label: 'Profile (.json)', desc: 'Profile, work, education, answers', icon: 'user' },
  { href: '/api/transfer/listings.csv', label: 'Listings (.csv)', desc: 'All saved listings', icon: 'listings' },
  { href: '/api/transfer/listings.json', label: 'Listings (.json)', desc: 'All saved listings', icon: 'listings' },
  { href: '/api/transfer/applications.csv', label: 'Applications (.csv)', desc: 'Your application log', icon: 'applications' },
]

function ProfileImport() {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<ImportPreview | null>(null)
  const [merge, setMerge] = useState(true)

  const runPreview = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData()
      form.append('file', f)
      return api.upload<ImportPreview>('/api/transfer/profile/preview', form)
    },
    onSuccess: (res) => setPreview(res),
    onError: (e) => push({ title: 'Could not read file', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const apply = useMutation({
    mutationFn: () => {
      const form = new FormData()
      form.append('file', file as File)
      return api.upload<ImportResult>(`/api/transfer/profile/apply?merge=${merge}`, form)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: qk.profile })
      queryClient.invalidateQueries({ queryKey: qk.customFields })
      push({ title: 'Profile imported', tone: 'success' })
      setPreview(null)
      setFile(null)
    },
    onError: (e) => push({ title: 'Import failed', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const conflicts = preview ? Object.keys(preview.conflicts ?? {}) : []
  const counts: [string, number][] = preview
    ? [
        ['Profile fields', Object.keys(preview.profile_fields ?? {}).length],
        ['Work experiences', preview.work_experiences],
        ['Educations', preview.educations],
        ['Recommendations', preview.recommendations],
        ['Custom fields', preview.custom_fields],
        ['Saved answers', preview.saved_answers],
        ['Search targets', preview.search_targets],
      ]
    : []

  return (
    <div className="rounded-xl border border-neutral-200 p-4 dark:border-neutral-800">
      <h4 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Import profile (.json)</h4>
      <p className="mt-0.5 text-xs text-neutral-400">Preview the changes before anything is applied.</p>
      <input
        ref={inputRef}
        type="file"
        accept=".json,application/json"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) {
            setFile(f)
            runPreview.mutate(f)
          }
          e.target.value = ''
        }}
      />
      <div className="mt-3">
        <Button variant="secondary" size="sm" icon="upload" loading={runPreview.isPending} onClick={() => inputRef.current?.click()}>
          Choose file
        </Button>
      </div>

      {preview ? (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {counts.map(([label, n]) => (
              <div key={label} className="rounded-lg bg-neutral-50 px-3 py-2 dark:bg-neutral-800/50">
                <div className="text-lg font-semibold tabular-nums text-neutral-900 dark:text-neutral-100">{n}</div>
                <div className="text-[11px] text-neutral-500 dark:text-neutral-400">{label}</div>
              </div>
            ))}
          </div>
          {conflicts.length > 0 ? (
            <div className="flex flex-wrap items-center gap-1.5">
              <span className="text-xs text-amber-600 dark:text-amber-400">Conflicts:</span>
              {conflicts.map((c) => (
                <Badge key={c} tone="warning">
                  {titleCase(c)}
                </Badge>
              ))}
            </div>
          ) : null}
          <div className="rounded-lg border border-neutral-200 p-3 dark:border-neutral-800">
            <Toggle checked={merge} onChange={setMerge} label="Merge with existing data" description="Off replaces conflicting fields with the imported values." />
          </div>
          <div className="flex gap-2">
            <Button variant="primary" icon="check" loading={apply.isPending} onClick={() => apply.mutate()}>
              Apply import
            </Button>
            <Button variant="ghost" onClick={() => { setPreview(null); setFile(null) }}>
              Cancel
            </Button>
          </div>
        </div>
      ) : null}
    </div>
  )
}

/**
 * Restore a whole jobpilot-export.zip: profile, job list, application history
 * and uploaded files, in one step. Previews first — a restore is the kind of
 * thing people do when something has already gone wrong, so it should say what
 * it is about to do before doing it.
 */
function BackupRestore() {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const inputRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [contents, setContents] = useState<BackupContents | null>(null)
  const [overwrite, setOverwrite] = useState(false)

  const preview = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData()
      form.append('file', f)
      return api.upload<BackupContents>('/api/transfer/backup/preview', form)
    },
    onSuccess: (res, f) => {
      setContents(res)
      setFile(res.valid ? f : null)
    },
    onError: (e) => push({ title: 'Could not read that file', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  const restore = useMutation({
    mutationFn: () => {
      const form = new FormData()
      form.append('file', file as File)
      return api.upload<RestoreResult>(
        `/api/transfer/backup/restore?merge=${overwrite ? 'overwrite' : 'keep'}`,
        form,
      )
    },
    onSuccess: (res) => {
      // Everything on screen may have changed.
      void queryClient.invalidateQueries()
      setFile(null)
      setContents(null)
      push({
        title: 'Backup restored',
        tone: 'success',
        message:
          `${res.listings_imported} listings · ${res.applications_imported} applications · ` +
          `${res.files_imported} files`,
      })
    },
    onError: (e) => push({ title: 'Restore failed', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <div className="rounded-xl border border-neutral-200 p-4 dark:border-neutral-800">
      <h4 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">
        Restore a full backup (.zip)
      </h4>
      <p className="mt-0.5 text-xs text-neutral-400">
        The <b>Everything (.zip)</b> file from above — profile, job list, application history and
        your uploaded files. Nothing already here is deleted.
      </p>
      <input
        ref={inputRef}
        type="file"
        accept=".zip"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) preview.mutate(f)
          e.target.value = ''
        }}
      />

      {contents && !contents.valid ? (
        <p className="mt-3 rounded-lg bg-red-50 px-3 py-2 text-xs text-red-700 dark:bg-red-500/10 dark:text-red-300">
          {contents.problem}
        </p>
      ) : null}

      {contents?.valid ? (
        <div className="mt-3 rounded-lg bg-neutral-50 p-3 dark:bg-neutral-800/60">
          <p className="text-xs text-neutral-500 dark:text-neutral-400">
            From <b>{contents.account_email || 'an unnamed account'}</b>
            {contents.exported_at ? `, exported ${contents.exported_at.slice(0, 10)}` : ''}
            {contents.app_version ? ` · JobPilot v${contents.app_version}` : ''}
          </p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            <Badge tone="neutral">{contents.listings} listings</Badge>
            <Badge tone="neutral">{contents.applications} applications</Badge>
            <Badge tone="neutral">{contents.files} files</Badge>
            <Badge tone="neutral">{contents.work_experiences} roles</Badge>
            <Badge tone="neutral">{contents.custom_fields} custom fields</Badge>
            <Badge tone="neutral">{contents.saved_answers} saved answers</Badge>
          </div>
          {contents.existing_listings + contents.existing_applications + contents.existing_files >
          0 ? (
            <p className="mt-2 text-xs text-neutral-500 dark:text-neutral-400">
              This account already has {contents.existing_listings} listings,{' '}
              {contents.existing_applications} applications and {contents.existing_files} files.
              Duplicates are skipped, so restoring twice won't double anything.
            </p>
          ) : null}
          <div className="mt-3">
            <Toggle
              checked={overwrite}
              onChange={setOverwrite}
              label="Let the backup overwrite profile details that differ"
              description="Off: your current values are kept and only blanks are filled in."
            />
          </div>
          <div className="mt-3 flex gap-2">
            <Button variant="primary" size="sm" loading={restore.isPending} onClick={() => restore.mutate()}>
              Restore
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => {
                setFile(null)
                setContents(null)
              }}
            >
              Cancel
            </Button>
          </div>
        </div>
      ) : (
        <div className="mt-3">
          <Button
            variant="secondary"
            size="sm"
            icon="upload"
            loading={preview.isPending}
            onClick={() => inputRef.current?.click()}
          >
            Choose backup
          </Button>
        </div>
      )}
    </div>
  )
}

function ListingsImport() {
  const queryClient = useQueryClient()
  const { push } = useToast()
  const inputRef = useRef<HTMLInputElement>(null)

  const importListings = useMutation({
    mutationFn: (f: File) => {
      const form = new FormData()
      form.append('file', f)
      return api.upload<ImportListingsResult>('/api/transfer/listings/import', form)
    },
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['listings'] })
      push({ title: 'Listings imported', tone: 'success', message: `${res.imported} imported · ${res.skipped} skipped` })
    },
    onError: (e) => push({ title: 'Import failed', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <div className="rounded-xl border border-neutral-200 p-4 dark:border-neutral-800">
      <h4 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Import listings (.csv / .json)</h4>
      <p className="mt-0.5 text-xs text-neutral-400">Add listings exported from another JobPilot.</p>
      <input
        ref={inputRef}
        type="file"
        accept=".csv,.json"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0]
          if (f) importListings.mutate(f)
          e.target.value = ''
        }}
      />
      <div className="mt-3">
        <Button variant="secondary" size="sm" icon="upload" loading={importListings.isPending} onClick={() => inputRef.current?.click()}>
          Choose file
        </Button>
      </div>
    </div>
  )
}

export function DataSection() {
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader title="Export" subtitle="Download your data any time — it’s yours" icon={<Icon name="download" />} />
        <div className="grid gap-2 sm:grid-cols-2">
          {EXPORTS.map((x) => (
            <a
              key={x.href}
              href={x.href}
              className="flex items-center gap-3 rounded-xl border border-neutral-200 p-3 transition-colors hover:border-accent-300 dark:border-neutral-800 dark:hover:border-accent-500/40"
            >
              <Icon name={x.icon} className="h-5 w-5 text-accent-600" />
              <div>
                <p className="text-sm font-medium text-neutral-900 dark:text-neutral-100">{x.label}</p>
                <p className="text-xs text-neutral-400">{x.desc}</p>
              </div>
            </a>
          ))}
        </div>
      </Card>

      <Card>
        <CardHeader title="Import" subtitle="Bring data in from a backup or another instance" icon={<Icon name="upload" />} />
        <div className="space-y-3">
          <BackupRestore />
          <ProfileImport />
          <ListingsImport />
        </div>
      </Card>
    </div>
  )
}
