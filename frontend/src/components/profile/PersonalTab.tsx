import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { api } from '../../lib/api'
import { qk } from '../../lib/queryKeys'
import type { ProfileOut, ProfileUpdate } from '../../lib/types'
import { useAutosave } from '../../lib/useAutosave'
import { Card, CardHeader } from '../Card'
import { Input, Select } from '../Field'
import { Toggle } from '../Toggle'
import { ChipInput } from '../ChipInput'
import { SaveIndicator } from '../SaveIndicator'
import { Icon } from '../Icon'

// Local editable shape: text/number fields as strings, booleans, and arrays.
interface FormState {
  first_name: string
  last_name: string
  email: string
  phone: string
  address_line: string
  city: string
  state: string
  postal_code: string
  country: string
  linkedin_url: string
  portfolio_url: string
  github_url: string
  website_url: string
  pronouns: string
  authorized_countries: string[]
  requires_sponsorship: boolean
  work_model_preference: string
  willing_to_relocate: boolean
  salary_expectation_amount: string
  salary_expectation_currency: string
  salary_expectation_period: string
  current_compensation_amount: string
  current_compensation_currency: string
  current_compensation_period: string
  earliest_start_date: string
  notice_period_days: string
  total_years_experience: string
  how_heard_default: string
  over_18: boolean
  consent_background_check: boolean
  consent_drug_screening: boolean
  security_clearance: string
  shift_availability: string[]
  veteran_status: string
  disability_status: string
  gender: string
  race_ethnicity: string
}

const DECLINE = 'decline_to_self_identify'

function seed(p: ProfileOut): FormState {
  const s = (v: string | null | undefined) => v ?? ''
  const n = (v: number | null | undefined) => (v == null ? '' : String(v))
  return {
    first_name: s(p.first_name),
    last_name: s(p.last_name),
    email: s(p.email),
    phone: s(p.phone),
    address_line: s(p.address_line),
    city: s(p.city),
    state: s(p.state),
    postal_code: s(p.postal_code),
    country: s(p.country),
    linkedin_url: s(p.linkedin_url),
    portfolio_url: s(p.portfolio_url),
    github_url: s(p.github_url),
    website_url: s(p.website_url),
    pronouns: s(p.pronouns),
    authorized_countries: p.authorized_countries ?? [],
    requires_sponsorship: Boolean(p.requires_sponsorship),
    work_model_preference: s(p.work_model_preference),
    willing_to_relocate: Boolean(p.willing_to_relocate),
    salary_expectation_amount: n(p.salary_expectation_amount),
    salary_expectation_currency: s(p.salary_expectation_currency) || 'USD',
    salary_expectation_period: s(p.salary_expectation_period) || 'year',
    current_compensation_amount: n(p.current_compensation_amount),
    current_compensation_currency: s(p.current_compensation_currency) || 'USD',
    current_compensation_period: s(p.current_compensation_period) || 'year',
    earliest_start_date: s(p.earliest_start_date),
    notice_period_days: n(p.notice_period_days),
    total_years_experience: n(p.total_years_experience),
    how_heard_default: s(p.how_heard_default),
    over_18: Boolean(p.over_18),
    consent_background_check: Boolean(p.consent_background_check),
    consent_drug_screening: Boolean(p.consent_drug_screening),
    security_clearance: s(p.security_clearance),
    shift_availability: p.shift_availability ?? [],
    veteran_status: s(p.veteran_status) || DECLINE,
    disability_status: s(p.disability_status) || DECLINE,
    gender: s(p.gender) || DECLINE,
    race_ethnicity: s(p.race_ethnicity) || DECLINE,
  }
}

function toUpdate(f: FormState): ProfileUpdate {
  const num = (v: string) => (v.trim() === '' ? null : Number(v))
  const str = (v: string) => (v.trim() === '' ? null : v)
  return {
    first_name: str(f.first_name),
    last_name: str(f.last_name),
    email: str(f.email),
    phone: str(f.phone),
    address_line: str(f.address_line),
    city: str(f.city),
    state: str(f.state),
    postal_code: str(f.postal_code),
    country: str(f.country),
    linkedin_url: str(f.linkedin_url),
    portfolio_url: str(f.portfolio_url),
    github_url: str(f.github_url),
    website_url: str(f.website_url),
    pronouns: str(f.pronouns),
    authorized_countries: f.authorized_countries,
    requires_sponsorship: f.requires_sponsorship,
    work_model_preference: (str(f.work_model_preference) as ProfileUpdate['work_model_preference']) ?? null,
    willing_to_relocate: f.willing_to_relocate,
    salary_expectation_amount: num(f.salary_expectation_amount),
    salary_expectation_currency: str(f.salary_expectation_currency),
    salary_expectation_period: (str(f.salary_expectation_period) as ProfileUpdate['salary_expectation_period']) ?? null,
    current_compensation_amount: num(f.current_compensation_amount),
    current_compensation_currency: str(f.current_compensation_currency),
    current_compensation_period: (str(f.current_compensation_period) as ProfileUpdate['current_compensation_period']) ?? null,
    earliest_start_date: str(f.earliest_start_date),
    notice_period_days: num(f.notice_period_days),
    total_years_experience: num(f.total_years_experience),
    how_heard_default: str(f.how_heard_default),
    over_18: f.over_18,
    consent_background_check: f.consent_background_check,
    consent_drug_screening: f.consent_drug_screening,
    security_clearance: str(f.security_clearance),
    shift_availability: f.shift_availability,
    veteran_status: str(f.veteran_status),
    disability_status: str(f.disability_status),
    gender: str(f.gender),
    race_ethnicity: str(f.race_ethnicity),
  }
}

