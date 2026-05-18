<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { TaiwanStockPriceBar } from '@/types/stock'
import { toYmdTaipei } from '@/utils/date'
import CandlestickChart from '@/components/CandlestickChart.vue'
import VirtualStockPriceList from '@/components/VirtualStockPriceList.vue'
import { ApiError } from '@/services/errors'
import { useFugleStockStreaming } from '@/composables/useFugleStockStreaming'
import { getHistoricalCandlesFromFugle } from '@/services/fugle'
import { useStockStore } from '@/stores/stockStore'

const route = useRoute()
const router = useRouter()

const stockId = computed(() => String(route.params.id ?? '').trim())
const stockStore = useStockStore()
const stockNameFromQuery = computed(() => String(route.query.name ?? '').trim())
const stockName = computed(() => stockNameFromQuery.value || stockStore.getName(stockId.value))
const isFavorite = computed(() => stockStore.isFavorite(stockId.value))

watch(
  [stockId, stockNameFromQuery],
  ([id, name]) => {
    if (id && name) stockStore.setName(id, name)
  },
  { immediate: true },
)

type StockTab = 'realtime' | 'kline'
const activeTab = ref<StockTab>('realtime')

const wsEnabled = computed(() => activeTab.value === 'realtime')

const {
  status: fugleStreamStatus,
  errorMessage: fugleStreamError,
  lastTrade: fugleLastTrade,
  lastCandle: fugleLastCandle,
  candlesSnapshot: fugleCandlesSnapshot,
} = useFugleStockStreaming(stockId, wsEnabled)

const tradeLine = ref<Array<{ time: number; value: number }>>([])

const fugleStreamLabel = computed(() => {
  switch (fugleStreamStatus.value) {
    case 'idle':
      return '未連線'
    case 'connecting':
      return '連線中…'
    case 'authenticated':
      return '已連線（即時成交）'
    case 'error':
      return '連線錯誤'
    case 'closed':
      return '連線已中斷'
    default:
      return fugleStreamStatus.value
  }
})

/** Fugle trades `time` 為奈秒時間戳 */
function formatFugleTime(ns: number | undefined) {
  if (ns == null || !Number.isFinite(ns)) return ''
  const ms = ns / 1_000_000
  if (!Number.isFinite(ms)) return ''
  try {
    return new Date(ms).toLocaleString('zh-TW', { timeZone: 'Asia/Taipei' })
  } catch {
    return ''
  }
}

function toTradeTimeSec(ns: number | undefined): number | null {
  if (ns == null || !Number.isFinite(ns)) return null
  const ms = ns / 1_000_000
  if (!Number.isFinite(ms)) return null
  return Math.floor(ms / 1000)
}

/** 即時分頁分 K：`historical/candles` 分 K（1/3/5/10/15/30/60），近 30 日 */
const INTRADAY_TIMEFRAMES = [1, 3, 5, 10, 15, 30, 60] as const
type IntradayTimeframe = (typeof INTRADAY_TIMEFRAMES)[number]
const intradayTimeframe = ref<IntradayTimeframe>(1)
const timeframeMenuOpen = ref(false)

function closeTimeframeMenu() {
  timeframeMenuOpen.value = false
}

function onDocPointerDown(e: PointerEvent) {
  const target = e.target as HTMLElement | null
  if (!target) return
  if (timeframeMenuOpen.value && !target.closest('[data-timeframe-menu]')) {
    closeTimeframeMenu()
  }
  if (klineDatePanelOpen.value && !target.closest('[data-kline-range-panel]') && !target.closest('[data-kline-resolution-btn]')) {
    klineDatePanelOpen.value = false
  }
}

type KlineResolution = 'minute' | 'day' | 'week' | 'month'
const resolution = ref<KlineResolution>('day')

/** K 線分 K 週期（僅在 resolution === 'minute' 時使用） */
const klineMinuteTimeframe = ref<IntradayTimeframe>(1)

const timeframeLabel = computed(() => {
  return activeTab.value === 'kline' && resolution.value === 'minute' ? klineMinuteTimeframe.value : intradayTimeframe.value
})

function isTaiwanMarketOpenNow(): boolean {
  // 簡化判斷：週一～週五，台北 09:00–13:35 視為開市（不處理例假日/颱風停市）
  const now = new Date()
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Taipei',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).formatToParts(now)
  const weekday = parts.find((p) => p.type === 'weekday')?.value ?? ''
  const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? NaN)
  const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? NaN)
  const dow = weekday.toLowerCase()
  const isWeekday = dow.startsWith('mon') || dow.startsWith('tue') || dow.startsWith('wed') || dow.startsWith('thu') || dow.startsWith('fri')
  if (!isWeekday) return false
  const hm = hour * 60 + minute
  return hm >= 9 * 60 && hm <= 13 * 60 + 35
}

