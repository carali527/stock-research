<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useAIStream } from '@/composables/useAIStream'
import { useStockStore } from '@/stores/stockStore'

const PRODUCTION_TEMPLATES: {
  id: string
  label: string
  short: string
  needsSymbol: boolean
}[] = [
  { id: 'candles_short', label: '短線走勢分析（近10日）', short: '分K', needsSymbol: true },
  { id: 'support_resistance', label: '支撐壓力分析', short: '技術位', needsSymbol: true },
  { id: 'trade_flow', label: '主力動向分析', short: '逐筆', needsSymbol: true },
  { id: 'volume_profile', label: '籌碼分布分析', short: '分價量', needsSymbol: true },
  { id: 'trend_strength', label: '趨勢強弱判斷', short: '綜合', needsSymbol: true },
  { id: 'daily_quant', label: '日K走勢（定量）', short: '日K', needsSymbol: true },
]

const followUpQuestion = ref('')
const followUpUsed = ref(false)
const selectedTemplateId = ref<string>('candles_short')
const minuteTimeframe = ref(5)
const { start, stop, output, loading, errorMessage, lastRequestId } = useAIStream()
const stockStore = useStockStore()

const stockSearchQuery = ref('')
const stockPickerOpen = ref(false)
const pickedStock = ref({ symbol: '2330', name: '台積電' })

const selectedTemplate = computed(
  () => PRODUCTION_TEMPLATES.find((t) => t.id === selectedTemplateId.value) ?? PRODUCTION_TEMPLATES[0],
)
const hasOutput = computed(() => output.value.trim().length > 0)
const submitLabel = computed(() => {
  if (loading.value) return '分析中…'
  return '送出分析'
})
const canAskFollowUp = computed(() => hasOutput.value && !followUpUsed.value)

const stockEntries = computed(() => {
  const map = stockStore.nameBySymbol
  return Object.entries(map)
    .map(([symbol, name]) => ({ symbol: symbol.trim(), name: (name || '').trim() }))
    .filter((r) => r.symbol)
    .sort((a, b) => a.symbol.localeCompare(b.symbol, 'zh-Hant'))
})

const filteredStocks = computed(() => {
  const raw = stockSearchQuery.value.trim()
  if (!raw) return []
  const qLower = raw.toLowerCase()
  const out: { symbol: string; name: string }[] = []
  for (const row of stockEntries.value) {
    const symMatch = row.symbol.includes(raw) || row.symbol.toLowerCase().includes(qLower)
    const nameMatch = row.name.includes(raw)
    if (symMatch || nameMatch) {
      out.push(row)
      if (out.length >= 80) break
    }
  }
  return out
})

function pickStockForTemplates(row: { symbol: string; name: string }) {
  pickedStock.value = { symbol: row.symbol, name: row.name }
  stockSearchQuery.value = ''
  stockPickerOpen.value = false
}

function onStockSearchBlur() {
  window.setTimeout(() => {
    stockPickerOpen.value = false
  }, 150)
}

onMounted(() => {
  void stockStore.prefetchStockListIfNeeded()
})

watch(lastRequestId, (id) => {
  if (id && import.meta.env.DEV) {
    console.log('[Research] X-Request-ID（對齊後端日誌）:', id)
  }
})

function buildTemplateData(): Record<string, unknown> {
  const tpl = selectedTemplate.value
  const sym = pickedStock.value.symbol.trim()

  const data: Record<string, unknown> = {
    prefetchFugleMarketData: true,
    marketTemplateId: tpl.id,
    templateSymbol: sym,
  }
  if (tpl.id === 'candles_short') {
    data.templateParams = {
      timeframeMinutes: Math.min(60, Math.max(1, Number(minuteTimeframe.value) || 5)),
    }
  }
  return data
}

async function run() {
  const tpl = selectedTemplate.value
  if (tpl.needsSymbol && !pickedStock.value.symbol.trim()) {
    errorMessage.value = '請先搜尋並選擇股票'
    return
  }
  await stockStore.prefetchStockListIfNeeded().catch(() => {})

  followUpQuestion.value = ''
  followUpUsed.value = false

  await start(tpl.label, buildTemplateData())
}

async function runFollowUp() {
  const tpl = selectedTemplate.value
  const text = followUpQuestion.value.trim()
  if (!text || followUpUsed.value) return
  if (tpl.needsSymbol && !pickedStock.value.symbol.trim()) {
    errorMessage.value = '請先搜尋並選擇股票'
    return
  }

  const data = buildTemplateData()
  data.userNote = `使用者追問：${text}`
  followUpUsed.value = true
  followUpQuestion.value = ''

  await start(tpl.label, data)
}
</script>

