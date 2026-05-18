/** 股票清單列（例：Fugle tickers 對應欄位） */
export type TaiwanStockListItem = {
  stockId: string
  stockName: string
  /** 產業別欄位：由 API 的 `industry` 代碼對照為中文產業名（不顯示數字代碼前綴） */
  industry: string
  type: string
  date: string
}

/** K 線／成交列 */
export type TaiwanStockPriceBar = {
  date: string
  /** 分 K 用 minute；日 K 為空字串 */
  minute: string
  stockId: string
  open: number
  high: number
  low: number
  close: number
  volume: number
  amount: number
  turnover: number
  spread: number
}
