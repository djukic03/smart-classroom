import { useMemo } from 'react'

import { fetchLatest } from '@/api'
import type { Classroom, Measurement, MetricKey } from '@/api/types'
import { CAPACITY } from '@/config/classrooms'
import { METRICS, METRIC_BY_KEY, occupancyBands } from '@/config/metrics'
import { classify, rankOf, worstOf, type Severity } from '@/lib/status'
import { useResource, type Resource } from './useResource'

const POLL_MS = 30_000

export interface RoomOverview {
  classroom: Classroom
  severity: Severity
  label: string
}

function mean(measurements: Measurement[], key: MetricKey): number | null {
  const values = measurements
    .map((m) => m[key])
    .filter((v): v is number => v !== null && Number.isFinite(v))
  return values.length ? values.reduce((a, b) => a + b, 0) / values.length : null
}


export function useRooms(
  classrooms: Classroom[],
): Resource<Map<number, Measurement[]>> & { overview: RoomOverview[] } {
  const key = classrooms.map((c) => c.id).join(',')

  const resource = useResource<Map<number, Measurement[]>>(
    'rooms:' + key,
    async () => {
      const pairs = await Promise.all(
        classrooms.map(async (c) => [c.id, await fetchLatest(c.id)] as const),
      )
      return new Map(pairs)
    },
    POLL_MS,
  )

  const { data } = resource

  const overview = useMemo<RoomOverview[]>(() => {
    if (!data) return []

    return classrooms
      .map<RoomOverview>((classroom) => {
        const measurements = data.get(classroom.id) ?? []
        const capacity = CAPACITY[classroom.id] ?? null

        let severity: Severity = measurements.length ? 'ok' : 'unknown'
        let worstLabel: string | null = null
        let worstRank = 1

        for (const def of METRICS) {
          const value = mean(measurements, def.key)
          if (value === null) continue

          const bands =
            def.key === 'occupancy' && capacity !== null
              ? occupancyBands(capacity)
              : def.bands

          const band = classify(bands, value)
          if (!band) continue

          severity = worstOf(severity, band.severity)
          if (rankOf(band.severity) > worstRank) {
            worstRank = rankOf(band.severity)
            worstLabel = band.label
          }
        }

        const co2 = mean(measurements, 'co2')
        const air = classify(METRIC_BY_KEY.co2.bands, co2)

        return {
          classroom,
          severity,
          label: worstLabel ?? air?.label ?? 'Nema merenja',
        }
      })
  }, [data, classrooms])

  return { ...resource, overview }
}
