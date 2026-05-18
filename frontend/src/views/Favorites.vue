<script setup lang="ts">
import { computed } from 'vue'
import { useStockStore } from '@/stores/stockStore'

const stockStore = useStockStore()

const items = computed(() =>
  stockStore.favoriteItems.filter((it) => it.symbol).map((it) => ({ ...it, label: it.name ? `${it.name}（${it.symbol}）` : it.symbol })),
)
</script>

<template>
  <main>
    <div class="mb-6 flex flex-wrap items-end justify-between gap-4">
      <div>
        <h1 class="!my-0 hidden text-2xl tracking-tight sm:text-3xl md:block">自選清單</h1>
        <p class="mt-2 text-sm text-slate-500 dark:text-slate-400">已收藏：{{ items.length }} 檔</p>
      </div>
    </div>

    <section class="max-w-3xl">
      <div v-if="!items.length" class="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-600 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-300">
        目前沒有自選股票。到「股價日成交資訊」頁面點右側星星即可加入。
      </div>

      <ul v-else class="grid gap-2">
        <li
          v-for="it in items"
          :key="it.symbol"
          class="flex items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm dark:border-slate-800 dark:bg-slate-950"
        >
          <RouterLink
            :to="{ name: 'stockPrice', params: { id: it.symbol } }"
            class="min-w-0 flex-1 truncate font-medium text-slate-900 no-underline hover:underline dark:text-slate-100"
            :title="it.label"
          >
            {{ it.label }}
          </RouterLink>

          <button
            type="button"
            class="shrink-0 rounded-md px-2 py-1 text-xs text-slate-600 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-900"
            @click="stockStore.removeFavorite(it.symbol)"
          >
            移除
          </button>
        </li>
      </ul>
    </section>
  </main>
</template>

