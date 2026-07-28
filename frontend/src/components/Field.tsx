import { forwardRef, useId } from 'react'
import { cx } from '../lib/format'

interface FieldWrapProps {
  label?: string
  hint?: string
  error?: string
  required?: boolean
  htmlFor?: string
  children: React.ReactNode
  className?: string
}

export function FieldWrap({ label, hint, error, required, htmlFor, children, className }: FieldWrapProps) {
  return (
    <div className={className}>
      {label ? (
        <label htmlFor={htmlFor} className="label">
          {label}
          {required ? <span className="ml-0.5 text-red-500">*</span> : null}
        </label>
      ) : null}
      {children}
      {error ? (
        <p className="mt-1 text-xs text-red-600 dark:text-red-400">{error}</p>
      ) : hint ? (
        <p className="mt-1 text-xs text-neutral-500 dark:text-neutral-400">{hint}</p>
      ) : null}
    </div>
  )
}

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  hint?: string
  error?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, required, className, id, ...rest },
  ref,
) {
  const autoId = useId()
  const fieldId = id || autoId
  return (
    <FieldWrap label={label} hint={hint} error={error} required={required} htmlFor={fieldId}>
      <input
        ref={ref}
        id={fieldId}
        required={required}
        className={cx('input', error && 'border-red-400 focus:border-red-500 focus:ring-red-500/30', className)}
        {...rest}
      />
    </FieldWrap>
  )
})

interface TextareaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  hint?: string
  error?: string
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, required, className, id, ...rest },
  ref,
) {
  const autoId = useId()
  const fieldId = id || autoId
  return (
    <FieldWrap label={label} hint={hint} error={error} required={required} htmlFor={fieldId}>
      <textarea
        ref={ref}
        id={fieldId}
        required={required}
        className={cx('input min-h-[80px] resize-y', className)}
        {...rest}
      />
    </FieldWrap>
  )
})

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  hint?: string
  error?: string
  children: React.ReactNode
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, required, className, id, children, ...rest },
  ref,
) {
  const autoId = useId()
  const fieldId = id || autoId
  return (
    <FieldWrap label={label} hint={hint} error={error} required={required} htmlFor={fieldId}>
      <select ref={ref} id={fieldId} className={cx('input pr-8', className)} {...rest}>
        {children}
      </select>
    </FieldWrap>
  )
})
