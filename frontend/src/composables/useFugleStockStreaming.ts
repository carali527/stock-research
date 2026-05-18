import { onUnmounted, ref, watch, type MaybeRefOrGetter, toValue } from 'vue'

import { sanitizeWsServiceMessage } from '@/utils/userFacingErrors'

/** 同源 WS：後端 `/ws/fugle/streaming` 轉發至 Fugle（金鑰僅在後端）。 */
function fugleStreamingWsUrl(): string {
  const { protocol, host } = window.location
  const wsProto = protocol === 'https:' ? 'wss:' : 'ws:'
  return `${wsProto}//${host}/ws/fugle/streaming`
}

export type FugleStreamStatus = 'idle' | 'connecting' | 'authenticated' | 'error' | 'closed'

export type FugleLastTrade = {
  price: number
  volume?: number
  time?: number
}

export type FugleLastCandle = {
  symbol: string
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  average?: number
}

export type FugleCandleRow = FugleLastCandle

type WsPayload = {
  event?: string
  channel?: string
  id?: string
  data?: unknown
}

function normalizeFugleSymbol(raw: string): string {
  const t = raw.trim()
  if (!t) return ''
  const i = t.indexOf('.')
  if (i > 0) return t.slice(0, i)
  return t
}

/**
 * 進入個股頁時建立 Fugle 即時行情 WebSocket：連線後送 `auth`，成功後訂閱 `candles`（1 分 K）。
 * 離開頁面或股票代碼變更時關閉連線。
 */
