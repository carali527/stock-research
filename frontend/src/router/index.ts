import type { RouteLocationNormalizedLoaded, RouteRecordRaw } from 'vue-router'
import { createRouter, createWebHistory } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/Home.vue'),
    meta: {
      title: '首頁',
      seoTitle: '台股研究助手',
      description:
        '台股研究助手提供上市成交量排行、漲幅排行、個股股價、K 線與 AI 輔助分析，協助快速整理台灣股票研究線索。',
    },
  },
  {
    path: '/stock/:id',
    name: 'stock',
    component: () => import('@/views/Stock.vue'),
    meta: {
      title: '股票總覽',
      description: '瀏覽台灣上市股票清單，依代號、名稱與產業別快速搜尋個股。',
    },
  },
  {
    path: '/stock/:id/price',
    name: 'stockPrice',
    component: () => import('@/views/StockPrice.vue'),
    meta: {
      title: '股價日成交資訊',
      seoTitle: (route: RouteLocationNormalizedLoaded) =>
        `${String(route.params.id || '').trim() || '個股'} 股價與 K 線`,
      description: (route: RouteLocationNormalizedLoaded) =>
        `查看 ${String(route.params.id || '').trim() || '個股'} 的股價、即時成交、K 線與歷史交易資訊。`,
    },
  },
  {
    path: '/research',
    name: 'research',
    component: () => import('@/views/Research.vue'),
    meta: {
      title: '股票小幫手',
      description: '使用 AI 輔助整理台股研究問題、即時市場資料與分析重點。',
    },
  },
  {
    path: '/favorites',
    name: 'favorites',
    component: () => import('@/views/Favorites.vue'),
    meta: {
      title: '自選清單',
      description: '管理本機瀏覽器中的台股自選清單。',
      robots: 'noindex,nofollow',
    },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

export default router
