import { defineStore } from 'pinia'
import { computed, ref } from 'vue'
import { getStockListFromFugle } from '@/services/fugle'

/** 個股行情／詳情（骨架，之後接上真實 API path） */
export const useStockStore = defineStore('stock', () => {
  const nameBySymbol = ref<Record<string, string>>({})
  const listFetchedAt = ref<number | null>(null)
  const listDateKey = ref<string | null>(null)

  const STORAGE_KEY = 'stock-research:twse-stock-list:v1'
  const STORAGE_MAX_AGE_MS = 24 * 60 * 60 * 1000

  const FAVORITES_KEY = 'stock-research:favorites:v1'
  const favoriteSymbols = ref<string[]>([])

  function getName(symbol: string) {
    return nameBySymbol.value[symbol] || ''
  }

  function setName(symbol: string, name: string) {
    const s = (symbol || '').trim()
    const n = (name || '').trim()
    if (!s || !n) return
    nameBySymbol.value = { ...nameBySymbol.value, [s]: n }
  }

  function hydrateFromLocalStorage() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as { fetchedAt?: unknown; dateKey?: unknown; nameBySymbol?: unknown }
      const fetchedAt = typeof parsed.fetchedAt === 'number' ? parsed.fetchedAt : null
      const dateKey = typeof parsed.dateKey === 'string' ? parsed.dateKey : null
      const map = parsed.nameBySymbol
      if (!fetchedAt || !dateKey || !map || typeof map !== 'object') return
      if (Date.now() - fetchedAt > STORAGE_MAX_AGE_MS) return
      nameBySymbol.value = map as Record<string, string>
      listFetchedAt.value = fetchedAt
      listDateKey.value = dateKey
    } catch {
      /* ignore */
    }
  }

  function persistToLocalStorage() {
    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          fetchedAt: listFetchedAt.value,
          dateKey: listDateKey.value,
          nameBySymbol: nameBySymbol.value,
        }),
      )
    } catch {
      /* ignore */
    }
  }

  function hydrateFavoritesFromLocalStorage() {
    try {
      const raw = localStorage.getItem(FAVORITES_KEY)
      if (!raw) return
      const parsed = JSON.parse(raw) as unknown
      if (!Array.isArray(parsed)) return
      favoriteSymbols.value = parsed.map((x) => String(x || '').trim()).filter(Boolean)
    } catch {
      /* ignore */
    }
  }

  function persistFavoritesToLocalStorage() {
    try {
      localStorage.setItem(FAVORITES_KEY, JSON.stringify(favoriteSymbols.value))
    } catch {
      /* ignore */
    }
  }

  function isFavorite(symbol: string) {
    const s = (symbol || '').trim()
    if (!s) return false
    return favoriteSymbols.value.includes(s)
  }

  function toggleFavorite(symbol: string) {
    const s = (symbol || '').trim()
    if (!s) return
    const cur = favoriteSymbols.value
    if (cur.includes(s)) {
      favoriteSymbols.value = cur.filter((x) => x !== s)
    } else {
      favoriteSymbols.value = [s, ...cur.filter((x) => x !== s)]
    }
    persistFavoritesToLocalStorage()
  }

  function removeFavorite(symbol: string) {
    const s = (symbol || '').trim()
    if (!s) return
    favoriteSymbols.value = favoriteSymbols.value.filter((x) => x !== s)
    persistFavoritesToLocalStorage()
  }

  const favoriteItems = computed(() =>
    favoriteSymbols.value.map((s) => ({
      symbol: s,
      name: getName(s),
    })),
  )

  function normalizeTwSymbol(raw: string): string {
    const t = raw.trim()
    if (!t) return ''
    const i = t.indexOf('.')
    if (i > 0) return t.slice(0, i)
    return t
  }

  /** 常見俗名（清單尚未載入或名稱與行情略有出入時補強） */
  const KNOWN_ALIASES: Record<string, string> = {
    台積電: '2330',
    台積電公司: '2330',
    聯發科: '2454',
    鴻海: '2317',
    大立光: '3008',
    國泰金: '2882',
    富邦金: '2881',
    元大台灣50: '0050',
    台灣50: '0050',
  }

  /**
   * 從使用者問題中盡量抽出台股代號：數字代碼 + 俗名 + Fugle 清單名稱對照。
   */
  function resolveSymbolsFromQuestion(question: string): { symbols: string[]; notes: string[] } {
    const symbols = new Set<string>()
    const notes: string[] = []
    const q = (question || '').trim()
    if (!q) return { symbols: [], notes: [] }

    const codeRe = /\b(\d{4,6}[A-Za-z]?)\b/g
    let m: RegExpExecArray | null
    while ((m = codeRe.exec(q)) !== null) {
      const sym = normalizeTwSymbol(m[1])
      if (sym) symbols.add(sym)
    }

    for (const [alias, sym] of Object.entries(KNOWN_ALIASES)) {
      if (q.includes(alias)) {
        symbols.add(sym)
        notes.push(`${alias}→${sym}`)
      }
    }

    const entries = Object.entries(nameBySymbol.value).sort((a, b) => (b[1] || '').length - (a[1] || '').length)
    for (const [sym, name] of entries) {
      const nm = (name || '').trim()
      if (nm.length < 2) continue
      if (q.includes(nm)) {
        const s = normalizeTwSymbol(sym)
        if (s) {
          symbols.add(s)
          notes.push(`${nm}→${s}`)
        }
      }
    }

    return { symbols: [...symbols].sort(), notes }
  }

  async function prefetchStockListIfNeeded() {
    // 先嘗試用 localStorage（不打 API）
    if (!Object.keys(nameBySymbol.value).length) hydrateFromLocalStorage()
    // 若已有資料且不過期，就不再打 API
    if (Object.keys(nameBySymbol.value).length && listFetchedAt.value && Date.now() - listFetchedAt.value < STORAGE_MAX_AGE_MS) return

    // 需要時才抓一次 Fugle 股票總覽（用來建立 symbol → name）
    const rows = await getStockListFromFugle()
    const map: Record<string, string> = {}
    for (const r of rows) {
      const id = (r.stockId || '').trim()
      const nm = (r.stockName || '').trim()
      if (!id || !nm) continue
      map[id] = nm
    }
    nameBySymbol.value = map
    listFetchedAt.value = Date.now()
    listDateKey.value = rows[0]?.date || null
    persistToLocalStorage()
  }

  return {
    nameBySymbol,
    listFetchedAt,
    listDateKey,
    favoriteSymbols,
    favoriteItems,
    getName,
    setName,
    hydrateFromLocalStorage,
    prefetchStockListIfNeeded,
    hydrateFavoritesFromLocalStorage,
    isFavorite,
    toggleFavorite,
    removeFavorite,
    normalizeTwSymbol,
    resolveSymbolsFromQuestion,
  }
})
