export type Severity = 'ok' | 'watch' | 'alarm' | 'unknown'

export interface Band {
  max: number
  severity: Severity
  label: string
}

const RANK: Record<Severity, number> = {
  unknown: 0,
  ok: 1,
  watch: 2,
  alarm: 3,
}

export function classify(bands: readonly Band[], value: number | null): Band | null {
  if (value === null || !Number.isFinite(value)) return null
  return bands.find((band) => value < band.max) ?? bands[bands.length - 1]
}

export function worstOf(a: Severity, b: Severity): Severity {
  return RANK[a] >= RANK[b] ? a : b
}

export function rankOf(severity: Severity): number {
  return RANK[severity]
}
