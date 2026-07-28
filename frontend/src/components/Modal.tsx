import { useEffect } from 'react'
import { cx } from '../lib/format'
import { Icon } from './Icon'

interface ModalProps {
  open: boolean
  onClose: () => void
  title?: React.ReactNode
  description?: React.ReactNode
  children: React.ReactNode
  footer?: React.ReactNode
  size?: 'sm' | 'md' | 'lg'
}

const SIZES = { sm: 'max-w-sm', md: 'max-w-lg', lg: 'max-w-2xl' }

export function Modal({ open, onClose, title, description, children, footer, size = 'md' }: ModalProps) {
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
    <div className="fixed inset-0 z-50 flex items-end justify-center p-0 sm:items-center sm:p-4" role="dialog" aria-modal="true">
      <div
        className="absolute inset-0 animate-fade-in bg-neutral-900/40 backdrop-blur-sm dark:bg-black/60"
        onClick={onClose}
      />
      <div
        className={cx(
          'relative w-full animate-slide-up rounded-t-2xl bg-white shadow-xl ring-1 ring-black/5 sm:rounded-2xl dark:bg-neutral-900 dark:ring-white/10',
          SIZES[size],
        )}
      >
        {title ? (
          <div className="flex items-start justify-between gap-4 border-b border-neutral-200 px-5 py-4 dark:border-neutral-800">
            <div>
              <h2 className="text-base font-semibold text-neutral-900 dark:text-neutral-100">{title}</h2>
              {description ? (
                <p className="mt-0.5 text-sm text-neutral-500 dark:text-neutral-400">{description}</p>
              ) : null}
            </div>
            <button
              onClick={onClose}
              className="rounded-lg p-1.5 text-neutral-500 hover:bg-neutral-100 dark:hover:bg-neutral-800"
              aria-label="Close dialog"
            >
              <Icon name="close" />
            </button>
          </div>
        ) : null}
        <div className="max-h-[70vh] overflow-y-auto px-5 py-4">{children}</div>
        {footer ? (
          <div className="flex items-center justify-end gap-2 border-t border-neutral-200 px-5 py-3.5 dark:border-neutral-800">
            {footer}
          </div>
        ) : null}
      </div>
    </div>
  )
}
