// @vitest-environment jsdom

import { mount } from '@vue/test-utils'
import { afterEach, expect, it, vi } from 'vitest'
import { useFugleStockStreaming } from './useFugleStockStreaming'

class FakeWebSocket {
  static OPEN = 1
  static instances: FakeWebSocket[] = []
  readyState = 1
  onmessage: ((event: { data: string }) => void) | null = null
  send = vi.fn()
  close = vi.fn()

  constructor() {
    FakeWebSocket.instances.push(this)
  }

  receive(event: string) {
    this.onmessage?.({ data: JSON.stringify({ event, data: { time: Date.now() } }) })
  }
}

afterEach(() => {
  vi.useRealTimers()
  vi.restoreAllMocks()
  vi.unstubAllGlobals()
  FakeWebSocket.instances = []
})

it('accepts 30-second heartbeats and reconnects only after more than 35 seconds of silence', () => {
  vi.useFakeTimers()
  vi.stubGlobal('WebSocket', FakeWebSocket)
  vi.spyOn(Math, 'random').mockReturnValue(0)
  const wrapper = mount({
    setup() {
      useFugleStockStreaming('2330')
      return () => null
    },
  })
  try {
    const socket = FakeWebSocket.instances[0]!
    socket.receive('authenticated')
    vi.advanceTimersByTime(30_000)
    expect(socket.close).not.toHaveBeenCalled()
    socket.receive('heartbeat')
    vi.advanceTimersByTime(35_000)
    expect(socket.close).not.toHaveBeenCalled()
    vi.advanceTimersByTime(5_000)
    expect(socket.close).toHaveBeenCalledOnce()
    vi.advanceTimersByTime(500)
    expect(FakeWebSocket.instances).toHaveLength(2)
  } finally {
    wrapper.unmount()
  }
})

it('waits for backend reconnection without starting competing browser retries', () => {
  vi.useFakeTimers()
  vi.stubGlobal('WebSocket', FakeWebSocket)
  const wrapper = mount({
    setup() {
      useFugleStockStreaming('2330')
      return () => null
    },
  })
  try {
    const socket = FakeWebSocket.instances[0]!
    socket.receive('authenticated')
    socket.receive('reconnecting')
    vi.advanceTimersByTime(120_000)
    window.dispatchEvent(new Event('online'))
    expect(socket.close).not.toHaveBeenCalled()
    expect(FakeWebSocket.instances).toHaveLength(1)
    socket.receive('authenticated')
    expect(socket.send).toHaveBeenLastCalledWith(
      JSON.stringify({ event: 'subscribe', data: { channel: 'candles', symbol: '2330' } }),
    )
  } finally {
    wrapper.unmount()
  }
})
