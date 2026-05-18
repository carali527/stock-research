import { apiClient } from './client'

export type YahooQuote = {
  symbol: string
  name: string
  price: number | null
  change: number | null
  changePercent: number | null
  asOf: string | null
  sourceUrl: string
}

export async function fetchYahooQuote(symbol: string, opts?: { signal?: AbortSignal }): Promise<YahooQuote> {
  const res = await apiClient.get(`/api/yahoo/quote/${encodeURIComponent(symbol)}`, { signal: opts?.signal })
  return res.data as YahooQuote
}

export type YahooListedHotRankItem = { symbol: string; name: string }

export async function fetchYahooListedHotRank(): Promise<{ items: YahooListedHotRankItem[]; sourceUrl: string }> {
  const res = await apiClient.get('/api/yahoo/listed-hot-rank')
  return res.data as { items: YahooListedHotRankItem[]; sourceUrl: string }
}

export async function fetchYahooListedChangeUpRank(): Promise<{ items: YahooListedHotRankItem[]; sourceUrl: string }> {
  const res = await apiClient.get('/api/yahoo/listed-change-up-rank')
  return res.data as { items: YahooListedHotRankItem[]; sourceUrl: string }
}

