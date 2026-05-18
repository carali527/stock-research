import { computed, ref, watch } from 'vue'

export type UseScrollChunkRowsOptions = {
  /** 第一次畫幾列；可傳函式讀最新 props */
  chunkSize?: number | (() => number)
  /** 捲到底每次再畫幾列 */
  step?: number | (() => number)
  /** 距離底部多少 px 觸發載入 */
  nearBottomPx?: number
}

function rowSig(r: unknown): string {
  if (r && typeof r === 'object') {
    const o = r as { id?: unknown; key?: unknown }
    if (typeof o.id === 'string') return o.id
    if (typeof o.key === 'string') return o.key
  }
  return ''
}

function resolve(n: number | (() => number) | undefined, fallback: number): number {
  if (typeof n === 'function') return n()
  if (typeof n === 'number' && Number.isFinite(n)) return n
  return fallback
}

/**
 * 長清單：先畫前 N 列，捲到底再往後加 N（不依賴虛擬捲動套件）。
 */
export function useScrollChunkRows<T>(
  getRows: () => readonly T[],
  options: UseScrollChunkRowsOptions = {},
) {
  const nearBottomPx = options.nearBottomPx ?? 80

  const end = ref(0)

  function chunkSize() {
    return resolve(options.chunkSize, 20)
  }

  function step() {
    return resolve(options.step, chunkSize())
  }

  function reset() {
    const rows = getRows()
    end.value = Math.min(chunkSize(), rows.length)
  }

  const signature = computed(() => {
    const rows = getRows()
    if (!rows.length) return '0'
    return `${rows.length}:${rowSig(rows[0])}:${rowSig(rows[rows.length - 1])}`
  })

  watch(signature, reset, { immediate: true })

  function onScroll(e: Event) {
    const el = e.currentTarget as HTMLElement | null
    if (!el) return
    const n = getRows().length
    const st = step()
    if (end.value >= n) return
    if (el.scrollTop + el.clientHeight >= el.scrollHeight - nearBottomPx) {
      end.value = Math.min(n, end.value + st)
      requestAnimationFrame(() => {
        if (el.scrollTop + el.clientHeight >= el.scrollHeight - nearBottomPx && end.value < n) {
          end.value = Math.min(n, end.value + st)
        }
      })
    }
  }

  const displayed = computed(() => getRows().slice(0, end.value))

  return { displayed, onScroll, end }
}