export function useFugleStockStreaming(symbol: MaybeRefOrGetter<string>, enabled: MaybeRefOrGetter<boolean> = true) {
  const status = ref<FugleStreamStatus>('idle')
  const errorMessage = ref<string | null>(null)
  const lastTrade = ref<FugleLastTrade | null>(null)
  const lastCandle = ref<FugleLastCandle | null>(null)
  const candlesSnapshot = ref<FugleCandleRow[]>([])

  let ws: WebSocket | null = null
  let pendingSymbol = ''
  let subscribedSymbol = ''

  // Reconnect / watchdog
  let manualClose = false
  let retryCount = 0
  let reconnectTimer: number | null = null
  let heartbeatTimer: number | null = null
  let lastMessageAt = 0

  const HEARTBEAT_CHECK_MS = 5_000
  const HEARTBEAT_TIMEOUT_MS = 25_000
  const BACKOFF_BASE_MS = 500
  const BACKOFF_CAP_MS = 30_000

  function clearReconnectTimer() {
    if (reconnectTimer != null) {
      window.clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
  }

  function clearHeartbeatTimer() {
    if (heartbeatTimer != null) {
      window.clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function startHeartbeatWatchdog() {
    clearHeartbeatTimer()
    lastMessageAt = Date.now()
    heartbeatTimer = window.setInterval(() => {
      if (!ws) return
      // If no message for a while, treat as a dead connection and reconnect.
      if (Date.now() - lastMessageAt > HEARTBEAT_TIMEOUT_MS) {
        const sym = subscribedSymbol || pendingSymbol
        teardownSocket()
        status.value = 'closed'
        scheduleReconnect('heartbeat-timeout', sym)
      }
    }, HEARTBEAT_CHECK_MS)
  }

  function scheduleReconnect(reason: string, sym: string) {
    if (manualClose) return
    if (!toValue(enabled)) return
    if (!sym) return

    clearReconnectTimer()

    const backoff = Math.min(BACKOFF_CAP_MS, BACKOFF_BASE_MS * 2 ** retryCount)
    const jitter = Math.floor(Math.random() * 250)
    const waitMs = backoff + jitter
    retryCount += 1

    if (import.meta.env.DEV) {
      console.debug(`[Fugle WS] reconnect scheduled (${reason}) in ${waitMs}ms (retry=${retryCount})`)
    }

    status.value = 'connecting'
    reconnectTimer = window.setTimeout(() => connect(sym), waitMs)
  }

  function send(obj: object) {
    if (ws?.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(obj))
    }
  }

  function teardownSocket() {
    if (!ws) return
    const s = ws
    ws = null
    s.onopen = null
    s.onmessage = null
    s.onerror = null
    s.onclose = null
    try {
      s.close()
    } catch {
      /* ignore */
    }
  }

  function disconnect() {
    manualClose = true
    pendingSymbol = ''
    subscribedSymbol = ''
    candlesSnapshot.value = []
    clearReconnectTimer()
    clearHeartbeatTimer()
    teardownSocket()
    status.value = 'idle'
    errorMessage.value = null
    retryCount = 0
    manualClose = false
  }

  function connect(sym: string) {
    manualClose = false
    clearReconnectTimer()
    clearHeartbeatTimer()
    teardownSocket()
    lastTrade.value = null
    lastCandle.value = null
    candlesSnapshot.value = []

    if (!sym) {
      status.value = 'idle'
      errorMessage.value = null
      return
    }

    pendingSymbol = sym
    status.value = 'connecting'
    errorMessage.value = null

    const socket = new WebSocket(fugleStreamingWsUrl())
    ws = socket
    lastMessageAt = Date.now()

    socket.onmessage = (ev) => {
      let msg: WsPayload
      try {
        msg = JSON.parse(String(ev.data)) as WsPayload
      } catch {
        return
      }

      lastMessageAt = Date.now()

      if (import.meta.env.DEV) {
        // Fugle WebSocket: authenticated / subscribed / data / heartbeat / error ...
        console.log('[Fugle WS]', msg)
      }

      const event = msg.event
      if (event === 'authenticated') {
        status.value = 'authenticated'
        subscribedSymbol = pendingSymbol
        retryCount = 0
        startHeartbeatWatchdog()
        send({
          event: 'subscribe',
          data: { channel: 'candles', symbol: subscribedSymbol },
        })
        return
      }

      if (event === 'error') {
        const d = msg.data as { message?: string } | undefined
        errorMessage.value = sanitizeWsServiceMessage(d?.message)
        status.value = 'error'
        // Permanent errors (e.g. bad apikey) shouldn't be retried forever.
        // If it's transient, the onclose/onerror path will schedule reconnect.
        return
      }

      const isCandlesChannel = msg.channel === 'candles'
      const isDataEvent = event === 'data'
      const isSnapshotEvent = event === 'snapshot'

      if ((isDataEvent || isSnapshotEvent) && isCandlesChannel && msg.data && typeof msg.data === 'object') {
        // Fugle WS 可能回：
        // 1) event=data, data={...單根...}
        // 2) event=snapshot, data={..., data:[...多根...] }
        const root = msg.data as {
          symbol?: unknown
          data?: unknown
          date?: unknown
          open?: unknown
          high?: unknown
          low?: unknown
          close?: unknown
          volume?: unknown
          average?: unknown
        }

        const parseRow = (raw: unknown): FugleCandleRow | null => {
          if (!raw || typeof raw !== 'object') return null
          const d = raw as {
            symbol?: unknown
            date?: unknown
            open?: unknown
            high?: unknown
            low?: unknown
            close?: unknown
            volume?: unknown
            average?: unknown
          }
          const sym = typeof d.symbol === 'string' ? d.symbol : typeof root.symbol === 'string' ? root.symbol : ''
          if (
            !sym ||
            typeof d.date !== 'string' ||
            typeof d.open !== 'number' ||
            typeof d.high !== 'number' ||
            typeof d.low !== 'number' ||
            typeof d.close !== 'number' ||
            typeof d.volume !== 'number'
          ) {
            return null
          }
          return {
            symbol: sym,
            date: d.date,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
            volume: d.volume,
            average: typeof d.average === 'number' ? d.average : undefined,
          }
        }

        if (Array.isArray(root.data)) {
          const rows = root.data.map(parseRow).filter(Boolean) as FugleCandleRow[]
          candlesSnapshot.value = rows
          const last = rows[rows.length - 1]
          if (last) lastCandle.value = last
        } else {
          const one = parseRow(root)
          if (one) lastCandle.value = one
        }
      }
    }

    socket.onerror = () => {
      if (status.value === 'connecting') {
        errorMessage.value = 'WebSocket 連線失敗'
        status.value = 'error'
      }
      const symNow = pendingSymbol || subscribedSymbol
      teardownSocket()
      scheduleReconnect('error', symNow)
    }

    socket.onclose = () => {
      if (ws !== socket) return
      ws = null
      if (status.value !== 'error') status.value = 'closed'
      clearHeartbeatTimer()
      const symNow = subscribedSymbol || pendingSymbol
      scheduleReconnect('close', symNow)
    }
  }

  watch(
    [() => normalizeFugleSymbol(toValue(symbol)), () => Boolean(toValue(enabled))],
    ([sym, on]) => {
      if (!on) {
        disconnect()
        return
      }
      if (!sym) disconnect()
      else connect(sym)
    },
    { immediate: true },
  )

  // Best-effort: when network comes back or tab becomes visible, try reconnect quickly.
  function onOnline() {
    const on = Boolean(toValue(enabled))
    const sym = normalizeFugleSymbol(toValue(symbol))
    if (!on || !sym) return
    if (status.value === 'authenticated') return
    retryCount = 0
    void connect(sym)
  }

  function onVisibilityChange() {
    if (document.visibilityState !== 'visible') return
    onOnline()
  }

  window.addEventListener('online', onOnline)
  document.addEventListener('visibilitychange', onVisibilityChange)

  onUnmounted(() => {
    window.removeEventListener('online', onOnline)
    document.removeEventListener('visibilitychange', onVisibilityChange)
    disconnect()
  })

  return { status, errorMessage, lastTrade, lastCandle, candlesSnapshot }
}
