import type { RunOut } from './types'

const TERMINAL = new Set(['finished', 'completed', 'done', 'stopped', 'failed', 'cancelled', 'canceled'])

export function isRunActive(run: RunOut): boolean {
  return !TERMINAL.has(run.status)
}

// Most relevant run to surface in the shell: an active one if present,
// otherwise the most recently created.
export function pickActiveRun(runs: RunOut[] | undefined): RunOut | null {
  if (!runs || runs.length === 0) return null
  const sorted = [...runs].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  )
  return sorted.find(isRunActive) ?? sorted[0] ?? null
}

// Count of applications still in flight for a run.
export function runInFlight(run: RunOut): number {
  return run.queued + run.filling + run.needs_human
}

export function runDone(run: RunOut): number {
  return run.submitted + run.drafted + run.failed + run.skipped + run.stopped
}
