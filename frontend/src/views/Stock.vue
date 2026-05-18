<script setup lang="ts">
import { computed, onMounted, ref, shallowRef } from 'vue'
import { useRouter } from 'vue-router'
import { getStockListFromFugle } from '@/services/fugle'
import type { TaiwanStockListItem } from '@/types/stock'
import VirtualStockInfoList from '@/components/VirtualStockInfoList.vue'
import type { ApiError } from '@/services/errors'
import { userMessageForApiError } from '@/utils/userFacingErrors'

const isDev = import.meta.env.DEV

const router = useRouter()

const loading = ref(false)
const lastError = ref<ApiError | null>(null)
/** 大陣列用 shallow，避免每個欄位都做深層響應式（捲動較順） */
const list = shallowRef<TaiwanStockListItem[]>([])
const query = ref('')

const filteredList = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return list.value
  return list.value.filter((r) => {
    const hay = `${r.stockId} ${r.stockName} ${r.industry}`.toLowerCase()
    return hay.includes(q)
  })
})

/** 全量列傳給子元件，由子元件分段渲染（捲到底再加一批） */
const listRows = computed(() =>
  filteredList.value.map((r, i) => ({
    ...r,
    id: `${i}-${r.stockId}`,
  })),
)

async function loadList() {
  loading.value = true
  lastError.value = null
  try {
    list.value = await getStockListFromFugle()
  } catch (e) {
    lastError.value = e as ApiError
    list.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  void loadList()
})

function goPrice(stockId: string) {
  const row = list.value.find((r) => r.stockId === stockId)
  void router.push({ name: 'stockPrice', params: { id: stockId }, query: row?.stockName ? { name: row.stockName } : {} })
}
</script>

<template>
  <main class="flex min-h-0 min-w-0 flex-1 flex-col">
    <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="!my-0 text-2xl tracking-tight sm:text-3xl">股票總覽</h1>
      </div>

      <div class="flex flex-wrap items-end gap-3">
        <label class="grid gap-1 text-xs text-slate-500 dark:text-slate-400">
          Search
          <input
            v-model="query"
            type="search"
            placeholder="代號 / 名稱 / 產業別"
            class="h-10 w-64 rounded-md border border-slate-200 bg-white px-3 text-sm text-slate-900 shadow-sm outline-none placeholder:text-slate-400 focus:border-blue-400 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-600"
          />
        </label>
      </div>
    </div>

    <div
      v-if="lastError"
      class="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800 dark:border-red-900/60 dark:bg-red-950/40 dark:text-red-200"
    >
      {{ userMessageForApiError(lastError) }}
      <span v-if="isDev" class="opacity-70">（HTTP {{ lastError.status }}）</span>
      <pre
        v-if="isDev && lastError.payload"
        class="mt-2 overflow-auto rounded bg-red-100/60 p-2 text-xs text-red-900 dark:bg-red-950/60 dark:text-red-100"
      >{{ JSON.stringify(lastError.payload, null, 2) }}</pre>
    </div>

    <section class="flex min-h-0 flex-1 flex-col gap-3">
      <div v-if="list.length" class="flex min-h-0 flex-1 flex-col gap-2">
        <div class="flex shrink-0 items-baseline justify-between text-xs text-slate-500 dark:text-slate-400">
          <span>
            清單筆數：{{ filteredList.length }}
            <span v-if="query.trim()" class="opacity-70">（已套用搜尋）</span>
          </span>
        </div>
        <div class="min-h-0 flex-1">
          <VirtualStockInfoList class="h-full min-h-0" :rows="listRows" :visible-rows="20" @select="goPrice" />
        </div>
      </div>
      <div v-else class="text-sm text-slate-500 dark:text-slate-400">
        Loading…
      </div>
    </section>
  </main>
</template>
