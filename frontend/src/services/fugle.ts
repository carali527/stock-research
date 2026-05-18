import axios, { type AxiosInstance } from 'axios'
import { formatTwseIndustryLabel } from '@/constants/twseIndustryCodes'
import type { TaiwanStockListItem } from '@/types/stock'
import { ApiError, normalizeAxiosError } from '@/services/errors'
import { toYmdTaipei } from '@/utils/date'

export type FugleIntradayTickerRow = {
  symbol: string
  name: string
  /** 若單筆 ticker 帶產業代碼則優先使用，否則用回應根層的 `industry` */
  industry?: string
}

export type FugleIntradayTickersResponse = {
  date: string
  type: string
  exchange: string
  market?: string
  industry?: string
  data: FugleIntradayTickerRow[]
}

/** 後端 `/fugle` 代理至 Fugle；金鑰僅在伺服器 `FUGLE_API_KEY`，前端零 secret。 */
const FUGLE_PATH = '/marketdata/v1.0/stock/intraday/tickers'
const FUGLE_BASE = '/fugle'

let fugleClient: AxiosInstance | null = null

function getFugleClient(): AxiosInstance {
  if (!fugleClient) {
    fugleClient = axios.create({
      baseURL: FUGLE_BASE,
      timeout: 60_000,
      headers: {
        Accept: 'application/json',
      },
    })
  }
  return fugleClient
}

function assertFugleTickers(body: unknown): FugleIntradayTickersResponse {
  if (!body || typeof body !== 'object') {
    throw new ApiError('Fugle returned empty response', { status: 0, payload: body })
  }
  const b = body as FugleIntradayTickersResponse
  if (!Array.isArray(b.data)) {
    throw new ApiError('Fugle tickers: missing data array', { status: 0, payload: body })
  }
  return b
}

function pickIndustry(d: FugleIntradayTickerRow, res: FugleIntradayTickersResponse): string {
  const fromRow = d.industry != null ? String(d.industry).trim() : ''
  if (fromRow) return fromRow
  const fromRoot = res.industry != null ? String(res.industry).trim() : ''
  return fromRoot
}

function mapToStockListItems(res: FugleIntradayTickersResponse): TaiwanStockListItem[] {
  return res.data
    .filter((d) => d.symbol)
    .map((d) => {
      const name = (d.name ?? '').trim()
      const label = formatTwseIndustryLabel(pickIndustry(d, res))
      return {
        stockId: d.symbol,
        stockName: name || d.symbol || '（無名稱）',
        industry: label || '—',
        type: res.type,
        date: res.date,
      }
    })
}

let listCache: { rows: TaiwanStockListItem[]; fetchedAt: number; dateKey: string } | null = null
const LIST_TTL_MS = 60_000

/**
 * 股票總覽：只呼叫一次 Fugle intraday tickers，query 帶 `type=EQUITY`、`exchange=TWSE`、`date=當日（台北）`。
 * 開發時網址形如 `.../tickers?type=EQUITY&exchange=TWSE&date=YYYY-MM-DD`（同源 + Vite proxy）。
 */
export async function getStockListFromFugle(): Promise<TaiwanStockListItem[]> {
  const dateKey = toYmdTaipei(new Date())
  const now = Date.now()
  if (listCache && listCache.dateKey === dateKey && now - listCache.fetchedAt < LIST_TTL_MS) {
    return listCache.rows
  }

  try {
    const { data } = await getFugleClient().get<unknown>(FUGLE_PATH, {
      params: { type: 'EQUITY', exchange: 'TWSE', date: dateKey },
    })
    const rows = mapToStockListItems(assertFugleTickers(data))
    listCache = { rows, fetchedAt: Date.now(), dateKey }
    if (import.meta.env.DEV) {
      // 僅單一交易日 date=YYYY-MM-DD，非多日歷史；與 /intraday/ticker/{symbol} 亦為當日快照
      console.info(`[Fugle] intraday/tickers date=${dateKey} → ${rows.length} 檔（1 個交易日）`)
    }
    return rows
  } catch (e) {
    throw normalizeAxiosError(e)
  }
}

/** Historical：`GET /marketdata/v1.0/stock/historical/candles/{symbol}`。日／週／月可帶 `from`／`to`；分 K 近 30 日且無法指定區間。 */
export type FugleHistoricalCandleRow = {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  turnover?: number
  change?: number
}

export type FugleHistoricalCandlesResponse = {
  symbol: string
  type: string
  exchange: string
  market?: string
  timeframe: string
  data: FugleHistoricalCandleRow[]
}

const FUGLE_HISTORICAL_CANDLES_PATH = '/marketdata/v1.0/stock/historical/candles'

function assertFugleHistoricalCandles(body: unknown): FugleHistoricalCandlesResponse {
  if (!body || typeof body !== 'object') {
    throw new ApiError('Fugle historical candles: empty response', { status: 0, payload: body })
  }
  const b = body as FugleHistoricalCandlesResponse
  if (!b.symbol) {
    throw new ApiError('Fugle historical candles: missing symbol', { status: 0, payload: body })
  }
  if (!Array.isArray(b.data)) {
    throw new ApiError('Fugle historical candles: missing data array', { status: 0, payload: body })
  }
  return b
}

/** 本地日曆 yyyy-MM-dd → Date（僅用於區間計算） */
function parseYmdLocal(ymd: string): Date {
  const s = ymd.trim().slice(0, 10)
  const [y, m, d] = s.split('-').map((x) => Number.parseInt(x, 10))
  if (!Number.isFinite(y) || !Number.isFinite(m) || !Number.isFinite(d)) return new Date(NaN)
  return new Date(y, m - 1, d)
}

