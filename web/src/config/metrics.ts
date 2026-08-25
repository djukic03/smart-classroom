import type { Band, Severity } from '@/lib/status'
import type { MetricEnum, MetricKey } from '@/api/types'

/**
 * Display bands and the words that go with them.
 *
 * These are presentation defaults drawn from published guidance, not the
 * system's alarm thresholds. Those live per device in `sensor_configs` and are
 * what actually fires a push notification. The dashboard overlays the
 * backend's own open anomalies on top of these bands (see `useDashboard`), so
 * a row can never read "prijatno" for a metric the server is already paging
 * someone about.
 *
 * Sources: CO2, EN 16798-1 IDA classes; temperature and humidity, EN ISO 7730
 * comfort range for sedentary classroom work; illuminance, EN 12464-1 section
 * 6.36 (300 lx maintained for classrooms, 500 lx for evening teaching); sound,
 * WHO Guidelines for Community Noise, classroom background.
 *
 * Copy stays Serbian Latin: these strings are rendered to the user.
 */
export interface MetricDef {
  key: MetricKey
  apiEnum: MetricEnum
  name: string
  unit: string
  decimals: number
  bands: readonly Band[]
  /**
   * Floor for the sparkline's y-window. The line is scaled to its own data so
   * the shape is legible, but never tighter than this, otherwise a 0,2 °C
   * wobble would draw itself as a dramatic climb.
   */
  minSpan: number
  /** Shown only when the metric needs attention: what to do about it. */
  advice: Partial<Record<Severity, string>>
}

export const METRICS: readonly MetricDef[] = [
  {
    key: 'co2',
    apiEnum: 'CO2',
    name: 'CO₂',
    unit: 'ppm',
    decimals: 0,
    minSpan: 250,
    bands: [
      { max: 1000, severity: 'ok', label: 'Svež vazduh' },
      { max: 2900, severity: 'watch', label: 'Ustajao vazduh' },
      { max: Infinity, severity: 'alarm', label: 'Zagušljivo' },
    ],
    advice: {
      watch: 'Otvorite prozor pred kraj časa.',
      alarm: 'Provetrite učionicu: otvorite prozore na pet minuta.',
    },
  },
  {
    key: 'temperature',
    apiEnum: 'TEMPERATURE',
    name: 'Temperatura',
    unit: '°C',
    decimals: 1,
    minSpan: 2.5,
    bands: [
      { max: 17, severity: 'alarm', label: 'Prehladno' },
      { max: 19, severity: 'watch', label: 'Hladno' },
      { max: 25.5, severity: 'ok', label: 'Prijatno' },
      { max: 27, severity: 'watch', label: 'Toplo' },
      { max: Infinity, severity: 'alarm', label: 'Prevruće' },
    ],
    advice: {
      watch: 'Proverite grejanje i zavese.',
      alarm: 'Podesite grejanje. Odstupanje je van opsega za nastavu.',
    },
  },
  {
    key: 'humidity',
    apiEnum: 'HUMIDITY',
    name: 'Vlažnost',
    unit: '%',
    decimals: 0,
    minSpan: 8,
    bands: [
      { max: 25, severity: 'alarm', label: 'Presuvo' },
      { max: 35, severity: 'watch', label: 'Suvo' },
      { max: 60, severity: 'ok', label: 'Prijatno' },
      { max: 70, severity: 'watch', label: 'Vlažno' },
      { max: Infinity, severity: 'alarm', label: 'Prevlažno' },
    ],
    advice: {
      watch: 'Suv vazduh iritira grlo i oči.',
      alarm: 'Dugotrajna vlažnost van opsega oštećuje opremu i zidove.',
    },
  },
  {
    key: 'illuminance',
    apiEnum: 'ILLUMINANCE',
    name: 'Osvetljenje',
    unit: 'lx',
    decimals: 0,
    minSpan: 250,
    bands: [
      { max: 150, severity: 'alarm', label: 'Premračno' },
      { max: 300, severity: 'watch', label: 'Nedovoljno svetla' },
      { max: 750, severity: 'ok', label: 'Dovoljno svetla' },
      { max: 1200, severity: 'watch', label: 'Presvetlo' },
      { max: Infinity, severity: 'alarm', label: 'Blešti' },
    ],
    advice: {
      watch: 'Ispod 300 lx čitanje i pisanje zamaraju oči.',
      alarm: 'Upalite svetlo ili navucite zavese.',
    },
  },
  {
    key: 'sound',
    apiEnum: 'SOUND',
    name: 'Buka',
    unit: 'dB',
    decimals: 0,
    minSpan: 12,
    bands: [
      { max: 50, severity: 'ok', label: 'Tiho' },
      { max: 65, severity: 'watch', label: 'Žagor' },
      { max: Infinity, severity: 'alarm', label: 'Prebučno' },
    ],
    advice: {
      watch: 'Predavača je teže pratiti iz zadnjih klupa.',
      alarm: 'Iznad 65 dB govor se gubi u pozadinskoj buci.',
    },
  },
  {
    key: 'occupancy',
    apiEnum: 'OCCUPANCY',
    name: 'Popunjenost',
    unit: '',
    decimals: 0,
    minSpan: 6,
    bands: [{ max: Infinity, severity: 'ok', label: 'U upotrebi' }],
    advice: {},
  },
]

export const METRIC_BY_KEY: Record<MetricKey, MetricDef> = Object.fromEntries(
  METRICS.map((m) => [m.key, m]),
) as Record<MetricKey, MetricDef>


export function occupancyBands(capacity: number): readonly Band[] {
  return [
    { max: 1, severity: 'ok', label: 'Prazno' },
    { max: Math.ceil(capacity * 0.9), severity: 'ok', label: 'U upotrebi' },
    { max: capacity + 1, severity: 'watch', label: 'Skoro puno' },
    { max: Infinity, severity: 'alarm', label: 'Prekoračen kapacitet' },
  ]
}
