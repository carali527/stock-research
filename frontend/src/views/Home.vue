<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { onMounted, ref } from 'vue'
import { fetchYahooListedChangeUpRank, fetchYahooListedHotRank } from '@/services/yahoo'

const hotItems = ref<Array<{ symbol: string; name: string }>>([])
const changeUpItems = ref<Array<{ symbol: string; name: string }>>([])
const hotLoading = ref(false)
const changeUpLoading = ref(false)

onMounted(async () => {
  hotLoading.value = true
  try {
    const res = await fetchYahooListedHotRank()
    hotItems.value = Array.isArray(res.items) ? res.items : []
  } catch {
    hotItems.value = []
  } finally {
    hotLoading.value = false
  }

  changeUpLoading.value = true
  try {
    const res = await fetchYahooListedChangeUpRank()
    changeUpItems.value = Array.isArray(res.items) ? res.items : []
  } catch {
    changeUpItems.value = []
  } finally {
    changeUpLoading.value = false
  }
})
</script>

<template>
  <main>
    <section class="mt-10">
      <h2 class="text-base font-semibold text-slate-900 dark:text-slate-100">上市成交量排行</h2>
      <div class="mt-3 rounded-lg border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-950">
        <div v-if="hotLoading" class="text-slate-500 dark:text-slate-400">載入中…</div>
        <div v-else-if="!hotItems.length" class="text-slate-500 dark:text-slate-400">暫時無法取得資料。</div>
        <ul v-else class="flex flex-wrap gap-2">
          <li v-for="it in hotItems" :key="it.symbol">
            <RouterLink
              :to="{ name: 'stockPrice', params: { id: it.symbol }, query: { name: it.name } }"
              class="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-900 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-50 dark:hover:bg-slate-700"
            >
              {{ it.name }}（{{ it.symbol }}）
            </RouterLink>
          </li>
        </ul>
      </div>
    </section>

    <section class="mt-8">
      <h2 class="text-base font-semibold text-slate-900 dark:text-slate-100">上市漲幅排行</h2>
      <div class="mt-3 rounded-lg border border-slate-200 bg-white p-4 text-sm dark:border-slate-800 dark:bg-slate-950">
        <div v-if="changeUpLoading" class="text-slate-500 dark:text-slate-400">載入中…</div>
        <div v-else-if="!changeUpItems.length" class="text-slate-500 dark:text-slate-400">暫時無法取得資料。</div>
        <ul v-else class="flex flex-wrap gap-2">
          <li v-for="it in changeUpItems" :key="it.symbol">
            <RouterLink
              :to="{ name: 'stockPrice', params: { id: it.symbol }, query: { name: it.name } }"
              class="inline-flex items-center rounded-full bg-slate-100 px-3 py-1 text-sm font-medium text-slate-900 hover:bg-slate-200 dark:bg-slate-800 dark:text-slate-50 dark:hover:bg-slate-700"
            >
              {{ it.name }}（{{ it.symbol }}）
            </RouterLink>
          </li>
        </ul>
      </div>
    </section>
  </main>
</template>
