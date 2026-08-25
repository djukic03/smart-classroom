import { useMemo } from 'react'

import { fetchHistory, fetchLatest, fetchOpenAnomalies } from '@/api'
import {
  METRIC_BY_ENUM,
  type Anomaly,
  type Measurement,
  type MeasurementHistory,
  type MetricKey,
} from '@/api/types'
import { CAPACITY } from '@/config/classrooms'
import { METRICS, occupancyBands, type MetricDef } from '@/config/metrics'
import { classify, type Band, type Severity } from '@/lib/status'
import { useResource, type Resource } from './useResource'

const POLL_MS = 15_000

export interface MetricView {
  def: MetricDef
  value: number | null
  severity: Severity
  label: string
  series: (number | null)[]
  sparkRange: [number, number]
  bands: readonly Band[]
  advice: string | null
}

export interface Dashboard {
  metrics: MetricView[]
  measuredAt: string | null
  devices: string[]
}

interface Raw {
  measurements: Measurement[]
  history: MeasurementHistory
  anomalies: Anomaly[]
}

function deviceMean(measurements: Measurement[], key: MetricKey): number | null {
  const values = measurements
    .map((m) => m[key])
    .filter((v): v is number => v !== null && Number.isFinite(v))

  if (values.length === 0) return null
  return values.reduce((a, b) => a + b, 0) / values.length
}

function sparkRangeFor(
  series: (number | null)[],
  minSpan: number,
): [number, number] {
  const values = series.filter((v): v is number => v !== null)
  if (values.length === 0) return [0, 1]

  const low = Math.min(...values)
  const high = Math.max(...values)
  const mid = (low + high) / 2
  const span = Math.max(high - low, minSpan) * 1.18

  return [mid - span / 2, mid + span / 2]
}

export function useDashboard(
  classroomId: number,
): Resource<Raw> & { dashboard: Dashboard | null } {
  const resource = useResource<Raw>(
    `dashboard:${classroomId}`,
    async () => {
      const [measurements, history, anomalies] = await Promise.all([
        fetchLatest(classroomId),
        fetchHistory(classroomId),
        fetchOpenAnomalies(classroomId),
      ])
      return { measurements, history, anomalies }
    },
    POLL_MS,
  )

  const { data } = resource

  const dashboard = useMemo<Dashboard | null>(() => {
    if (!data) return null

    const { measurements, history, anomalies } = data
    const capacity = CAPACITY[classroomId] ?? null

    const metrics = METRICS.map<MetricView>((def) => {
      const value = deviceMean(measurements, def.key)
      const series = history.buckets.map((b) => b[def.key].avg)

      const bands =
        def.key === 'occupancy' && capacity !== null
          ? occupancyBands(capacity)
          : def.bands

      const band = classify(bands, value)
      const anomaly =
        anomalies.find((a) => METRIC_BY_ENUM[a.metric_type] === def.key) ?? null

      const severity: Severity = anomaly
        ? 'alarm'
        : band
          ? band.severity
          : 'unknown'

      const label = anomaly
        ? 'Prag prekoračen'
        : (band?.label ?? 'Nema merenja')

      return {
        def,
        value,
        severity,
        label,
        series,
        sparkRange: sparkRangeFor(series, def.minSpan),
        bands,
        advice: def.advice[severity] ?? null,
      }
    })

    return {
      metrics,
      measuredAt: measurements[0]?.timestamp ?? null,
      devices: [...new Set(measurements.map((m) => m.device_username))],
    }
  }, [data, classroomId])

  return { ...resource, dashboard }
}
