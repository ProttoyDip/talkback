import { AnimatePresence, motion, useReducedMotion } from 'motion/react'
import { forwardRef, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { cn } from '../../lib/utils'
import { dur, ease } from '../../styles/motion'
import { Icon } from '../Icon'

/*
 * A prompt box that rests as a one-line pill and opens into a card when used
 * (adapted from the 21st.dev "AI chat input"). Built on TalkBack's tokens:
 * the original's shadcn colours, model picker, effort switch and browser
 * speech recognition are left out. TalkBack picks its model in Settings and
 * listens through its own microphone button, so a second recognizer here
 * would hear every word twice.
 */

export interface PromptAttachment {
  id: string
  name: string
  /** "Reading…", "Ready", or the reason it failed. */
  status: string
  tone?: 'busy' | 'ready' | 'failed'
}

export interface PromptInputProps {
  onSubmit: (value: string) => void
  /** Accessible name (also what tests and screen readers call it). */
  label?: string
  placeholder?: string
  disabled?: boolean
  className?: string
  maxLength?: number
  /** Files chosen with "+". Leave out to hide the button. */
  onAttach?: (files: File[]) => void
  accept?: string
  attachLabel?: string
  attachments?: PromptAttachment[]
  onDismissAttachment?: (id: string) => void
}

const MAX_LINES = 6

// A gentle settle for opening and closing; instant with reduced motion.
function useSpring() {
  const reduced = useReducedMotion()
  return reduced
    ? { duration: 0 }
    : { type: 'spring' as const, duration: dur.slow, bounce: 0.2 }
}

function AttachmentChip({ item, onDismiss }: { item: PromptAttachment; onDismiss?: (id: string) => void }) {
  const tone = item.tone ?? 'ready'
  return (
    <motion.li
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0, transition: { duration: dur.base, ease: ease.out } }}
      exit={{ opacity: 0, transition: { duration: dur.fast, ease: ease.in } }}
      className="flex min-w-0 max-w-full shrink-0 items-center gap-2 rounded-input border border-border bg-surface-raised py-1 pl-2"
    >
      <Icon name="document" className="size-4 shrink-0 text-text-muted" />
      <span className="flex min-w-0 flex-col">
        <span className="truncate text-data text-text">{item.name}</span>
        <span
          role={tone === 'failed' ? 'alert' : 'status'}
          className={cn('text-label', tone === 'failed' ? 'text-danger' : 'text-text-muted')}
        >
          {item.status}
        </span>
      </span>
      {onDismiss && (
        <button
          type="button"
          onClick={() => onDismiss(item.id)}
          aria-label={`Hide ${item.name}`}
          className="grid size-6 shrink-0 place-items-center rounded-pill text-text-muted transition-colors duration-(--dur-fast) hover:text-text"
        >
          <Icon name="close" className="size-4" />
        </button>
      )}
    </motion.li>
  )
}

