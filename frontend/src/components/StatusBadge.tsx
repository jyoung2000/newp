import { Badge, type BadgeTone } from './Badge'
import { titleCase } from '../lib/format'

// Application / run / intervention status → tone + label.
const STATUS_TONE: Record<string, BadgeTone> = {
  // application / run lifecycle
  queued: 'neutral',
  pending: 'neutral',
  filling: 'accent',
  running: 'accent',
  in_progress: 'accent',
  needs_human: 'warning',
  paused: 'warning',
  review: 'warning',
  submitted: 'success',
  applied: 'success',
  finished: 'success',
  completed: 'success',
  drafted: 'purple',
  draft: 'purple',
  failed: 'error',
  error: 'error',
  stopped: 'neutral',
  skipped: 'neutral',
  cancelled: 'neutral',
  canceled: 'neutral',
  // intervention status
  open: 'warning',
  answered: 'success',
  resolved: 'success',
  // outcomes
  none: 'neutral',
  no_response: 'neutral',
  rejected: 'error',
  recruiter_reply: 'accent',
  interview: 'purple',
  offer: 'success',
}

const LABELS: Record<string, string> = {
  needs_human: 'Needs you',
  no_response: 'No response',
  recruiter_reply: 'Recruiter reply',
  in_progress: 'In progress',
}

export function StatusBadge({ status, dot = true }: { status: string; dot?: boolean }) {
  const tone = STATUS_TONE[status] ?? 'neutral'
  const label = LABELS[status] ?? titleCase(status)
  return (
    <Badge tone={tone} dot={dot}>
      {label}
    </Badge>
  )
}

// Search source status: ok / blocked / disabled / forbidden.
const SOURCE_TONE: Record<string, BadgeTone> = {
  ok: 'success',
  ready: 'success',
  blocked: 'warning',
  rate_limited: 'warning',
  disabled: 'neutral',
  not_configured: 'neutral',
  forbidden: 'error',
}

export function SourceStatusBadge({ status }: { status: string }) {
  const tone = SOURCE_TONE[status] ?? 'neutral'
  return (
    <Badge tone={tone} dot>
      {titleCase(status)}
    </Badge>
  )
}
