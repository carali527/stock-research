/** `/api/...` → 同源相對路徑；開發環境由 Vite proxy 轉到後端。 */
export function apiUrl(path: string): string {
  return path.startsWith('/') ? path : `/${path}`
}
