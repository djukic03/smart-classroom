import { AlertRow } from '@/components/AlertRow'
import { MetricRow } from '@/components/MetricRow'
import type { Dashboard } from '@/hooks/useDashboard'
import { formatTime } from '@/lib/format'

export function RoomDashboard({ dashboard }: { dashboard: Dashboard }) {
  const alerts = dashboard.metrics.filter((m) => m.severity === 'alarm')
  const listed = dashboard.metrics.filter((m) => m.severity !== 'alarm')

  return (
    <div>
      {alerts.length > 0 && (
        <div className="grid gap-2 px-[var(--gutter)] pt-4 tablet:px-0">
          {alerts.map((m) => (
            <AlertRow key={m.def.key} metric={m} />
          ))}
        </div>
      )}

      <div className="list-rules mt-4 border-y border-line-soft tablet:mt-5 tablet:grid tablet:grid-cols-2 tablet:overflow-hidden tablet:rounded-list tablet:border">
        {listed.map((m) => (
          <MetricRow key={m.def.key} metric={m} />
        ))}
      </div>

      <p className="px-[var(--gutter)] py-5 text-small text-ink-3">
        {dashboard.measuredAt
          ? `Poslednjih deset sati. Poslednje merenje u ${formatTime(dashboard.measuredAt)}, uređaj ${dashboard.devices[0] ?? 'nepoznat'}.`
          : 'Merenja nisu dostupna.'}
      </p>
    </div>
  )
}
