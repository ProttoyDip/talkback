import { useEffect, useState } from 'react'
import { ApiError, api } from '../api/client'
import type { DocumentItem } from '../api/types'
import { PromptInput, type PromptAttachment } from './ui/ai-chat-input'

const ACCEPT = '.pdf,.txt,.md,.markdown,application/pdf,text/plain,text/markdown'

function chip(doc: DocumentItem): PromptAttachment {
  if (doc.status === 'processing') return { id: doc.id, name: doc.title, status: 'Reading…', tone: 'busy' }
  if (doc.status === 'failed')
    return { id: doc.id, name: doc.title, status: `Couldn't add it. ${doc.error ?? ''}`.trim(), tone: 'failed' }
  return { id: doc.id, name: doc.title, status: 'Ready: ask about it', tone: 'ready' }
}

/**
 * Type instead of talking (plan P3): for corrections, quiet places, or when
 * the microphone is not available. A typed turn is handled like a spoken one.
 * "+" adds a document to the Library (plan P8) so it can be asked about.
 */
export function TextComposer({ onSend, disabled }: { onSend: (text: string) => void; disabled?: boolean }) {
  const [files, setFiles] = useState<PromptAttachment[]>([])
  const reading = files.some((f) => f.tone === 'busy')

  // Reading and indexing finish after the upload: check again until done.
  useEffect(() => {
    if (!reading) return
    const timer = window.setTimeout(() => {
      api.listDocuments().then(
        (docs) => setFiles((shown) => shown.map((f) => {
          const doc = docs.find((d) => d.id === f.id)
          return doc ? chip(doc) : f
        })),
        () => {},
      )
    }, 2000)
    return () => window.clearTimeout(timer)
  }, [reading, files])

  const attach = async (chosen: File[]) => {
    for (const file of chosen) {
      const temp = `upload-${file.name}-${file.lastModified}`
      setFiles((shown) => [...shown, { id: temp, name: file.name, status: 'Adding…', tone: 'busy' }])
      try {
        const doc = await api.uploadDocument(file)
        setFiles((shown) => shown.map((f) => (f.id === temp ? chip(doc) : f)))
      } catch (error) {
        const reason = error instanceof ApiError && error.status !== 0 ? error.message : 'Could not reach the server.'
        setFiles((shown) => shown.map((f) => (f.id === temp ? { ...f, status: reason, tone: 'failed' } : f)))
      }
    }
  }

  return (
    <PromptInput
      label="Type instead"
      placeholder="Type instead of talking…"
      disabled={disabled}
      onSubmit={onSend}
      onAttach={(chosen) => void attach(chosen)}
      accept={ACCEPT}
      attachLabel="Add a document (PDF, TXT or Markdown)"
      attachments={files}
      onDismissAttachment={(id) => setFiles((shown) => shown.filter((f) => f.id !== id))}
    />
  )
}
