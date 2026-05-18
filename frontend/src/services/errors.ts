import axios from 'axios'

export class ApiError extends Error {
  readonly status: number
  readonly code?: string
  readonly payload: unknown

  constructor(
    message: string,
    options: {
      status: number
      code?: string
      payload?: unknown
      cause?: unknown
    },
  ) {
    super(message, options.cause instanceof Error ? { cause: options.cause } : undefined)
    this.name = 'ApiError'
    this.status = options.status
    this.code = options.code
    this.payload = options.payload
  }
}

function pickMessage(data: unknown, fallback: string): string {
  if (data && typeof data === 'object' && 'message' in data) {
    const m = (data as { message: unknown }).message
    if (typeof m === 'string' && m.trim()) return m
  }
  // 常見 API 欄位：{ msg: "...", status: ... }
  if (data && typeof data === 'object' && 'msg' in data) {
    const m = (data as { msg: unknown }).msg
    if (typeof m === 'string' && m.trim()) return m
  }
  if (data && typeof data === 'object' && 'error' in data) {
    const e = (data as { error: unknown }).error
    if (typeof e === 'string' && e.trim()) return e
  }
  return fallback
}

/** 將 Axios / 網路錯誤轉成 ApiError，供攔截器與 store 使用 */
export function normalizeAxiosError(error: unknown): ApiError {
  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? 0
    const data = error.response?.data
    const message = pickMessage(data, error.message || 'Request failed')
    const code =
      data &&
      typeof data === 'object' &&
      'code' in data &&
      typeof (data as { code: unknown }).code === 'string'
        ? (data as { code: string }).code
        : undefined
    return new ApiError(message, { status, code, payload: data, cause: error })
  }
  if (error instanceof ApiError) return error
  if (error instanceof Error) return new ApiError(error.message, { status: 0, cause: error })
  return new ApiError('Unknown error', { status: 0, payload: error })
}
