<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useScrollChunkRows } from '@/composables/useScrollChunkRows'
import type { TaiwanStockPriceBar } from '@/types/stock'

type Row = TaiwanStockPriceBar & { key: string }

const props = defineProps<{
  rows: Row[]
  height?: number
  rowHeight?: number
}>()

const heightPx = computed(() => props.height ?? 560)
const rowHeightPx = computed(() => props.rowHeight ?? 40)
const visibleRows = computed(() => Math.max(8, Math.floor(heightPx.value / rowHeightPx.value)))

const { displayed, onScroll } = useScrollChunkRows<Row>(() => props.rows, {
  chunkSize: () => visibleRows.value,
  step: () => visibleRows.value,
})

const viewportStyle = computed(() => ({ maxHeight: `${heightPx.value}px` }))

const scrollViewportRef = ref<HTMLElement | null>(null)

/** 一般滾輪預設只動直向；寬表需橫向時：Shift+滾輪（系統預設）或捲到直向頂／底後繼續滾會轉成橫向。 */
function onWheelViewport(e: WheelEvent) {
  const el = scrollViewportRef.value
  if (!el || e.shiftKey) return
  if (el.scrollWidth <= el.clientWidth + 1) return

  const dx = e.deltaX
  const dy = e.deltaY
  if (Math.abs(dx) > Math.abs(dy)) return

  const canY = el.scrollHeight > el.clientHeight + 2
  if (!canY) {
    el.scrollLeft += dy
    e.preventDefault()
    return
  }

  const goingDown = dy > 0
  const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 2
  const atTop = el.scrollTop <= 0
  if ((goingDown && atBottom) || (!goingDown && atTop)) {
    el.scrollLeft += dy
    e.preventDefault()
  }
}

let wheelEl: HTMLElement | null = null
onMounted(() => {
  wheelEl = scrollViewportRef.value
  wheelEl?.addEventListener('wheel', onWheelViewport, { passive: false })
})
onBeforeUnmount(() => {
  wheelEl?.removeEventListener('wheel', onWheelViewport)
  wheelEl = null
})
</script>

<template>
  <div
    class="min-w-0 overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
  >
    <div
      ref="scrollViewportRef"
      class="min-h-0 w-full overflow-auto overscroll-contain [scrollbar-gutter:stable]"
      :style="viewportStyle"
      @scroll.passive="onScroll"
    >
      <div class="min-w-max">
        <div
          class="grid shrink-0 grid-cols-6 items-center gap-3 border-b border-slate-100 px-3 py-2 text-xs text-slate-500 dark:border-slate-900 dark:text-slate-400"
        >
          <div class="whitespace-nowrap font-mono">日期</div>
          <div class="text-right font-mono">開盤價</div>
          <div class="text-right font-mono">最高</div>
          <div class="text-right font-mono">最低</div>
          <div class="text-right font-mono">收盤價</div>
          <div class="text-right font-mono">成交量(張)</div>
        </div>

        <div
          v-for="item in displayed"
          :key="item.key"
          class="grid grid-cols-6 items-center gap-3 border-b border-slate-100 px-3 text-sm text-slate-800 dark:border-slate-900 dark:text-slate-200"
          :style="{ minHeight: `${rowHeightPx}px` }"
        >
          <div class="whitespace-nowrap font-mono tabular-nums">
            <template v-if="item.minute">{{ item.date }} {{ item.minute }}</template>
            <template v-else>{{ String(item.date).slice(0, 10) }}</template>
          </div>
          <div class="text-right font-mono tabular-nums">{{ item.open }}</div>
          <div class="text-right font-mono tabular-nums">{{ item.high }}</div>
          <div class="text-right font-mono tabular-nums">{{ item.low }}</div>
          <div class="text-right font-mono tabular-nums">{{ item.close }}</div>
          <div class="text-right font-mono tabular-nums text-slate-500 dark:text-slate-400">
            {{ item.volume }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>
