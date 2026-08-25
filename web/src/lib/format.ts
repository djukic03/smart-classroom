const LOCALE = 'sr-Latn-RS'

const cache = new Map<number, Intl.NumberFormat>()

function formatter(decimals: number): Intl.NumberFormat {
  let f = cache.get(decimals)
  if (!f) {
    f = new Intl.NumberFormat(LOCALE, {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    })
    cache.set(decimals, f)
  }
  return f
}

export function formatNumber(value: number, decimals = 0): string {
  return formatter(decimals).format(value)
}

const clock = new Intl.DateTimeFormat(LOCALE, {
  hour: '2-digit',
  minute: '2-digit',
})

export function formatTime(iso: string | Date): string {
  return clock.format(typeof iso === 'string' ? new Date(iso) : iso)
}

export function peopleNoun(n: number): string {
  const d = n % 10
  const dd = n % 100
  if (d === 1 && dd !== 11) return 'osoba'
  if (d >= 2 && d <= 4 && (dd < 12 || dd > 14)) return 'osobe'
  return 'osoba'
}
