// @vitest-environment jsdom

import { computed, effectScope, nextTick, ref, type EffectScope } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { useRealtimeOwnership } from './useRealtimeOwnership'

type Listener = (event: MessageEvent<unknown>) => void

class FakeBroadcastChannel {
  static channels = new Map<string, Set<FakeBroadcastChannel>>()

  name: string
  listeners = new Set<Listener>()
  closed = false

  constructor(name: string) {
    this.name = name
    const peers = FakeBroadcastChannel.channels.get(name) ?? new Set<FakeBroadcastChannel>()
    peers.add(this)
    FakeBroadcastChannel.channels.set(name, peers)
  }

  postMessage(data: unknown) {
    const peers = FakeBroadcastChannel.channels.get(this.name) ?? new Set<FakeBroadcastChannel>()
    for (const peer of peers) {
      if (peer === this || peer.closed) continue
      for (const listener of peer.listeners) listener({ data } as MessageEvent<unknown>)
    }
  }

  addEventListener(_type: 'message', listener: Listener) {
    this.listeners.add(listener)
  }

  removeEventListener(_type: 'message', listener: Listener) {
    this.listeners.delete(listener)
  }

  close() {
    this.closed = true
    this.listeners.clear()
    FakeBroadcastChannel.channels.get(this.name)?.delete(this)
  }

  static reset() {
    FakeBroadcastChannel.channels.clear()
  }
}

function createOwnershipScope(enabled = ref(true)) {
  const scope = effectScope()
  const state = scope.run(() => useRealtimeOwnership(computed(() => enabled.value)))
  if (!state) throw new Error('failed to create ownership scope')
  return { enabled, scope, state }
}

function stopScopes(scopes: EffectScope[]) {
  for (const scope of scopes) scope.stop()
}

describe('useRealtimeOwnership', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.spyOn(Math, 'random').mockReturnValue(0)
    vi.stubGlobal('BroadcastChannel', FakeBroadcastChannel)
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    window.localStorage.clear()
    FakeBroadcastChannel.reset()
  })

  it('claims realtime leadership after the election delay', () => {
    const first = createOwnershipScope()

    expect(first.state.canStream.value).toBe(false)

    vi.advanceTimersByTime(200)

    expect(first.state.isOwner.value).toBe(true)
    expect(first.state.canStream.value).toBe(true)
    expect(first.state.hasOtherOwner.value).toBe(false)

    stopScopes([first.scope])
  })

  it('lets a new visible tab request ownership and makes the previous leader step down', () => {
    const first = createOwnershipScope()
    vi.advanceTimersByTime(200)
    expect(first.state.canStream.value).toBe(true)

    const second = createOwnershipScope()
    vi.advanceTimersByTime(200)

    expect(first.state.canStream.value).toBe(false)
    expect(first.state.isSuspended.value).toBe(true)
    expect(second.state.canStream.value).toBe(true)

    stopScopes([second.scope, first.scope])
  })

  it('lets another enabled tab claim after the leader releases', async () => {
    const first = createOwnershipScope()
    vi.advanceTimersByTime(200)
    const secondEnabled = ref(false)
    const second = createOwnershipScope(secondEnabled)

    first.enabled.value = false
    secondEnabled.value = true
    await nextTick()
    vi.advanceTimersByTime(200)

    expect(first.state.canStream.value).toBe(false)
    expect(second.state.canStream.value).toBe(true)

    stopScopes([second.scope, first.scope])
  })

  it('steps down when it receives a newer leader term', () => {
    const first = createOwnershipScope()
    vi.advanceTimersByTime(200)
    expect(first.state.canStream.value).toBe(true)

    const channel = new FakeBroadcastChannel('stock-research:realtime-leader')
    channel.postMessage({
      type: 'leader-announcement',
      instanceId: 'other-tab',
      term: { counter: 99, ownerId: 'other-tab' },
    })

    expect(first.state.canStream.value).toBe(false)
    expect(first.state.hasOtherOwner.value).toBe(true)
    expect(first.state.isSuspended.value).toBe(true)

    channel.close()
    stopScopes([first.scope])
  })

  it('releases leadership when disabled', async () => {
    const first = createOwnershipScope()
    vi.advanceTimersByTime(200)

    first.enabled.value = false
    await nextTick()

    expect(first.state.isOwner.value).toBe(false)
    expect(first.state.canStream.value).toBe(false)

    stopScopes([first.scope])
  })
})
