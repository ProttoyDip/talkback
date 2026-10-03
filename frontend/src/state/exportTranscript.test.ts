import { describe, expect, it } from 'vitest'
import { transcriptMarkdown } from './exportTranscript'

describe('transcriptMarkdown', () => {
  it('keeps speakers, unheard words, reactions and sources', () => {
    const md = transcriptMarkdown(
      [
        { id: 'u1', speaker: 'user', segments: [{ kind: 'heard', text: 'Weather in Lisbon?' }] },
        {
          id: 'a1',
          speaker: 'assistant',
          segments: [
            { kind: 'heard', text: 'Sunny, 24 degrees.' },
            { kind: 'backchannel', text: 'mm-hm' },
            { kind: 'unheard', text: 'Bring a jacket.' },
          ],
          tools: [
            {
              id: 'c1',
              name: 'web_search',
              status: 'done',
              sources: [{ title: 'Open-Meteo', url: 'https://open-meteo.com/' }],
            },
          ],
        },
      ],
      new Date(2026, 9, 3, 12, 0),
    )
    expect(md).toContain('**You:** Weather in Lisbon?')
    expect(md).toContain('**TalkBack:** Sunny, 24 degrees. _(you: mm-hm)_ ~~Bring a jacket.~~')
    expect(md).toContain('- [Open-Meteo](https://open-meteo.com/)')
  })

  it('skips empty turns', () => {
    const md = transcriptMarkdown([{ id: 'a1', speaker: 'assistant', segments: [{ kind: 'heard', text: ' ' }] }])
    expect(md).not.toContain('TalkBack:**')
  })
})
