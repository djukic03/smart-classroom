import type { MetricView } from '@/hooks/useDashboard'
import { formatNumber, peopleNoun } from '@/lib/format'
import { MetricIcon } from './MetricIcon'
import { Sparkline } from './Sparkline'

export function MetricRow({ metric }: { metric: MetricView }) {
  const { def, value, severity, label, series, sparkRange, bands } = metric

  const unit =
    def.key === 'occupancy'
      ? value !== null
        ? peopleNoun(Math.round(value))
        : ''
      : def.unit

  return (
    <div
      data-status={severity}
      className="grid min-h-24 w-full grid-cols-[auto_1fr_auto] items-center gap-x-4 gap-y-[2px] px-[var(--gutter)] py-4 text-left tablet:min-h-30"
    >
      <span className="col-start-1 row-span-2 row-start-1 grid size-10 place-items-center text-ink-3">
        <MetricIcon metric={def.key} size={24} />
      </span>

      <span className="col-start-2 row-start-1 text-lg font-medium tracking-[-0.011em] text-ink">
        {def.name}
      </span>
      <span className="col-start-2 row-start-2 text-sm text-[var(--status)]">
        {label}
      </span>

      <span className="col-start-3 row-start-1 flex items-baseline justify-self-end gap-[0.25em] text-[1.75rem] font-[560] tracking-[-0.028em] text-ink">
        {value !== null ? (
          <>
            <span className="tabular">{formatNumber(value, def.decimals)}</span>
            {unit && (
              <span className="font-data text-small font-medium text-ink-3">
                {unit}
              </span>
            )}
          </>
        ) : (
          <span className="font-data text-small font-normal text-ink-3">
            nema
          </span>
        )}
      </span>

      <span className="col-start-3 row-start-2 justify-self-end">
        <Sparkline series={series} range={sparkRange} bands={bands} />
      </span>
    </div>
  )
}
