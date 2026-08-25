import { api } from './client'
import type {
  Anomaly,
  Classroom,
  Measurement,
  MeasurementHistory,
} from './types'

/** Ten hours back is what the room list and the sparklines both draw. */
const WINDOW_MS = 10 * 60 * 60 * 1000

export function fetchClassrooms(): Promise<Classroom[]> {
  return api<Classroom[]>('/api/v1/classrooms')
}

export function fetchLatest(classroomId: number): Promise<Measurement[]> {
  return api<Measurement[]>(
    `/api/v1/classrooms/${classroomId}/measurements/latest`,
  )
}

export function fetchHistory(
  classroomId: number,
  points = 120,
): Promise<MeasurementHistory> {
  const from = new Date(Date.now() - WINDOW_MS).toISOString()
  const params = new URLSearchParams({ from, points: String(points) })
  return api<MeasurementHistory>(
    `/api/v1/classrooms/${classroomId}/measurements?${params}`,
  )
}

export function fetchOpenAnomalies(classroomId: number): Promise<Anomaly[]> {
  return api<Anomaly[]>(
    `/api/v1/classrooms/${classroomId}/anomalies?only_open=true&limit=50`,
  )
}

export { ApiError, getToken, login, setToken } from './client'
