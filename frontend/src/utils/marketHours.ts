const TAIWAN_MARKET_OPEN_MINUTE = 9 * 60
const TAIWAN_MARKET_CLOSE_MINUTE = 13 * 60 + 30

export function getTaipeiWeekdayAndMinute(date: Date): { weekday: string; minuteOfDay: number } | null {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'Asia/Taipei',
    weekday: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(date)

  const weekday = parts.find((p) => p.type === 'weekday')?.value.toLowerCase()
  const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? NaN)
  const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? NaN)
  if (!weekday || !Number.isFinite(hour) || !Number.isFinite(minute)) return null
  return { weekday, minuteOfDay: hour * 60 + minute }
}

export function isTaiwanMarketOpen(date = new Date()): boolean {
  const taipei = getTaipeiWeekdayAndMinute(date)
  if (!taipei) return false
  const isWeekday =
    taipei.weekday.startsWith('mon') ||
    taipei.weekday.startsWith('tue') ||
    taipei.weekday.startsWith('wed') ||
    taipei.weekday.startsWith('thu') ||
    taipei.weekday.startsWith('fri')
  if (!isWeekday) return false
  return taipei.minuteOfDay >= TAIWAN_MARKET_OPEN_MINUTE && taipei.minuteOfDay <= TAIWAN_MARKET_CLOSE_MINUTE
}
