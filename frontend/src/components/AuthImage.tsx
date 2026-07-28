import { useEffect, useState } from 'react'
import { apiBlob } from '../lib/api'
import { cx } from '../lib/format'
import { Icon } from './Icon'
import { Spinner } from './Spinner'

// Loads an image that requires the session cookie (screenshots) as a blob and
// renders it. Object URLs are revoked on unmount.
export function AuthImage({
  src,
  alt,
  className,
  cropHeight,
}: {
  src: string | null | undefined
  alt: string
  className?: string
  cropHeight?: string
}) {
  const [url, setUrl] = useState<string | null>(null)
  const [state, setState] = useState<'loading' | 'ok' | 'error'>('loading')

  useEffect(() => {
    if (!src) {
      setState('error')
      return
    }
    let objectUrl: string | null = null
    let cancelled = false
    setState('loading')
    apiBlob(src)
      .then((blob) => {
        if (cancelled) return
        objectUrl = URL.createObjectURL(blob)
        setUrl(objectUrl)
        setState('ok')
      })
      .catch(() => {
        if (!cancelled) setState('error')
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [src])

  if (state === 'error') {
    return (
      <div
        className={cx(
          'flex items-center justify-center gap-2 rounded-xl border border-dashed border-neutral-300 bg-neutral-50 text-sm text-neutral-400 dark:border-neutral-700 dark:bg-neutral-900',
          cropHeight || 'h-40',
          className,
        )}
      >
        <Icon name="eyeOff" className="h-4 w-4" />
        No screenshot
      </div>
    )
  }

  if (state === 'loading') {
    return (
      <div
        className={cx(
          'flex items-center justify-center rounded-xl bg-neutral-100 text-neutral-400 dark:bg-neutral-800',
          cropHeight || 'h-40',
          className,
        )}
      >
        <Spinner className="h-5 w-5" />
      </div>
    )
  }

  return (
    <div className={cx('overflow-hidden rounded-xl border border-neutral-200 dark:border-neutral-800', cropHeight, className)}>
      <img src={url || undefined} alt={alt} className="w-full object-cover object-top" />
    </div>
  )
}
