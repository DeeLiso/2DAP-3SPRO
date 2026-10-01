export class ApiError extends Error {
  status: number
  payload: Record<string, unknown> | null

  constructor(message: string, status: number, payload: Record<string, unknown> | null = null) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.payload = payload
  }
}

function readCookie(name: string) {
  const prefix = `${name}=`
  const value = document.cookie.split(';').map((part) => part.trim()).find((part) => part.startsWith(prefix))
  return value ? decodeURIComponent(value.slice(prefix.length)) : ''
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null
}

export interface ApiRequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
}

export class ApiClient {
  private readonly csrfToken: string

  constructor(csrfToken: string) {
    this.csrfToken = csrfToken
  }

  async request<T>(path: string, options: ApiRequestOptions = {}): Promise<T> {
    const headers = new Headers({ Accept: 'application/json' })
    headers.set('X-CSRFToken', this.csrfToken || readCookie('csrftoken'))
    if (options.body !== undefined) {
      headers.set('Content-Type', 'application/json')
    }

    let response: Response
    try {
      response = await fetch(path, {
        method: options.method ?? 'GET',
        credentials: 'same-origin',
        headers,
        body: options.body === undefined ? undefined : JSON.stringify(options.body)
      })
    } catch {
      throw new ApiError('Network connection failed', 0)
    }

    const raw = await response.text()
    let payload: unknown = null
    if (raw) {
      try {
        payload = JSON.parse(raw)
      } catch {
        payload = null
      }
    }

    const record = isRecord(payload) ? payload : null
    if (!response.ok || (record && record.ok === false)) {
      const message = typeof record?.error === 'string' ? record.error : response.status === 403 ? 'Access denied' : 'The server could not complete this request'
      throw new ApiError(message, response.status, record)
    }
    if (payload === null) {
      throw new ApiError('The server returned an invalid response', response.status)
    }
    return payload as T
  }

  get<T>(path: string) {
    return this.request<T>(path)
  }

  post<T>(path: string, body: unknown) {
    return this.request<T>(path, { method: 'POST', body })
  }
}