function addDays(base: Date, days: number) {
  const d = new Date(base)
  d.setDate(d.getDate() + days)
  return d
}

/** 含首尾日數；Fugle 單次 from/to 須 ≤365 日 */
function inclusiveDaySpanLocal(fromYmd: string, toYmd: string): number {
  const a = new Date(`${fromYmd.slice(0, 10)}T12:00:00`)
  const b = new Date(`${toYmd.slice(0, 10)}T12:00:00`)
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime()) || a > b) return 0
  return Math.floor((b.getTime() - a.getTime()) / 86_400_000) + 1
}

/** UI 用：結束日往前一週為開始日 */
function deriveStartYmdFromEndYmd(endYmd: string): string {
  const end = endYmd.trim().slice(0, 10)
  if (!end) return toYmdTaipei(addDays(new Date(), -7))
  const endDate = new Date(`${end}T12:00:00`)
  return toYmdTaipei(addDays(endDate, -7))
}

/** Fugle historical：使用者可調整 from/to；預設 from 為 to 往前一週 */
const klineRangeEnd = ref(toYmdTaipei(new Date()))
const klineRangeStart = ref(deriveStartYmdFromEndYmd(klineRangeEnd.value))
const klineStartTouched = ref(false)
const klineEndTouched = ref(false)
const klineDatePanelOpen = ref(false)

// `input[type="date"]` 允許清空/輸入到一半；避免造成 start 掉回 fallback 而出現 end < start 的視覺不一致
watch(
  klineRangeEnd,
  (raw) => {
  let end = String(raw ?? '').trim().slice(0, 10)
  const today = toYmdTaipei(new Date())
  if (!end) {
    klineRangeEnd.value = today
    return
  }
  const d = new Date(`${end}T12:00:00`)
  if (Number.isNaN(d.getTime())) {
    klineRangeEnd.value = today
    return
  }
  const prevStart = String(klineRangeStart.value ?? '').trim().slice(0, 10)
  // 不限制 end；若使用者把 end 選到「目前 start 之前」，start 直接貼齊同一天
  if (prevStart && end < prevStart) {
    klineRangeStart.value = end
    klineStartTouched.value = true
  }
  // normalize to YYYY-MM-DD (防止帶入非標準字串)
  if (end !== raw) klineRangeEnd.value = end
  },
  { flush: 'post' },
)

watch(klineRangeStart, (raw) => {
  let start = String(raw ?? '').trim().slice(0, 10)
  const end = String(klineRangeEnd.value ?? '').trim().slice(0, 10)
  const fallback = end ? deriveStartYmdFromEndYmd(end) : toYmdTaipei(addDays(new Date(), -7))
  if (!start) {
    klineRangeStart.value = fallback
    klineStartTouched.value = false
    return
  }
  const d = new Date(`${start}T12:00:00`)
  if (Number.isNaN(d.getTime())) {
    klineRangeStart.value = fallback
    klineStartTouched.value = false
    return
  }
  // 保證 end >= start：若 start > end（或 end 不存在），直接把 end 拉到 start
  if (!end || start > end) {
    klineRangeEnd.value = start
  }
  if (start !== raw) klineRangeStart.value = start
})

function presetKlineRangeForResolution() {
  klineStartTouched.value = false
  klineEndTouched.value = false
  klineRangeEnd.value = toYmdTaipei(new Date())
  klineRangeStart.value = deriveStartYmdFromEndYmd(klineRangeEnd.value)
}

/** 日／週／月：切到 K 線、開日期面板並預設區間（重載由 watch resolution 負責，避免與 activeTab 重複打 API） */
function setKlineResolution(r: KlineResolution) {
  resolution.value = r
  activeTab.value = 'kline'
  presetKlineRangeForResolution()
  klineDatePanelOpen.value = true
}

/** K 線分 K：停留在 K 線/列表，只呼叫 historical/candles（不啟用 WS） */
function setKlineMinuteTimeframe(tf: IntradayTimeframe) {
  klineMinuteTimeframe.value = tf
  resolution.value = 'minute'
  activeTab.value = 'kline'
  klineDatePanelOpen.value = false
  timeframeMenuOpen.value = false
}

