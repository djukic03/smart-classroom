import { useState, type FormEvent } from 'react'

import { login } from '@/api'
import { BrandMark } from './BrandMark'

const FIELD = 'grid gap-2 text-small text-ink-2'
const INPUT =
  'min-h-11 rounded-field border border-line bg-surface px-3 py-2.5 text-body text-ink placeholder:text-ink-3'

export function LoginPanel({ onSignedIn }: { onSignedIn: () => void }) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  async function submit(e: FormEvent) {
    e.preventDefault()
    setSending(true)
    setError(null)

    try {
      await login(email, password)
      onSignedIn()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Prijava nije uspela.')
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="grid min-h-[100dvh] place-items-center bg-paper p-[var(--gutter)]">
      <form onSubmit={submit} className="grid w-[min(22rem,100%)] gap-4">
        <span className="text-ink">
          <BrandMark size={32} />
        </span>
        <h1 className="text-display tracking-[-0.02em]">Pametna učionica</h1>
        <p className="-mt-3 text-small text-ink-3">
          Prijavite se da biste videli merenja.
        </p>

        <label className={FIELD}>
          <span>E-pošta</span>
          <input
            type="email"
            name="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={INPUT}
          />
        </label>

        <label className={FIELD}>
          <span>Lozinka</span>
          <input
            type="password"
            name="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={INPUT}
          />
        </label>

        {error && (
          <p role="alert" className="text-small text-alarm">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={sending}
          className="mt-2 min-h-11 rounded-field bg-ink px-4 py-3 font-[540] text-paper disabled:cursor-progress disabled:opacity-50"
        >
          {sending ? 'Prijavljivanje…' : 'Prijavite se'}
        </button>
      </form>
    </div>
  )
}
