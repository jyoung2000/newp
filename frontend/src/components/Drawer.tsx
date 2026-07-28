import { useEffect } from 'react'
import { cx } from '../lib/format'
import { Icon } from './Icon'

interface DrawerProps {
  open: boolean
  onClose: () => void
  title?: React.ReactNode
  subtitle?: React.ReactNode
  children: React.ReactNode
  footer?: React.ReactNode
  width?: string
}

export function Drawer({ open, onClose, title, subtitle, children, footer, width = 'max-w-xl' }: DrawerProps) {
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true">
      <div className="absolute inset-0 animate-fade-in bg-neutral-900/40 backdrop-blur-sm dark:bg-black/60" onClick={onClose} />
      <div
        className={cx(
          'relative flex h-full w-full animate-slide-in-right flex-col bg-white shadow-2xl ring-1 ring-black/5 dark:bg-neutral-900 dark:ring-white/10',
          width,
        )}
      >
        <div className="flex items-start justify-between gap-4 border-b border-neutral-200 px-5 py-4 dark:border-neutral-800">
          <div className="min-w-0">
            {title ? (
              <h2 className="truncate text-base font-semibold text-neutral-900 dark:text-neutral-100">{title}</h2>
            ) : null}
            {subtitle ? (
              <p className="mt-0.5 truncate text-sm text-neutral-500 dark:text-neutral-400">{subtitle}</p>
            ) : null}
          </div>
          <button
            onClick={onClose}
            className="rounded-lg p-1.5 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
            aria-label="Close panel"
          >
            <Icon name="close" />
          </button>
        </div>
        <div className="flex-1 overflow-y-auto px-5 py-5">{children}</div>
        {footer ? (
          <div className="border-t border-neutral-200 px-5 py-3.5 dark:border-neutral-800">{footer}</div>
        ) : null}
      </div>
    </div>
  )
}
