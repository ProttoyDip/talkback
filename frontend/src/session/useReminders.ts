import { useCallback, useEffect, useRef, useState } from 'react'
import { api } from '../api/client'
import type { ReminderItem } from '../api/types'
import { localInput } from '../state/when'

/** How far ahead the page looks, and how often (plan P5). */
const LOOK_AHEAD_MS = 5 * 60 * 1000
const POLL_MS = 60 * 1000
/** A reminder this late when first seen was missed while TalkBack was closed. */
const MISSED_AFTER_MS = 15 * 60 * 1000

export interface DueReminder {
  reminder: ReminderItem
  missed: boolean
}

/**
 * Reminders while the page is open. The server sends reminder.due to an open
 * conversation; without one, the page polls, sets timers, shows the reminder
 * (and a notification when the tab is hidden) and tells the server.
 */
export function useReminders(enabled: boolean, fromServer?: ReminderItem) {
  const [due, setDue] = useState<DueReminder[]>([])
  const timers = useRef(new Map<string, ReturnType<typeof setTimeout>>())

  const show = useCallback((reminder: ReminderItem, missed: boolean) => {
    setDue((list) => (list.some((d) => d.reminder.id === reminder.id) ? list : [...list, { reminder, missed }]))
    if (document.visibilityState === 'hidden' && 'Notification' in window && Notification.permission === 'granted') {
      new Notification('TalkBack reminder', { body: reminder.text, tag: reminder.id })
    }
  }, [])


  useEffect(() => {
    if (!enabled) return
    let stopped = false
    const check = async () => {
      let items: ReminderItem[]
      try {
        items = await api.listReminders(localInput(new Date(Date.now() + LOOK_AHEAD_MS)))
      } catch {
        return // offline: try again at the next poll
      }
      for (const reminder of items) {
        if (stopped || timers.current.has(reminder.id)) continue
        const wait = new Date(reminder.due_at).getTime() - Date.now()
        timers.current.set(
          reminder.id,
          setTimeout(() => {
            show(reminder, wait < -MISSED_AFTER_MS)
            void api.reminderDelivered(reminder.id).catch(() => {})
          }, Math.max(0, wait)),
        )
      }
    }
    void check()
    const poll = setInterval(() => void check(), POLL_MS)
    const pending = timers.current
    return () => {
      stopped = true
      clearInterval(poll)
      pending.forEach(clearTimeout)
      pending.clear()
    }
  }, [enabled, show])

  const [dismissed, setDismissed] = useState<ReadonlySet<string>>(new Set())
  const dismiss = useCallback((id: string) => {
    setDue((list) => list.filter((d) => d.reminder.id !== id))
    setDismissed((ids) => new Set(ids).add(id))
  }, [])

  // From the server, during a conversation (already marked delivered there).
  const all =
    fromServer && !dismissed.has(fromServer.id) && !due.some((d) => d.reminder.id === fromServer.id)
      ? [...due, { reminder: fromServer, missed: false }]
      : due
  return { due: all.filter((d) => !dismissed.has(d.reminder.id)), dismiss }
}

/** Ask once, on a click, so the browser can show reminders when the tab is hidden. */
export function askForNotifications() {
  if ('Notification' in window && Notification.permission === 'default') void Notification.requestPermission()
}
