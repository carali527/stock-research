import { onScopeDispose, ref } from 'vue'

import { apiUrl } from '@/config/apiBase'
import {
  inlineErrorHintFromStreamOutput,
  sanitizeClientThrownMessage,
  sanitizeHttpDetailForUser,
  stripTechnicalStreamMarkers,
} from '@/utils/userFacingErrors'

const MAX_FETCH_ATTEMPTS = 4
const STREAM_IDLE_AFTER_OUTPUT_MS = 8000
const DEMO_TOKEN = 'stock-research-demo'

function newClientRequestId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID()
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function sleep(ms: number) {
  return new Promise<void>((resolve) => setTimeout(resolve, ms))
}

/** 解析 Retry-After（秒數或 HTTP-date）；無效時用指數退避（毫秒）。 */
function parseRetryAfterMs(header: string | null, attemptIndex: number): number {
  const fallback = Math.min(60_000, 1000 * 2 ** attemptIndex + Math.random() * 500)
  if (!header?.trim()) return fallback
  const t = header.trim()
  if (/^\d+$/.test(t)) {
    return Math.min(120_000, parseInt(t, 10) * 1000) + Math.floor(Math.random() * 400)
  }
  const d = Date.parse(t)
  if (!Number.isNaN(d)) {
    return Math.max(0, d - Date.now()) + Math.floor(Math.random() * 400)
  }
  return fallback
}

/**
 * 將 ReadableStream 以 async 迭代讀取並解成 UTF-8 字串片段（等同 for-await 逐塊處理 chunk）。
 * fetch 被 Abort 時，reader.read() 會 reject AbortError。
 */
async function readWithIdleTimeout(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  shouldUseIdleTimeout: boolean,
): Promise<ReadableStreamReadResult<Uint8Array> | { idleTimeout: true }> {
  if (!shouldUseIdleTimeout) return reader.read()

  let timer: ReturnType<typeof setTimeout> | undefined
  try {
    return await Promise.race([
      reader.read(),
      new Promise<{ idleTimeout: true }>((resolve) => {
        timer = setTimeout(() => resolve({ idleTimeout: true }), STREAM_IDLE_AFTER_OUTPUT_MS)
      }),
    ])
  } finally {
    if (timer) clearTimeout(timer)
  }
}

async function* decodeUtf8StreamChunks(stream: ReadableStream<Uint8Array>): AsyncGenerator<string> {
  const reader = stream.getReader()
  const decoder = new TextDecoder()
  let hasReceivedOutput = false
  try {
    for (;;) {
      const result = await readWithIdleTimeout(reader, hasReceivedOutput)
      if ('idleTimeout' in result) {
        await reader.cancel().catch(() => {})
        const tail = decoder.decode()
        if (tail) yield tail
        break
      }

      const { value, done } = result
      if (done) {
        const tail = decoder.decode()
        if (tail) yield tail
        break
      }
      if (value?.byteLength) {
        hasReceivedOutput = true
        yield decoder.decode(value, { stream: true })
      }
    }
  } finally {
    try {
      reader.releaseLock()
    } catch {
      /* ignore */
    }
  }
}

function parseHttpErrorMessage(txt: string, status: number): string {
  let msg = txt || `Request failed (${status})`
  try {
    const j = JSON.parse(txt) as { detail?: unknown }
    if (typeof j.detail === 'string') msg = j.detail
    else if (Array.isArray(j.detail))
      msg = j.detail
        .map((x) =>
          typeof x === 'object' && x && 'msg' in x ? String((x as { msg: unknown }).msg) : JSON.stringify(x),
        )
        .join('; ')
  } catch {
    /* keep raw txt */
  }
  return msg
}

/** 除錯用；畫面上仍會顯示經 sanitize 的基本錯誤。 */
function logStreamDebug(scope: string, msg: string) {
  if (import.meta.env.DEV) console.log(`[useAIStream:${scope}]`, msg)
}

