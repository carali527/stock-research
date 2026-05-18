import type { RouteRecordRaw } from 'vue-router'
import { createRouter, createWebHistory } from 'vue-router'

const routes: RouteRecordRaw[] = [
  {
    path: '/',
    name: 'home',
    component: () => import('@/views/Home.vue'),
    meta: { title: '首頁' },
  },
  {
    path: '/stock/:id',
    name: 'stock',
    component: () => import('@/views/Stock.vue'),
    meta: { title: '股票總覽' },
  },
  {
    path: '/stock/:id/price',
    name: 'stockPrice',
    component: () => import('@/views/StockPrice.vue'),
    meta: { title: '股價日成交資訊' },
  },
  {
    path: '/research',
    name: 'research',
    component: () => import('@/views/Research.vue'),
    meta: { title: '股票小幫手' },
  },
  {
    path: '/favorites',
    name: 'favorites',
    component: () => import('@/views/Favorites.vue'),
    meta: { title: '自選清單' },
  },
]

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes,
})

export default router
