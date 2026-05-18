<script setup lang="ts">
import { computed } from 'vue'
import { useScrollChunkRows } from '@/composables/useScrollChunkRows'

export type RankRow = {
  key: string
  stockId: string
  stockName: string
  subtitle?: string
  valueText: string
}

const props = defineProps<{
  title: string
  rows: RankRow[]
  height?: number
  rowHeight?: number
}>()

const emit = defineEmits<{
  (e: 'select', stockId: string): void
}>()

const heightPx = computed(() => props.height ?? 420)
const rowHeightPx = computed(() => props.rowHeight ?? 56)
const visibleRows = computed(() => Math.max(6, Math.floor(heightPx.value / rowHeightPx.value)))

const { displayed, onScroll } = useScrollChunkRows<RankRow>(() => props.rows, {
  chunkSize: () => visibleRows.value,
  step: () => visibleRows.value,
})

const viewportStyle = computed(() => ({ maxHeight: `${heightPx.value}px` }))
</script>

<template>
  <section class="grid gap-2">
    <div class="flex items-baseline justify-between">
      <h2 class="text-sm font-semibold text-slate-900 dark:text-slate-100">{{ title }}</h2>
      <p class="text-xs text-slate-500 dark:text-slate-400">Top {{ rows.length }}</p>
    </div>

    <div
      class="overflow-hidden rounded-lg border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-950"
    >
      <div
        class="w-full overflow-y-auto overscroll-contain"
        :style="viewportStyle"
        @scroll.passive="onScroll"
      >
        <button
          v-for="(item, index) in displayed"
          :key="item.key"
          type="button"
          class="flex w-full items-center justify-between gap-3 border-b border-slate-100 px-3 text-left dark:border-slate-900"
          :style="{ minHeight: `${rowHeightPx}px` }"
          @click="emit('select', item.stockId)"
        >
          <div class="flex min-w-0 items-center gap-3">
            <div class="w-8 shrink-0 text-right font-mono text-xs text-slate-400">
              {{ index + 1 }}
            </div>
            <div class="min-w-0">
              <div class="truncate text-base font-semibold text-blue-700 dark:text-blue-300">
                {{ item.stockName }}
              </div>
              <div class="truncate font-mono text-xs text-slate-400 dark:text-slate-500">
                {{ item.stockId }}
                <span v-if="item.subtitle" class="font-sans"> · {{ item.subtitle }}</span>
              </div>
            </div>
          </div>
          <div class="shrink-0 font-mono text-sm tabular-nums text-slate-700 dark:text-slate-200">
            {{ item.valueText }}
          </div>
        </button>
      </div>
    </div>
  </section>
</template>