export const PromptInput = forwardRef<HTMLTextAreaElement, PromptInputProps>(function PromptInput(
  {
    onSubmit,
    label = 'Message',
    placeholder = 'Ask anything',
    disabled = false,
    className,
    maxLength = 2000,
    onAttach,
    accept,
    attachLabel = 'Add a file',
    attachments = [],
    onDismissAttachment,
  },
  forwarded,
) {
  const [value, setValue] = useState('')
  const [focused, setFocused] = useState(false)
  const [overflow, setOverflow] = useState({ top: false, bottom: false })
  const textarea = useRef<HTMLTextAreaElement | null>(null)
  const fileInput = useRef<HTMLInputElement>(null)
  const hint = useId()
  const spring = useSpring()

  const hasValue = value.trim() !== ''
  const hasAttachments = attachments.length > 0
  // Open while in use, while it holds text, or while files are shown.
  const active = focused && !disabled
  const expanded = active || hasValue || hasAttachments

  const setRefs = useCallback(
    (node: HTMLTextAreaElement | null) => {
      textarea.current = node
      if (typeof forwarded === 'function') forwarded(node)
      else if (forwarded) forwarded.current = node
    },
    [forwarded],
  )

  const updateOverflow = useCallback(() => {
    const el = textarea.current
    if (!el) return
    setOverflow({
      top: el.scrollTop > 2,
      bottom: el.scrollHeight - el.clientHeight - el.scrollTop > 2,
    })
  }, [])

  // Grow with the text, up to six lines, then scroll.
  useLayoutEffect(() => {
    const el = textarea.current
    if (!el) return
    const line = parseFloat(getComputedStyle(el).lineHeight) || 24
    const padding = parseFloat(getComputedStyle(el).paddingTop) + parseFloat(getComputedStyle(el).paddingBottom)
    el.style.height = '0px'
    const lines = expanded ? Math.max(2, Math.min(MAX_LINES, Math.round((el.scrollHeight - padding) / line))) : 1
    el.style.height = `${lines * line + padding}px`
    el.style.overflowY = el.scrollHeight > el.clientHeight + 1 ? 'auto' : 'hidden'
    updateOverflow()
  }, [value, expanded, updateOverflow])

  // Opening makes the card taller: keep all of it on screen (above the
  // phone tab bar too), once the size change has settled.
  const card = useRef<HTMLDivElement>(null)
  const reduced = useReducedMotion()
  useEffect(() => {
    if (!expanded) return
    const timer = window.setTimeout(
      () => card.current?.scrollIntoView({ block: 'nearest', behavior: reduced ? 'auto' : 'smooth' }),
      reduced ? 0 : dur.slow * 1000,
    )
    return () => window.clearTimeout(timer)
  }, [expanded, attachments.length, reduced])

  const submit = () => {
    const text = value.trim()
    if (!text || disabled) return
    onSubmit(text)
    setValue('')
  }

  return (
    <div className={cn('relative w-full', className)}>
      {/* The attachment tray slides up from behind the card. */}
      <AnimatePresence initial={false}>
        {hasAttachments && (
          <motion.ul
            aria-label="Added files"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0, transition: spring }}
            exit={{ opacity: 0, y: 16, transition: { duration: dur.fast, ease: ease.in } }}
            className="relative z-0 mx-4 -mb-px flex gap-2 overflow-x-auto rounded-t-card border border-b-0 border-border bg-surface p-2"
          >
            <AnimatePresence initial={false}>
              {attachments.map((item) => (
                <AttachmentChip key={item.id} item={item} onDismiss={onDismissAttachment} />
              ))}
            </AnimatePresence>
          </motion.ul>
        )}
      </AnimatePresence>

      <motion.div
        ref={card}
        data-prompt
        layout
        transition={spring}
        style={{ borderRadius: expanded ? 'var(--corner-panel)' : 'var(--corner-pill)' }}
        onMouseDown={(e) => {
          // A click on the card's padding still lands in the text.
          if (e.target === e.currentTarget && !disabled) {
            e.preventDefault()
            textarea.current?.focus()
          }
        }}
        className={cn(
          // Phones: clear the tab bar and its raised mic when scrolled into view.
          'relative z-10 flex scroll-mb-[calc(var(--mic-size)+var(--space-4))] flex-col border bg-chrome transition-colors duration-(--dur-fast) lg:scroll-mb-8',
          active ? 'border-voice-assistant-dim' : 'border-field-line hover:border-border',
          disabled && 'opacity-60',
        )}
      >
        <motion.div layout="position" transition={spring} className="relative flex items-start">
          <textarea
            ref={setRefs}
            rows={1}
            value={value}
            maxLength={maxLength}
            disabled={disabled}
            aria-label={label}
            aria-describedby={expanded ? hint : undefined}
            placeholder={placeholder}
            onChange={(e) => setValue(e.target.value)}
            onFocus={() => setFocused(true)}
            onBlur={(e) => {
              // Staying inside the card (the "+" button) keeps it open.
              if (!e.currentTarget.closest('[data-prompt]')?.contains(e.relatedTarget as Node)) setFocused(false)
            }}
            onScroll={updateOverflow}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault()
                submit()
              } else if (e.key === 'Escape' && !hasValue) {
                e.currentTarget.blur()
              }
            }}
            className="min-w-0 flex-1 resize-none bg-transparent py-3 pl-4 pr-16 text-body text-text outline-none placeholder:text-text-muted disabled:cursor-not-allowed"
          />
          {/* Fades show there is more above or below when it scrolls. */}
          <span
            aria-hidden
            className={cn(
              'pointer-events-none absolute inset-x-4 top-0 h-6 bg-linear-to-b from-chrome to-transparent transition-opacity duration-(--dur-fast)',
              overflow.top ? 'opacity-100' : 'opacity-0',
            )}
          />
          <span
            aria-hidden
            className={cn(
              'pointer-events-none absolute inset-x-4 bottom-0 h-6 bg-linear-to-t from-chrome to-transparent transition-opacity duration-(--dur-fast)',
              overflow.bottom ? 'opacity-100' : 'opacity-0',
            )}
          />
        </motion.div>

        <AnimatePresence initial={false}>
          {expanded && (
            <motion.div
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0, transition: { duration: dur.base, ease: ease.out } }}
              exit={{ opacity: 0, transition: { duration: dur.fast, ease: ease.in } }}
              className="flex items-center gap-2 pb-2 pl-2 pr-16"
            >
              {onAttach && (
                <>
                  <input
                    ref={fileInput}
                    type="file"
                    accept={accept}
                    tabIndex={-1}
                    aria-hidden
                    className="hidden"
                    onChange={(e) => {
                      const files = Array.from(e.target.files ?? [])
                      e.target.value = ''
                      if (files.length) onAttach(files)
                    }}
                  />
                  <button
                    type="button"
                    disabled={disabled}
                    onMouseDown={(e) => e.preventDefault()}
                    onClick={() => fileInput.current?.click()}
                    aria-label={attachLabel}
                    title={attachLabel}
                    className="grid size-8 place-items-center rounded-pill text-text-muted transition-colors duration-(--dur-fast) hover:bg-surface-raised hover:text-text"
                  >
                    <Icon name="plus" className="size-4" />
                  </button>
                </>
              )}
              <span id={hint} className="hidden truncate font-mono text-label uppercase text-text-subtle sm:inline">
                Enter to send · Shift+Enter for a new line
              </span>
            </motion.div>
          )}
        </AnimatePresence>

        {/* The send button morphs between ready and waiting for words. */}
        <button
          type="button"
          onMouseDown={(e) => e.preventDefault()}
          onClick={submit}
          disabled={disabled || !hasValue}
          aria-label="Send"
          className={cn(
            'absolute bottom-1 right-1 grid size-target place-items-center rounded-pill transition-[background-color,color,transform] duration-(--dur-base) ease-enter active:scale-[0.96]',
            hasValue && !disabled ? 'bg-voice-assistant text-on-accent' : 'bg-surface-raised text-text-subtle',
          )}
        >
          <motion.span
            key={hasValue ? 'ready' : 'waiting'}
            initial={{ opacity: 0, scale: 0.6, rotate: hasValue ? -45 : 45 }}
            animate={{ opacity: 1, scale: 1, rotate: 0, transition: spring }}
            className="grid place-items-center"
          >
            <Icon name="arrowUp" className="size-4" />
          </motion.span>
        </button>
      </motion.div>
    </div>
  )
})
