import type { SaveStatus } from '../lib/useAutosave'
import { Icon } from './Icon'
import { Spinner } from './Spinner'

export function SaveIndicator({ status }: { status: SaveStatus }) {
  if (status === 'idle') return null
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-medium">
      {status === 'saving' ? (
        <span className="text-neutral-400">
          <Spinner className="mr-1 inline h-3 w-3" />
          Saving…
        </span>
      ) : status === 'saved' ? (
        <span className="text-emerald-600 dark:text-emerald-400">
          <Icon name="check" className="mr-0.5 inline h-3.5 w-3.5" />
          Saved
        </span>
      ) : (
        <span className="text-red-600 dark:text-red-400">
          <Icon name="alert" className="mr-0.5 inline h-3.5 w-3.5" />
          Save failed
        </span>
      )}
    </span>
  )
}
