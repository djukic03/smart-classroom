/**
 * Wire types. These mirror the FastAPI response models one-for-one
 * (app/schemas/measurement.py, classroom.py, anomaly.py) - keep them in step
 * with the backend rather than reshaping data here.
 */

export const METRIC_KEYS = [
  'co2',
  'temperature',
  'humidity',
  'illuminance',
  'sound',
  'occupancy',
] as const

export type MetricKey = (typeof METRIC_KEYS)[number]

/** app/models/metric_enum.py - the enum the API speaks. */
export type MetricEnum =
  | 'CO2'
  | 'TEMPERATURE'
  | 'HUMIDITY'
  | 'ILLUMINANCE'
  | 'SOUND'
  | 'OCCUPANCY'

export type AnomalyDirection = 'ABOVE' | 'BELOW'

export interface Classroom {
  id: number
  name: string
  description: string | null
}

export interface Measurement {
  device_id: number
  device_username: string
  timestamp: string
  co2: number | null
  temperature: number | null
  humidity: number | null
  illuminance: number | null
  sound: number | null
  occupancy: number | null
}

export interface MetricStats {
  avg: number | null
  min: number | null
  max: number | null
}

export type MetricStatsByKey = Record<MetricKey, MetricStats>

export interface MeasurementBucket extends MetricStatsByKey {
  timestamp: string
  samples: number
}

export interface MeasurementHistory {
  classroom_id: number
  start: string
  end: string
  interval: string
  source: string
  buckets: MeasurementBucket[]
}

export interface Anomaly {
  id: number
  device_id: number
  device_username: string
  metric_type: MetricEnum
  direction: AnomalyDirection
  threshold_value: number
  triggering_value: number
  peak_value: number
  started_at: string
  resolved_at: string | null
  notified_at: string | null
}

export const METRIC_BY_ENUM: Record<MetricEnum, MetricKey> = {
  CO2: 'co2',
  TEMPERATURE: 'temperature',
  HUMIDITY: 'humidity',
  ILLUMINANCE: 'illuminance',
  SOUND: 'sound',
  OCCUPANCY: 'occupancy',
}
