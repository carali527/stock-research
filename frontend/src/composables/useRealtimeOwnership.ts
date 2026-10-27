import { computed, onScopeDispose, ref, shallowRef, watch, type MaybeRefOrGetter, toValue } from 'vue'

const CHANNEL_NAME = 'stock-research:realtime-leader'
const LEADER_COUNTER_KEY = 'stock-research:realtime-leader:counter'
const HEARTBEAT_MS = 1_000
const STALE_MS = 3_000
const CLAIM_DELAY_BASE_MS = 200
const CLAIM_DELAY_JITTER_MS = 200

type LeaderRole = 'follower' | 'leader'
type MessageType = 'request-leader' | 'leader-announcement' | 'leader-heartbeat' | 'leader-release'

type LeaderTerm = {
  counter: number
  ownerId: string
}

type LeaderMessage = {
  type: MessageType
  instanceId: string
  term?: LeaderTerm
}

function newInstanceId(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) return crypto.randomUUID()
  return `inst-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function isLeaderTerm(value: unknown): value is LeaderTerm {
  if (!value || typeof value !== 'object') return false
  const term = value as Partial<LeaderTerm>
  return typeof term.counter === 'number' && Number.isSafeInteger(term.counter) && typeof term.ownerId === 'string'
}

function asLeaderMessage(raw: unknown): LeaderMessage | null {
  if (!raw || typeof raw !== 'object') return null
  const candidate = raw as Partial<LeaderMessage>
  if (
    candidate.type !== 'request-leader' &&
    candidate.type !== 'leader-announcement' &&
    candidate.type !== 'leader-heartbeat' &&
    candidate.type !== 'leader-release'
  ) {
    return null
  }
  if (typeof candidate.instanceId !== 'string') return null
  if (candidate.term !== undefined && !isLeaderTerm(candidate.term)) return null
  return {
    type: candidate.type,
    instanceId: candidate.instanceId,
    term: candidate.term,
  }
}

function compareLeaderTerm(a: LeaderTerm, b: LeaderTerm): number {
  if (a.counter !== b.counter) return a.counter - b.counter
  if (a.ownerId === b.ownerId) return 0
  return a.ownerId < b.ownerId ? 1 : -1
}

function nextLeaderTerm(ownerId: string, lastSeenCounter: number): LeaderTerm {
  try {
    const raw = window.localStorage.getItem(LEADER_COUNTER_KEY)
    const stored = raw === null ? 0 : Number.parseInt(raw, 10)
    const base = Number.isFinite(stored) ? stored : 0
    const counter = Math.max(base, lastSeenCounter) + 1
    window.localStorage.setItem(LEADER_COUNTER_KEY, String(counter))
    return { counter, ownerId }
  } catch {
    return { counter: Math.max(Date.now(), lastSeenCounter + 1), ownerId }
  }
}

export function useRealtimeOwnership(enabled: MaybeRefOrGetter<boolean>) {
  const instanceId = newInstanceId()
  const role = ref<LeaderRole>('follower')
  const leaderTerm = shallowRef<LeaderTerm | null>(null)
  const isSuspended = ref(false)

  const isOwner = computed(() => role.value === 'leader')
  const hasOtherOwner = computed(() => role.value !== 'leader' && leaderTerm.value?.ownerId !== undefined)
  const canStream = computed(() => Boolean(toValue(enabled)) && isOwner.value)

  const channel = typeof BroadcastChannel !== 'undefined' ? new BroadcastChannel(CHANNEL_NAME) : null
  let lastSeenCounter = 0
  let knownLeaderTerm: LeaderTerm | null = null
  let lastHeartbeatAt: number | null = null
  let claimTimer: number | null = null
  let heartbeatTimer: number | null = null
  let staleTimer: number | null = null

  function post(type: MessageType, term = leaderTerm.value) {
    channel?.postMessage({ type, instanceId, term: term ?? undefined } satisfies LeaderMessage)
  }

  function clearClaimTimer() {
    if (claimTimer != null) {
      window.clearTimeout(claimTimer)
      claimTimer = null
    }
  }

  function clearHeartbeatTimer() {
    if (heartbeatTimer != null) {
      window.clearInterval(heartbeatTimer)
      heartbeatTimer = null
    }
  }

  function clearStaleTimer() {
    if (staleTimer != null) {
      window.clearTimeout(staleTimer)
      staleTimer = null
    }
  }

  function isVisible() {
    return document.visibilityState === 'visible'
  }

  function rememberTerm(term: LeaderTerm) {
    lastSeenCounter = Math.max(lastSeenCounter, term.counter)
    if (!knownLeaderTerm || compareLeaderTerm(term, knownLeaderTerm) > 0) knownLeaderTerm = term
  }

  function resetStaleTimer() {
    clearStaleTimer()
    staleTimer = window.setTimeout(() => {
      staleTimer = null
      // A previously yielded tab may take over once the current leader is gone.
      isSuspended.value = false
      leaderTerm.value = null
      if (isVisible()) scheduleClaim()
    }, STALE_MS)
  }

  function hasFreshOtherLeader() {
    return (
      lastHeartbeatAt !== null &&
      knownLeaderTerm !== null &&
      knownLeaderTerm.ownerId !== instanceId &&
      Date.now() - lastHeartbeatAt < STALE_MS
    )
  }

  function becomeFollower() {
    role.value = 'follower'
    leaderTerm.value = knownLeaderTerm
    clearHeartbeatTimer()
    resetStaleTimer()
  }

  function startHeartbeat() {
    clearHeartbeatTimer()
    post('leader-heartbeat')
    heartbeatTimer = window.setInterval(() => {
      if (role.value !== 'leader' || leaderTerm.value === null) return
      post('leader-heartbeat')
    }, HEARTBEAT_MS)
  }

  function becomeLeader() {
    const term = nextLeaderTerm(instanceId, lastSeenCounter)
    rememberTerm(term)
    leaderTerm.value = term
    role.value = 'leader'
    clearStaleTimer()
    post('leader-announcement', term)
    startHeartbeat()
  }

  function attemptClaim() {
    if (!toValue(enabled) || isSuspended.value || !isVisible()) return
    if (hasFreshOtherLeader()) {
      becomeFollower()
      return
    }
    becomeLeader()
  }

  function scheduleClaim() {
    clearClaimTimer()
    if (!toValue(enabled) || isSuspended.value || !isVisible()) return
    const delay = CLAIM_DELAY_BASE_MS + Math.random() * CLAIM_DELAY_JITTER_MS
    claimTimer = window.setTimeout(() => {
      claimTimer = null
      attemptClaim()
    }, delay)
  }

  function releaseLeadership() {
    if (role.value === 'leader') post('leader-release')
    becomeFollower()
  }

  function handleLeaderSignal(message: LeaderMessage) {
    if (!message.term) return
    rememberTerm(message.term)
    lastHeartbeatAt = Date.now()
    clearClaimTimer()

    const current = leaderTerm.value
    if (role.value !== 'leader' || current === null) {
      becomeFollower()
      return
    }

    if (compareLeaderTerm(message.term, current) <= 0) return
    if (isVisible()) isSuspended.value = true
    becomeFollower()
  }

  function handleMessage(event: MessageEvent<unknown>) {
    const message = asLeaderMessage(event.data)
    if (message === null || message.instanceId === instanceId) return

    if (message.type === 'request-leader') {
      if (role.value !== 'leader') return
      if (isVisible()) isSuspended.value = true
      releaseLeadership()
      return
    }

    if (message.type === 'leader-release') {
      // Delayed releases from an older owner must not interrupt the current leader.
      if (!message.term || !knownLeaderTerm || compareLeaderTerm(message.term, knownLeaderTerm) !== 0) return
      lastHeartbeatAt = null
      isSuspended.value = false
      leaderTerm.value = null
      if (isVisible()) scheduleClaim()
      return
    }

    handleLeaderSignal(message)
  }

  function requestLeadership() {
    if (!toValue(enabled)) return
    isSuspended.value = false
    post('request-leader', null)
    scheduleClaim()
  }

  function onVisibilityChange() {
    if (!isVisible()) {
      clearClaimTimer()
      return
    }
    requestLeadership()
  }

  function stopParticipating() {
    clearClaimTimer()
    clearHeartbeatTimer()
    clearStaleTimer()
    if (role.value === 'leader') post('leader-release')
    role.value = 'follower'
    leaderTerm.value = null
    knownLeaderTerm = null
    lastHeartbeatAt = null
    isSuspended.value = false
  }

  channel?.addEventListener('message', handleMessage)
  document.addEventListener('visibilitychange', onVisibilityChange)

  watch(
    () => Boolean(toValue(enabled)),
    (on) => {
      if (on) requestLeadership()
      else stopParticipating()
    },
    { immediate: true },
  )

  onScopeDispose(() => {
    stopParticipating()
    channel?.removeEventListener('message', handleMessage)
    channel?.close()
    document.removeEventListener('visibilitychange', onVisibilityChange)
  })

  return {
    canStream,
    isOwner,
    hasOtherOwner,
    isSuspended,
  }
}
