import { WarningCircle } from '@phosphor-icons/react/WarningCircle'
import { WarningOctagon } from '@phosphor-icons/react/WarningOctagon'

import type { MetricView } from '@/hooks/useDashboard'
import { formatNumber, peopleNoun } from '@/lib/format'


export function AlertRow({ metric }: { metric: MetricView }) {
  const { def, value, severity, label, advice } = metric
  const Glyph = severity === 'alarm' ? WarningOctagon : WarningCircle

  const unit =
    def.key === 'occupancy'
      ? value !== null
        ? peopleNoun(Math.round(value))
        : ''
      : def.unit

  return (
    <div
      data-status={severity}
      className="grid w-full grid-cols-[auto_1fr_auto] items-start gap-3 rounded-list bg-[var(--status-soft)] p-4 text-left"
    >
      <span className="mt-px text-[var(--status)]">
        <Glyph size={22} weight="fill" aria-hidden="true" />
      </span>

      <span>
        <span className="block text-title font-[560] text-ink">{def.name}</span>
        <span className="mt-0.5 block text-small leading-[1.4] text-ink-2">
          {advice ?? label}
        </span>
      </span>

      <span className="flex items-baseline gap-[0.22em] whitespace-nowrap text-[1.375rem] font-[560] tracking-[-0.025em] text-[var(--status)]">
        {value !== null ? (
          <>
            <span className="tabular">{formatNumber(value, def.decimals)}</span>
            {unit && (
              <span className="font-data text-xs font-medium">{unit}</span>
            )}
          </>
        ) : (
          <span className="font-data text-xs font-medium">nema merenja</span>
        )}
      </span>
    </div>
  )
}
