/*
 * Transports deliver server events and audio to the app. The live transport
 * talks to the backend; the replay transport (replay.ts) plays the shared
 * fixture. Both have the same interface, so the screen does not care which.
 */
import type { Connection } from './model'
import { rememberSessionToken } from '../api/client'
import { AccessCodeError, requestSession } from '../api/session'
import { parseServerEvent, type ClientMessage, type ServerEvent } from './protocol'

export interface TransportHandlers {
  onEvent: (event: ServerEvent) => void
  /** PCM16 mono at 22.05 kHz, with the seq from its audio.chunk header. */
  onAudio: (seq: number, pcm: Int16Array) => void
  onConnection: (connection: Connection) => void
}

export interface Transport {
  connect: (handlers: TransportHandlers) => void
  send: (message: ClientMessage) => void
  sendAudio: (frame: ArrayBuffer) => void
  /** Try again now (after an error or a closed session). */
  reconnect: () => void
  close: () => void
}

/** Wait before reconnect attempts 1, 2, 3, ... (ms). */
const BACKOFF_MS = [1000, 2000, 5000]

/** Sessions the server ended on purpose are not reopened automatically. */
const FINAL_END_REASONS = new Set(['idle', 'time_limit'])

export class LiveTransport implements Transport {
  private handlers?: TransportHandlers
  private socket?: WebSocket
  private pendingChunk?: number
  private attempt = 0
  private retryTimer?: ReturnType<typeof setTimeout>
  private endedOnPurpose = false
  private closed = false

  connect(handlers: TransportHandlers) {
    this.handlers = handlers
    void this.open()
  }

  private async open() {
    if (this.closed) return
    this.endedOnPurpose = false
    this.handlers?.onConnection(this.attempt === 0 ? 'connecting' : 'reconnecting')
    let token: string
    try {
      const body = await requestSession()
      token = body.token
      rememberSessionToken(body.token, body.expires_at)
    } catch (error) {
      // A missing access code will not fix itself by retrying.
      if (error instanceof AccessCodeError) this.handlers?.onConnection('closed')
      else this.scheduleRetry()
      return
    }
    if (this.closed) return

    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const socket = new WebSocket(
      `${scheme}://${window.location.host}/ws/session?token=${encodeURIComponent(token)}`,
    )
    socket.binaryType = 'arraybuffer'
    this.socket = socket

    socket.onopen = () => {
      this.attempt = 0
      socket.send(JSON.stringify({ type: 'session.start', client_sample_rate: 16000 }))
      this.handlers?.onConnection('open')
    }
    socket.onmessage = (message) => {
      if (typeof message.data === 'string') {
        const event = parseServerEvent(message.data)
        if (!event) return
        if (event.type === 'audio.chunk') this.pendingChunk = event.seq
        if (event.type === 'session.end' && FINAL_END_REASONS.has(event.reason)) {
          this.endedOnPurpose = true
        }
        this.handlers?.onEvent(event)
      } else if (this.pendingChunk !== undefined) {
        this.handlers?.onAudio(this.pendingChunk, new Int16Array(message.data as ArrayBuffer))
        this.pendingChunk = undefined
      }
    }
    socket.onclose = () => {
      if (this.socket !== socket || this.closed) return
      this.socket = undefined
      if (this.endedOnPurpose) this.handlers?.onConnection('closed')
      else this.scheduleRetry()
    }
  }

  private scheduleRetry() {
    if (this.closed) return
    this.handlers?.onConnection('reconnecting')
    const wait = BACKOFF_MS[Math.min(this.attempt, BACKOFF_MS.length - 1)]
    this.attempt += 1
    this.retryTimer = setTimeout(() => void this.open(), wait)
  }

  send(message: ClientMessage) {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify(message))
  }

  sendAudio(frame: ArrayBuffer) {
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(frame)
  }

  reconnect() {
    clearTimeout(this.retryTimer)
    this.socket?.close()
    this.socket = undefined
    this.attempt = 0
    void this.open()
  }

  close() {
    this.closed = true
    clearTimeout(this.retryTimer)
    this.socket?.close()
    this.socket = undefined
  }
}
