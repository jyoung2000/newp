import { cx } from '../lib/format'

export function Skeleton({ className }: { className?: string }) {
  return <div className={cx('skeleton', className || 'h-4 w-full')} />
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cx('space-y-2', className)}>
      {Array.from({ length: lines }).map((_, i) => (
        <Skeleton key={i} className={cx('h-3.5', i === lines - 1 ? 'w-2/3' : 'w-full')} />
      ))}
    </div>
  )
}

export function SkeletonRows({ rows = 5, className }: { rows?: number; className?: string }) {
  return (
    <div className={cx('space-y-3', className)}>
      {Array.from({ length: rows }).map((_, i) => (
        <div key={i} className="flex items-center gap-3">
          <Skeleton className="h-10 w-10 rounded-xl" />
          <div className="flex-1 space-y-2">
            <Skeleton className="h-3.5 w-1/3" />
            <Skeleton className="h-3 w-1/2" />
          </div>
          <Skeleton className="h-6 w-16 rounded-full" />
        </div>
      ))}
    </div>
  )
}

export function SkeletonCards({ count = 4, className }: { count?: number; className?: string }) {
  return (
    <div className={cx('grid gap-4', className)}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="card p-5">
          <Skeleton className="h-3 w-24" />
          <Skeleton className="mt-3 h-8 w-16" />
        </div>
      ))}
    </div>
  )
}
