import { useState } from 'react'

import { ApiError, fetchClassrooms, getToken } from '@/api'
import { AppShell } from '@/components/AppShell'
import { LoginPanel } from '@/components/LoginPanel'
import { useResource } from '@/hooks/useResource'

export default function App() {
  const [session, setSession] = useState(0)
  const rooms = useResource('classrooms:' + session, fetchClassrooms)

  const signedOut =
    getToken() === null ||
    (rooms.error instanceof ApiError && rooms.error.isUnauthorized)

  if (signedOut) {
    return <LoginPanel onSignedIn={() => setSession((n) => n + 1)} />
  }

  if (rooms.data && rooms.data.length > 0) {
    return <AppShell classrooms={rooms.data} />
  }

  return (
    <main
      id="main"
      className="grid justify-items-start gap-3 px-[var(--gutter)] py-8"
    >
      {rooms.error ? (
        <>
          <h2 className="text-display">Spisak učionica nije dostupan</h2>
          <p className="max-w-[40ch] text-ink-2">{rooms.error.message}</p>
          <button
            type="button"
            onClick={rooms.refresh}
            className="min-h-11 rounded-full bg-ink px-4 py-3 font-[520] text-paper"
          >
            Pokušaj ponovo
          </button>
        </>
      ) : rooms.loading ? (
        <div aria-busy="true" className="grid w-full gap-3">
          <span className="sr-only">Učitavanje učionica</span>
          <div className="skeleton h-21 rounded-field" />
          <div className="skeleton h-21 rounded-field" />
          <div className="skeleton h-21 rounded-field" />
        </div>
      ) : (
        <>
          <h2 className="text-display">Nema učionica</h2>
          <p className="max-w-[40ch] text-ink-2">
            Nijedna učionica još nije registrovana u sistemu.
          </p>
        </>
      )}
    </main>
  )
}
