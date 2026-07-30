import { useEffect, useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api, ApiError } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import { useDevices, useExtensionInfo } from '../../lib/hooks'
import type { PairingCodeOut } from '../../lib/types'
import { Card, CardHeader } from '../Card'
import { Button } from '../Button'
import { Badge } from '../Badge'
import { Icon } from '../Icon'
import { EmptyState } from '../EmptyState'
import { SkeletonRows } from '../Skeleton'
import { useToast } from '../../lib/toast'
import { cx, fmtRelative } from '../../lib/format'

const CHROME_STEPS = [
  'Download and unzip the Chrome extension below.',
  'Open chrome://extensions in your browser.',
  'Turn on “Developer mode” (top-right toggle).',
  'Click “Load unpacked” and select the unzipped folder.',
  'Pin JobPilot from the extensions menu, then pair it below.',
]
const FIREFOX_STEPS = [
  'Download and unzip the Firefox extension below.',
  'Open about:debugging in your browser.',
  'Click “This Firefox”, then “Load Temporary Add-on…”.',
  'Select the manifest.json inside the unzipped folder.',
  'Pair it below. Note: temporary add-ons are removed when Firefox restarts.',
]

function Walkthrough({ title, steps, caveat }: { title: string; steps: string[]; caveat?: string }) {
  return (
    <details className="group rounded-xl border border-neutral-200 dark:border-neutral-800">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-4 py-3 text-sm font-medium text-neutral-800 dark:text-neutral-200">
        <Icon name="chevronRight" className="h-4 w-4 transition-transform group-open:rotate-90" />
        {title}
      </summary>
      <div className="border-t border-neutral-100 px-4 py-3 dark:border-neutral-800">
        <ol className="space-y-2">
          {steps.map((s, i) => (
            <li key={i} className="flex gap-3 text-sm text-neutral-600 dark:text-neutral-300">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-100 text-xs font-semibold text-accent-700 dark:bg-accent-500/20 dark:text-accent-300">
                {i + 1}
              </span>
              {s}
            </li>
          ))}
        </ol>
        {caveat ? (
          <div className="mt-3 flex items-start gap-2 rounded-lg bg-amber-50 p-2.5 text-xs text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
            <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0" />
            {caveat}
          </div>
        ) : null}
      </div>
    </details>
  )
}

function Countdown({ expiresAt }: { expiresAt: string }) {
  const [left, setLeft] = useState(() => Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000)))
  useEffect(() => {
    const t = setInterval(() => {
      setLeft(Math.max(0, Math.floor((new Date(expiresAt).getTime() - Date.now()) / 1000)))
    }, 1000)
    return () => clearInterval(t)
  }, [expiresAt])
  const m = Math.floor(left / 60)
  const sec = left % 60
  if (left <= 0) return <span className="text-red-600 dark:text-red-400">Expired — generate a new code</span>
  return (
    <span className="tabular-nums">
      Expires in {m}:{String(sec).padStart(2, '0')}
    </span>
  )
}

function Pairing() {
  const { push } = useToast()
  const [pairing, setPairing] = useState<PairingCodeOut | null>(null)

  const generate = useMutation({
    mutationFn: () => api.post<PairingCodeOut>('/api/devices/pairing-code'),
    onSuccess: (res) => setPairing(res),
    onError: (e) => push({ title: 'Could not generate code', tone: 'error', message: e instanceof ApiError ? e.detail : '' }),
  })

  return (
    <div className="rounded-xl border border-neutral-200 p-4 dark:border-neutral-800">
      <div className="flex items-center justify-between">
        <div>
          <h4 className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Link a browser</h4>
          <p className="text-xs text-neutral-400">
            Copy one code, paste it into the extension. It carries this server's address with it,
            so there's nothing to type.
          </p>
        </div>
        <Button variant="secondary" size="sm" icon="refresh" loading={generate.isPending} onClick={() => generate.mutate()}>
          {pairing ? 'New code' : 'Generate code'}
        </Button>
      </div>

      {pairing ? (
        <div className="mt-4 grid gap-4">
          {/* The one thing to copy, first and biggest. */}
          <div>
            <div className="flex flex-col gap-2 sm:flex-row sm:items-start">
              <code className="min-w-0 flex-1 break-all rounded-xl bg-neutral-100 px-3 py-2.5 font-mono text-xs leading-relaxed text-neutral-800 dark:bg-neutral-800 dark:text-neutral-200">
                {pairing.link_code}
              </code>
              <CopyLinkCode value={pairing.link_code} />
            </div>
            <p className="mt-2 text-xs text-neutral-400">
              <Countdown expiresAt={pairing.expires_at} />
            </p>
          </div>

          <details className="text-xs text-neutral-500 dark:text-neutral-400">
            <summary className="cursor-pointer select-none">
              Scan a QR code, or enter it by hand
            </summary>
            <div className="mt-3 grid gap-4 sm:grid-cols-[auto,1fr] sm:items-center">
              <div className="flex justify-center">
                <div className="rounded-xl border border-neutral-200 bg-white p-3 [&_svg]:h-36 [&_svg]:w-36 dark:border-neutral-700" dangerouslySetInnerHTML={{ __html: pairing.qr_svg }} />
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  {pairing.code.split('').map((d, i) => (
                    <span key={i} className="flex h-11 w-9 items-center justify-center rounded-lg bg-neutral-100 text-xl font-semibold tabular-nums text-neutral-900 dark:bg-neutral-800 dark:text-neutral-100">
                      {d}
                    </span>
                  ))}
                </div>
                <p className="mt-2 break-all">Server: {pairing.app_url}</p>
                <p className="mt-1">
                  Both halves of the link code, if you'd rather type them into the extension's
                  manual fields.
                </p>
              </div>
            </div>
          </details>
        </div>
      ) : null}
    </div>
  )
}

