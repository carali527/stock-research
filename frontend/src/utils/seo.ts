import type { RouteLocationNormalizedLoaded, Router } from 'vue-router'

const SITE_NAME = '台股研究助手'
const DEFAULT_TITLE = SITE_NAME
const DEFAULT_DESCRIPTION =
  '台股研究助手提供上市成交量排行、漲幅排行、個股股價、K 線與 AI 輔助分析，協助快速整理台灣股票研究線索。'

function textFromMeta(value: unknown, route: RouteLocationNormalizedLoaded): string {
  if (typeof value === 'function')
    return String((value as (route: RouteLocationNormalizedLoaded) => string)(route) || '').trim()
  if (typeof value === 'string') return value.trim()
  return ''
}

function siteOrigin(): string {
  const configured = String(import.meta.env.VITE_SITE_URL || '').trim()
  if (configured) return configured.replace(/\/+$/, '')
  return window.location.origin
}

function canonicalUrl(route: RouteLocationNormalizedLoaded): string {
  const path = route.path.startsWith('/') ? route.path : `/${route.path}`
  return `${siteOrigin()}${path}`
}

function setMetaByName(name: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[name="${name}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('name', name)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

function setMetaByProperty(property: string, content: string) {
  let el = document.head.querySelector<HTMLMetaElement>(`meta[property="${property}"]`)
  if (!el) {
    el = document.createElement('meta')
    el.setAttribute('property', property)
    document.head.appendChild(el)
  }
  el.setAttribute('content', content)
}

function setCanonical(href: string) {
  let el = document.head.querySelector<HTMLLinkElement>('link[rel="canonical"]')
  if (!el) {
    el = document.createElement('link')
    el.setAttribute('rel', 'canonical')
    document.head.appendChild(el)
  }
  el.setAttribute('href', href)
}

export function installSeo(router: Router) {
  router.afterEach((route) => {
    const title =
      textFromMeta(route.meta.seoTitle, route) ||
      textFromMeta(route.meta.title, route) ||
      DEFAULT_TITLE
    const description = textFromMeta(route.meta.description, route) || DEFAULT_DESCRIPTION
    const robots = textFromMeta(route.meta.robots, route) || 'index,follow'
    const canonical = canonicalUrl(route)
    const fullTitle = title === SITE_NAME ? title : `${title} | ${SITE_NAME}`

    document.title = fullTitle
    setMetaByName('description', description)
    setMetaByName('robots', robots)
    setMetaByName('twitter:title', fullTitle)
    setMetaByName('twitter:description', description)
    setMetaByProperty('og:title', fullTitle)
    setMetaByProperty('og:description', description)
    setMetaByProperty('og:url', canonical)
    setCanonical(canonical)
  })
}