<template>
  <main>
    <h1 class="!my-0 text-2xl tracking-tight sm:text-3xl">股票小幫手</h1>

    <section class="mt-6 max-w-3xl">

      <div class="mt-6 grid gap-6">
        <div class="grid gap-2">
          <span class="text-sm font-medium text-slate-900 dark:text-slate-100">搜尋股票（代號或名稱）</span>
          <div class="relative">
            <input
              v-model="stockSearchQuery"
              type="search"
              autocomplete="off"
              class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 placeholder:text-slate-400 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100 dark:placeholder:text-slate-500"
              placeholder="例：2330、台積電…"
              @focus="stockPickerOpen = true"
              @blur="onStockSearchBlur"
            />
            <ul
              v-if="stockPickerOpen && stockSearchQuery.trim() && filteredStocks.length"
              class="absolute left-0 right-0 top-full z-20 mt-1 max-h-56 overflow-auto rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900"
              role="listbox"
            >
              <li
                v-for="row in filteredStocks"
                :key="row.symbol"
                class="cursor-pointer px-3 py-2 text-slate-800 hover:bg-slate-100 dark:text-slate-100 dark:hover:bg-slate-800"
                role="option"
                @mousedown.prevent="pickStockForTemplates(row)"
              >
                <span class="font-mono tabular-nums text-slate-600 dark:text-slate-300">{{ row.symbol }}</span>
                <span class="ml-2">{{ row.name }}</span>
              </li>
            </ul>
          </div>
          <p class="text-xs text-slate-500 dark:text-slate-400">
            目前標的：
            <span class="font-mono font-medium text-slate-800 dark:text-slate-200">{{ pickedStock.symbol }}</span>
            <span v-if="pickedStock.name" class="ml-1">{{ pickedStock.name }}</span>
          </p>
        </div>

        <fieldset class="grid gap-3">
          <legend class="text-sm font-medium text-slate-900 dark:text-slate-100">分析模板</legend>
          <div class="grid gap-2 sm:grid-cols-2">
            <label
              v-for="t in PRODUCTION_TEMPLATES"
              :key="t.id"
              class="flex cursor-pointer gap-2 rounded-lg border border-slate-200 p-3 text-sm has-[:checked]:border-slate-900 has-[:checked]:bg-slate-50 dark:border-slate-700 dark:has-[:checked]:border-slate-300 dark:has-[:checked]:bg-slate-900/80"
            >
              <input v-model="selectedTemplateId" type="radio" class="mt-0.5 shrink-0" :value="t.id" />
              <span>
                <span class="font-medium text-slate-900 dark:text-slate-100">{{ t.label }}</span>
              </span>
            </label>
          </div>
          <div v-if="selectedTemplateId === 'candles_short'" class="flex flex-wrap items-center gap-2 text-sm">
            <label class="text-slate-700 dark:text-slate-300">分K 週期</label>
            <select
              v-model.number="minuteTimeframe"
              class="rounded-md border border-slate-200 bg-white px-2 py-1.5 dark:border-slate-600 dark:bg-slate-950"
            >
              <option :value="1">1 分</option>
              <option :value="3">3 分</option>
              <option :value="5">5 分</option>
              <option :value="10">10 分</option>
              <option :value="15">15 分</option>
              <option :value="30">30 分</option>
              <option :value="60">60 分</option>
            </select>
          </div>
        </fieldset>

        <div class="flex flex-wrap items-center gap-3">
          <button
            type="button"
            class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
            :disabled="loading"
            @click="run"
          >
            {{ submitLabel }}
          </button>
          <button
            v-if="loading"
            type="button"
            class="rounded-lg px-4 py-2 text-sm text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-900"
            @click="stop"
          >
            停止
          </button>
          <span v-if="errorMessage" class="text-sm text-red-700 dark:text-red-300">{{ errorMessage }}</span>
        </div>

        <div
          v-if="output"
          class="rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-800 dark:border-slate-800 dark:bg-slate-950 dark:text-slate-200"
        >
          <div class="whitespace-pre-wrap">{{ output }}</div>
        </div>

        <div v-if="canAskFollowUp" class="grid gap-2">
          <label class="grid gap-2">
            <span class="text-sm font-medium text-slate-900 dark:text-slate-100">追問這次分析</span>
            <textarea
              v-model="followUpQuestion"
              rows="2"
              class="w-full rounded-lg border border-slate-200 bg-white px-3 py-2 text-sm text-slate-900 dark:border-slate-700 dark:bg-slate-950 dark:text-slate-100"
              placeholder="例：支撐價怎麼算？成交量有放大嗎？"
            />
          </label>

          <div class="flex flex-wrap items-center gap-3">
            <button
              type="button"
              class="rounded-lg bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-800 disabled:cursor-not-allowed disabled:opacity-60 dark:bg-slate-100 dark:text-slate-900 dark:hover:bg-white"
              :disabled="!followUpQuestion.trim()"
              @click="runFollowUp"
            >
              送出追問
            </button>
          </div>
        </div>

        <p v-else-if="followUpUsed" class="text-sm text-slate-500 dark:text-slate-400">
          已完成一次追問；如需換角度分析，請重新送出標準分析。
        </p>
      </div>
    </section>
  </main>
</template>
