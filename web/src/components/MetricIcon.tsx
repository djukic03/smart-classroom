import { Drop } from '@phosphor-icons/react/Drop'
import { Sun } from '@phosphor-icons/react/Sun'
import { Thermometer } from '@phosphor-icons/react/Thermometer'
import { UsersThree } from '@phosphor-icons/react/UsersThree'
import { Waveform } from '@phosphor-icons/react/Waveform'
import { Wind } from '@phosphor-icons/react/Wind'
import type { Icon } from '@phosphor-icons/react/lib'

import type { MetricKey } from '@/api/types'

const ICONS: Record<MetricKey, Icon> = {
  co2: Wind,
  temperature: Thermometer,
  humidity: Drop,
  illuminance: Sun,
  sound: Waveform,
  occupancy: UsersThree,
}

interface Props {
  metric: MetricKey
  size?: number
  weight?: 'regular' | 'bold' | 'fill'
}

export function MetricIcon({ metric, size = 20, weight = 'regular' }: Props) {
  const Glyph = ICONS[metric]
  return <Glyph size={size} weight={weight} aria-hidden="true" />
}
