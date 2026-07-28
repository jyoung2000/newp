import { useEffect, useRef, useState } from 'react'

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'error'

// Debounced autosave: watches `value`, and after `delay` ms of no changes
// calls `save`. Skips the initial mount so loading data doesn't trigger a PUT.
export function useAutosave<T>(value: T, save: (v: T) => Promise<unknown>, delay = 700) {
  const [status, setStatus] = useState<SaveStatus>('idle')
  const first = useRef(true)
  const savedTimer = useRef<number | null>(null)

  useEffect(() => {
    if (first.current) {
      first.current = false
      return
    }
    setStatus('saving')
    const handle = window.setTimeout(() => {
      save(value)
        .then(() => {
          setStatus('saved')
          if (savedTimer.current) window.clearTimeout(savedTimer.current)
          savedTimer.current = window.setTimeout(() => setStatus('idle'), 1800)
        })
        .catch(() => setStatus('error'))
    }, delay)
    return () => window.clearTimeout(handle)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  return status
}
