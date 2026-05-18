import { apiUrl } from '@/config/apiBase'

const DEMO_TOKEN = 'stock-research-demo'

export type GeminiRequest = {
  question: string
  data?: Record<string, unknown>
  stream?: boolean
}

export type GeminiResponse = {
  model: string
  analysis: string
  risk: string
  next_step: string
}


/** 串流：以純文字 chunk 回傳（需搭配 fetch + ReadableStream 逐段讀取）。 */
export async function callGeminiStream(req: GeminiRequest): Promise<Response> {
  const res = await fetch(apiUrl('/api/gemini'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Demo-Token': DEMO_TOKEN },
    body: JSON.stringify({ ...req, stream: true }),
  })
  return res
}