async function applyKlineRange() {
  const ok = await load()
  if (ok) {
    klineDatePanelOpen.value = false
    return
  }
  // 失敗時保留面板（讓使用者立刻調整日期）
  alert('請重新選擇日期')
}

const loading = ref(false)
const lastError = ref<ApiError | null>(null)
// Fugle historical candles（分 K：timeframe 1–60，API 近 30 日、不可指定 from/to）
const dailyRows = ref<TaiwanStockPriceBar[]>([])
const intradayCandles = ref<Array<{ date: string; timeSec: number; open: number; high: number; low: number; close: number; volume: number }>>(
  [],
)
// Fugle historical candles（日 D／週 W／月 M）
const historicalKlineRows = ref<TaiwanStockPriceBar[]>([])
const klineMinuteCandles = ref<Array<{ date: string; timeSec: number; open: number; high: number; low: number; close: number }>>([])

function parseIsoToTimeSec(iso: string): number | null {
  const ms = Date.parse(iso)
  if (!Number.isFinite(ms)) return null
  return Math.floor(ms / 1000)
}

function upsertLinePoint(series: Array<{ time: number; value: number }>, incoming: { time: number; value: number }) {
  const t = Math.floor(incoming.time / 60) * 60 // 同分鐘更新最後一點（不做補值）
  const next = { time: t, value: incoming.value }
  if (!series.length) return [next]
  const last = series[series.length - 1]
  if (last.time === next.time) return [...series.slice(0, -1), next]
  if (last.time < next.time) return [...series, next]
  // out-of-order：更新同分鐘或插入並排序（量小，成本可控）
  const byT = new Map<number, { time: number; value: number }>()
  for (const p of series) byT.set(p.time, p)
  byT.set(next.time, next)
  return [...byT.values()].sort((a, b) => a.time - b.time)
}

function isoToYmd(iso: string): string {
  // Fugle 回傳包含 +08:00；直接取前 10 碼即可
  return String(iso).slice(0, 10)
}

function isoToHm(iso: string): string {
  // YYYY-MM-DDTHH:mm...
  return String(iso).slice(11, 16)
}

const displayRows = computed<(TaiwanStockPriceBar & { key: string })[]>(() => {
  if (activeTab.value === 'kline') {
    const rows = klineResolvedRows.value
    const desc = [...rows].sort((a, b) => b.date.localeCompare(a.date))
    return desc.map((r) => ({ ...r, key: r.date }))
  }
  const asc = [...dailyRows.value].sort((a, b) => a.date.localeCompare(b.date))
  const desc = [...asc].sort((a, b) => {
    const ak = a.minute ? `${a.date}T${a.minute}` : a.date
    const bk = b.minute ? `${b.date}T${b.minute}` : b.date
    return bk.localeCompare(ak)
  })
  return desc.map((r) => ({
    ...r,
    key: r.minute ? `${r.date}T${r.minute}` : r.date,
  }))
})

const klineResolvedRows = computed(() => [...historicalKlineRows.value].sort((a, b) => a.date.localeCompare(b.date)))

const candles = computed(() =>
  activeTab.value === 'kline'
    ? resolution.value === 'minute'
      ? klineMinuteCandles.value.map((c) => ({ ...c }))
      : klineResolvedRows.value.map((r) => ({
          date: r.date,
          open: r.open,
          high: r.high,
          low: r.low,
          close: r.close,
        }))
    : [],
)

async function loadFugleIntraday(signal?: AbortSignal) {
  if (!stockId.value) return
  const res = await getHistoricalCandlesFromFugle({
    symbol: stockId.value,
    timeframe: intradayTimeframe.value,
    sort: 'asc',
    fields: 'open,high,low,close,volume',
    signal,
  })
  const mapped = res.data
    .map((c) => {
      const timeSec = parseIsoToTimeSec(c.date)
      if (timeSec == null) return null
      return {
        date: isoToYmd(c.date),
        timeSec,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
      }
    })
    .filter(Boolean) as Array<{
    date: string
    timeSec: number
    open: number
    high: number
    low: number
    close: number
    volume: number
  }>

  intradayCandles.value = mapped.slice(-1200)

  // 表格沿用既有 TaiwanStockPriceBar：用 minute 顯示 HH:mm
  dailyRows.value = res.data
    .map((c) => ({
      date: isoToYmd(c.date),
      minute: isoToHm(c.date),
      stockId: res.symbol,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume,
      amount: 0,
      turnover: 0,
      spread: c.close - c.open,
    }))
    .filter((r) => r.date && r.minute)
}

