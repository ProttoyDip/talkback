/*
 * STATIC PLACEHOLDER DATA for the layout. Nothing here is measured or live.
 * It follows the demo script in docs/prd.md, section 11, and is replaced by
 * session events (docs/architecture.md, section 3) once audio is built.
 */
import type { ConfirmRequest, TimelineData, Turn } from './types'

export const placeholderTurns: Turn[] = [
  {
    id: 't1',
    speaker: 'user',
    segments: [{ kind: 'heard', text: 'What does full-duplex mean?' }],
  },
  {
    id: 't2',
    speaker: 'assistant',
    tools: [
      {
        id: 'c1',
        name: 'web_search',
        status: 'done',
        sources: [
          {
            title: 'Duplex (telecommunications) - Wikipedia',
            url: 'https://en.wikipedia.org/wiki/Duplex_(telecommunications)',
          },
          {
            title: 'NVIDIA NemotronLabs VoiceChat 11B - model card',
            url: 'https://huggingface.co/nvidia/NVIDIA-NemotronLabs-VoiceChat-11B',
          },
          {
            title: 'NemotronLabs VoiceChat - paper',
            url: 'https://arxiv.org/html/2609.21967',
          },
        ],
      },
    ],
    segments: [
      {
        kind: 'heard',
        text: "It means both sides can talk at the same time, like a phone call. I keep listening while I speak, so you can cut in whenever you like.",
      },
    ],
  },
  {
    id: 't3',
    speaker: 'user',
    segments: [{ kind: 'heard', text: "Good. What's the weather in Lisbon?" }],
  },
  {
    id: 't4',
    speaker: 'assistant',
    tools: [{ id: 'c2', name: 'weather', status: 'done' }],
    segments: [
      { kind: 'heard', text: "It's sunny in Lisbon right now, around 24 degrees." },
      { kind: 'backchannel', text: 'mm-hm' },
      { kind: 'heard', text: 'This evening the wind picks up from the north,' },
      {
        kind: 'unheard',
        text: "so take a light jacket if you're out after dinner.",
      },
    ],
  },
  {
    id: 't5',
    speaker: 'user',
    segments: [{ kind: 'heard', text: 'No, tomorrow.' }],
  },
  {
    id: 't6',
    speaker: 'assistant',
    segments: [
      {
        kind: 'heard',
        text: 'Tomorrow is cloudier, with a high of 21 and rain likely after 4 pm.',
      },
    ],
  },
]

/** Extra turn shown in the `thinking` and `tool` preview states. */
export const placeholderToolTurn: Turn = {
  id: 't7',
  speaker: 'assistant',
  tools: [{ id: 'c3', name: 'weather', status: 'running' }],
  segments: [{ kind: 'heard', text: 'Let me check that.' }],
}

export const placeholderConfirm: ConfirmRequest = {
  callId: 'c4',
  summary: 'Delete the memory “Home city is Lisbon”?',
}

/*
 * Ten seconds of fake levels (100 ms per value) that draw the same story as
 * the transcript: TalkBack talks, the user says "mm-hm" (TalkBack keeps
 * going), the user interrupts at 6.4 s, TalkBack stops, then answers again.
 * A fixed formula keeps the picture identical on every render.
 */
function speech(index: number, start: number, end: number, seed: number) {
  const t = index / 10
  if (t < start || t >= end) return 0
  const edge = Math.min(t - start, end - t) / 0.3
  const envelope = Math.min(1, edge + 0.35)
  const wobble =
    0.55 +
    0.3 * Math.sin(index * 1.7 + seed) +
    0.15 * Math.sin(index * 4.3 + seed * 2)
  return Math.max(0.12, Math.min(1, envelope * wobble))
}

const STEPS = 100

export const placeholderTimeline: TimelineData = {
  windowSeconds: 10,
  user: Array.from({ length: STEPS }, (_, i) =>
    Math.max(speech(i, 2.3, 2.7, 3), speech(i, 6.1, 7.6, 5)),
  ),
  assistant: Array.from({ length: STEPS }, (_, i) =>
    Math.max(speech(i, 0, 6.6, 1), speech(i, 8.2, 10.01, 7)),
  ),
  interrupts: [6.4],
}

/** Static mic input level for the ring (0..1). Real levels come later. */
export const placeholderInputLevel = 0.6