/** Copy button that confirms it worked, and degrades to select-all when the
 *  clipboard API is unavailable — plain http origins don't always grant it. */
function CopyLinkCode({ value }: { value: string }) {
  const { push } = useToast()
  const [copied, setCopied] = useState(false)

  const copy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch {
      push({
        title: 'Select and copy it manually',
        tone: 'info',
        message: 'This browser blocked clipboard access on a plain http:// page.',
      })
    }
  }

  return (
    <Button
      variant="primary"
      size="sm"
      icon={copied ? 'check' : 'grip'}
      className="shrink-0"
      onClick={() => void copy()}
    >
      {copied ? 'Copied' : 'Copy link code'}
    </Button>
  )
}

function Devices() {
  const queryClient = useQueryClient()
  const { data, isLoading } = useDevices()
  const revoke = useMutation({
    mutationFn: (id: number) => api.del(`/api/devices/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.devices }),
  })

  if (isLoading) return <SkeletonRows rows={2} />
  if (!data || data.length === 0) {
    return <EmptyState compact icon="laptop" title="No paired devices" description="Pair the extension above to see it here." />
  }
  return (
    <ul className="space-y-2">
      {data.map((d) => (
        <li key={d.id} className="flex items-center gap-3 rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
          <span className={cx('flex h-9 w-9 items-center justify-center rounded-lg', d.online ? 'bg-emerald-50 text-emerald-600 dark:bg-emerald-500/15 dark:text-emerald-400' : 'bg-neutral-100 text-neutral-400 dark:bg-neutral-800')}>
            <Icon name="laptop" className="h-5 w-5" />
          </span>
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              <p className="truncate text-sm font-medium text-neutral-800 dark:text-neutral-200">{d.name}</p>
              {d.online ? <Badge tone="success" dot>Online</Badge> : <Badge tone="neutral">Offline</Badge>}
            </div>
            <p className="text-xs text-neutral-400">
              {d.browser || 'Browser'}
              {d.extension_version ? ` · v${d.extension_version}` : ''} · seen {fmtRelative(d.last_seen_at)}
            </p>
          </div>
          <Button size="sm" variant="ghost" icon="trash" onClick={() => revoke.mutate(d.id)}>
            Revoke
          </Button>
        </li>
      ))}
    </ul>
  )
}

export function ExtensionSection() {
  const info = useExtensionInfo()
  const chromeUrl = info.data?.chrome_url || '/api/files/extension/chrome'
  const firefoxUrl = info.data?.firefox_url || '/api/files/extension/firefox'
  const available = info.data?.available ?? false

  return (
    <div className="space-y-5">
      <Card>
        <CardHeader
          title="Browser extension"
          subtitle="Applies on real employer pages from your own browser"
          icon={<Icon name="laptop" />}
          action={info.data?.version ? <Badge tone="neutral">v{info.data.version}</Badge> : null}
        />

        {!available ? (
          <div className="mb-4 flex items-start gap-2 rounded-xl bg-amber-50 p-3 text-sm text-amber-800 dark:bg-amber-500/10 dark:text-amber-300">
            <Icon name="info" className="mt-0.5 h-4 w-4 shrink-0" />
            The packaged extension isn’t available on this server yet. You can still pair a device once it is built.
          </div>
        ) : null}

        <div className="grid gap-3 sm:grid-cols-2">
          <a href={chromeUrl} className={cx(!available && 'pointer-events-none opacity-50')}>
            <div className="flex items-center gap-3 rounded-xl border border-neutral-200 p-4 transition-colors hover:border-accent-300 dark:border-neutral-800 dark:hover:border-accent-500/40">
              <Icon name="download" className="h-5 w-5 text-accent-600" />
              <div>
                <p className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Chrome / Edge</p>
                <p className="text-xs text-neutral-400">Download unpacked extension</p>
              </div>
            </div>
          </a>
          <a href={firefoxUrl} className={cx(!available && 'pointer-events-none opacity-50')}>
            <div className="flex items-center gap-3 rounded-xl border border-neutral-200 p-4 transition-colors hover:border-accent-300 dark:border-neutral-800 dark:hover:border-accent-500/40">
              <Icon name="download" className="h-5 w-5 text-accent-600" />
              <div>
                <p className="text-sm font-semibold text-neutral-900 dark:text-neutral-100">Firefox</p>
                <p className="text-xs text-neutral-400">Download unpacked extension</p>
              </div>
            </div>
          </a>
        </div>

        <div className="mt-4 space-y-2">
          <Walkthrough title="How to install on Chrome / Edge" steps={CHROME_STEPS} />
          <Walkthrough
            title="How to install on Firefox"
            steps={FIREFOX_STEPS}
            caveat="Firefox removes unsigned temporary add-ons every time it restarts — you’ll re-load it each session unless the add-on is signed."
          />
        </div>
      </Card>

      <Card>
        <CardHeader title="Pairing & devices" icon={<Icon name="key" />} />
        <Pairing />
        <div className="mt-4">
          <h4 className="mb-2 text-sm font-semibold text-neutral-700 dark:text-neutral-300">Paired devices</h4>
          <Devices />
        </div>
      </Card>
    </div>
  )
}
