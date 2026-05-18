import axios, { type AxiosInstance, type InternalAxiosRequestConfig } from 'axios'

import { ApiError, normalizeAxiosError } from './errors'

export type ApiErrorHandler = (error: ApiError) => void

let globalErrorHandler: ApiErrorHandler | null = null

/** 註冊全域錯誤回呼（例如 toast）；攔截器仍會 reject，store 可自行處理 */
export function setApiErrorHandler(handler: ApiErrorHandler | null) {
  globalErrorHandler = handler
}

function dispatchApiError(error: ApiError) {
  if (import.meta.env.DEV) {
    console.error(`[API] ${error.status} ${error.message}`, error.payload)
  }
  globalErrorHandler?.(error)
}

function applyRequestDefaults(config: InternalAxiosRequestConfig) {
  config.headers.set('Accept', 'application/json')
  return config
}

export const apiClient: AxiosInstance = axios.create({
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

apiClient.interceptors.request.use(
  (config) => applyRequestDefaults(config),
  (error) => Promise.reject(normalizeAxiosError(error)),
)

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    const apiError = normalizeAxiosError(error)
    dispatchApiError(apiError)
    return Promise.reject(apiError)
  },
)