function formatYmdLocal(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/** 含首尾兩日，最多 `maxInclusiveDays` 天一段（Fugle 單次 from/to 須在約 1 年內，否則常回 400） */
function splitHistoricalRange(fromYmd: string, toYmd: string, maxInclusiveDays: number): Array<{ from: string; to: string }> {
  let start = parseYmdLocal(fromYmd)
  const end = parseYmdLocal(toYmd)
  if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime()) || start > end) return []

  const chunks: Array<{ from: string; to: string }> = []
  while (start <= end) {
    const chunkEnd = new Date(start)
    chunkEnd.setDate(chunkEnd.getDate() + maxInclusiveDays - 1)
    if (chunkEnd > end) chunkEnd.setTime(end.getTime())
    chunks.push({ from: formatYmdLocal(start), to: formatYmdLocal(chunkEnd) })
    start = new Date(chunkEnd)
    start.setDate(start.getDate() + 1)
  }
  return chunks
}

function inclusiveDaySpan(fromYmd: string, toYmd: string): number {
  const a = parseYmdLocal(fromYmd)
  const b = parseYmdLocal(toYmd)
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime()) || a > b) return 0
  return Math.floor((b.getTime() - a.getTime()) / 86_400_000) + 1
}

/** 單次 HTTP，不拆段 */
async function getHistoricalCandlesFromFugleOnce(params: {
  symbol: string
  timeframe: string | number
  from?: string
  to?: string
  sort?: 'asc' | 'desc'
  adjusted?: boolean | 'true' | 'false'
  fields?: string
  signal?: AbortSignal
}): Promise<FugleHistoricalCandlesResponse> {
  const symbol = String(params.symbol ?? '').trim()
  if (!symbol) throw new ApiError('Fugle historical candles: missing symbol', { status: 0 })

  const tf = String(params.timeframe)
  if (!tf) throw new ApiError('Fugle historical candles: missing timeframe', { status: 0 })

  try {
    const { data } = await getFugleClient().get<unknown>(`${FUGLE_HISTORICAL_CANDLES_PATH}/${encodeURIComponent(symbol)}`, {
      params: {
        timeframe: tf,
        ...(params.from ? { from: params.from } : {}),
        ...(params.to ? { to: params.to } : {}),
        ...(params.sort ? { sort: params.sort } : {}),
        ...(params.adjusted != null ? { adjusted: String(params.adjusted) } : {}),
        ...(params.fields ? { fields: params.fields } : { fields: 'open,high,low,close,volume' }),
      },
      ...(params.signal ? { signal: params.signal } : {}),
    })
    return assertFugleHistoricalCandles(data)
  } catch (e) {
    throw normalizeAxiosError(e)
  }
}

/**
 * 歷史 K 線。`timeframe`：1/3/5/10/15/30/60 分、D 日、W 週、M 月。
 * 日／週／月可傳 `from`、`to`（yyyy-MM-dd）；**單次查詢區間須在約 1 年內**（文件），否則 400 — 本函式會自動拆成多段後合併。
 * 分 K 不支援日期區間（API 固定近 30 日），勿帶 from/to。
 */
export async function getHistoricalCandlesFromFugle(params: {
  symbol: string
  /** 1 | 3 | 5 | 10 | 15 | 30 | 60 | D | W | M */
  timeframe: string | number
  from?: string
  to?: string
  sort?: 'asc' | 'desc'
  /** 還原股價 */
  adjusted?: boolean | 'true' | 'false'
  /** 預設 open,high,low,close,volume */
  fields?: string
  signal?: AbortSignal
}): Promise<FugleHistoricalCandlesResponse> {
  const symbol = String(params.symbol ?? '').trim()
  if (!symbol) throw new ApiError('Fugle historical candles: missing symbol', { status: 0 })

  const tf = String(params.timeframe)
  if (!tf) throw new ApiError('Fugle historical candles: missing timeframe', { status: 0 })

  const from = params.from?.trim().slice(0, 10)
  const to = params.to?.trim().slice(0, 10)
  const isDwm = tf === 'D' || tf === 'W' || tf === 'M'

  if (!from || !to || !isDwm) {
    return getHistoricalCandlesFromFugleOnce(params)
  }

  /** Fugle：單次 from～to 超過 365 天常回 400 */
  const MAX_DAYS = 365
  if (inclusiveDaySpan(from, to) <= MAX_DAYS) {
    return getHistoricalCandlesFromFugleOnce(params)
  }

  const chunks = splitHistoricalRange(from, to, MAX_DAYS)
  if (chunks.length === 0) {
    return getHistoricalCandlesFromFugleOnce(params)
  }

  const fieldParams = params.fields ? { fields: params.fields } : { fields: 'open,high,low,close,volume' as const }
  const sig = params.signal
  const results = await Promise.all(
    chunks.map((ch) =>
      getHistoricalCandlesFromFugleOnce({
        symbol,
        timeframe: tf,
        from: ch.from,
        to: ch.to,
        sort: 'asc',
        adjusted: params.adjusted,
        ...fieldParams,
        ...(sig ? { signal: sig } : {}),
      }),
    ),
  )

  const byDate = new Map<string, FugleHistoricalCandleRow>()
  for (const res of results) {
    for (const row of res.data) {
      const key = String(row.date).trim().slice(0, 10)
      if (key) byDate.set(key, row)
    }
  }
  const asc = [...byDate.values()].sort((a, b) => String(a.date).localeCompare(String(b.date)))
  const data = params.sort === 'desc' ? [...asc].reverse() : asc
  const first = results[0]
  return {
    symbol: first.symbol,
    type: first.type,
    exchange: first.exchange,
    market: first.market,
    timeframe: first.timeframe,
    data,
  }
}