function resolutionToFugleHistoricalTf(r: Exclude<KlineResolution, 'minute'>): 'D' | 'W' | 'M' {
  if (r === 'week') return 'W'
  if (r === 'month') return 'M'
  return 'D'
}

async function loadFugleHistoricalKline(signal?: AbortSignal) {
  if (!stockId.value) return
  // minute K：單次 /historical/candles，不帶 from/to（API 固定近 30 日）
  if (resolution.value === 'minute') {
    const res = await getHistoricalCandlesFromFugle({
      symbol: stockId.value,
      timeframe: klineMinuteTimeframe.value,
      sort: 'asc',
      fields: 'open,high,low,close,volume',
      signal,
    })
    klineMinuteCandles.value = res.data
      .map((c) => {
        const timeSec = parseIsoToTimeSec(c.date)
        if (timeSec == null) return null
        return {
          date: isoToYmd(c.date),
          timeSec,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
        }
      })
      .filter(Boolean) as Array<{ date: string; timeSec: number; open: number; high: number; low: number; close: number }>

    historicalKlineRows.value = res.data
      .map((c) => ({
        date: isoToYmd(c.date),
        minute: isoToHm(c.date),
        stockId: res.symbol,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
        amount: 0,
        turnover: 0,
        spread: c.close - c.open,
      }))
      .filter((r) => r.date && r.minute)
    return
  }

  klineMinuteCandles.value = []
  let end = klineRangeEnd.value.trim().slice(0, 10)
  if (!end) {
    end = toYmdTaipei(new Date())
    klineRangeEnd.value = end
  }
  klineRangeEnd.value = end
  let wantedStart = klineRangeStart.value.trim().slice(0, 10)
  // 保底：不限制使用者選 end；若 end < start，改推進 start（讓 end 永遠可選）
  if (wantedStart && end && end < wantedStart) {
    wantedStart = end
    klineRangeStart.value = wantedStart
    klineStartTouched.value = true
  }

  const tf = resolutionToFugleHistoricalTf(resolution.value)
  const fields = 'open,high,low,close,volume'

  // Fugle 單次 from/to 需 ≤365（含首尾），超過則分段抓回後合併
  const span = inclusiveDaySpanLocal(wantedStart, end)
  const chunks: Array<{ from: string; to: string }> = []
  if (!wantedStart || span <= 365) {
    chunks.push({ from: wantedStart, to: end })
  } else {
    let curFrom = new Date(`${wantedStart}T12:00:00`)
    const endDate = new Date(`${end}T12:00:00`)
    while (curFrom <= endDate) {
      const curTo = addDays(curFrom, 364) // inclusive: 365 days
      const to = curTo > endDate ? endDate : curTo
      chunks.push({ from: toYmdTaipei(curFrom), to: toYmdTaipei(to) })
      curFrom = addDays(to, 1)
    }
  }

  const merged: TaiwanStockPriceBar[] = []
  for (const c of chunks) {
    const res = await getHistoricalCandlesFromFugle({
      symbol: stockId.value,
      timeframe: tf,
      from: c.from,
      to: c.to,
      sort: 'asc',
      fields,
      signal,
    })
    merged.push(
      ...res.data
        .filter((x) => x.date && Number.isFinite(x.open) && Number.isFinite(x.close))
        .map((x) => {
          const ymd = String(x.date).trim().slice(0, 10)
          return {
            date: ymd,
            minute: '',
            stockId: stockId.value,
            open: x.open,
            high: x.high,
            low: x.low,
            close: x.close,
            volume: x.volume ?? 0,
            amount: 0,
            turnover: x.turnover ?? 0,
            spread: x.close - x.open,
          }
        }),
    )
  }

  // 去重（分段邊界可能重疊/重複）
  const byDate = new Map<string, TaiwanStockPriceBar>()
  for (const r of merged) byDate.set(r.date, r)
  historicalKlineRows.value = [...byDate.values()].sort((a, b) => a.date.localeCompare(b.date))

  if (!historicalKlineRows.value.length) {
    throw new ApiError('該日期區間沒有交易資料（可能為假日、休市或無成交），請調整開始日/結束日再試一次。', {
      status: 204,
      code: 'NO_DATA',
      payload: { from: wantedStart, to: end },
    })
  }
}

let loadGeneration = 0
let loadAbort: AbortController | null = null
let realtimeFallbackKey = ''

