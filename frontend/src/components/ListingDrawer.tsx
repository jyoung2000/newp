import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../lib/api'
import { qk } from '../lib/queryKeys'
import type { ListingDetail } from '../lib/types'
import { Drawer } from './Drawer'
import { Button } from './Button'
import { Badge } from './Badge'
import { MatchMeter } from './MatchMeter'
import { Icon } from './Icon'
import { SkeletonText } from './Skeleton'
import { RunConfigModal } from './RunConfigModal'
import { fmtDate, fmtSalary, titleCase } from '../lib/format'

export function ListingDrawer({ listingId, onClose }: { listingId: number | null; onClose: () => void }) {
  const [showFullDesc, setShowFullDesc] = useState(false)
  const [applyOpen, setApplyOpen] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: qk.listing(listingId ?? 0),
    queryFn: () => api.get<ListingDetail>(`/api/listings/${listingId}`),
    enabled: listingId != null,
  })

  return (
    <>
      <Drawer
        open={listingId != null}
        onClose={onClose}
        title={data?.title ?? 'Listing'}
        subtitle={data ? `${data.company}${data.location ? ` · ${data.location}` : ''}` : undefined}
        footer={
          data ? (
            <div className="flex items-center justify-between gap-2">
              {data.apply_url ? (
                <a href={data.apply_url} target="_blank" rel="noreferrer">
                  <Button variant="ghost" iconRight="external">
                    Employer page
                  </Button>
                </a>
              ) : (
                <span />
              )}
              {data.applied ? (
                <Badge tone="success" dot>
                  Already applied
                </Badge>
              ) : (
                <Button variant="primary" icon="sparkles" onClick={() => setApplyOpen(true)}>
                  Apply with JobPilot
                </Button>
              )}
            </div>
          ) : null
        }
      >
        {isLoading || !data ? (
          <SkeletonText lines={6} />
        ) : (
          <div className="space-y-6">
            <div className="flex flex-wrap items-center gap-2">
              <Badge tone="neutral">{titleCase(data.source)}</Badge>
              {data.remote ? <Badge tone="accent">Remote</Badge> : null}
              {data.education_level ? <Badge tone="neutral">{titleCase(data.education_level)}</Badge> : null}
              <Badge tone="neutral">Posted {fmtDate(data.posted_at)}</Badge>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
                <div className="text-xs text-neutral-500">Salary</div>
                <div className="mt-0.5 font-medium text-neutral-900 dark:text-neutral-100">
                  {fmtSalary(data.salary_min, data.salary_max, data.salary_currency, data.salary_period, data.salary_raw)}
                </div>
              </div>
              <div className="rounded-xl border border-neutral-200 p-3 dark:border-neutral-800">
                <div className="text-xs text-neutral-500">Match score</div>
                <div className="mt-1.5">
                  <MatchMeter score={data.match_score} width="w-full" />
                </div>
              </div>
            </div>

            {data.summary ? (
              <section>
                <h4 className="mb-1.5 text-sm font-semibold text-neutral-900 dark:text-neutral-100">Summary</h4>
                <p className="text-sm leading-relaxed text-neutral-600 dark:text-neutral-300">{data.summary}</p>
              </section>
            ) : null}

            {data.match_rationale ? (
              <section className="rounded-xl bg-accent-50 p-3 dark:bg-accent-500/10">
                <h4 className="mb-1 flex items-center gap-1.5 text-sm font-semibold text-accent-800 dark:text-accent-300">
                  <Icon name="sparkles" className="h-4 w-4" />
                  Why it matched
                </h4>
                <p className="text-sm leading-relaxed text-accent-900/80 dark:text-accent-200/90">{data.match_rationale}</p>
              </section>
            ) : null}

            {data.requirements.length > 0 ? (
              <section>
                <h4 className="mb-2 text-sm font-semibold text-neutral-900 dark:text-neutral-100">Extracted requirements</h4>
                <ul className="space-y-1.5">
                  {data.requirements.map((r, i) => (
                    <li key={i} className="flex items-start gap-2 text-sm text-neutral-600 dark:text-neutral-300">
                      <Icon name="check" className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" />
                      {r}
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}

            {data.description ? (
              <section>
                <button
                  onClick={() => setShowFullDesc((s) => !s)}
                  className="flex items-center gap-1.5 text-sm font-semibold text-neutral-900 dark:text-neutral-100"
                >
                  <Icon name={showFullDesc ? 'chevronDown' : 'chevronRight'} className="h-4 w-4" />
                  Full description
                </button>
                {showFullDesc ? (
                  <p className="mt-2 whitespace-pre-wrap text-sm leading-relaxed text-neutral-600 dark:text-neutral-300">
                    {data.description}
                  </p>
                ) : null}
              </section>
            ) : null}
          </div>
        )}
      </Drawer>

      {listingId != null ? (
        <RunConfigModal
          open={applyOpen}
          onClose={() => setApplyOpen(false)}
          listingIds={[listingId]}
          initialMode="review"
          title="Apply to this listing"
        />
      ) : null}
    </>
  )
}
