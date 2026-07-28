import { createContext, useCallback, useContext, useMemo, useRef, useState } from 'react'

export type ToastTone = 'info' | 'success' | 'warning' | 'error'

export interface Toast {
  id: number
  title: string
  message?: string
  tone: ToastTone
  // Optional action link (e.g. jump to an intervention).
  href?: string
  actionLabel?: string
}

interface ToastContextValue {
  toasts: Toast[]
  push: (t: Omit<Toast, 'id'>) => number
  dismiss: (id: number) => void
}

const ToastContext = createContext<ToastContextValue | null>(null)

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const push = useCallback(
    (t: Omit<Toast, 'id'>) => {
      const id = nextId.current++
      setToasts((prev) => [...prev, { ...t, id }])
      const ttl = t.tone === 'error' ? 8000 : 5000
      window.setTimeout(() => dismiss(id), ttl)
      return id
    },
    [dismiss],
  )

  const value = useMemo<ToastContextValue>(() => ({ toasts, push, dismiss }), [toasts, push, dismiss])
  return <ToastContext.Provider value={value}>{children}</ToastContext.Provider>
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext)
  if (!ctx) throw new Error('useToast must be used within ToastProvider')
  return ctx
}
