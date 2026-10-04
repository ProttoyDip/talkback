import type { Turn } from './types'

/**
 * The conversation as Markdown, for "Save transcript". Words TalkBack did not
 * get to say are kept, struck through, as on screen; reactions such as
 * "mm-hm" stay where they happened.
 */
export function transcriptMarkdown(turns: Turn[], when = new Date()): string {
  const lines = [`# TalkBack conversation`, '', `Saved ${when.toLocaleString()}`, '']
  for (const turn of turns) {
    const text = turn.segments
      .map((segment) => {
        const words = segment.text.trim()
        if (!words) return ''
        if (segment.kind === 'unheard') return `~~${words}~~ _(not spoken: you interrupted)_`
        if (segment.kind === 'backchannel') return `_(you: ${words})_`
        return words
      })
      .filter(Boolean)
      .join(' ')
    if (!text) continue
    lines.push(`**${turn.speaker === 'user' ? 'You' : 'TalkBack'}:** ${text}`)
    for (const tool of turn.tools ?? []) {
      for (const source of tool.sources ?? []) lines.push(`- [${source.title}](${source.url})`)
    }
    lines.push('')
  }
  return lines.join('\n')
}

/** Starts a browser download of the transcript. Nothing leaves the device. */
export function downloadTranscript(turns: Turn[]) {
  const blob = new Blob([transcriptMarkdown(turns)], { type: 'text/markdown' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `talkback-${new Date().toISOString().slice(0, 16).replace(':', '-')}.md`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
