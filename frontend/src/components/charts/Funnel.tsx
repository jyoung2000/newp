import type { FunnelStage } from '../../lib/types'
import { titleCase } from '../../lib/format'

// Five-stage funnel rendered as tapering horizontal bars.
const TONES = ['#2563eb', '#4f46e5', '#7c3aed', '#9333ea', '#c026d3']

export function Funnel({ stages }: { stages: FunnelStage[] }) {
  if (stages.length === 0) {
    return <div className="py-8 text-center text-sm text-neutral-400">No data yet</div>
  }
  const max = Math.max(1, ...stages.map((s) => s.count))
  const top = stages[0]?.count ?? 0
  return (
    <div className="space-y-2">
      {stages.map((s, i) => {
        const pct = Math.max(4, (s.count / max) * 100)
        const conv = top > 0 ? Math.round((s.count / top) * 100) : 0
        return (
          <div key={s.stage} className="flex items-center gap-3">
            <div className="w-28 shrink-0 text-right text-xs font-medium text-neutral-600 dark:text-neutral-400">
              {titleCase(s.stage)}
            </div>
            <div className="relative h-8 flex-1 overflow-hidden rounded-lg bg-neutral-100 dark:bg-neutral-800">
              <div
                className="flex h-full items-center rounded-lg px-2.5 text-xs font-semibold text-white transition-[width] duration-500"
                style={{ width: `${pct}%`, background: TONES[i % TONES.length] }}
              >
                <span className="tabular-nums">{s.count}</span>
              </div>
            </div>
            <div className="w-10 shrink-0 text-right text-xs tabular-nums text-neutral-400">{conv}%</div>
          </div>
        )
      })}
    </div>
  )
}
