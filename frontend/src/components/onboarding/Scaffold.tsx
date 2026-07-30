import { useEffect, useRef } from 'react'
import { Button } from '../Button'
import { Icon } from '../Icon'
import { cx } from '../../lib/format'

/**
 * The frame every onboarding step sits in.
 *
 * The whole flow is one column, one idea per screen, and the chrome never
 * moves: progress in the same place, question in the same place, actions in the
 * same place. That stillness is most of what makes a multi-step form feel
 * calm — the content changes, the room doesn't.
 */

export function Progress({ total, index }: { total: number; index: number }) {
  return (
    <div className="flex items-center gap-1.5" role="progressbar" aria-valuenow={index + 1} aria-valuemin={1} aria-valuemax={total}>
      {Array.from({ length: total }).map((_, i) => (
        <span
          key={i}
          className={cx(
            'h-1 rounded-full transition-all duration-500 ease-[cubic-bezier(0.16,1,0.3,1)]',
            i === index
              ? 'w-7 bg-accent-600 dark:bg-accent-400'
              : i < index
                ? 'w-3 bg-accent-600/40 dark:bg-accent-400/40'
                : 'w-3 bg-neutral-200 dark:bg-neutral-700',
          )}
        />
      ))}
    </div>
  )
}

export interface StepFrameProps {
  stepIndex: number
  stepCount: number
  eyebrow?: string
  title: string
  subtitle?: string
  children: React.ReactNode
  /** Label for the primary action. */
  nextLabel?: string
  onNext: () => void
  nextDisabled?: boolean
  nextLoading?: boolean
  onBack?: () => void
  /** Shown as a quiet third action when a step is optional. */
  onSkip?: () => void
  skipLabel?: string
  /** Suppresses Enter-to-advance where a step owns the key (e.g. chip entry). */
  captureEnter?: boolean
}

export function StepFrame({
  stepIndex,
  stepCount,
  eyebrow,
  title,
  subtitle,
  children,
  nextLabel = 'Continue',
  onNext,
  nextDisabled,
  nextLoading,
  onBack,
  onSkip,
  skipLabel = 'Skip for now',
  captureEnter,
}: StepFrameProps) {
  const bodyRef = useRef<HTMLDivElement>(null)

  // Enter advances, the way a native dialog would — except from a textarea,
  // where Enter means a new line, and except where the step wants the key.
  useEffect(() => {
    if (captureEnter) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Enter' || e.shiftKey || e.metaKey || e.ctrlKey) return
      const el = e.target as HTMLElement | null
      const tag = el?.tagName
      if (tag === 'TEXTAREA' || tag === 'BUTTON' || tag === 'A' || tag === 'SELECT') return
      if (nextDisabled || nextLoading) return
      e.preventDefault()
      onNext()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [captureEnter, nextDisabled, nextLoading, onNext])

  // Each step is a fresh mount (the route keys on the step), so focusing the
  // first field here lands on the right one every time.
  useEffect(() => {
    const first = bodyRef.current?.querySelector<HTMLElement>(
      'input:not([type=hidden]):not([disabled]), textarea, select',
    )
    first?.focus({ preventScroll: true })
  }, [])

  return (
    <div className="mx-auto flex min-h-[100dvh] w-full max-w-2xl flex-col px-5 py-8 sm:px-8 sm:py-12">
      <header className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-600 text-white">
            <Icon name="onboarding" className="h-4 w-4" />
          </div>
          <span className="text-sm font-semibold tracking-tightheading text-neutral-900 dark:text-white">
            JobPilot
          </span>
        </div>
        <Progress total={stepCount} index={stepIndex} />
      </header>

      <main key={stepIndex} className="flex flex-1 flex-col justify-center py-10 animate-slide-up">
        {eyebrow ? (
          <p className="text-xs font-semibold uppercase tracking-widest text-accent-600 dark:text-accent-400">
            {eyebrow}
          </p>
        ) : null}
        <h1 className="mt-2 text-2xl font-semibold tracking-tightheading text-neutral-900 sm:text-3xl dark:text-white">
          {title}
        </h1>
        {subtitle ? (
          <p className="mt-2 max-w-xl text-[15px] leading-relaxed text-neutral-500 dark:text-neutral-400">
            {subtitle}
          </p>
        ) : null}
        <div ref={bodyRef} className="mt-7">
          {children}
        </div>
      </main>

      <footer className="flex items-center gap-3 border-t border-neutral-200/70 pt-5 dark:border-neutral-800/70">
        {onBack ? (
          <Button variant="ghost" icon="chevronDown" className="[&>svg]:rotate-90" onClick={onBack}>
            Back
          </Button>
        ) : null}
        <div className="flex-1" />
        {onSkip ? (
          <button
            onClick={onSkip}
            className="rounded-lg px-3 py-2 text-sm text-neutral-500 transition-colors hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-100"
          >
            {skipLabel}
          </button>
        ) : null}
        <Button
          variant="primary"
          onClick={onNext}
          disabled={nextDisabled}
          loading={nextLoading}
          iconRight="chevronDown"
          className="[&>svg:last-child]:-rotate-90"
        >
          {nextLabel}
        </Button>
      </footer>
    </div>
  )
}

/** A labelled group of related inputs inside a step. */
export function Fieldset({
  legend,
  hint,
  children,
  className,
}: {
  legend?: string
  hint?: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section className={className}>
      {legend ? (
        <h2 className="text-xs font-semibold uppercase tracking-wide text-neutral-500 dark:text-neutral-400">
          {legend}
        </h2>
      ) : null}
      {hint ? <p className="mt-0.5 text-xs text-neutral-400">{hint}</p> : null}
      <div className={legend || hint ? 'mt-3' : undefined}>{children}</div>
    </section>
  )
}

/**
 * A large tappable choice. Used where a question has a handful of answers and
 * a dropdown would be a worse way to ask it.
 */
export function ChoiceCard({
  selected,
  title,
  description,
  onSelect,
}: {
  selected: boolean
  title: string
  description?: string
  onSelect: () => void
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-pressed={selected}
      className={cx(
        'w-full rounded-xl border px-4 py-3 text-left transition-all duration-200',
        selected
          ? 'border-accent-500 bg-accent-50 ring-1 ring-accent-500 dark:border-accent-500/60 dark:bg-accent-500/10'
          : 'border-neutral-200 hover:border-neutral-300 hover:bg-neutral-50 dark:border-neutral-800 dark:hover:border-neutral-700 dark:hover:bg-neutral-800/50',
      )}
    >
      <span className="flex items-center gap-2">
        <span
          className={cx(
            'flex h-4 w-4 shrink-0 items-center justify-center rounded-full border transition-colors',
            selected ? 'border-accent-600 bg-accent-600 text-white' : 'border-neutral-300 dark:border-neutral-600',
          )}
        >
          {selected ? <Icon name="check" className="h-2.5 w-2.5" /> : null}
        </span>
        <span className="text-sm font-medium text-neutral-900 dark:text-neutral-100">{title}</span>
      </span>
      {description ? (
        <span className="mt-1 block pl-6 text-xs text-neutral-500 dark:text-neutral-400">
          {description}
        </span>
      ) : null}
    </button>
  )
}
