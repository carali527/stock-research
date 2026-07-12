import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  inlineErrorHintFromStreamOutput,
  sanitizeClientThrownMessage,
  sanitizeHttpDetailForUser,
  sanitizeWsServiceMessage,
  stripTechnicalStreamMarkers,
} from './userFacingErrors'

describe('user-facing error sanitizers', () => {
  beforeEach(() => {
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('maps service and rate-limit failures to stable user messages', () => {
    expect(sanitizeHttpDetailForUser(500, 'Traceback: RuntimeError')).toBe(
      '服務暫時無法使用，請稍後再試。',
    )
    expect(sanitizeHttpDetailForUser(429, 'rate limit exceeded')).toBe(
      'Demo 服務忙碌或今日額度暫時用完，請稍後再試。',
    )
  })

  it('keeps safe validation details but hides technical details', () => {
    expect(sanitizeHttpDetailForUser(422, '請輸入股票代號')).toBe('請輸入股票代號')
    expect(sanitizeHttpDetailForUser(422, 'KeyError: api_key')).toBe(
      '無法處理此次請求，請調整內容後再試。',
    )
  })

  it('removes stream markers and returns matching inline hints', () => {
    const text = '分析內容\n[串流中斷: ECONNREFUSED]\n'

    expect(stripTechnicalStreamMarkers(text)).toBe('分析內容')
    expect(inlineErrorHintFromStreamOutput(text)).toBe('回應中斷，請稍後再試。')
  })

  it('sanitizes client and websocket transport errors', () => {
    expect(sanitizeClientThrownMessage('Failed to fetch')).toBe(
      '無法連線，請檢查網路或稍後再試。',
    )
    expect(sanitizeWsServiceMessage('UPSTREAM_TIMEOUT')).toBe(
      '即時行情連線異常，請稍後再試。',
    )
  })
})
