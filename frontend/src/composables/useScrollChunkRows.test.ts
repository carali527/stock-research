import { nextTick, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useScrollChunkRows } from './useScrollChunkRows'

type Row = {
  key: string
  label: string
}

function rows(count: number): Row[] {
  return Array.from({ length: count }, (_, index) => ({
    key: String(index + 1),
    label: `Row ${index + 1}`,
  }))
}

function scrollEvent(target: Partial<HTMLElement>): Event {
  return { currentTarget: target } as Event
}

describe('useScrollChunkRows', () => {
  beforeEach(() => {
    vi.stubGlobal('requestAnimationFrame', (callback: FrameRequestCallback) => {
      callback(0)
      return 1
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('renders the initial chunk', async () => {
    const source = ref(rows(10))
    const { displayed, end } = useScrollChunkRows(() => source.value, { chunkSize: 3 })

    await nextTick()

    expect(end.value).toBe(3)
    expect(displayed.value.map((row) => row.key)).toEqual(['1', '2', '3'])
  })

  it('loads more rows when scrolled near the bottom', async () => {
    const source = ref(rows(8))
    const { displayed, onScroll } = useScrollChunkRows(() => source.value, {
      chunkSize: 2,
      step: 2,
      nearBottomPx: 20,
    })

    await nextTick()
    onScroll(scrollEvent({ scrollTop: 80, clientHeight: 100, scrollHeight: 190 }))

    expect(displayed.value).toHaveLength(6)
  })

  it('resets the visible window when the row signature changes', async () => {
    const source = ref(rows(6))
    const { displayed, onScroll } = useScrollChunkRows(() => source.value, {
      chunkSize: 2,
      step: 2,
    })

    await nextTick()
    onScroll(scrollEvent({ scrollTop: 200, clientHeight: 100, scrollHeight: 250 }))
    expect(displayed.value).toHaveLength(6)

    source.value = rows(4).map((row) => ({ ...row, key: `new-${row.key}` }))
    await nextTick()

    expect(displayed.value.map((row) => row.key)).toEqual(['new-1', 'new-2'])
  })
})
