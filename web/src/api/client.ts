const BASE = import.meta.env.VITE_API_BASE_URL ?? ''

const TOKEN_KEY = 'pu.token'

/**
 * The backend issues a bearer token from the OAuth2 password flow, so the SPA
 * has to hold it somewhere reachable from JS. That is the usual trade-off for
 * this token style; if the deployment ever moves to a cookie session, this is
 * the only module that needs to change.
 */
export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY)
  } catch {
    return null
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token)
    else localStorage.removeItem(TOKEN_KEY)
  } catch {
    /* private mode - the session simply won't survive a reload */
  }
}

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }

  get isUnauthorized(): boolean {
    return this.status === 401
  }
}

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === 'string') return body.detail
  } catch {
    /* not JSON */
  }
  return `Zahtev nije uspeo (${response.status}).`
}

export async function api<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const token = getToken()
  const response = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      Accept: 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...init.headers,
    },
  })

  if (!response.ok) throw new ApiError(response.status, await errorMessage(response))
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export async function login(
  email: string,
  password: string,
): Promise<string> {
  const form = new URLSearchParams({
    username: email,
    password,
    device_name: 'Pametna učionica (web)',
  })

  const response = await fetch(`${BASE}/api/v1/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: form,
  })

  if (!response.ok) throw new ApiError(response.status, await errorMessage(response))
  const { access_token } = (await response.json()) as { access_token: string }
  setToken(access_token)
  return access_token
}