export function PersonalTab({ profile }: { profile: ProfileOut }) {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<FormState>(() => seed(profile))

  const save = useMutation({
    mutationFn: (f: FormState) => api.put<ProfileOut>('/api/profile', toUpdate(f)),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: qk.profile }),
  })
  const status = useAutosave(form, (f) => save.mutateAsync(f))

  function set<K extends keyof FormState>(key: K, value: FormState[K]) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-end">
        <SaveIndicator status={status} />
      </div>

      <Card>
        <CardHeader title="Basics" icon={<Icon name="user" />} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="First name" value={form.first_name} onChange={(e) => set('first_name', e.target.value)} />
          <Input label="Last name" value={form.last_name} onChange={(e) => set('last_name', e.target.value)} />
          <Input label="Email" type="email" value={form.email} onChange={(e) => set('email', e.target.value)} />
          <Input label="Phone" value={form.phone} onChange={(e) => set('phone', e.target.value)} />
          <Input label="Pronouns" value={form.pronouns} onChange={(e) => set('pronouns', e.target.value)} placeholder="e.g. she/her" />
        </div>
      </Card>

      <Card>
        <CardHeader title="Address" icon={<Icon name="mapPin" />} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="Street address" value={form.address_line} onChange={(e) => set('address_line', e.target.value)} className="sm:col-span-2" />
          <Input label="City" value={form.city} onChange={(e) => set('city', e.target.value)} />
          <Input label="State / region" value={form.state} onChange={(e) => set('state', e.target.value)} />
          <Input label="Postal code" value={form.postal_code} onChange={(e) => set('postal_code', e.target.value)} />
          <Input label="Country" value={form.country} onChange={(e) => set('country', e.target.value)} />
        </div>
      </Card>

      <Card>
        <CardHeader title="Links" icon={<Icon name="link" />} />
        <div className="grid gap-4 sm:grid-cols-2">
          <Input label="LinkedIn" value={form.linkedin_url} onChange={(e) => set('linkedin_url', e.target.value)} placeholder="https://linkedin.com/in/…" />
          <Input label="GitHub" value={form.github_url} onChange={(e) => set('github_url', e.target.value)} placeholder="https://github.com/…" />
          <Input label="Portfolio" value={form.portfolio_url} onChange={(e) => set('portfolio_url', e.target.value)} />
          <Input label="Website" value={form.website_url} onChange={(e) => set('website_url', e.target.value)} />
        </div>
      </Card>

      <Card>
        <CardHeader title="Work authorization" icon={<Icon name="shield" />} />
        <div className="space-y-4">
          <ChipInput
            label="Authorized to work in"
            value={form.authorized_countries}
            onChange={(v) => set('authorized_countries', v)}
            placeholder="Add a country"
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <Select label="Work model preference" value={form.work_model_preference} onChange={(e) => set('work_model_preference', e.target.value)}>
              <option value="">No preference</option>
              <option value="remote">Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-site</option>
              <option value="any">Any</option>
            </Select>
            <Input label="Security clearance" value={form.security_clearance} onChange={(e) => set('security_clearance', e.target.value)} placeholder="None / level" />
          </div>
          <div className="grid gap-3 rounded-xl border border-neutral-200 p-3 dark:border-neutral-800 sm:grid-cols-2">
            <Toggle checked={form.requires_sponsorship} onChange={(v) => set('requires_sponsorship', v)} label="Requires visa sponsorship" />
            <Toggle checked={form.willing_to_relocate} onChange={(v) => set('willing_to_relocate', v)} label="Willing to relocate" />
            <Toggle checked={form.over_18} onChange={(v) => set('over_18', v)} label="Over 18" />
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader title="Compensation & availability" icon={<Icon name="dollar" />} />
        <div className="space-y-4">
          <div>
            <span className="label">Salary expectation</span>
            <div className="grid grid-cols-3 gap-2">
              <Input type="number" inputMode="numeric" value={form.salary_expectation_amount} onChange={(e) => set('salary_expectation_amount', e.target.value)} placeholder="Amount" />
              <Input value={form.salary_expectation_currency} onChange={(e) => set('salary_expectation_currency', e.target.value)} placeholder="USD" />
              <Select value={form.salary_expectation_period} onChange={(e) => set('salary_expectation_period', e.target.value)}>
                <option value="year">per year</option>
                <option value="month">per month</option>
                <option value="hour">per hour</option>
              </Select>
            </div>
          </div>
          <div>
            <span className="label">Current compensation</span>
            <div className="grid grid-cols-3 gap-2">
              <Input type="number" inputMode="numeric" value={form.current_compensation_amount} onChange={(e) => set('current_compensation_amount', e.target.value)} placeholder="Leave blank" />
              <Input value={form.current_compensation_currency} onChange={(e) => set('current_compensation_currency', e.target.value)} placeholder="USD" />
              <Select value={form.current_compensation_period} onChange={(e) => set('current_compensation_period', e.target.value)}>
                <option value="year">per year</option>
                <option value="month">per month</option>
                <option value="hour">per hour</option>
              </Select>
            </div>
            <p className="mt-1.5 flex items-center gap-1.5 text-xs text-neutral-500 dark:text-neutral-400">
              <Icon name="lock" className="h-3.5 w-3.5" />
              Leaving this blank is respected — JobPilot won’t volunteer a current salary you didn’t provide.
            </p>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Input label="Earliest start date" type="date" value={form.earliest_start_date} onChange={(e) => set('earliest_start_date', e.target.value)} />
            <Input label="Notice period (days)" type="number" inputMode="numeric" value={form.notice_period_days} onChange={(e) => set('notice_period_days', e.target.value)} />
            <Input label="Total years experience" type="number" inputMode="decimal" value={form.total_years_experience} onChange={(e) => set('total_years_experience', e.target.value)} />
          </div>
          <ChipInput label="Shift availability" value={form.shift_availability} onChange={(v) => set('shift_availability', v)} placeholder="e.g. Weekends, Nights" />
          <Input label="How did you hear about us (default)" value={form.how_heard_default} onChange={(e) => set('how_heard_default', e.target.value)} />
          <div className="grid gap-3 rounded-xl border border-neutral-200 p-3 dark:border-neutral-800 sm:grid-cols-2">
            <Toggle checked={form.consent_background_check} onChange={(v) => set('consent_background_check', v)} label="Consent to background check" />
            <Toggle checked={form.consent_drug_screening} onChange={(v) => set('consent_drug_screening', v)} label="Consent to drug screening" />
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="Voluntary self-identification"
          subtitle="Optional EEO questions — every field defaults to “decline to self-identify”."
          icon={<Icon name="info" />}
        />
        <div className="mb-3 flex items-start gap-2 rounded-xl bg-neutral-50 p-3 text-xs text-neutral-600 dark:bg-neutral-800/60 dark:text-neutral-300">
          <Icon name="shield" className="mt-0.5 h-4 w-4 shrink-0 text-accent-500" />
          These answers are never required. JobPilot leaves them at “decline to self-identify” unless you choose otherwise.
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Select label="Gender" value={form.gender} onChange={(e) => set('gender', e.target.value)}>
            <option value={DECLINE}>Decline to self-identify</option>
            <option value="male">Male</option>
            <option value="female">Female</option>
            <option value="non_binary">Non-binary</option>
            <option value="other">Other</option>
          </Select>
          <Select label="Race / ethnicity" value={form.race_ethnicity} onChange={(e) => set('race_ethnicity', e.target.value)}>
            <option value={DECLINE}>Decline to self-identify</option>
            <option value="american_indian">American Indian or Alaska Native</option>
            <option value="asian">Asian</option>
            <option value="black">Black or African American</option>
            <option value="hispanic">Hispanic or Latino</option>
            <option value="pacific_islander">Native Hawaiian or Pacific Islander</option>
            <option value="white">White</option>
            <option value="two_or_more">Two or more races</option>
          </Select>
          <Select label="Veteran status" value={form.veteran_status} onChange={(e) => set('veteran_status', e.target.value)}>
            <option value={DECLINE}>Decline to self-identify</option>
            <option value="not_a_veteran">Not a veteran</option>
            <option value="veteran">Veteran</option>
            <option value="protected_veteran">Protected veteran</option>
          </Select>
          <Select label="Disability status" value={form.disability_status} onChange={(e) => set('disability_status', e.target.value)}>
            <option value={DECLINE}>Decline to self-identify</option>
            <option value="yes">Yes, I have a disability</option>
            <option value="no">No, I don’t have a disability</option>
          </Select>
        </div>
      </Card>
    </div>
  )
}
