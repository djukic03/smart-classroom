import { useEffect, useState } from 'react'
import { ArrowLeft } from '@phosphor-icons/react/ArrowLeft'
import { ArrowsClockwise } from '@phosphor-icons/react/ArrowsClockwise'
import { Moon } from '@phosphor-icons/react/Moon'
import { Sun } from '@phosphor-icons/react/Sun'

import type { Classroom } from '@/api/types'
import { useDashboard } from '@/hooks/useDashboard'
import { useRooms } from '@/hooks/useRooms'
import { useTheme } from '@/hooks/useTheme'
import { RoomDashboard } from '@/screens/RoomDashboard'
import { RoomList } from '@/screens/RoomList'
import { BrandMark } from './BrandMark'

type Theme = ReturnType<typeof useTheme>

const WIDTH = 'w-full max-w-[46rem] tablet:max-w-[68rem] mx-auto'
const HEADER = `flex items-center gap-2 px-[var(--gutter)] pt-4 pb-1 ${WIDTH}`
const ICON_BUTTON =
  'grid size-11 place-items-center rounded-full text-ink-2 transition-colors duration-150 ease-soft active:bg-paper-2 active:text-ink'
const SCREEN = 'w-full flex-1 pb-[calc(var(--safe-bottom)+2.5rem)]'

function Tools({
  theme,
  refreshing,
  onRefresh,
}: {
  theme: Theme
  refreshing: boolean
  onRefresh: () => void
}) {
  return (
    <div className="ml-auto flex items-center gap-1">
      <button
        type="button"
        className={ICON_BUTTON}
        onClick={theme.toggle}
        aria-label={theme.dark ? 'Pređi na svetlu temu' : 'Pređi na tamnu temu'}
      >
        {theme.dark ? <Sun size={20} /> : <Moon size={20} />}
      </button>
      <button
        type="button"
        className={ICON_BUTTON}
        onClick={onRefresh}
        aria-label="Osveži merenja"
      >
        <div className={refreshing ? 'animate-spin' : undefined}>
          <ArrowsClockwise size={20} />
        </div>
      </button>
    </div>
  )
}

function BuildingScreen({
  classrooms,
  onSelect,
  theme,
}: {
  classrooms: Classroom[]
  onSelect: (id: number) => void
  theme: Theme
}) {
  const { overview, loading, refreshing, refresh } = useRooms(classrooms)

  return (
    <>
      <header className={HEADER}>
        <span className="inline-flex items-center gap-2 text-ink">
          <BrandMark size={20} />
          <span className="text-body font-[520] tracking-[-0.008em]">
            Pametna učionica
          </span>
        </span>
        <Tools theme={theme} refreshing={refreshing} onRefresh={refresh} />
      </header>

      <main id="main" className={SCREEN}>
        <div className={WIDTH}>
          <RoomList
            overview={overview}
            total={classrooms.length}
            loading={loading}
            onSelect={onSelect}
          />
        </div>
      </main>
    </>
  )
}

function RoomScreen({
  classroom,
  onBack,
  theme,
}: {
  classroom: Classroom
  onBack: () => void
  theme: Theme
}) {
  const { dashboard, loading, error, refreshing, refresh } = useDashboard(
    classroom.id,
  )

  return (
    <>
      <header className={HEADER}>
        <button
          type="button"
          onClick={onBack}
          aria-label="Nazad na spisak učionica"
          className="-ml-2.5 grid size-11 place-items-center rounded-full text-ink transition-colors duration-150 ease-soft active:bg-paper-2"
        >
          <ArrowLeft size={20} />
        </button>
        <span className="text-title font-[560] tracking-[-0.012em] text-ink">
          {classroom.name}
        </span>
        <Tools theme={theme} refreshing={refreshing} onRefresh={refresh} />
      </header>

      <main id="main" className={`${SCREEN} animate-enter`}>
        <div className={WIDTH}>
          {error && !dashboard ? (
            <div className="grid justify-items-start gap-3 px-[var(--gutter)] py-8">
              <h2 className="text-display">Merenja nisu stigla</h2>
              <p className="max-w-[40ch] text-ink-2">{error.message}</p>
              <button
                type="button"
                onClick={refresh}
                className="min-h-11 rounded-full bg-ink px-4 py-3 font-[520] text-paper"
              >
                Pokušaj ponovo
              </button>
            </div>
          ) : loading && !dashboard ? (
            <div aria-busy="true" className="grid gap-3 px-[var(--gutter)] py-8">
              <span className="sr-only">Učitavanje merenja</span>
              <div className="skeleton h-44 rounded-field" />
              <div className="skeleton h-24 rounded-field" />
              <div className="skeleton h-24 rounded-field" />
            </div>
          ) : dashboard ? (
            <RoomDashboard dashboard={dashboard} />
          ) : null}
        </div>
      </main>
    </>
  )
}

export function AppShell({ classrooms }: { classrooms: Classroom[] }) {
  const theme = useTheme()
  const [selectedId, setSelectedId] = useState<number | null>(null)

  const classroom = classrooms.find((c) => c.id === selectedId) ?? null

  useEffect(() => {
    if (selectedId === null) return

    window.history.pushState({ room: selectedId }, '')
    const onPop = () => setSelectedId(null)
    window.addEventListener('popstate', onPop)
    return () => window.removeEventListener('popstate', onPop)
  }, [selectedId])

  function goBack() {
    const state = window.history.state as { room?: number } | null
    if (state?.room === classroom?.id) window.history.back()
    else setSelectedId(null)
  }

  return (
    <div className="flex min-h-[100dvh] flex-col">
      <a
        href="#main"
        className="absolute top-2 left-2 z-100 min-h-11 -translate-y-[250%] rounded-field bg-ink px-4 py-3 font-[560] text-paper focus-visible:translate-y-0"
      >
        Pređite na sadržaj
      </a>

      {classroom ? (
        <RoomScreen classroom={classroom} onBack={goBack} theme={theme} />
      ) : (
        <BuildingScreen
          classrooms={classrooms}
          onSelect={setSelectedId}
          theme={theme}
        />
      )}
    </div>
  )
}
