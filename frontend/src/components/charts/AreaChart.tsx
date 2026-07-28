import { useId } from 'react'
import type { TimePoint } from '../../lib/types'
import { fmtDate } from '../../lib/format'

// Dependency-free area/line chart for applications-over-time. Two series
// (found + applied) drawn in a fixed logical coordinate space, stretched
// responsively with non-scaling strokes so lines stay crisp at any width.
const W = 640
const H = 220
const PAD = { top: 16, right: 12, bottom: 26, left: 30 }

interface Series {
  key: keyof Pick<TimePoint, 'found' | 'applied'>
  label: string
  stroke: string
  fillFrom: string
  fillTo: string
}

const SERIES: Series[] = [
  { key: 'found', label: 'Found', stroke: '#2563eb', fillFrom: 'rgba(37,99,235,0.28)', fillTo: 'rgba(37,99,235,0)' },
  { key: 'applied', label: 'Applied', stroke: '#10b981', fillFrom: 'rgba(16,185,129,0.24)', fillTo: 'rgba(16,185,129,0)' },
]

export function AreaChart({ data }: { data: TimePoint[] }) {
  const gid = useId().replace(/:/g, '')
  if (data.length === 0) {
    return <div className="flex h-48 items-center justify-center text-sm text-neutral-400">No data yet</div>
  }

  const innerW = W - PAD.left - PAD.right
  const innerH = H - PAD.top - PAD.bottom
  const maxY = Math.max(1, ...data.map((d) => Math.max(d.found, d.applied)))
  const n = data.length

  const x = (i: number) => PAD.left + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW)
  const y = (v: number) => PAD.top + innerH - (v / maxY) * innerH

  const linePath = (key: Series['key']) =>
    data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(d[key]).toFixed(1)}`).join(' ')
  const areaPath = (key: Series['key']) => {
    const line = data.map((d, i) => `${i === 0 ? 'M' : 'L'} ${x(i).toFixed(1)} ${y(d[key]).toFixed(1)}`).join(' ')
    return `${line} L ${x(n - 1).toFixed(1)} ${(PAD.top + innerH).toFixed(1)} L ${x(0).toFixed(1)} ${(PAD.top + innerH).toFixed(1)} Z`
  }

  const gridLines = 4
  const ticks = Math.min(n, 6)

  return (
    <div>
      <div className="mb-2 flex items-center gap-4">
        {SERIES.map((s) => (
          <span key={s.key} className="inline-flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
            <span className="h-2 w-2 rounded-full" style={{ background: s.stroke }} />
            {s.label}
          </span>
        ))}
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="h-52 w-full" role="img" aria-label="Applications over time">
        <defs>
          {SERIES.map((s) => (
            <linearGradient key={s.key} id={`${gid}-${s.key}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.fillFrom} />
              <stop offset="100%" stopColor={s.fillTo} />
            </linearGradient>
          ))}
        </defs>
        {Array.from({ length: gridLines + 1 }).map((_, i) => {
          const gy = PAD.top + (i / gridLines) * innerH
          const val = Math.round(maxY - (i / gridLines) * maxY)
          return (
            <g key={i}>
              <line x1={PAD.left} y1={gy} x2={W - PAD.right} y2={gy} stroke="currentColor" strokeWidth={1} className="text-neutral-200 dark:text-neutral-800" vectorEffect="non-scaling-stroke" />
              <text x={PAD.left - 6} y={gy + 3} textAnchor="end" className="fill-neutral-400 text-[9px]" style={{ fontSize: 9 }}>
                {val}
              </text>
            </g>
          )
        })}
        {SERIES.map((s) => (
          <path key={`area-${s.key}`} d={areaPath(s.key)} fill={`url(#${gid}-${s.key})`} />
        ))}
        {SERIES.map((s) => (
          <path
            key={`line-${s.key}`}
            d={linePath(s.key)}
            fill="none"
            stroke={s.stroke}
            strokeWidth={2}
            strokeLinejoin="round"
            strokeLinecap="round"
            vectorEffect="non-scaling-stroke"
          />
        ))}
        {Array.from({ length: ticks }).map((_, i) => {
          const idx = Math.round((i / Math.max(1, ticks - 1)) * (n - 1))
          return (
            <text
              key={i}
              x={x(idx)}
              y={H - 8}
              textAnchor="middle"
              className="fill-neutral-400 text-[9px]"
              style={{ fontSize: 9 }}
            >
              {fmtDate(data[idx]?.date).replace(/,.*/, '')}
            </text>
          )
        })}
      </svg>
    </div>
  )
}
