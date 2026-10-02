import { motion } from 'motion/react'
import { Fragment, useId } from 'react'
import type { Segment, Turn } from '../state/types'
import { enter } from '../styles/motion'
import { ToolChip } from './ToolChip'

/**
 * Words TalkBack did not get to say. They stay visible, faded and lightly
 * struck through, with a tooltip. This is the product's signature detail
 * (design.md 5.2). Focusable so keyboard users can reach the tooltip.
 */
function Unheard({ text }: { text: string }) {
  const tipId = useId()
  return (
    <span className="group relative">
      <span
        tabIndex={0}
        aria-describedby={tipId}
        className="cursor-help rounded-input text-voice-assistant-dim line-through decoration-voice-assistant-dim decoration-1 transition-opacity duration-(--dur-fast)"
      >
        <span className="sr-only">Not spoken: </span>
        {text}
      </span>
      <span
        id={tipId}
        role="tooltip"
        className="pointer-events-none invisible absolute bottom-[calc(100%+var(--space-2))] left-0 z-10 whitespace-nowrap rounded-input border border-border bg-surface-raised px-3 py-2 font-mono text-label text-text opacity-0 shadow-popover transition-opacity duration-(--dur-fast) group-hover:visible group-hover:opacity-100 group-focus-within:visible group-focus-within:opacity-100"
      >
        Not spoken: you interrupted here
      </span>
    </span>
  )
}

/** A "mm-hm" from the user that TalkBack treated as "keep going". */
function Backchannel({ text }: { text: string }) {
  return (
    <span className="mx-1 inline-flex items-baseline gap-1 rounded-input border border-border px-2 align-baseline font-mono text-label text-voice-user">
      <span className="sr-only">(You said: </span>
      {text}
      <span className="sr-only">. TalkBack kept going.)</span>
      <span aria-hidden className="text-text-muted">· kept going</span>
    </span>
  )
}

function SegmentView({ segment }: { segment: Segment }) {
  switch (segment.kind) {
    case 'heard':
      return <span>{segment.text}</span>
    case 'unheard':
      return <Unheard text={segment.text} />
    case 'backchannel':
      return <Backchannel text={segment.text} />
  }
}

export function TranscriptTurn({ turn, startsExchange }: { turn: Turn; startsExchange: boolean }) {
  const isUser = turn.speaker === 'user'

  return (
    <motion.li
      className={`grid grid-cols-1 gap-1 sm:col-span-2 sm:grid-cols-subgrid sm:gap-x-6 ${startsExchange ? 'mt-8 first:mt-0' : ''}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={enter}
    >
      <p
        className={`font-mono text-label font-medium uppercase sm:leading-(--line-height-transcript) ${
          isUser ? 'text-voice-user' : 'text-voice-assistant'
        }`}
      >
        {isUser ? 'You' : 'TalkBack'}
      </p>

      <div className="flex flex-col items-start gap-3">
        <p className={`text-transcript ${isUser ? 'text-text-muted' : 'text-text'}`}>
          {turn.segments.map((segment, i) => (
            <Fragment key={i}>
              {i > 0 && ' '}
              <SegmentView segment={segment} />
            </Fragment>
          ))}
        </p>
        {turn.tools && turn.tools.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {turn.tools.map((call) => (
              <ToolChip key={call.id} call={call} />
            ))}
          </div>
        )}
      </div>
    </motion.li>
  )
}
