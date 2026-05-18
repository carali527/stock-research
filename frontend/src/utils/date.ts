/** 台北時區 `YYYY-MM-DD` */
export function toYmdTaipei(d: Date): string {
  return d.toLocaleDateString('en-CA', { timeZone: 'Asia/Taipei' })
}