export function useAIStream() {
  const loading = ref(false)
  const output = ref('')
  /** 給使用者的基本錯誤提示（已過濾技術堆疊／過長原文） */
  const errorMessage = ref('')
  /** 與後端 log / 檔案除錯對齊（請求送出時產生，回應標頭 `X-Request-ID` 優先） */
  const lastRequestId = ref('')
  let controller: AbortController | null = null

  onScopeDispose(() => {
    controller?.abort()
    controller = null
  })

  const start = async (question: string, data: Record<string, unknown> = {}) => {
    controller?.abort()

    loading.value = true
    output.value = ''
    errorMessage.value = ''
    lastRequestId.value = ''
    controller = new AbortController()
    const signal = controller.signal

    try {
      const url = apiUrl('/api/ai/stream')
      const xRequestId = newClientRequestId()
      if (import.meta.env.DEV) {
        console.debug('[useAIStream] POST', url, '(同源 /api；開發環境由 Vite proxy → :8000)', 'X-Request-ID:', xRequestId)
      }

      let res: Response | undefined
      for (let attempt = 0; attempt < MAX_FETCH_ATTEMPTS; attempt++) {
        res = await fetch(url, {
          method: 'POST',
          signal,
          headers: {
            'Content-Type': 'application/json',
            'X-Request-ID': xRequestId,
            'X-Demo-Token': DEMO_TOKEN,
          },
          body: JSON.stringify({ question, data }),
        })
        if (res.status !== 429) break
        if (res.headers.get('X-Demo-Daily-Limit') === '1') break
        if (attempt >= MAX_FETCH_ATTEMPTS - 1) break
        const waitMs = parseRetryAfterMs(res.headers.get('Retry-After'), attempt)
        await sleep(waitMs)
        if (signal.aborted) return
      }

      if (!res) throw new Error('No response')

      if (!res.ok) {
        const txt = await res.text().catch(() => '')
        const rawDetail = parseHttpErrorMessage(txt, res.status)
        throw new Error(sanitizeHttpDetailForUser(res.status, rawDetail))
      }
      lastRequestId.value = (res.headers.get('X-Request-ID') || xRequestId).trim()
      if (!res.body) throw new Error('No response body')

      try {
        for await (const chunk of decodeUtf8StreamChunks(res.body)) {
          if (signal.aborted) break
          output.value += chunk
        }
      } catch (e) {
        if ((e as Error)?.name === 'AbortError') return
        const partial = output.value.trim().length > 0
        const m = sanitizeClientThrownMessage((e as Error)?.message || '串流讀取失敗')
        errorMessage.value = partial ? `${m}（上方為已收到的部分內容）` : m
        logStreamDebug('stream_read', errorMessage.value)
        throw e
      }

      if (!signal.aborted) {
        const hint = inlineErrorHintFromStreamOutput(output.value)
        output.value = stripTechnicalStreamMarkers(output.value)
        if (hint && !errorMessage.value) {
          errorMessage.value = hint
          logStreamDebug('stream_marker', hint)
        }
      }
    } catch (e) {
      if ((e as Error)?.name === 'AbortError') return
      const raw = (e as Error)?.message || '串流失敗'
      const m = sanitizeClientThrownMessage(raw)
      const hint =
        import.meta.env.DEV && (m.includes('無法連線') || m.includes('Failed to fetch') || m.includes('NetworkError'))
          ? '（請確認後端 :8000 已起，開發環境會由 Vite proxy 轉發 /api）'
          : ''
      const partial = output.value.trim().length > 0
      if (!errorMessage.value) {
        errorMessage.value = partial ? `${m}${hint}（上方為已收到的部分內容）` : m + hint
      }
      logStreamDebug('request', errorMessage.value)
      if (import.meta.env.DEV && raw !== m) console.log('[useAIStream:request] raw', raw)
    } finally {
      loading.value = false
      controller = null
    }
  }

  const stop = () => {
    controller?.abort()
    controller = null
    loading.value = false
  }

  return { start, stop, output, loading, errorMessage, lastRequestId }
}