async function load(): Promise<boolean> {
  if (!stockId.value) return false
  loadAbort?.abort()
  const ac = new AbortController()
  loadAbort = ac
  const gen = ++loadGeneration
  lastError.value = null

  // 即時行情：
  // - 開市：只用 WebSocket
  // - 休市：用 REST 補一份可畫的分 K（否則 WS snapshot 可能只有幾根）
  if (activeTab.value === 'realtime') {
    if (isTaiwanMarketOpenNow()) {
      loading.value = false
      return true
    }
    const key = `${stockId.value}:${intradayTimeframe.value}:${toYmdTaipei(new Date())}`
    if (realtimeFallbackKey === key && intradayCandles.value.length) {
      loading.value = false
      return true
    }
    realtimeFallbackKey = key
    loading.value = true
    try {
      const res = await getHistoricalCandlesFromFugle({
        symbol: stockId.value,
        timeframe: intradayTimeframe.value,
        sort: 'asc',
        fields: 'open,high,low,close,volume',
        signal: ac.signal,
      })
      if (gen !== loadGeneration || ac.signal.aborted) return false
      const mapped = res.data
        .map((c) => {
          const timeSec = parseIsoToTimeSec(c.date)
          if (timeSec == null) return null
          return {
            date: isoToYmd(c.date),
            timeSec,
            open: c.open,
            high: c.high,
            low: c.low,
            close: c.close,
            volume: c.volume,
          }
        })
        .filter(Boolean) as Array<{ date: string; timeSec: number; open: number; high: number; low: number; close: number; volume: number }>
      intradayCandles.value = mapped
      dailyRows.value = res.data
        .map((c) => ({
          date: isoToYmd(c.date),
          minute: isoToHm(c.date),
          stockId: stockId.value,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
          volume: c.volume,
          amount: 0,
          turnover: 0,
          spread: c.close - c.open,
        }))
        .filter((r) => r.date && r.minute)
      intradayCandles.value = mapped
    } catch (e) {
      if (gen !== loadGeneration || ac.signal.aborted) return false
      lastError.value = e as ApiError
      return false
    } finally {
      if (gen === loadGeneration) {
        loading.value = false
        if (loadAbort === ac) loadAbort = null
      }
    }
    return true
  }

  loading.value = true
  try {
    if (activeTab.value === 'kline') await loadFugleHistoricalKline(ac.signal)
    else await loadFugleIntraday(ac.signal)
    return true
  } catch (e) {
    if (gen !== loadGeneration) return false
    if (ac.signal.aborted) return false
    lastError.value = e as ApiError
    return false
  } finally {
    if (gen === loadGeneration) {
      loading.value = false
      if (loadAbort === ac) loadAbort = null
    }
  }
}

function back() {
  void router.push({ name: 'stock', params: { id: stockId.value || 'all' } })
}

watch(
  fugleLastTrade,
  (t) => {
    if (!t) return
    const timeSec = toTradeTimeSec(t.time) ?? Math.floor(Date.now() / 1000)
    const last = tradeLine.value[tradeLine.value.length - 1]
    if (last && last.time === timeSec) {
      last.value = t.price
      tradeLine.value = [...tradeLine.value]
      return
    }
    tradeLine.value = [...tradeLine.value, { time: timeSec, value: t.price }].slice(-600)
  },
  { deep: true },
)

watch(
  fugleLastCandle,
  (c) => {
    if (!c) return
    // WebSocket candles 為 1 分 K；即時行情只用 WS 來畫圖
    if (!wsEnabled.value) return

    const timeSecRaw = parseIsoToTimeSec(c.date)
    if (timeSecRaw == null) return
    const timeSec = timeSecRaw

    const ymd = isoToYmd(c.date)
    const hm = isoToHm(c.date)

    const next = { time: timeSec, value: c.close }
    tradeLine.value = upsertLinePoint(tradeLine.value, next).slice(-1200)

    // 表格同步更新（用 date+minute 當 key）
    const rowKey = `${ymd}T${hm}`
    const ridx = dailyRows.value.findIndex((r) => (r.minute ? `${r.date}T${r.minute}` : r.date) === rowKey)
    const nextRow: TaiwanStockPriceBar = {
      date: ymd,
      minute: hm,
      stockId: stockId.value,
      open: c.open,
      high: c.high,
      low: c.low,
      close: c.close,
      volume: c.volume,
      amount: 0,
      turnover: 0,
      spread: c.close - c.open,
    }
    if (ridx >= 0) {
      const rows = [...dailyRows.value]
      rows[ridx] = nextRow
      dailyRows.value = rows
    } else {
      dailyRows.value = [...dailyRows.value, nextRow].sort((a, b) => {
        const ak = a.minute ? `${a.date}T${a.minute}` : a.date
        const bk = b.minute ? `${b.date}T${b.minute}` : b.date
        return ak.localeCompare(bk)
      })
    }
  },
  { deep: true },
)

