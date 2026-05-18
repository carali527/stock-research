<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  CandlestickSeries,
  ColorType,
  LineSeries,
  createChart,
  type CandlestickData,
  type LineData,
  type IChartApi,
  type UTCTimestamp,
} from 'lightweight-charts'

const props = defineProps<{
  variant?: 'candlestick' | 'line'
  candles?: Array<{
    /** 日 K：YYYY-MM-DD；分鐘 K 也會保留日期字串供表格顯示 */
    date: string
    /** 分 K：秒級 UNIX timestamp（若有提供，圖表 time 會用這個） */
    timeSec?: number
    open: number
    high: number
    low: number
    close: number
  }>
  /** 線圖資料（time 為秒級 UNIX timestamp） */
  line?: Array<{ time: number; value: number }>
  height?: number
  /** 日／週／月 K：時間軸只顯示日期，不顯示時分 */
  timeAxisDateOnly?: boolean
}>()

type CandleRow = NonNullable<typeof props.candles>[number]

const containerRef = ref<HTMLDivElement | null>(null)
const heightPx = computed(() => props.height ?? 320)

let chart: IChartApi | null = null
let series: ReturnType<IChartApi['addSeries']> | null = null
let lineSeries: ReturnType<IChartApi['addSeries']> | null = null
let ro: ResizeObserver | null = null

function normalizeYmd(raw: string): string {
  const s = String(raw).trim()
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (m) return `${m[1]}-${m[2]}-${m[3]}`
  const t = Date.parse(s)
  if (Number.isFinite(t)) return new Date(t).toISOString().slice(0, 10)
  return s.slice(0, 10)
}

/** 日 K 用 UTC 日界 timestamp，與分 K 的 timeSec 一致，避免 BusinessDay 長區間異常 */
function ymdToUtcTimestamp(ymd: string): UTCTimestamp {
  const s = normalizeYmd(ymd)
  const [y, m, d] = s.split('-').map((x) => Number(x))
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) {
    return 0 as UTCTimestamp
  }
  return Math.floor(Date.UTC(y, m - 1, d) / 1000) as UTCTimestamp
}

function formatTaipeiFromUtcSeconds(sec: number): string {
  const ms = sec * 1000
  // 用台北時區，避免輕量圖表預設用 UTC 造成日期顯示偏移
  const dtf = new Intl.DateTimeFormat('zh-TW', {
    timeZone: 'Asia/Taipei',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  })
  return dtf.format(new Date(ms))
}

