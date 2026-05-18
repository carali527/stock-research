import { defineStore } from 'pinia'
import { ref } from 'vue'
import { apiClient } from '@/services/client'
import type { ApiError } from '@/services/errors'

/** AI 研究／摘要（骨架） */
export const useAiStore = defineStore('ai', () => {
  const loading = ref(false)
  const lastError = ref<ApiError | null>(null)
  const lastReply = ref<string | null>(null)

  async function ask(prompt: string) {
    loading.value = true
    lastError.value = null
    lastReply.value = null
    try {
      const { data } = await apiClient.post<{ reply?: string } | string>('/ai/chat', { prompt })
      const text =
        typeof data === 'string' ? data : typeof data?.reply === 'string' ? data.reply : null
      lastReply.value = text
      return text
    } catch (e) {
      lastError.value = e as ApiError
      throw e
    } finally {
      loading.value = false
    }
  }

  return {
    loading,
    lastError,
    lastReply,
    ask,
  }
})