watch(
  fugleCandlesSnapshot,
  (rows) => {
    if (!wsEnabled.value) return
    if (!rows?.length) return
    const mapped = rows
      .map((c) => {
        const timeSecRaw = parseIsoToTimeSec(c.date)
        if (timeSecRaw == null) return null
        const timeSec = timeSecRaw
        return {
          date: isoToYmd(c.date),
          timeSec,
          open: c.open,
          high: c.high,
          low: c.low,
          close: c.close,
          volume: c.volume,
        }
      })
      .filter(Boolean) as Array<{ date: string; timeSec: number; open: number; high: number; low: number; close: number; volume: number }>

    intradayCandles.value = mapped.sort((a, b) => a.timeSec - b.timeSec).slice(-1200)
    tradeLine.value = mapped.map((c) => ({ time: c.timeSec, value: c.close })).slice(-1200)
    dailyRows.value = mapped
      .map((c) => ({
        date: c.date,
        minute: isoToHm(`${c.date}T00:00:00`).slice(0, 0), // keep empty for snapshot list
        stockId: stockId.value,
        open: c.open,
        high: c.high,
        low: c.low,
        close: c.close,
        volume: c.volume,
        amount: 0,
        turnover: 0,
        spread: c.close - c.open,
      }))
      .map((r) => ({ ...r, minute: '' }))
  },
  { deep: true },
)

/** 頁籤／分 K／日週月週期／代碼：同一輪只觸發一次 load；含 resolution 避免只改日週月時漏載 */
watch(
  [activeTab, intradayTimeframe, stockId, resolution, klineMinuteTimeframe, klineRangeEnd],
  ([t, , sid], old) => {
    if (old) {
      const [, , prevSid] = old
      if (prevSid !== sid) {
        tradeLine.value = []
        intradayCandles.value = []
        dailyRows.value = []
        historicalKlineRows.value = []
        klineMinuteCandles.value = []
      }
    }
    if (t === 'realtime') {
      // 即時行情只顯示 WS：切回即時時清掉 K 線/列表殘留
      // WS `candles` 推播為 1 分 K；確保切回即時時一定能接到資料更新圖表
      intradayTimeframe.value = 1
      intradayCandles.value = []
      dailyRows.value = []
      tradeLine.value = []
    } else {
      tradeLine.value = []
    }
    void load()
  },
  { flush: 'post', immediate: true },
)

onMounted(() => {
  // 預設區間：只在初次載入時套用一次（避免後續手動調整還被硬套「前一週」）
  if (!klineStartTouched.value && !klineEndTouched.value) {
    klineRangeStart.value = deriveStartYmdFromEndYmd(klineRangeEnd.value)
  }
  document.addEventListener('pointerdown', onDocPointerDown, true)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocPointerDown, true)
})
</script>

