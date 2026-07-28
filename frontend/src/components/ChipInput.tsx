import { useState } from 'react'
import { cx } from '../lib/format'
import { Icon } from './Icon'

interface ChipInputProps {
  value: string[]
  onChange: (v: string[]) => void
  placeholder?: string
  label?: string
  hint?: string
  id?: string
}

// A tag/chip input: type + Enter (or comma) to add, backspace to remove last.
export function ChipInput({ value, onChange, placeholder, label, hint, id }: ChipInputProps) {
  const [draft, setDraft] = useState('')

  const add = (raw: string) => {
    const parts = raw
      .split(',')
      .map((s) => s.trim())
      .filter(Boolean)
    if (parts.length === 0) return
    const next = [...value]
    for (const p of parts) if (!next.includes(p)) next.push(p)
    onChange(next)
    setDraft('')
  }

  const removeAt = (i: number) => onChange(value.filter((_, idx) => idx !== i))

  return (
    <div>
      {label ? <span className="label">{label}</span> : null}
      <div
        className={cx(
          'flex flex-wrap items-center gap-1.5 rounded-xl border border-neutral-300 bg-white px-2 py-1.5 shadow-sm transition',
          'focus-within:border-accent-500 focus-within:ring-2 focus-within:ring-accent-500/30',
          'dark:border-neutral-700 dark:bg-neutral-900',
        )}
      >
        {value.map((chip, i) => (
          <span
            key={`${chip}-${i}`}
            className="inline-flex items-center gap-1 rounded-lg bg-accent-50 py-0.5 pl-2 pr-1 text-xs font-medium text-accent-700 ring-1 ring-inset ring-accent-200 dark:bg-accent-500/15 dark:text-accent-300 dark:ring-accent-500/30"
          >
            {chip}
            <button
              type="button"
              onClick={() => removeAt(i)}
              className="rounded p-0.5 hover:bg-accent-100 dark:hover:bg-accent-500/25"
              aria-label={`Remove ${chip}`}
            >
              <Icon name="close" className="h-3 w-3" strokeWidth={2.5} />
            </button>
          </span>
        ))}
        <input
          id={id}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' || e.key === ',') {
              e.preventDefault()
              add(draft)
            } else if (e.key === 'Backspace' && draft === '' && value.length > 0) {
              removeAt(value.length - 1)
            }
          }}
          onBlur={() => draft && add(draft)}
          placeholder={value.length === 0 ? placeholder : ''}
          className="min-w-[8ch] flex-1 border-0 bg-transparent px-1 py-1 text-sm text-neutral-900 outline-none placeholder:text-neutral-400 dark:text-neutral-100"
        />
      </div>
      {hint ? <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{hint}</p> : null}
    </div>
  )
}
