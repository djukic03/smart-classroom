import { useMemo } from 'react'

import { classify, type Band, type Severity } from '@/lib/status'

const W = 104
const H = 36
const PAD = 3

const STROKE: Record<Severity, string> = {
  ok: 'var(--color-good)',
  watch: 'var(--color-watch)',
  alarm: 'var(--color-alarm)',
  unknown: 'var(--color-idle)',
}

interface Run {
  d: string
  severity: Severity
}

function downsample(series: (number | null)[], max: number): (number | null)[] {
  if (series.length <= max) return series

  const perBucket = Math.ceil(series.length / max)
  const out: (number | null)[] = []
  for (let i = 0; i < series.length; i += perBucket) {
    const slice = series
      .slice(i, i + perBucket)
      .filter((v): v is number => v !== null)
    out.push(slice.length ? slice.reduce((a, b) => a + b, 0) / slice.length : null)
  }
  return out
}

interface Props {
  series: (number | null)[]
  range: [number, number]
  bands?: readonly Band[]
}

export function Sparkline({ series, range, bands }: Props) {
  const model = useMemo(() => {
    const points = downsample(series, 40)
    const n = points.length
    const [low, high] = range
    const span = high - low || 1

    const x = (i: number) => PAD + (n <= 1 ? 0 : (i / (n - 1)) * (W - PAD * 2))
    const y = (v: number) =>
      H - PAD - ((Math.min(high, Math.max(low, v)) - low) / span) * (H - PAD * 2)

    const runs: Run[] = []
    let segment: string[] = []
    let current: Severity | null = null
    let previous: string | null = null
    let last: [number, number] | null = null

    const close = () => {
      if (segment.length > 1 && current) {
        runs.push({ d: segment.join(' '), severity: current })
      }
      segment = []
    }

    points.forEach((v, i) => {
      if (v === null) {
        close()
        current = null
        previous = null
        return
      }

      const px = x(i)
      const py = y(v)
      const point = px.toFixed(1) + ' ' + py.toFixed(1)
      const severity: Severity = bands
        ? (classify(bands, v)?.severity ?? 'unknown')
        : 'ok'

      if (current !== null && severity !== current) {
        segment.push('L' + point)
        close()
        segment = ['M' + (previous ?? point), 'L' + point]
      } else {
        segment.push((segment.length === 0 ? 'M' : 'L') + point)
      }

      current = severity
      previous = point
      last = [px, py]
    })
    close()

    return { runs, last }
  }, [series, range, bands])

  if (model.runs.length === 0) return null

  return (
    <svg viewBox={`0 0 ${W} ${H}`} width={W} height={H} aria-hidden="true">
      {model.runs.map((run, i) => (
        <path
          key={i}
          d={run.d}
          fill="none"
          stroke={bands ? STROKE[run.severity] : 'currentColor'}
          strokeWidth="1.75"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      ))}
      {model.last && (
        <circle
          cx={model.last[0]}
          cy={model.last[1]}
          r="2.4"
          fill={bands ? 'var(--status)' : 'currentColor'}
        />
      )}
    </svg>
  )
}
