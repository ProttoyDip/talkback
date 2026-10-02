import { describe, expect, it } from 'vitest'
import fixture from '../../../docs/fixtures/demo_session.jsonl?raw'
import { initialModel, reduce, toTurns, type ConversationModel } from './model'
import type { ServerEvent } from './protocol'

const lines = fixture
  .trim()
  .split('\n')
  .map((line) => JSON.parse(line) as { t_ms: number; event: ServerEvent })

function replay(upToMs = Infinity): ConversationModel {
  return lines
    .filter((l) => l.t_ms <= upToMs)
    .reduce((model, l) => reduce(model, { kind: 'event', event: l.event, at: l.t_ms }), initialModel)
}

describe('conversation model on the shared demo fixture', () => {
  const model = replay()
  const turns = toTurns(model)
  const byId = Object.fromEntries(turns.map((t) => [t.id, t]))

  it('builds every turn in order, with the backchannel folded into the assistant turn', () => {
    expect(turns.map((t) => t.id)).toEqual(['u1', 'a1', 'u2', 'a2', 'u4', 'a3', 'u5', 'a4'])
  })

  it('splits the interrupted turn into heard, backchannel and unheard parts', () => {
    expect(byId.a2.segments).toEqual([
      { kind: 'heard', text: "It's sunny in Lisbon right now, around 24 degrees." },
      { kind: 'backchannel', text: 'mm-hm' },
      { kind: 'heard', text: 'This evening the wind picks up from the north,' },
      { kind: 'unheard', text: "so take a light jacket if you're out after dinner." },
    ])
  })

  it('attaches tool chips to their assistant turn', () => {
    expect(byId.a1.tools?.[0]).toMatchObject({ name: 'web_search', status: 'done' })
    expect(byId.a1.tools?.[0].sources).toHaveLength(3)
    expect(byId.a2.tools?.[0]).toMatchObject({ name: 'weather', status: 'done' })
  })

  it('records the interruption and ends waiting for confirmation', () => {
    expect(model.interrupts).toHaveLength(1)
    expect(model.state).toBe('confirm')
    expect(model.confirm?.callId).toBe('c3')
  })

  it('shows a running tool while the search is in progress', () => {
    const during = replay(lines.find((l) => l.event.type === 'tool.status')!.t_ms)
    expect(during.state).toBe('tool')
    expect(during.tool).toBe('web_search')
    expect(toTurns(during).find((t) => t.id === 'a1')?.tools?.[0].status).toBe('running')
  })
})

describe('reducer edge cases', () => {
  it('shows a backchannel as a user turn when nothing is playing', () => {
    const model = reduce(initialModel, {
      kind: 'event',
      at: 0,
      event: { type: 'transcript.delta', message_id: 'u9', speaker: 'user', text: 'okay', final: true, backchannel: true },
    })
    expect(toTurns(model)).toEqual([{ id: 'u9', speaker: 'user', tools: undefined, segments: [{ kind: 'heard', text: 'okay' }] }])
  })

  it('puts a filler said during a tool call before the answer it is waiting for', () => {
    const events: ServerEvent[] = [
      { type: 'transcript.delta', message_id: 'u1', speaker: 'user', text: 'Weather in Lisbon?', final: true },
      { type: 'tool.status', call_id: 'c1', message_id: 'a1', name: 'weather', status: 'running' },
      { type: 'transcript.delta', message_id: 'f1', speaker: 'assistant', text: 'Let me check that.', final: false },
      { type: 'transcript.delta', message_id: 'f1', speaker: 'assistant', text: '', final: true },
      { type: 'tool.status', call_id: 'c1', message_id: 'a1', name: 'weather', status: 'done' },
      { type: 'transcript.delta', message_id: 'a1', speaker: 'assistant', text: 'About 21 degrees.', final: false },
    ]
    const model = events.reduce((m, event) => reduce(m, { kind: 'event', event, at: 0 }), initialModel)
    expect(toTurns(model).map((t) => t.id)).toEqual(['u1', 'f1', 'a1'])
    expect(toTurns(model)[2].tools?.[0].status).toBe('done')
  })

  it('keeps the transcript but clears errors when the connection reopens', () => {
    let model = replay(3000)
    model = reduce(model, { kind: 'event', at: 0, event: { type: 'error', code: 'voice_engine_offline', message: 'x' } })
    model = reduce(model, { kind: 'connection', connection: 'open' })
    expect(model.error).toBeUndefined()
    expect(model.turns.length).toBeGreaterThan(0)
  })
})