/** 日／週／月 K 時間軸：僅日期（台北日曆日） */
function formatTaipeiDateOnlyFromUtcSeconds(sec: number): string {
  return new Date(sec * 1000).toLocaleDateString('zh-TW', {
    timeZone: 'Asia/Taipei',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

function formatTaipeiBusinessDay(ymd: string): string {
  // 顯示為 MM/DD
  const m = ymd.slice(5, 7)
  const d = ymd.slice(8, 10)
  if (!m || !d) return ymd
  return `${m}/${d}`
}

function isDark(): boolean {
  return typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: dark)').matches
}

function applyTheme() {
  if (!chart) return
  const dark = isDark()
  chart.applyOptions({
    layout: {
      background: { type: ColorType.Solid, color: dark ? '#020617' : '#ffffff' },
      textColor: dark ? '#cbd5e1' : '#334155',
    },
    grid: {
      vertLines: { color: dark ? '#0f172a' : '#e2e8f0' },
      horzLines: { color: dark ? '#0f172a' : '#e2e8f0' },
    },
    rightPriceScale: { borderColor: dark ? '#0f172a' : '#e2e8f0' },
    timeScale: { borderColor: dark ? '#0f172a' : '#e2e8f0' },
  })
}

function num(v: unknown): number {
  const n = typeof v === 'number' ? v : Number(v)
  return n
}

function isValidBar(c: CandleRow): boolean {
  if (!c.date && c.timeSec == null) return false
  const nums = [num(c.open), num(c.high), num(c.low), num(c.close)]
  return nums.every((n) => Number.isFinite(n))
}

function toSeriesData(): CandlestickData[] {
  const candles = props.candles ?? []
  // time 必須遞增（asc）；同時間只保留最後一根
  const sorted = [...candles].filter(isValidBar).sort((a, b) => {
    if (a.timeSec != null && b.timeSec != null) return a.timeSec - b.timeSec
    return normalizeYmd(a.date).localeCompare(normalizeYmd(b.date))
  })
  const byKey = new Map<string, CandleRow>()
  for (const c of sorted) {
    const key = c.timeSec != null ? `t:${Math.floor(c.timeSec)}` : `d:${normalizeYmd(c.date)}`
    byKey.set(key, c)
  }
  const deduped = [...byKey.values()].sort((a, b) => {
    if (a.timeSec != null && b.timeSec != null) return a.timeSec - b.timeSec
    return normalizeYmd(a.date).localeCompare(normalizeYmd(b.date))
  })
  return deduped.map((c) => ({
    time: (c.timeSec != null ? (Math.floor(c.timeSec) as UTCTimestamp) : ymdToUtcTimestamp(c.date)) as UTCTimestamp,
    open: num(c.open),
    high: num(c.high),
    low: num(c.low),
    close: num(c.close),
  }))
}

function toLineSeriesData(): LineData[] {
  const rows = props.line ?? []
  const sorted = [...rows].filter((r) => Number.isFinite(r.time) && Number.isFinite(r.value)).sort((a, b) => a.time - b.time)
  return sorted.map((r) => ({ time: Math.floor(r.time) as UTCTimestamp, value: r.value }))
}

function render() {
  if (!chart) return
  const variant = props.variant ?? 'candlestick'
  const lineData = toLineSeriesData()

  if (variant === 'line') {
    if (lineSeries) lineSeries.setData(lineData)
    const n = lineData.length
    if (n === 0) return
    chart.timeScale().fitContent()
    chart.timeScale().scrollToRealTime()
    return
  }

  if (!series) return
  const data = toSeriesData()
  series.setData(data)
  if (lineSeries) lineSeries.setData(lineData)

  const n = data.length
  if (n === 0) return
  // minBarSpacing 已拉高，fitContent 無法無限壓縮；再捲到最新 K
  chart.timeScale().fitContent()
  chart.timeScale().scrollToRealTime()
}

onMounted(() => {
  const el = containerRef.value
  if (!el) return

  const axisDateOnly = props.timeAxisDateOnly === true
  const width = el.clientWidth || 600
  chart = createChart(el, {
    width,
    height: heightPx.value,
    autoSize: false,
    rightPriceScale: { borderVisible: true },
    localization: axisDateOnly
      ? {
          timeFormatter: (time: unknown) => {
            if (typeof time === 'number') return formatTaipeiDateOnlyFromUtcSeconds(time)
            if (time && typeof time === 'object' && 'year' in time && 'month' in time && 'day' in time) {
              const t = time as { year: number; month: number; day: number }
              const mm = String(t.month).padStart(2, '0')
              const dd = String(t.day).padStart(2, '0')
              return `${t.year}/${mm}/${dd}`
            }
            return String(time ?? '')
          },
        }
      : undefined,
    timeScale: {
      borderVisible: true,
      timeVisible: !axisDateOnly,
      secondsVisible: false,
      /** 預設 0.5 會讓幾千根日 K 被壓成看不到的寬度 */
      minBarSpacing: 4,
      barSpacing: 8,
      rightOffset: 4,
      tickMarkFormatter: (time: unknown) => {
        // `time` 可能是 UTCTimestamp(number) 或 BusinessDay(object)
        if (typeof time === 'number') {
          return axisDateOnly ? formatTaipeiDateOnlyFromUtcSeconds(time) : formatTaipeiFromUtcSeconds(time)
        }
        if (time && typeof time === 'object' && 'year' in time && 'month' in time && 'day' in time) {
          const t = time as { year: number; month: number; day: number }
          const mm = String(t.month).padStart(2, '0')
          const dd = String(t.day).padStart(2, '0')
          return formatTaipeiBusinessDay(`${t.year}-${mm}-${dd}`)
        }
        return String(time ?? '')
      },
    },
  })
  const variant = props.variant ?? 'candlestick'
  if (variant === 'candlestick') {
    series = chart.addSeries(CandlestickSeries, {
      upColor: '#16a34a',
      downColor: '#dc2626',
      wickUpColor: '#16a34a',
      wickDownColor: '#dc2626',
      borderVisible: false,
    })
  }

  lineSeries = chart.addSeries(LineSeries, {
    color: '#dc2626',
    lineWidth: 2,
    priceLineVisible: false,
    lastValueVisible: true,
  })

  applyTheme()
  render()

  let layoutReady = false
  ro = new ResizeObserver((entries) => {
    const entry = entries[0]
    const w = Math.floor(entry?.contentRect?.width ?? el.clientWidth ?? width)
    chart?.applyOptions({ width: w, height: heightPx.value, autoSize: false })
    // 分頁剛開時寬度常為 0，之後才有寬度；此時需重畫才看得到 K 線
    if (w > 8 && !layoutReady) {
      layoutReady = true
      void nextTick(() => render())
    }
  })
  ro.observe(el)

  const mq = window.matchMedia?.('(prefers-color-scheme: dark)')
  const onChange = () => applyTheme()
  mq?.addEventListener?.('change', onChange)

  onBeforeUnmount(() => {
    mq?.removeEventListener?.('change', onChange)
  })
})

watch(
  () => props.candles,
  () => {
    void nextTick(() => render())
  },
  { deep: true },
)

watch(
  () => props.line,
  () => {
    void nextTick(() => render())
  },
  { deep: true },
)

watch(heightPx, () => {
  const el = containerRef.value
  const width = el?.clientWidth
  chart?.applyOptions({ ...(width ? { width } : {}), height: heightPx.value, autoSize: false })
})

onBeforeUnmount(() => {
  ro?.disconnect()
  ro = null
  chart?.remove()
  chart = null
  series = null
  lineSeries = null
})
</script>

<template>
  <div
    ref="containerRef"
    class="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
  />
</template>

