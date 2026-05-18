import type { ApiError } from '@/services/errors'

function looksTechnical(s: string): boolean {
  return /traceback|exception|RuntimeError|KeyError|TypeError|HTTPError|ECONNREFUSED|NaN|undefined|502|503|504|Gemini API failed|Yahoo scrape|sql|INSERT|SELECT|apikey|api_key|token|secret|at 0x[0-9a-f]+/i.test(
    s,
  )
}

/** HTTP 非 2xx 的 body 字串（已 parse 過 detail）→ 給一般使用者看的短句；技術內容只寫入 console。 */
export function sanitizeHttpDetailForUser(status: number, detail: string): string {
  const d = (detail || '').trim()
  if (import.meta.env.DEV) console.warn('[HTTP error]', status, d)

  if (status === 429 || /rate limit/i.test(d)) {
    return 'Demo 服務忙碌或今日額度暫時用完，請稍後再試。'
  }
  if (status >= 500) {
    return '服務暫時無法使用，請稍後再試。'
  }
  if (status === 422) {
    if (d.length > 0 && d.length <= 200 && !looksTechnical(d)) return d
    return '無法處理此次請求，請調整內容後再試。'
  }
  if (status === 401 || status === 403) {
    return '無權限或連線已失效，請稍後再試。'
  }
  if (status === 404) {
    return '找不到資源，請稍後再試。'
  }
  if (!d || looksTechnical(d) || d.length > 200) {
    return '發生錯誤，請稍後再試。'
  }
  return d
}

export function userMessageForApiError(e: ApiError): string {
  if (import.meta.env.DEV) console.warn('[ApiError]', e.status, e.message, e.payload)
  return sanitizeHttpDetailForUser(e.status, e.message)
}

/** 串流本文中不應給使用者看的技術尾註（內含例外字串）— 從畫面移除；提示改由 console（useAIStream）輸出。 */
export function stripTechnicalStreamMarkers(text: string): string {
  return text
    .replace(/\n*\[分析階段錯誤:[^\]]*\]\n*/g, '\n')
    .replace(/\n*\[串流中斷[^\]]*\]\n*/g, '\n')
    .replace(/\n*\[API 用量限制[^\]]*\]\n*/g, '\n')
    .replace(/\n*\[輸出被安全規則攔截[^\]]*\]\n*/g, '\n')
    .replace(/\n*\[此輪分析無文字輸出[^\]]*\]\n*/g, '\n')
    .replace(/\n*\[分析無內容[^\]]*\]\n*/g, '\n')
    .replace(/\n{3,}/g, '\n\n')
    .trimEnd()
}

const STREAM_ERROR_USER: { test: (s: string) => boolean; user: string }[] = [
  { test: (s) => s.includes('[串流中斷'), user: '回應中斷，請稍後再試。' },
  { test: (s) => s.includes('[API 用量限制'), user: 'Demo AI 額度暫時用完，請稍後再試。' },
  { test: (s) => s.includes('[輸出被安全規則攔截'), user: '內容未能完整顯示，請調整提問方式後再試。' },
  { test: (s) => s.includes('[分析階段錯誤'), user: '分析服務暫時異常，請稍後再試。' },
  {
    test: (s) => s.includes('[此輪分析無文字輸出') || s.includes('[分析無內容'),
    user: '本次未取得分析內容，請換個方式提問或稍後再試。',
  },
]

/** 依串流尾部標記決定紅字提示（不透傳含 Exception 的整行）。 */
export function inlineErrorHintFromStreamOutput(text: string): string {
  const lines = text.split('\n')
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim()
    for (const { test, user } of STREAM_ERROR_USER) {
      if (test(line)) {
        if (import.meta.env.DEV) console.warn('[stream marker]', line)
        return user
      }
    }
  }
  return ''
}

/** fetch / reader 失敗的英文訊息 → 中文 */
export function sanitizeClientThrownMessage(message: string): string {
  const m = (message || '').trim()
  if (import.meta.env.DEV) console.warn('[client]', m)
  if (!m) return '發生錯誤，請稍後再試。'
  if (/^(No response|No response body)$/i.test(m)) return '無法取得伺服器回應，請稍後再試。'
  if (/failed to fetch|networkerror|load failed/i.test(m)) return '無法連線，請檢查網路或稍後再試。'
  if (looksTechnical(m) || m.length > 220) return '發生錯誤，請稍後再試。'
  return m
}

/** Fugle WS error 事件文字：過長或像錯誤碼時不要直接露出 */
export function sanitizeWsServiceMessage(raw?: string): string {
  const s = raw?.trim()
  if (!s) return '即時行情連線異常，請稍後再試。'
  if (import.meta.env.DEV) console.warn('[Fugle WS]', s)
  if (s.length > 160 || /^[A-Z0-9_]+$/.test(s) || looksTechnical(s)) {
    return '即時行情連線異常，請稍後再試。'
  }
  return s
}
