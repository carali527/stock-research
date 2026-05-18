<script setup lang="ts">
import type { RouteLocationRaw } from 'vue-router'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { useStockStore } from '@/stores/stockStore'

const navLinks: { to: RouteLocationRaw; label: string }[] = [
  { to: '/', label: '首頁' },
  { to: { name: 'stock', params: { id: 'demo' } }, label: '股票總覽' },
  { to: '/research', label: '股票小幫手' },
  { to: '/favorites', label: '自選清單' },
]

const linkClass =
  'rounded-md px-3 py-2 text-sm font-medium text-slate-700 no-underline transition-colors hover:bg-slate-200/80 dark:text-slate-200 dark:hover:bg-slate-800/80'
const linkActiveClass = 'bg-blue-100 text-blue-900 dark:bg-blue-950/60 dark:text-blue-100'

const stockStore = useStockStore()
const route = useRoute()

const mobileMenuOpen = ref(false)
const appTitle = computed(() => {
  const t = String(route.meta?.title ?? '').trim()
  return t || (typeof route.name === 'string' ? route.name : 'stock-research')
})

function openMobileMenu() {
  mobileMenuOpen.value = true
}

function closeMobileMenu() {
  mobileMenuOpen.value = false
}

watch(
  () => route.fullPath,
  () => {
    mobileMenuOpen.value = false
  },
)

onMounted(() => {
  void stockStore.prefetchStockListIfNeeded()
  stockStore.hydrateFavoritesFromLocalStorage()
})
</script>

<template>
  <div class="flex min-h-screen bg-white dark:bg-slate-950">
    <!-- Desktop sidebar -->
    <aside
      class="hidden w-48 shrink-0 flex-col gap-1 border-r border-slate-200 bg-slate-50 p-3 dark:border-slate-800 dark:bg-slate-900 md:flex"
    >
      <RouterLink
        v-for="item in navLinks"
        :key="item.label"
        :to="item.to"
        :class="linkClass"
        :active-class="linkActiveClass"
      >
        {{ item.label }}
      </RouterLink>
    </aside>

    <!-- Mobile top bar -->
    <div class="fixed inset-x-0 top-0 z-40 flex h-12 items-center gap-3 border-b border-slate-200 bg-white/90 px-3 backdrop-blur dark:border-slate-800 dark:bg-slate-950/80 md:hidden">
      <button
        type="button"
        class="inline-flex flex-col h-9 w-9 items-center justify-center rounded-md text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-900"
        aria-label="Open menu"
        @click="openMobileMenu"
      >
        <span class="sr-only">Menu</span>
        <span class="block h-0.5 w-5 bg-current" />
        <span class="mt-1 block h-0.5 w-5 bg-current" />
        <span class="mt-1 block h-0.5 w-5 bg-current" />
      </button>
      <div class="min-w-0 truncate text-sm font-semibold text-slate-900 dark:text-slate-50">
        {{ appTitle }}
      </div>
    </div>

    <transition
      enter-active-class="transition-opacity duration-150"
      enter-from-class="opacity-0"
      enter-to-class="opacity-100"
      leave-active-class="transition-opacity duration-150"
      leave-from-class="opacity-100"
      leave-to-class="opacity-0"
    >
      <div v-if="mobileMenuOpen" class="fixed inset-0 z-50 md:hidden">
        <div class="absolute inset-0 bg-slate-900/40" @click="closeMobileMenu" />
        <transition
          enter-active-class="transition-transform duration-200 ease-out"
          enter-from-class="-translate-x-full"
          enter-to-class="translate-x-0"
          leave-active-class="transition-transform duration-200 ease-in"
          leave-from-class="translate-x-0"
          leave-to-class="-translate-x-full"
        >
          <aside
            v-if="mobileMenuOpen"
            class="absolute left-0 top-0 flex h-full w-72 flex-col gap-1 border-r border-slate-200 bg-slate-50 p-3 shadow-xl dark:border-slate-800 dark:bg-slate-900"
          >
            <div class="mb-2 flex items-center justify-between">
              <div class="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-50">Menu</div>
              <button
                type="button"
                class="inline-flex h-9 w-9 items-center justify-center rounded-md text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                aria-label="Close menu"
                @click="closeMobileMenu"
              >
                ✕
              </button>
            </div>

            <RouterLink
              v-for="item in navLinks"
              :key="item.label"
              :to="item.to"
              :class="linkClass"
              :active-class="linkActiveClass"
              @click="closeMobileMenu"
            >
              {{ item.label }}
            </RouterLink>
          </aside>
        </transition>
      </div>
    </transition>

    <main class="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden p-6 pt-16 md:pt-6">
      <RouterView class="flex min-h-0 min-w-0 flex-1 flex-col" />
    </main>
  </div>
</template>