<template>
  <main>
    <div class="mb-6 flex flex-wrap items-end gap-4">
      <div>
        <button
          type="button"
          class="mb-2 text-sm text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
          @click="back"
        >
          ← Back
        </button>
        <h1 class="!my-0 text-2xl tracking-tight sm:text-3xl">股價日成交資訊</h1>
        <p class="mt-2 text-sm text-slate-500 dark:text-slate-400">
          股票代碼: {{ stockId }}<span v-if="stockName" class="text-slate-600 dark:text-slate-300"> · {{ stockName }}</span>
          <button
            type="button"
            class="ml-2 inline-flex h-6 w-6 items-center justify-center rounded-md text-base leading-none text-amber-500 hover:bg-slate-200/70 dark:hover:bg-slate-800/70"
            :aria-label="isFavorite ? '從自選移除' : '加入自選'"
            :title="isFavorite ? '從自選移除' : '加入自選'"
            @click="stockStore.toggleFavorite(stockId)"
          >
            {{ isFavorite ? '★' : '☆' }}
          </button>
        </p>
      </div>

      <div class="flex flex-wrap items-end gap-3">
        <!-- 日/週/月 vs 分：同一條灰底工具列；選「分」時日週月明顯不 active -->
        <div
          class="relative inline-flex h-10 items-center gap-1 rounded-xl border border-slate-200/80 bg-slate-100 px-1 shadow-inner dark:border-slate-700 dark:bg-slate-900/90"
        >
          <div class="inline-flex h-full items-center px-1">
            <button
              type="button"
              data-kline-resolution-btn
              class="rounded-md px-3 text-sm transition-colors"
              :class="
                activeTab === 'kline' && resolution === 'day'
                  ? 'bg-white font-medium text-slate-900 shadow-sm ring-1 ring-slate-200/90 dark:bg-slate-800 dark:text-slate-50 dark:ring-slate-600'
                  : activeTab === 'realtime'
                    ? 'text-slate-400 dark:text-slate-500'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'
              "
              @click="setKlineResolution('day')"
            >
              日
            </button>
            <button
              type="button"
              data-kline-resolution-btn
              class="rounded-md px-3 text-sm transition-colors"
              :class="
                activeTab === 'kline' && resolution === 'week'
                  ? 'bg-white font-medium text-slate-900 shadow-sm ring-1 ring-slate-200/90 dark:bg-slate-800 dark:text-slate-50 dark:ring-slate-600'
                  : activeTab === 'realtime'
                    ? 'text-slate-400 dark:text-slate-500'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'
              "
              @click="setKlineResolution('week')"
            >
              週
            </button>
            <button
              type="button"
              data-kline-resolution-btn
              class="rounded-md px-3 text-sm transition-colors"
              :class="
                activeTab === 'kline' && resolution === 'month'
                  ? 'bg-white font-medium text-slate-900 shadow-sm ring-1 ring-slate-200/90 dark:bg-slate-800 dark:text-slate-50 dark:ring-slate-600'
                  : activeTab === 'realtime'
                    ? 'text-slate-400 dark:text-slate-500'
                    : 'text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100'
              "
              @click="setKlineResolution('month')"
            >
              月
            </button>
          </div>

          <div class="relative flex h-full items-center" data-timeframe-menu>
            <button
              type="button"
              class="inline-flex h-9 items-center gap-1 rounded-lg px-3 text-sm transition-colors disabled:opacity-60"
              :class="
                activeTab === 'kline' && resolution === 'minute'
                  ? 'bg-white font-medium text-slate-900 shadow-sm ring-1 ring-slate-200/90 dark:bg-slate-950 dark:text-slate-50 dark:ring-slate-600'
                  : 'text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
              "
              :disabled="loading || !stockId"
              @click="
                timeframeMenuOpen = !timeframeMenuOpen
              "
            >
              {{ timeframeLabel }}分
              <svg
                class="h-4 w-4"
                viewBox="0 0 20 20"
                fill="currentColor"
                aria-hidden="true"
                :class="timeframeMenuOpen ? 'rotate-180' : ''"
              >
                <path
                  fill-rule="evenodd"
                  d="M5.22 7.47a.75.75 0 0 1 1.06 0L10 11.19l3.72-3.72a.75.75 0 1 1 1.06 1.06l-4.25 4.25a.75.75 0 0 1-1.06 0L5.22 8.53a.75.75 0 0 1 0-1.06Z"
                  clip-rule="evenodd"
                />
              </svg>
            </button>

            <div
              v-if="timeframeMenuOpen"
              class="absolute top-4 right-0 z-20 mt-2 w-44 overflow-hidden rounded-2xl border border-slate-200 bg-white p-2 shadow-xl dark:border-slate-800 dark:bg-slate-950"
            >
              <button
                v-for="tf in INTRADAY_TIMEFRAMES"
                :key="tf"
                type="button"
                class="flex w-full items-center justify-between rounded-xl px-4 py-3 text-left text-lg text-slate-900 hover:bg-slate-50 dark:text-slate-100 dark:hover:bg-slate-900"
                @click="
                  intradayTimeframe = tf;
                  setKlineMinuteTimeframe(tf)
                "
              >
                <span>{{ tf }}分</span>
                <span
                  v-if="timeframeLabel === tf"
                  class="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-slate-100 text-slate-900 dark:bg-slate-800 dark:text-slate-50"
                  aria-hidden="true"
                >
                  ✓
                </span>
              </button>
            </div>
          </div>

          <div
            v-if="klineDatePanelOpen && activeTab === 'kline'"
            data-kline-range-panel
            class="absolute left-0 top-[calc(100%+0.5rem)] z-30 w-[min(calc(100vw-2rem),22rem)] rounded-xl border border-slate-200 bg-white p-4 shadow-xl dark:border-slate-700 dark:bg-slate-950"
            @pointerdown.stop
          >
            <div class="text-sm font-medium text-slate-900 dark:text-slate-100">歷史 K 線區間</div>
            <p class="mt-1 text-xs text-slate-500 dark:text-slate-400">
              可選開始/結束日；預設開始日為結束日往前一週。資料若超過單次查詢上限會自動分段抓取並合併。
            </p>
            <div class="mt-3 grid gap-3 sm:grid-cols-2">
              <label class="block text-xs text-slate-600 dark:text-slate-400">
                開始日
                <input
                  v-model="klineRangeStart"
                  type="date"
                  :max="klineRangeEnd"
                  class="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                  @input="klineStartTouched = true"
                />
              </label>
              <label class="block text-xs text-slate-600 dark:text-slate-400">
                結束日
                <input
                  v-model="klineRangeEnd"
                  type="date"
                  class="mt-1 w-full rounded-lg border border-slate-200 bg-white px-2 py-1.5 text-sm text-slate-900 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-100"
                  @input="klineEndTouched = true"
                />
              </label>
            </div>
            <div class="mt-4 flex justify-end gap-2">
              <button
                type="button"
                class="rounded-lg px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-900"
                @click="klineDatePanelOpen = false"
              >
                關閉
              </button>
              <button
                type="button"
                class="rounded-lg bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
                :disabled="loading"
                @click="applyKlineRange"
              >
                套用
              </button>
            </div>
          </div>
        </div>

      </div>
    </div>

    <div class="grid min-h-0 gap-4 lg:grid-cols-[220px_minmax(0,1fr)]">
      <aside class="rounded-lg border border-slate-200 bg-white p-2 shadow-sm dark:border-slate-800 dark:bg-slate-950">
        <button
          type="button"
          class="flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors"
          :class="
            activeTab === 'realtime'
              ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
              : 'text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-900'
          "
          @click="
            activeTab = 'realtime';
            // 離開 minute 模式，避免回到 K 線時卡在分 K
            if (resolution === 'minute') resolution = 'day'
          "
        >
          <span>即時行情</span>
          <span class="text-xs opacity-70">WS</span>
        </button>
        <button
          type="button"
          class="mt-1 flex w-full items-center justify-between rounded-md px-3 py-2 text-left text-sm transition-colors"
          :class="
            activeTab === 'kline'
              ? 'bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900'
              : 'text-slate-700 hover:bg-slate-50 dark:text-slate-200 dark:hover:bg-slate-900'
          "
          @click="activeTab = 'kline'"
        >
          <span>K 線/列表</span>
          <span class="text-xs opacity-70">REST</span>
        </button>
      </aside>

      <section class="min-w-0">
        <div v-if="activeTab === 'realtime'" class="grid gap-3">
          <div class="rounded-lg border border-slate-200 bg-white p-3 text-sm shadow-sm dark:border-slate-800 dark:bg-slate-950">
            <div class="flex flex-wrap items-center justify-between gap-2">
              <div class="text-slate-700 dark:text-slate-200">
                富果即時行情：
                <span
                  :class="{
                    'text-emerald-700 dark:text-emerald-300': fugleStreamStatus === 'authenticated',
                    'text-amber-700 dark:text-amber-300': fugleStreamStatus === 'connecting',
                    'text-red-700 dark:text-red-300': fugleStreamStatus === 'error',
                  }"
                >{{ fugleStreamLabel }}</span>
              </div>
              <div v-if="fugleLastTrade" class="text-slate-700 dark:text-slate-200">
                最新成交
                <span class="font-medium tabular-nums">{{ fugleLastTrade.price }}</span>
                <span v-if="fugleLastTrade.volume != null" class="tabular-nums text-slate-500 dark:text-slate-400">
                  （量 {{ fugleLastTrade.volume }}）</span>
                <span v-if="formatFugleTime(fugleLastTrade.time)" class="text-slate-500 dark:text-slate-400">
                  {{ formatFugleTime(fugleLastTrade.time) }}</span>
              </div>
            </div>
            <p v-if="fugleStreamError" class="mt-1 text-sm text-red-700 dark:text-red-300">
              {{ fugleStreamError }}
            </p>
          </div>

          <CandlestickChart variant="line" :candles="[]" :line="tradeLine" />
        </div>

        <div v-else class="grid gap-3">
          <div class="flex items-baseline justify-between text-xs text-slate-500 dark:text-slate-400">
            <span>資料量: {{ displayRows.length }}</span>
          </div>
          <CandlestickChart :candles="candles" :time-axis-date-only="resolution !== 'minute'" />
          <VirtualStockPriceList :rows="displayRows" />
        </div>
      </section>
    </div>
  </main>
</template>