import { titleCase } from '../../lib/format'

interface BarRow {
  label: string
  value: number
  max: number
  caption?: string
  tone?: string
}

// A simple horizontal bar list — used for per-source volume and response rate.
export function BarBreakdown({ rows, emptyLabel = 'No data yet' }: { rows: BarRow[]; emptyLabel?: string }) {
  if (rows.length === 0) {
    return <div className="py-8 text-center text-sm text-neutral-400">{emptyLabel}</div>
  }
  return (
    <div className="space-y-3">
      {rows.map((r) => {
        const pct = r.max > 0 ? Math.max(2, (r.value / r.max) * 100) : 0
        return (
          <div key={r.label}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="font-medium text-neutral-700 dark:text-neutral-300">{titleCase(r.label)}</span>
              <span className="tabular-nums text-neutral-500 dark:text-neutral-400">{r.caption ?? r.value}</span>
            </div>
            <div className="h-2 overflow-hidden rounded-full bg-neutral-200 dark:bg-neutral-800">
              <div
                className="h-full rounded-full transition-[width] duration-500"
                style={{ width: `${pct}%`, background: r.tone ?? '#2563eb' }}
              />
            </div>
          </div>
        )
      })}
    </div>
  )
}
