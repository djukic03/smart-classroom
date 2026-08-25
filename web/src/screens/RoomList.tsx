import { CaretRight } from '@phosphor-icons/react/CaretRight'

import type { RoomOverview } from '@/hooks/useRooms'

interface Props {
  overview: RoomOverview[]
  total: number
  loading: boolean
  onSelect: (id: number) => void
}

const ROW =
  'grid min-h-21 w-full grid-cols-[1fr_auto] items-center gap-x-4 border-b border-line-soft px-[var(--gutter)] py-4 text-left'

  
export function RoomList({ overview, total, loading, onSelect }: Props) {
  return (
    <div>
      <h1 className="px-[var(--gutter)] pt-2 text-display">Učionice</h1>

      <div className="mt-6 border-t border-line-soft">
        {loading && overview.length === 0
          ? Array.from({ length: total || 3 }, (_, i) => (
              <div key={i} className={ROW} aria-hidden="true">
                <span className="skeleton col-start-1 row-start-1 h-10 rounded-field" />
              </div>
            ))
          : overview.map((room) => (
              <button
                key={room.classroom.id}
                type="button"
                data-status={room.severity}
                onClick={() => onSelect(room.classroom.id)}
                className={`${ROW} transition-colors duration-150 ease-soft active:bg-paper-2`}
              >
                <span className="col-start-1 row-start-1 text-title font-medium text-ink">
                  {room.classroom.name}
                </span>
                <span className="col-start-1 row-start-2 text-small text-[var(--status)]">
                  {room.label}
                </span>
                {room.classroom.description && (
                  <span className="col-start-1 row-start-3 text-xs text-ink-3">
                    {room.classroom.description}
                  </span>
                )}

                <span className="col-start-2 row-span-3 row-start-1 grid place-items-center self-center text-ink-3">
                  <CaretRight size={16} aria-hidden="true" />
                </span>
              </button>
            ))}
      </div>
    </div>
  )
}
