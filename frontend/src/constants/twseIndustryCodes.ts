/**
 * 臺灣證券產業別代碼 ↔ 名稱（上市／上櫃分類；與 Fugle `industry` 參數一致）
 * @see 證交所／櫃買中心 產業別代碼表
 */
export const TWSE_INDUSTRY_CODE_LABELS: Record<string, string> = {
  '00': '不具產業屬性（ETF／衍生商品等）',
  '01': '水泥工業',
  '02': '食品工業',
  '03': '塑膠工業',
  '04': '紡織纖維',
  '05': '電機機械',
  '06': '電器電纜',
  '08': '玻璃陶瓷',
  '09': '造紙工業',
  '10': '鋼鐵工業',
  '11': '橡膠工業',
  '12': '汽車工業',
  '14': '建材營造',
  '15': '航運業',
  '16': '觀光餐旅',
  '17': '金融保險',
  '18': '貿易百貨',
  '19': '綜合',
  '20': '其他',
  '21': '化學工業',
  '22': '生技醫療業',
  '23': '油電燃氣業',
  '24': '半導體業',
  '25': '電腦及週邊設備業',
  '26': '光電業',
  '27': '通信網路業',
  '28': '電子零組件業',
  '29': '電子通路業',
  '30': '資訊服務業',
  '31': '其他電子業',
  '32': '文化創意業',
  '33': '農業科技業',
  '34': '電子商務',
  '35': '綠能環保',
  '36': '數位雲端',
  '37': '運動休閒',
  '38': '居家生活',
  '80': '管理股票',
}

/** 將純數字代碼正規成兩位字串（例：`1` → `01`，`8` → `08`） */
function normalizeNumericIndustryCode(code: string): string {
  const t = code.trim()
  if (!/^\d+$/.test(t)) return t
  return String(parseInt(t, 10)).padStart(2, '0')
}

/**
 * 產業別欄位顯示：只顯示中文產業名，不顯示前綴代碼（例：`02` →「食品工業」）；空字串回傳空。
 */
export function formatTwseIndustryLabel(rawCode: string): string {
  const trimmed = rawCode.trim()
  if (!trimmed) return ''
  if (!/^\d+$/.test(trimmed)) return trimmed
  const key = normalizeNumericIndustryCode(trimmed)
  const name = TWSE_INDUSTRY_CODE_LABELS[key]
  return name ?? '（未知產業代碼）'
}
