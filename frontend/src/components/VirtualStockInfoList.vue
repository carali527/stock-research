<script setup lang="ts">
import { computed } from 'vue'
import { useScrollChunkRows } from '@/composables/useScrollChunkRows'
import type { TaiwanStockListItem } from '@/types/stock'

type Row = TaiwanStockListItem & { id: string }

const props = withDefaults(
  defineProps<{
    rows: Row[]
    /** 視窗內約略可見列數（捲動區高度） */
    visibleRows?: number
    height?: number
    rowHeight?: number
  }>(),
  { visibleRows: 20 },
)

const emit = defineEmits<{
  (e: 'select', stockId: string): void
}>()

const rowHeightPx = computed(() => props.rowHeight ?? 58)

const { displayed, onScroll } = useScrollChunkRows<Row>(() => props.rows, {
  chunkSize: () => props.visibleRows ?? 20,
  step: () => props.visibleRows ?? 20,
})

const viewportStyle = computed(() => {
  const h = props.height ?? (props.visibleRows ?? 20) * rowHeightPx.value
  if (props.height != null) return { maxHeight: `${h}px` }
  return { maxHeight: `min(${h}px, calc(100svh - 14rem))` }
})

</script>

<template>
  <div
    class="flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
  >
    <div
      class="min-h-0 w-full min-w-0 flex-1 overflow-auto overscroll-contain [scrollbar-gutter:stable]"
      :style="viewportStyle"
      @scroll.passive="onScroll"
    >
      <div class="min-w-max">
        <div
          class="sticky top-0 z-10 flex items-center gap-3 border-b border-slate-100 bg-white px-3 py-2 text-xs text-slate-500 dark:border-slate-900 dark:bg-slate-950 dark:text-slate-400"
        >
          <div class="w-64 shrink-0">股票名稱/代號</div>
          <div class="min-w-[12rem] shrink-0 whitespace-nowrap pr-3 sm:min-w-0 sm:flex-1">產業別</div>
        </div>

        <div
          v-for="item in displayed"
          :key="item.id"
          class="flex items-center gap-3 border-b border-slate-100 px-3 text-sm leading-tight text-slate-800 dark:border-slate-900 dark:text-slate-200"
          :style="{ minHeight: `${rowHeightPx}px` }"
        >
          <button
            type="button"
            class="w-64 shrink-0 cursor-pointer bg-transparent p-0 text-left"
            @click="emit('select', item.stockId)"
          >
            <div class="truncate text-[15px] font-semibold text-blue-700 dark:text-blue-300">
              {{ item.stockName }}
            </div>
            <div class="truncate font-mono text-xs tabular-nums text-slate-400 dark:text-slate-500">
              {{ item.stockId }}
            </div>
          </button>
          <div
            class="min-w-[12rem] shrink-0 whitespace-nowrap pr-3 text-slate-600 dark:text-slate-300 sm:min-w-0 sm:flex-1 sm:truncate"
          >
            {{ item.industry }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
